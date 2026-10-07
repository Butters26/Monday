#!/usr/bin/env python3
"""Language comprehension for Mercy — meaning from offline OEWN.

Language owns linguistic comprehension and expression. This module is the
comprehension half: observed text → linguistic meaning packet.

HARD RULES:
- Meaning source is the offline OEWN lexicon on disk under Monday/lexicon/.
- Runtime never reaches the internet.
- Unknown words are marked unknown — never forced into a toy verb/noun list.
- Does NOT decide truth, importance, emotion, memory policy, reasoning, or intent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from lexicon.oewn_offline import (
    OfflineLexiconError,
    lemma_and_pos_candidates,
    lookup_senses,
    sense_is_affective,
    surface_is_affective,
)


_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+(?:\.\d+)?|[^\w\s]", re.UNICODE)

# Closed-class grammar inventories (function words). These are not a meaning
# lexicon — OEWN owns open-class senses (nouns/verbs/adjectives/adverbs).
_CONTRACTIONS = {
    "didn't": "did not",
    "doesn't": "does not",
    "don't": "do not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "can't": "can not",
    "cannot": "can not",
    "couldn't": "could not",
    "wouldn't": "would not",
    "shouldn't": "should not",
    "won't": "will not",
    "mightn't": "might not",
    "mustn't": "must not",
    "i'm": "i am",
    "you're": "you are",
    "he's": "he is",
    "she's": "she is",
    "it's": "it is",
    "they're": "they are",
    "we're": "we are",
}

_MODALS = {
    "may": "possibility",
    "might": "possibility",
    "could": "possibility",
    "can": "ability",
    "must": "obligation",
    "should": "recommendation",
    "would": "conditional",
    "will": "future",
}
_DETERMINERS = {
    "a", "an", "the", "this", "that", "these", "those",
    "my", "your", "his", "her", "our", "their",
}
_PREPOSITIONS = {
    "to", "from", "with", "at", "in", "on", "into", "onto", "for", "of", "by",
    "about", "under", "over", "inside", "outside", "across", "through", "between",
}
_NEGATION = {"not", "never", "no"}
_WH = {"who", "what", "when", "where", "why", "how", "which"}
_DEMONSTRATIVES = {"this", "that", "these", "those"}
_PROFORMS = {"one"}  # nominal pro-form ("the one on the shelf")
_TIME = {
    "yesterday": {"temporal_relation": "before_now", "event_time_text": "yesterday"},
    "today": {"temporal_relation": "at_now_day", "event_time_text": "today"},
    "tomorrow": {"temporal_relation": "after_now", "event_time_text": "tomorrow"},
    "tonight": {"temporal_relation": "at_now_night", "event_time_text": "tonight"},
    "now": {"temporal_relation": "at_now", "event_time_text": "now"},
    "earlier": {"temporal_relation": "before_now", "event_time_text": "earlier"},
    "later": {"temporal_relation": "after_now", "event_time_text": "later"},
}
_LINKING_VERBS = frozenset({"look", "seem", "appear", "become", "feel", "get", "grow", "remain", "stay"})
_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_PRONOUNS = {"i", "me", "you", "he", "him", "she", "her", "it", "we", "us", "they", "them"}
_DEICTIC = {
    "i": "user", "me": "user", "we": "user_group", "us": "user_group",
    "you": "mercy",
}
_AUX_RAW = {
    "am", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had",
}
_AUX_LEMMAS = {"be", "do", "have"}
_DITRANSITIVE = {"give", "send", "tell", "show", "hand", "lend", "offer"}
_EXPERIENCER = {"like", "love", "hate", "want", "prefer", "know", "see", "hear"}
_THEME_SUBJECT = {"fail", "slip"}

# POS map: OEWN → packet kind
_POS_KIND = {
    "n": "noun",
    "v": "verb",
    "a": "adjective",
    "s": "adjective",  # satellite adjective
    "r": "adverb",
}


@dataclass
class LinguisticMention:
    mention_id: str
    surface: str
    concept_surface: Optional[str]
    start: int
    end: int
    kind: str = "nominal"
    quantity: Optional[float] = None
    pronoun: bool = False
    unresolved_reference: bool = False
    properties: Dict[str, Any] = field(default_factory=dict)
    senses: List[Dict[str, Any]] = field(default_factory=list)

    def to_public(self) -> Dict[str, Any]:
        return {
            "mention_id": self.mention_id,
            "surface": self.surface,
            "concept_surface": self.concept_surface,
            "start": self.start,
            "end": self.end,
            "kind": self.kind,
            "quantity": self.quantity,
            "pronoun": self.pronoun,
            "unresolved_reference": self.unresolved_reference,
            "properties": dict(self.properties),
            "senses": list(self.senses),
        }


class LanguageComprehensionEngine:
    """Open-vocabulary English comprehension backed by offline OEWN."""

    HARD_BOUNDARY = (
        "Language may determine lexical/syntactic/semantic language structure, "
        "but may not decide truth, memory, emotion, attention, reasoning, or intent."
    )

    def __init__(self) -> None:
        self._lexicon_error: Optional[str] = None
        try:
            # Touch lexicon once at construction so failures are early and honest.
            from lexicon.oewn_offline import ensure_oewn

            ensure_oewn(allow_download=False)
        except OfflineLexiconError as exc:
            self._lexicon_error = str(exc)
        except Exception as exc:  # pragma: no cover - defensive
            self._lexicon_error = f"OEWN init failed: {exc}"

    def normalize(self, text: str) -> str:
        raw = " ".join(str(text or "").strip().split())
        if not raw:
            return ""
        low = raw.lower()
        for contraction, expanded in sorted(
            _CONTRACTIONS.items(), key=lambda item: -len(item[0])
        ):
            low = re.sub(rf"\b{re.escape(contraction)}\b", expanded, low)
        return low

    def tokenize(self, text: str) -> List[str]:
        return _WORD_RE.findall(text)

    def _lookup(self, surface: str, *, pos: Optional[str] = None) -> List[Dict[str, Any]]:
        if self._lexicon_error:
            return []
        try:
            return lookup_senses(surface, pos=pos)
        except OfflineLexiconError:
            return []
        except Exception:
            return []

    def _lemma_candidates(self, surface: str) -> List[Dict[str, str]]:
        if self._lexicon_error:
            return []
        try:
            return lemma_and_pos_candidates(surface)
        except OfflineLexiconError:
            return []
        except Exception:
            return []

    def lemma(self, token: str, *, prefer_pos: Optional[str] = None) -> str:
        """Best lemma for a token from OEWN/Morphy; fall back to surface lower."""
        low = token.lower()
        cands = self._lemma_candidates(low)
        if prefer_pos:
            preferred = [c for c in cands if c.get("pos") == prefer_pos]
            if preferred:
                # Prefer lowercase/common lemma over Proper-case OEWN entries.
                preferred.sort(key=lambda c: (0 if str(c["lemma"]).casefold() == low else 1,
                                              0 if str(c["lemma"])[:1].islower() else 1,
                                              str(c["lemma"])))
                return str(preferred[0]["lemma"])
        if cands:
            cands = list(cands)
            cands.sort(key=lambda c: (0 if str(c["lemma"]).casefold() == low else 1,
                                      0 if str(c["lemma"])[:1].islower() else 1,
                                      str(c["lemma"])))
            return str(cands[0]["lemma"])
        return low

    def _pos_set(self, token: str) -> Set[str]:
        return {c["pos"] for c in self._lemma_candidates(token.lower()) if c.get("pos")}

    def _has_pos(self, token: str, pos: str) -> bool:
        return pos in self._pos_set(token)

    def _lexical_entry(
        self, token: str, original: str
    ) -> Tuple[str, str, List[Dict[str, Any]], bool]:
        """Return (kind, lemma, senses, known)."""
        low = token.lower()

        if re.fullmatch(r"[.!?,;:]", low):
            return "punctuation", low, [], True
        if low in _WH:
            return "wh", low, [], True
        if low in _MODALS:
            return "modal", low, [], True
        if low in _NEGATION:
            return "negation", low, [], True
        if low in _TIME:
            return "temporal", low, self._lookup(low), True
        if low in _DETERMINERS:
            return "determiner", low, [], True
        if low in _PREPOSITIONS:
            return "preposition", low, [], True
        if low in _PRONOUNS:
            return "pronoun", low, [], True
        # Cardinal number words — but "one" is also a nominal pro-form; mark number
        # here and let NP builder reclassify determiner+one as pro-form.
        if (low in _NUMBER_WORDS and low not in _PROFORMS) or re.fullmatch(r"\d+(?:\.\d+)?", low):
            return "number", low, [], True
        if low in _AUX_RAW:
            lemma = self.lemma(low, prefer_pos="v")
            return "auxiliary", lemma, self._lookup(low, pos="v") or self._lookup(low), True

        senses = self._lookup(low)
        cands = self._lemma_candidates(low)
        pos_set = {c["pos"] for c in cands}

        # Capitalized alpha token with no lexicon hit → proper noun (open class).
        if (
            original[:1].isupper()
            and original.isalpha()
            and not senses
        ):
            return "proper_noun", low, [], False

        if not senses and not cands:
            return "unknown", low, [], False

        # Prefer verb when both; clause finder needs verbs. Else prefer noun.
        if "v" in pos_set and (
            "n" not in pos_set
            or (original[:1].islower() and low.endswith(("ed", "ing", "s", "es")))
        ):
            # Inflected verb forms dominate when morphology says verb.
            pass

        primary_pos = None
        if "v" in pos_set and low.endswith(("ed", "ing", "s", "es", "ied")):
            primary_pos = "v"
        elif "v" in pos_set and "n" not in pos_set and "a" not in pos_set and "r" not in pos_set:
            primary_pos = "v"
        elif "n" in pos_set:
            primary_pos = "n"
        elif "v" in pos_set:
            primary_pos = "v"
        elif "a" in pos_set or "s" in pos_set:
            primary_pos = "a"
        elif "r" in pos_set:
            primary_pos = "r"
        elif cands:
            primary_pos = cands[0]["pos"]

        lemma = self.lemma(low, prefer_pos=primary_pos)
        kind = _POS_KIND.get(primary_pos or "", "unknown")
        # Capitalized open-class noun with no verb reading → proper noun.
        # Do NOT promote verb-capable tokens (Give/Tell) to proper_noun.
        if (
            original[:1].isupper()
            and original.isalpha()
            and kind == "noun"
            and "v" not in pos_set
        ):
            kind = "proper_noun"
        # Filter senses to primary POS when known; keep all if ambiguous.
        if primary_pos:
            filtered = [s for s in senses if s.get("pos") == primary_pos]
            if filtered:
                senses = filtered
        known = bool(senses)
        if not known:
            kind = "unknown"
        return kind, lemma, senses, known

    def _number_value(self, token: str) -> Optional[float]:
        low = token.lower()
        if low in _NUMBER_WORDS:
            return float(_NUMBER_WORDS[low])
        try:
            return float(low)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _strip_punctuation(tokens: Sequence[str]) -> List[str]:
        return [t for t in tokens if not re.fullmatch(r"[.!?,;:]", t)]

    def _noun_phrase(
        self, tokens: Sequence[str], start: int, end: int, mention_id: str
    ) -> Optional[LinguisticMention]:
        raw = list(tokens[start:end])
        raw = self._strip_punctuation(raw)
        raw = [
            t
            for t in raw
            if t.lower() not in _TIME and t.lower() not in _NEGATION
        ]
        while raw and raw[0].lower() in _PREPOSITIONS:
            raw.pop(0)
        while raw and raw[-1].lower() in _PREPOSITIONS:
            raw.pop()
        if not raw:
            return None

        surface = " ".join(raw)
        low = [t.lower() for t in raw]
        quantity = None
        if low and (
            low[0] in _NUMBER_WORDS or re.fullmatch(r"\d+(?:\.\d+)?", low[0])
        ):
            quantity = self._number_value(low[0])
            raw = raw[1:]
            low = low[1:]
        # Sole demonstrative NP (this/that/these/those) → unresolved deictic.
        if len(low) == 1 and low[0] in _DEMONSTRATIVES:
            dem = low[0]
            return LinguisticMention(
                mention_id=mention_id,
                surface=surface,
                concept_surface=None,
                start=start,
                end=end,
                kind="demonstrative",
                quantity=quantity,
                pronoun=True,
                unresolved_reference=True,
                properties={"demonstrative": dem, "deictic": True},
                senses=[],
            )

        stripped_det = None
        while low and low[0] in _DETERMINERS:
            stripped_det = low[0]
            raw = raw[1:]
            low = low[1:]
        if not raw:
            # Determiner-only residue after strip (shouldn't happen often)
            return None

        if len(raw) == 1 and low[0] in _PRONOUNS:
            pronoun = low[0]
            concept_surface = _DEICTIC.get(pronoun)
            return LinguisticMention(
                mention_id=mention_id,
                surface=surface,
                concept_surface=concept_surface,
                start=start,
                end=end,
                kind="pronoun",
                quantity=quantity,
                pronoun=True,
                unresolved_reference=concept_surface is None,
                properties={"pronoun": pronoun, "deictic": True},
                senses=self._lookup(pronoun),
            )

        # Determiner + pro-form "one" (+ optional modifiers / PP) → unresolved substitute.
        # "the one" / "the one on the shelf" — head is the pro-form, not the PP noun.
        if low and "one" in low:
            one_idx = low.index("one")
            after = low[one_idx + 1 :]
            before = low[:one_idx]
            pp_only_after = (not after) or (after and after[0] in _PREPOSITIONS)
            if pp_only_after and all(
                t in _PROFORMS or t in _PREPOSITIONS or True for t in after[:1]
            ):
                # before should be adjectives/modifiers only (no other nouns required)
                return LinguisticMention(
                    mention_id=mention_id,
                    surface=surface,
                    concept_surface=None,
                    start=start,
                    end=end,
                    kind="proform",
                    quantity=quantity,
                    pronoun=True,
                    unresolved_reference=True,
                    properties={
                        "proform": "one",
                        "deictic": True,
                        "determiner": stripped_det,
                        "modifiers": before,
                        "pp": after,
                    },
                    senses=self._lookup("one", pos="n") or self._lookup("one"),
                )
        if low and low[-1] in _PROFORMS:
            return LinguisticMention(
                mention_id=mention_id,
                surface=surface,
                concept_surface=None,
                start=start,
                end=end,
                kind="proform",
                quantity=quantity,
                pronoun=True,
                unresolved_reference=True,
                properties={
                    "proform": low[-1],
                    "deictic": True,
                    "determiner": stripped_det,
                    "modifiers": low[:-1],
                },
                senses=self._lookup(low[-1], pos="n") or self._lookup(low[-1]),
            )

        # Head lemma from OEWN when available (last content token).
        head = low[-1]
        head_lemma = self.lemma(head, prefer_pos="n")
        concept_surface = " ".join(low[:-1] + [head_lemma]) if len(low) > 1 else head_lemma

        head_senses = self._lookup(head, pos="n") or self._lookup(head)
        kind = "proper_noun" if raw[0][:1].isupper() and raw[0].isalpha() else "nominal"
        return LinguisticMention(
            mention_id=mention_id,
            surface=surface,
            concept_surface=concept_surface,
            start=start,
            end=end,
            kind=kind,
            quantity=quantity,
            pronoun=False,
            unresolved_reference=False,
            senses=head_senses,
            properties={
                "head": head,
                "head_lemma": head_lemma,
                "lexicon_known": bool(head_senses),
            },
        )

    def _verb_score(self, token: str, idx: int, tokens: Sequence[str]) -> int:
        """Score how likely a token is the clause's main verb (OEWN-informed).

        Penalize early nouny tokens that only accidentally have a verb reading
        (e.g. subject "dog" also meaning "chase"). Prefer clear verb morphology.
        """
        low = token.lower()
        pos_set = self._pos_set(token)
        if "v" not in pos_set:
            return -100
        score = 3
        if pos_set == {"v"} or pos_set <= {"v", "a", "s", "r"}:
            score += 3
        if low.endswith(("ed", "ing")):
            score += 3
        elif low.endswith(("s", "es")) and len(low) > 3 and not low.endswith("ss"):
            score += 1
        # Subject slot: first open-class content word — nouny verb readings lose,
        # EXCEPT verb-initial imperatives ("Tell me…", "Give the dog…").
        content_before = [
            t
            for t in tokens[:idx]
            if not re.fullmatch(r"[.!?,;:]", t)
            and t.lower() not in _DETERMINERS
            and t.lower() not in _MODALS
            and t.lower() not in _AUX_RAW
            and t.lower() not in _NEGATION
            and t.lower() not in _PREPOSITIONS
            and t.lower() not in _TIME
            and t.lower() not in _WH
        ]
        raw_before = [
            t
            for t in tokens[:idx]
            if not re.fullmatch(r"[.!?,;:]", t)
        ]
        # Sole preverbal demonstrative/pronoun = subject NP ("That looks awful"),
        # not a determiner attaching to the verb. Do not noun-penalize the verb.
        sole_deictic_subject = (
            len(raw_before) == 1
            and raw_before[0].lower() in (_DEMONSTRATIVES | _PRONOUNS | _WH)
        )
        has_subject_material = any(
            t.lower() in _DETERMINERS
            or t.lower() in _PRONOUNS
            or t.lower() in _WH
            for t in raw_before
        )
        if not content_before and "v" in pos_set and not has_subject_material:
            # True verb-initial imperative ("Tell me…", "Give the dog…").
            score += 4
        elif sole_deictic_subject and "v" in pos_set:
            score += 4
        elif "n" in pos_set and not content_before and not sole_deictic_subject:
            # Subject slot under a determiner — nouny verb readings lose
            # ("The dog barked" — dog must not win as verb).
            score -= 6
        elif (
            "n" in pos_set
            and content_before
            and not low.endswith(("ed", "ing", "s", "es"))
        ):
            # Mid-subject nouny verb reading ("Denver weather looks…"):
            # weather also has a verb sense — penalize uninflected nouny
            # forms only. Inflected "looks" keeps its score.
            score -= 3
        return score

    def _find_main_verb(
        self, tokens: Sequence[str]
    ) -> Tuple[Optional[int], Optional[str], bool, bool]:
        """Return (index, lemma, passive, known)."""
        lows = [t.lower() for t in tokens]
        closed = (
            _DETERMINERS
            | _PREPOSITIONS
            | _PRONOUNS
            | set(_MODALS)
            | _AUX_RAW
            | _NEGATION
            | set(_TIME)
        )

        # Passive: be-AUX + lexical past participle + by.
        for idx, token in enumerate(lows[:-1]):
            if token not in _AUX_RAW or self.lemma(token, prefer_pos="v") != "be":
                continue
            next_idx = idx + 1
            while next_idx < len(tokens) and lows[next_idx] in _NEGATION:
                next_idx += 1
            if next_idx >= len(tokens):
                continue
            if self._has_pos(tokens[next_idx], "v") and "by" in lows[next_idx + 1 :]:
                lemma = self.lemma(tokens[next_idx], prefer_pos="v")
                return next_idx, lemma, True, True

        known_candidates: List[Tuple[int, str, int]] = []
        for idx, token in enumerate(tokens):
            low = token.lower()
            if low in closed:
                continue
            if not self._has_pos(token, "v"):
                continue
            lemma = self.lemma(token, prefer_pos="v")
            if lemma in _AUX_LEMMAS:
                continue
            score = self._verb_score(token, idx, tokens)
            if score >= 3:
                known_candidates.append((idx, lemma, score))

        known = None
        if known_candidates:
            # Highest verb score wins (looks=4 beats weather=3 in
            # "Denver weather looks awful"). Tie-break: later token
            # (predicate after compound subject), then earlier.
            clear = [c for c in known_candidates if c[2] >= 5]
            pool = clear if clear else known_candidates
            known = max(pool, key=lambda c: (c[2], c[0]))

        # Copula: be-AUX + complement (adjective OR nominal).
        # "Matthew is happy" / "The gasket is aluminum" / "No, the gasket is steel".
        # Prefer this over noun-with-accidental-verb-reading as the complement itself.
        be_complement = None  # (idx, lemma, kind) kind in {"adjective","nominal"}
        for idx, token in enumerate(lows):
            if token not in _AUX_RAW or self.lemma(token, prefer_pos="v") != "be":
                continue
            next_idx = idx + 1
            while next_idx < len(tokens) and lows[next_idx] in _NEGATION:
                next_idx += 1
            if next_idx >= len(tokens):
                continue
            cand = tokens[next_idx]
            cand_low = cand.lower()
            if cand_low in _PRONOUNS or cand_low in _DETERMINERS or cand_low in _PREPOSITIONS:
                continue
            if re.fullmatch(r"[.!?,;:]", cand):
                continue
            pos_set = self._pos_set(cand)
            if "a" in pos_set or "s" in pos_set:
                # Predicative adjective (happy, afraid). Prefer adj lemma even if also v.
                lemma = self.lemma(cand, prefer_pos="a")
                be_complement = (next_idx, lemma, "adjective")
                break
            if "n" in pos_set:
                lemma = self.lemma(cand, prefer_pos="n")
                be_complement = (next_idx, lemma, "nominal")
                break

        # Unknown open-class token in verb position (between subject and object).
        unknown = None
        content = [i for i, t in enumerate(tokens) if not re.fullmatch(r"[.!?,;:]", t)]
        for idx in content:
            low = tokens[idx].lower()
            if low in closed:
                continue
            if self._has_pos(tokens[idx], "v"):
                continue
            pos_here = self._pos_set(tokens[idx])
            # Never treat pure adjectives/adverbs as unknown verbs
            # ("… looks awful" — awful is predicative adj, not the verb).
            if pos_here and pos_here <= {"a", "s", "r"}:
                continue
            left_open = [
                i
                for i in content
                if i < idx and tokens[i].lower() not in closed
            ]
            if not left_open:
                continue
            # Prefer unknown with verb-like morphology, else any non-noun-only gap.
            if low.endswith(("ed", "ing", "s", "es")) or "n" not in pos_here:
                unknown = (idx, low)
                break

        def _after_preposition(idx: int) -> bool:
            for i in range(idx - 1, -1, -1):
                low = tokens[i].lower()
                if low in _PREPOSITIONS:
                    return True
                if low in _AUX_RAW or low in _MODALS or low in _NEGATION:
                    continue
                if re.fullmatch(r"[.!?,;:]", tokens[i]):
                    continue
                break
            return False

        # Copula complement wins over: later PP verbs, complement-as-verb (steel),
        # and last-resort noun-as-verb (gasket).
        if be_complement is not None:
            c_idx, c_lemma, c_kind = be_complement
            known_ok = (
                known is not None
                and known[0] != c_idx
                and known[0] < c_idx
                and not _after_preposition(known[0])
            )
            # Lexical verb clearly before the be-complement (rare) keeps known.
            if not known_ok:
                # Return complement index; caller uses kind via lexical POS / flag.
                return c_idx, c_lemma, False, True

        # Unknown earlier than known (Steve florbed the dog) wins.
        if unknown is not None and (known is None or unknown[0] < known[0]):
            return unknown[0], unknown[1], False, False
        if known is not None:
            return known[0], known[1], False, True
        if unknown is not None:
            return unknown[0], unknown[1], False, False

        # No last-resort "second content token" — that produced garbage predicates
        # like gasket/aluminum. Honest: no verb found.
        return None, None, False, False

    def _subject_end(self, tokens: Sequence[str], verb_idx: int) -> int:
        end = verb_idx
        # Skip utterance-initial rejection particle "no" (+ following punct) so
        # "No, the gasket is copper" still yields subject "the gasket".
        start = 0
        lows = [t.lower() for t in tokens]
        if lows and lows[0] == "no":
            start = 1
            while start < verb_idx and re.fullmatch(r"[.!?,;:]", tokens[start]):
                start += 1
        for idx in range(start, verb_idx):
            low = tokens[idx].lower()
            if low in _MODALS or low in _AUX_RAW or low in _NEGATION:
                end = min(end, idx)
        return end

    def _trim_object_end(self, tokens: Sequence[str], start: int) -> int:
        end = len(tokens)
        for idx in range(start, len(tokens)):
            low = tokens[idx].lower()
            if low in _TIME or re.fullmatch(r"[.!?;]", tokens[idx]):
                end = idx
                break
        return end

    def _split_ditransitive(
        self, tokens: Sequence[str], start: int, end: int
    ) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """Split double-object: recipient NP then theme NP.

        Pronoun recipient is exactly one token ("Tell me more about it" → me | …),
        never "me more".
        """
        if start >= end:
            return None
        first = tokens[start].lower()
        if first in _PRONOUNS:
            return (start, start + 1), (start + 1, end)
        for idx in range(start + 1, end):
            low = tokens[idx].lower()
            if (
                low in _DETERMINERS
                or low in _NUMBER_WORDS
                or re.fullmatch(r"\d+(?:\.\d+)?", low)
            ):
                return (start, idx), (idx, end)
            if low in _PRONOUNS:
                return (start, idx), (idx, end)
        return None

    _DEGREE_ADVERBS = frozenset({"more", "less", "just", "even", "also", "still", "only"})

    def _has_be_auxiliary_before(self, tokens: Sequence[str], idx: int) -> bool:
        lows = [t.lower() for t in tokens]
        for i in range(max(0, idx)):
            if lows[i] in _AUX_RAW and self.lemma(tokens[i], prefer_pos="v") == "be":
                return True
        return False

    def _find_about_np(
        self, tokens: Sequence[str], start: int, end: int, mention_id: str
    ) -> Optional[LinguisticMention]:
        """about-complement NP head (patient/theme of 'about'), if present."""
        lows = [t.lower() for t in tokens]
        for i in range(start, end):
            if lows[i] != "about":
                continue
            np_start = i + 1
            np_end = self._trim_object_end(tokens, np_start)
            np_end = min(np_end, end)
            if np_start < np_end:
                return self._noun_phrase(tokens, np_start, np_end, mention_id)
        return None

    def _content_np_from_span(
        self, tokens: Sequence[str], start: int, end: int, mention_id: str
    ) -> Optional[LinguisticMention]:
        """Build NP from span, skipping leading degree adverbs; prefer about-NP."""
        if start >= end:
            return None
        about = self._find_about_np(tokens, start, end, mention_id)
        if about is not None:
            return about
        i = start
        lows = [t.lower() for t in tokens]
        while i < end and lows[i] in self._DEGREE_ADVERBS:
            i += 1
        while i < end and lows[i] in _PREPOSITIONS:
            i += 1
        if i >= end:
            return None
        return self._noun_phrase(tokens, i, end, mention_id)

    def _topic_head_from_roles(
        self,
        roles: Dict[str, str],
        mentions: Sequence[LinguisticMention],
    ) -> Optional[str]:
        """Content NP head for topic.

        Priority (Matty catch on bd4d5fb):
          1. about-NP (about the deadline → deadline)
          2. theme/patient content noun
          Never: emotion-noun as topic when about-complement exists;
          never proper-name experiencer/subject alone (matthew);
          never predicative adjective / attribute (awful, aluminum).
        """
        by_id = {m.mention_id: m for m in mentions}
        has_about = bool(roles.get("about"))

        def _is_emotion_noun_mention(mention: LinguisticMention) -> bool:
            head = (mention.properties or {}).get("head_lemma") or (
                mention.properties or {}
            ).get("head")
            surf = str(head or mention.concept_surface or mention.surface or "").strip()
            if not surf:
                return False
            # Prefer noun senses on the mention; fall back to surface bridge.
            for sense in mention.senses or []:
                if not isinstance(sense, dict):
                    continue
                if str(sense.get("pos") or "") != "n":
                    continue
                if sense_is_affective(
                    str(sense.get("synset_id") or ""),
                    str(sense.get("definition") or ""),
                    surface=surf.split()[-1] if surf else "",
                ):
                    return True
            return surface_is_affective(surf.split()[-1] if surf else surf)

        def _is_proper_experiencer(mention: LinguisticMention) -> bool:
            if mention.kind == "proper_noun":
                return True
            head = (mention.properties or {}).get("head_lemma") or (
                mention.properties or {}
            ).get("head")
            if head and str(head)[:1].isupper() and str(head).isalpha():
                return True
            # Single-token capitalized surface (Matthew) kept lowercased in tokens —
            # treat known proper-noun OEWN hits / kind.
            return False

        def _head_of(
            mention: LinguisticMention,
            *,
            allow_emotion: bool = True,
            allow_proper: bool = True,
        ) -> Optional[str]:
            if mention.pronoun or mention.unresolved_reference:
                return None
            if not allow_proper and _is_proper_experiencer(mention):
                return None
            if not allow_emotion and _is_emotion_noun_mention(mention):
                return None
            head = (mention.properties or {}).get("head_lemma") or (
                mention.properties or {}
            ).get("head")
            if head and str(head).isalpha():
                h = str(head).lower()
                if h in _TIME or h in self._DEGREE_ADVERBS:
                    return None
                if not allow_emotion and surface_is_affective(h):
                    return None
                return h
            concept = (mention.concept_surface or mention.surface or "").strip()
            parts = [p for p in concept.lower().split() if p.isalpha()]
            parts = [p for p in parts if p not in _TIME and p not in self._DEGREE_ADVERBS]
            if parts:
                # NP head = last content token ("denver weather" → weather;
                # "the aluminum gasket" → gasket). Never first proper alone.
                h = parts[-1]
                if not allow_emotion and surface_is_affective(h):
                    return None
                return h
            return None

        # 1) about-complement always wins when present.
        about_mid = roles.get("about")
        if about_mid and about_mid in by_id:
            head = _head_of(by_id[about_mid], allow_emotion=True, allow_proper=True)
            if head:
                return head

        # 2) theme / patient content — skip emotion nouns when about existed
        #    (about already preferred); skip proper-name subjects-as-topic.
        for role in ("theme", "patient", "topic"):
            mid = roles.get(role)
            mention = by_id.get(mid) if mid else None
            if not mention:
                continue
            head = _head_of(
                mention,
                allow_emotion=not has_about,
                allow_proper=False,
            )
            if head:
                return head
        # Attribute / predicative adjective are NEVER topic (aluminum, awful).
        return None

    def _qualifiers(self, tokens: Sequence[str]) -> Dict[str, Any]:

        lows = [t.lower() for t in tokens]
        q: Dict[str, Any] = {
            "polarity": "negative" if any(t in _NEGATION for t in lows) else "positive"
        }
        for token in lows:
            if token in _MODALS:
                q["modality"] = _MODALS[token]
                q["modality_text"] = token
                break
        for token in lows:
            if token in _TIME:
                q.update(_TIME[token])
                break
        return q

    def _content_tokens(self, tokens: Sequence[str]) -> List[str]:
        return [t for t in tokens if not re.fullmatch(r"[.!?,;:]", t)]

    def _speech_act_features(self, original: str, tokens: Sequence[str]) -> Dict[str, Any]:
        """Morphosyntax / punctuation features for clause type — not cue-word bags."""
        text = (original or "").strip()
        content = self._content_tokens(tokens)
        lows = [t.lower() for t in content]
        features: Dict[str, Any] = {
            "question_mark": bool(text.endswith("?")),
            "wh_fronted": bool(lows and lows[0] in _WH),
            "aux_inversion": False,
            "verb_initial": False,
            "has_subject_before_verb": False,
        }
        if not lows:
            return features

        first = lows[0]
        # Aux/modal inversion: Did you… / Are the bolts… / Can Mercy…
        if first in _AUX_RAW or first in _MODALS:
            if len(lows) >= 2 and lows[1] in _PRONOUNS:
                features["aux_inversion"] = True
            elif len(lows) >= 2 and lows[1] in _DETERMINERS:
                # Aux + NP subject + later lexical verb → inverted question.
                later_verb = False
                for tok in content[2:]:
                    low = tok.lower()
                    if low in _AUX_RAW or low in _MODALS or low in _NEGATION:
                        continue
                    if self._has_pos(tok, "v") and self.lemma(tok, prefer_pos="v") not in _AUX_LEMMAS:
                        later_verb = True
                        break
                features["aux_inversion"] = later_verb
            elif len(lows) >= 2 and self._has_pos(content[1], "n"):
                # Are carburetors noisy — aux + bare plural subject
                features["aux_inversion"] = True

        # Verb-initial (imperative candidate): lexical verb first, not aux/modal/pronoun.
        if (
            first not in _AUX_RAW
            and first not in _MODALS
            and first not in _PRONOUNS
            and first not in _WH
            and first not in _NEGATION
            and self._has_pos(content[0], "v")
        ):
            features["verb_initial"] = True

        # Subject before main verb?
        verb_idx, _, _, _ = self._find_main_verb(tokens)
        if verb_idx is not None:
            for i in range(verb_idx):
                low = tokens[i].lower()
                if low in _PRONOUNS or low in _DETERMINERS or (
                    low not in _AUX_RAW
                    and low not in _MODALS
                    and low not in _NEGATION
                    and low not in _PREPOSITIONS
                    and low not in _WH
                    and not re.fullmatch(r"[.!?,;:]", tokens[i])
                ):
                    features["has_subject_before_verb"] = True
                    break
        return features

    def _speech_act(self, original: str, tokens: Sequence[str]) -> str:
        text = (original or "").strip()
        if not text:
            return "none"
        features = self._speech_act_features(original, tokens)
        if features["question_mark"] or features["wh_fronted"] or features["aux_inversion"]:
            return "question"
        if features["verb_initial"] and not features["has_subject_before_verb"]:
            return "imperative"
        # Conservative imperative: verb-initial with v reading even if also n
        if features["verb_initial"]:
            content = self._content_tokens(tokens)
            if content and self._has_pos(content[0], "v"):
                # "Tell me…" has object pronoun after verb — imperative
                lows = [t.lower() for t in content]
                if len(lows) > 1 and (lows[1] in _PRONOUNS or lows[1] in _DETERMINERS):
                    return "imperative"
        return "declarative"

    def _contrast_features(self, tokens: Sequence[str], lexical: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """Structural contrast / rejection from polarity + particle position."""
        content = self._content_tokens(tokens)
        lows = [t.lower() for t in content]
        kinds = []
        for entry in lexical:
            if entry.get("kind") == "punctuation":
                continue
            kinds.append(entry.get("kind"))
        rejection_particle = bool(lows and lows[0] == "no")
        # "no" as leading rejection even if OEWN noun-tagged before closed-class fix
        if not rejection_particle and lexical:
            first_kind = None
            first_surf = None
            for entry in lexical:
                if entry.get("kind") == "punctuation":
                    continue
                first_kind = entry.get("kind")
                first_surf = str(entry.get("surface") or "").lower()
                break
            if first_surf == "no":
                rejection_particle = True
        has_negation = any(t in _NEGATION for t in lows)
        # Contrastive negation between content spans: "... not ..." with material both sides
        contrastive_negation = False
        if "not" in lows:
            idx = lows.index("not")
            left = [t for t in lows[:idx] if t not in _NEGATION and t != "no"]
            right = [t for t in lows[idx + 1 :] if t not in _NEGATION]
            contrastive_negation = bool(left and right)
        return {
            "rejection_particle": rejection_particle,
            "polarity": "negative" if has_negation or rejection_particle else "positive",
            "contrastive_negation": contrastive_negation,
        }

    def _affect_from_senses(
        self,
        senses: Sequence[Dict[str, Any]],
        *,
        surface: str = "",
    ) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        surf = (surface or "").strip()
        for sense in senses or []:
            if not isinstance(sense, dict):
                continue
            if sense_is_affective(
                str(sense.get("synset_id") or ""),
                str(sense.get("definition") or ""),
                surface=surf,
            ):
                hits.append(
                    {
                        "synset_id": sense.get("synset_id"),
                        "definition": sense.get("definition"),
                    }
                )
        # Lemma→noun/verb bridge when sense walk misses thin adj links (worried).
        if not hits and surf and surface_is_affective(surf):
            hits.append(
                {
                    "synset_id": None,
                    "definition": None,
                    "bridge": "lemma_noun_or_verb",
                    "surface": surf,
                }
            )
        return hits

    def _packet_affect(
        self,
        *,
        predicate_senses: Sequence[Dict[str, Any]],
        mentions: Sequence[LinguisticMention],
        lexical: Sequence[Dict[str, Any]],
        predicative_adjective: Optional[Dict[str, Any]] = None,
        predicate_surface: str = "",
    ) -> Dict[str, Any]:
        evidence: List[Dict[str, Any]] = []
        pred_surf = (predicate_surface or "").strip()
        for hit in self._affect_from_senses(predicate_senses, surface=pred_surf):
            evidence.append({"source": "predicate_sense", **hit})
        if predicative_adjective:
            adj_surf = str(predicative_adjective.get("surface") or predicative_adjective.get("lemma") or "")
            for hit in self._affect_from_senses(
                predicative_adjective.get("senses") or [], surface=adj_surf
            ):
                evidence.append(
                    {
                        "source": "predicative_adjective",
                        "surface": adj_surf,
                        **hit,
                    }
                )
        # Mentions: affect-bearing heads (anxiety/fear/joy…), surface-scoped.
        for mention in mentions:
            head = (mention.properties or {}).get("head_lemma") or (
                mention.properties or {}
            ).get("head") or mention.surface
            head_surf = str(head or "").strip()
            hits = self._affect_from_senses(mention.senses, surface=head_surf.split()[-1] if head_surf else "")
            if hits and mention.kind in {"nominal", "proper_noun", "proform"}:
                for hit in hits:
                    evidence.append(
                        {
                            "source": "mention_sense",
                            "surface": mention.surface,
                            **hit,
                        }
                    )
        # Adjective / adverb tokens only (predicative or modifiers) — not bare verbs/nouns
        for entry in lexical:
            if entry.get("kind") not in {"adjective", "adverb"}:
                continue
            tok_surf = str(entry.get("surface") or entry.get("lemma") or "")
            for hit in self._affect_from_senses(entry.get("senses") or [], surface=tok_surf):
                evidence.append(
                    {
                        "source": "token_sense",
                        "surface": tok_surf,
                        **hit,
                    }
                )
        # Dedup by synset
        seen = set()
        deduped = []
        for item in evidence:
            key = (item.get("synset_id"), item.get("source"), item.get("surface"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return {"present": bool(deduped), "evidence": deduped[:8]}

    def analyze(self, text: str) -> Dict[str, Any]:
        original = str(text or "").strip()
        normalized = self.normalize(original)
        tokens = self.tokenize(normalized)
        original_tokens = self.tokenize(original)
        lexical: List[Dict[str, Any]] = []
        unknown_words: List[str] = []
        ambiguous_words: List[Dict[str, Any]] = []

        for idx, token in enumerate(tokens):
            original_token = original_tokens[idx] if idx < len(original_tokens) else token
            kind, lemma, senses, known = self._lexical_entry(token, original_token)
            entry = {
                "index": idx,
                "surface": token,
                "lemma": lemma,
                "kind": kind,
                "senses": senses,
                "lexicon_known": known,
                "sense_count": len(senses),
            }
            if len(senses) > 1:
                entry["ambiguous"] = True
                ambiguous_words.append(
                    {
                        "surface": token,
                        "lemma": lemma,
                        "sense_ids": [s.get("synset_id") for s in senses],
                    }
                )
            lexical.append(entry)
            if kind == "unknown" and token.isalpha() and token not in unknown_words:
                unknown_words.append(token)

        verb_idx, predicate, passive, predicate_known = self._find_main_verb(tokens)
        mentions: List[LinguisticMention] = []
        roles: Dict[str, str] = {}
        qualifiers = self._qualifiers(tokens)
        unresolved_references: List[Dict[str, Any]] = []
        clause_confidence = 0.0
        predicate_senses: List[Dict[str, Any]] = []
        predicative_adjective: Optional[Dict[str, Any]] = None
        predicative_nominal = False
        copular = False
        topic_head: Optional[str] = None

        if verb_idx is not None and predicate:
            pred_token_kind = lexical[verb_idx]["kind"] if verb_idx < len(lexical) else None
            pos_at_pred = self._pos_set(tokens[verb_idx])
            copular = self._has_be_auxiliary_before(tokens, verb_idx)
            is_pred_adj = (
                pred_token_kind == "adjective"
                or ("a" in pos_at_pred or "s" in pos_at_pred)
                and copular
            )
            is_pred_nom = (
                copular
                and not is_pred_adj
                and ("n" in pos_at_pred or pred_token_kind in {"noun", "unknown"})
            )
            if is_pred_adj:
                predicate_senses = self._lookup(
                    tokens[verb_idx], pos="a"
                ) or self._lookup(predicate, pos="a") or self._lookup(tokens[verb_idx])
                predicative_adjective = {
                    "surface": tokens[verb_idx],
                    "lemma": predicate,
                    "senses": predicate_senses,
                }
            elif is_pred_nom:
                predicative_nominal = True
                # Copula predicate is be; complement keeps its noun senses on the mention.
                predicate = "be"
                predicate_known = True
                predicate_senses = self._lookup("be", pos="v") or self._lookup("is", pos="v")
            elif predicate_known:
                predicate_senses = self._lookup(
                    tokens[verb_idx], pos="v"
                ) or self._lookup(predicate, pos="v")

            # Subject ends at be-AUX when copular; else at verb_idx.
            subject_limit = verb_idx
            if copular:
                lows_tmp = [t.lower() for t in tokens]
                for i in range(verb_idx):
                    if lows_tmp[i] in _AUX_RAW and self.lemma(tokens[i], prefer_pos="v") == "be":
                        subject_limit = i
                        break
            subject_end = self._subject_end(tokens, subject_limit)
            subject = self._noun_phrase(tokens, 0, subject_end, "m1")
            if subject:
                mentions.append(subject)
                if subject.unresolved_reference:
                    unresolved_references.append(
                        {"mention_id": subject.mention_id, "surface": subject.surface}
                    )

            if passive:
                lows = [t.lower() for t in tokens]
                by_idx = lows.index("by", verb_idx + 1)
                agent = self._noun_phrase(
                    tokens,
                    by_idx + 1,
                    self._trim_object_end(tokens, by_idx + 1),
                    f"m{len(mentions)+1}",
                )
                if agent:
                    mentions.append(agent)
                    if agent.unresolved_reference:
                        unresolved_references.append(
                            {"mention_id": agent.mention_id, "surface": agent.surface}
                        )
                if subject:
                    roles["patient"] = subject.mention_id
                if agent:
                    roles["agent"] = agent.mention_id
                clause_confidence = 0.92 if subject and agent else 0.68
            elif is_pred_adj or is_pred_nom:
                # Copula: subject is theme; complement is attribute; about-PP is about.
                if subject:
                    roles["theme"] = subject.mention_id
                if is_pred_nom:
                    attr = self._noun_phrase(
                        tokens, verb_idx, verb_idx + 1, f"m{len(mentions)+1}"
                    )
                    if attr:
                        mentions.append(attr)
                        roles["attribute"] = attr.mention_id
                about = self._find_about_np(
                    tokens, verb_idx + 1, len(tokens), f"m{len(mentions)+1}"
                )
                if about:
                    mentions.append(about)
                    roles["about"] = about.mention_id
                clause_confidence = 0.90 if subject else 0.55
            else:
                object_start = verb_idx + 1
                while object_start < len(tokens) and tokens[object_start].lower() in (
                    _NEGATION | _PREPOSITIONS
                ):
                    object_start += 1
                object_end = self._trim_object_end(tokens, object_start)

                if predicate in _DITRANSITIVE and object_start < object_end:
                    split = self._split_ditransitive(tokens, object_start, object_end)
                    if split:
                        (a0, a1), (b0, b1) = split
                        recipient = self._noun_phrase(
                            tokens, a0, a1, f"m{len(mentions)+1}"
                        )
                        # Theme = content NP in remnant; about-PP preferred over "more…"
                        theme = self._content_np_from_span(
                            tokens, b0, b1, f"m{len(mentions)+2}"
                        )
                        about = None
                        # If theme came from about-PP, also tag about role.
                        if theme and any(
                            tokens[i].lower() == "about" for i in range(b0, min(b1, len(tokens)))
                        ):
                            about = theme
                        if recipient:
                            mentions.append(recipient)
                        if theme and about is not theme:
                            mentions.append(theme)
                        elif theme and about is theme:
                            mentions.append(theme)
                        if subject:
                            roles["agent"] = subject.mention_id
                        if recipient:
                            roles["recipient"] = recipient.mention_id
                        if about is not None:
                            roles["about"] = about.mention_id
                        elif theme is not None:
                            roles["theme"] = theme.mention_id
                        clause_confidence = 0.88 if recipient else 0.65
                    else:
                        obj = self._content_np_from_span(
                            tokens, object_start, object_end, f"m{len(mentions)+1}"
                        )
                        if obj:
                            mentions.append(obj)
                        if subject:
                            roles["agent"] = subject.mention_id
                        if obj:
                            roles["theme"] = obj.mention_id
                        clause_confidence = 0.72
                else:
                    # Linking verb + predicative adjective: "That looks awful tonight".
                    link_adj = None
                    if predicate in _LINKING_VERBS and object_start < len(tokens):
                        cand = tokens[object_start]
                        pos_set = self._pos_set(cand)
                        if "a" in pos_set or "s" in pos_set:
                            link_adj = {
                                "surface": cand,
                                "lemma": self.lemma(cand, prefer_pos="a"),
                                "senses": self._lookup(cand, pos="a")
                                or self._lookup(cand),
                            }
                            predicative_adjective = link_adj
                            if subject:
                                roles["theme"] = subject.mention_id
                            about = self._find_about_np(
                                tokens,
                                object_start + 1,
                                len(tokens),
                                f"m{len(mentions)+1}",
                            )
                            if about:
                                mentions.append(about)
                                roles["about"] = about.mention_id
                            clause_confidence = 0.88 if subject else 0.55
                    if link_adj is None:
                        # Direct object NP up to about-PP; about-complement separate.
                        lows_span = [t.lower() for t in tokens]
                        about_at = None
                        for i in range(object_start, min(object_end, len(tokens))):
                            if lows_span[i] == "about":
                                about_at = i
                                break
                        obj_end = about_at if about_at is not None else object_end
                        obj = (
                            self._noun_phrase(
                                tokens, object_start, obj_end, f"m{len(mentions)+1}"
                            )
                            if object_start < obj_end
                            else None
                        )
                        if obj:
                            mentions.append(obj)
                        about = None
                        if about_at is not None:
                            about = self._find_about_np(
                                tokens,
                                about_at,
                                max(object_end, about_at + 1),
                                f"m{len(mentions)+1}",
                            )
                            # about span may extend past trim if trim cut at time before about — use full tail
                            if about is None:
                                about = self._find_about_np(
                                    tokens,
                                    about_at,
                                    len(tokens),
                                    f"m{len(mentions)+1}",
                                )
                        if about:
                            mentions.append(about)
                            roles["about"] = about.mention_id
                        pred_lemma = predicate
                        if pred_lemma in _EXPERIENCER or pred_lemma == "feel":
                            if subject:
                                roles["experiencer"] = subject.mention_id
                            if obj:
                                roles["theme"] = obj.mention_id
                        elif predicate in _THEME_SUBJECT:
                            if subject:
                                roles["theme"] = subject.mention_id
                        else:
                            if subject:
                                roles["agent"] = subject.mention_id
                            if obj:
                                roles["patient"] = obj.mention_id
                        clause_confidence = 0.90 if subject else 0.55

            for mention in mentions:
                if mention.unresolved_reference and not any(
                    x.get("mention_id") == mention.mention_id
                    for x in unresolved_references
                ):
                    unresolved_references.append(
                        {"mention_id": mention.mention_id, "surface": mention.surface}
                    )
                if mention.quantity is not None:
                    role = next(
                        (r for r, mid in roles.items() if mid == mention.mention_id),
                        None,
                    )
                    if role:
                        qualifiers.setdefault("quantities", {})[role] = mention.quantity

        if predicate and not predicate_known and predicate not in unknown_words:
            if predicate.isalpha():
                unknown_words.append(predicate)

        speech_features = self._speech_act_features(original, tokens)
        speech_act = self._speech_act(original, tokens)
        contrast = self._contrast_features(tokens, lexical)
        affect = self._packet_affect(
            predicate_senses=predicate_senses,
            mentions=mentions,
            lexical=lexical,
            predicative_adjective=predicative_adjective,
            predicate_surface=str(predicate or ""),
        )
        # Experiencer + affective theme noun (anxiety/fear/joy…) also marks affect.
        if not affect.get("present"):
            for mid_role in ("theme", "patient", "about"):
                mid = roles.get(mid_role)
                if not mid:
                    continue
                for mention in mentions:
                    if mention.mention_id != mid:
                        continue
                    head = (mention.properties or {}).get("head_lemma") or (
                        mention.properties or {}
                    ).get("head") or mention.surface
                    head_surf = str(head or "").strip()
                    hits = self._affect_from_senses(
                        mention.senses,
                        surface=head_surf.split()[-1] if head_surf else "",
                    )
                    if hits:
                        affect = {
                            "present": True,
                            "evidence": [
                                {"source": "role_mention_sense", "surface": mention.surface, **h}
                                for h in hits[:4]
                            ],
                        }
                        break

        topic_head = self._topic_head_from_roles(roles, mentions)

        clause = None
        if predicate:
            clause = {
                "clause_id": "clause_1",
                "predicate_surface": predicate,
                "predicate_known": predicate_known,
                "predicate_senses": predicate_senses,
                "predicative_adjective": bool(predicative_adjective),
                "predicative_nominal": predicative_nominal,
                "copular": copular or bool(predicative_adjective) or predicative_nominal,
                "voice": "passive" if passive else "active",
                "roles": dict(roles),
                "qualifiers": qualifiers,
                "confidence": clause_confidence,
                "speech_act": speech_act,
                "clause_type": speech_act,
                "topic_head": topic_head,
            }

        overall = clause_confidence
        if unresolved_references:
            overall = min(overall or 0.5, 0.60)
        if not predicate_known and predicate:
            overall = min(overall or 0.4, 0.40)
        if ambiguous_words:
            overall = min(overall or 0.7, 0.75)
        if speech_act in {"question", "imperative"}:
            overall = max(overall or 0.0, 0.7)
        if self._lexicon_error:
            overall = 0.0

        return {
            "contract": "language_understanding_v1",
            "raw_text": original,
            "normalized_text": normalized,
            "tokens": lexical,
            "mentions": [m.to_public() for m in mentions],
            "clauses": [clause] if clause else [],
            "unknown_words": unknown_words,
            "unresolved_references": unresolved_references,
            "ambiguous_words": ambiguous_words,
            "speech_act": speech_act,
            "speech_act_features": speech_features,
            "clause_type": speech_act,
            "contrast": contrast,
            "affect": affect,
            "topic_head": topic_head if verb_idx is not None else None,
            "confidence": overall,
            "lexicon": {
                "name": "oewn",
                "version": "2024",
                "offline": True,
                "error": self._lexicon_error,
            },
            "boundary": self.HARD_BOUNDARY,
        }


__all__ = ["LanguageComprehensionEngine", "LinguisticMention"]
