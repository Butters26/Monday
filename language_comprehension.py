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
_NEGATION = {"not", "never"}
_TIME = {
    "yesterday": {"temporal_relation": "before_now", "event_time_text": "yesterday"},
    "today": {"temporal_relation": "at_now_day", "event_time_text": "today"},
    "tomorrow": {"temporal_relation": "after_now", "event_time_text": "tomorrow"},
    "now": {"temporal_relation": "at_now", "event_time_text": "now"},
    "earlier": {"temporal_relation": "before_now", "event_time_text": "earlier"},
    "later": {"temporal_relation": "after_now", "event_time_text": "later"},
}
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
        if low in _NUMBER_WORDS or re.fullmatch(r"\d+(?:\.\d+)?", low):
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
        if original[:1].isupper() and original.isalpha() and kind == "noun":
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
        while low and low[0] in _DETERMINERS:
            raw = raw[1:]
            low = low[1:]
        if not raw:
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
                properties={"pronoun": pronoun},
                senses=self._lookup(pronoun),
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
        # Subject slot: first open-class content word — nouny verb readings lose.
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
        ]
        if "n" in pos_set and not content_before:
            score -= 6
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
            clear = [c for c in known_candidates if c[2] >= 5]
            known = (clear[0] if clear else known_candidates[0])

        # Unknown open-class token in verb position (between subject and object).
        unknown = None
        content = [i for i, t in enumerate(tokens) if not re.fullmatch(r"[.!?,;:]", t)]
        for idx in content:
            low = tokens[idx].lower()
            if low in closed:
                continue
            if self._has_pos(tokens[idx], "v"):
                continue
            left_open = [
                i
                for i in content
                if i < idx and tokens[i].lower() not in closed
            ]
            if not left_open:
                continue
            # Prefer unknown with verb-like morphology, else any non-noun-only gap.
            if low.endswith(("ed", "ing", "s", "es")) or "n" not in self._pos_set(
                tokens[idx]
            ):
                unknown = (idx, low)
                break

        if unknown is not None and (known is None or unknown[0] < known[0]):
            return unknown[0], unknown[1], False, False
        if known is not None:
            return known[0], known[1], False, True

        # Last resort: second content token.
        if len(content) >= 2:
            idx = content[1]
            low = tokens[idx].lower()
            if low not in closed:
                return idx, low, False, self._has_pos(tokens[idx], "v")
        return None, None, False, False

    def _subject_end(self, tokens: Sequence[str], verb_idx: int) -> int:
        end = verb_idx
        for idx in range(verb_idx):
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

    def _speech_act(self, original: str, tokens: Sequence[str]) -> str:
        text = (original or "").strip()
        if not text:
            return "none"
        if text.endswith("?"):
            return "question"
        lows = [t.lower() for t in tokens]
        content = [t for t in lows if not re.fullmatch(r"[.!?,;:]", t)]
        if content and content[0] in {
            "who", "what", "when", "where", "why", "how", "which",
        }:
            return "question"
        # Imperative: bare verb at start, no subject pronoun/noun before it.
        if content and self._has_pos(content[0], "v") and content[0] not in _AUX_RAW:
            if content[0] not in _PRONOUNS and content[0] not in _DETERMINERS:
                # "Give the dog a ball" — verb-initial.
                if not (len(content) > 1 and content[0] in _PRONOUNS):
                    # Conservative: only if first token is verb and not a known noun-only.
                    pos = self._pos_set(content[0])
                    if "v" in pos and "n" not in pos:
                        return "imperative"
        return "declarative"

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

        if verb_idx is not None and predicate:
            if predicate_known:
                predicate_senses = self._lookup(
                    tokens[verb_idx], pos="v"
                ) or self._lookup(predicate, pos="v")
            subject_end = self._subject_end(tokens, verb_idx)
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
                        theme = self._noun_phrase(
                            tokens, b0, b1, f"m{len(mentions)+2}"
                        )
                        if recipient:
                            mentions.append(recipient)
                        if theme:
                            mentions.append(theme)
                        if subject:
                            roles["agent"] = subject.mention_id
                        if recipient:
                            roles["recipient"] = recipient.mention_id
                        if theme:
                            roles["theme"] = theme.mention_id
                        clause_confidence = (
                            0.94 if subject and recipient and theme else 0.65
                        )
                    else:
                        obj = self._noun_phrase(
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
                    obj = (
                        self._noun_phrase(
                            tokens, object_start, object_end, f"m{len(mentions)+1}"
                        )
                        if object_start < object_end
                        else None
                    )
                    if obj:
                        mentions.append(obj)
                    if predicate in _EXPERIENCER:
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

        clause = None
        if predicate:
            clause = {
                "clause_id": "clause_1",
                "predicate_surface": predicate,
                "predicate_known": predicate_known,
                "predicate_senses": predicate_senses,
                "voice": "passive" if passive else "active",
                "roles": dict(roles),
                "qualifiers": qualifiers,
                "confidence": clause_confidence,
                "speech_act": self._speech_act(original, tokens),
            }

        overall = clause_confidence
        if unresolved_references:
            overall = min(overall or 0.5, 0.60)
        if not predicate_known and predicate:
            overall = min(overall or 0.4, 0.40)
        if ambiguous_words:
            overall = min(overall or 0.7, 0.75)
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
            "speech_act": self._speech_act(original, tokens),
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
