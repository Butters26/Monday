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
import json
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from lexicon.oewn_offline import (
    OfflineLexiconError,
    complement_compete_keys,
    lemma_and_pos_candidates,
    lookup_senses,
    selected_affective_senses,
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
    "that's": "that is",
    "what's": "what is",
    "who's": "who is",
    "where's": "where is",
    "there's": "there is",
    "here's": "here is",
    "how's": "how is",
    "i've": "i have",
    "you've": "you have",
    "we've": "we have",
    "they've": "they have",
    "i'll": "i will",
    "you'll": "you will",
    "we'll": "we will",
    "they'll": "they will",
    "i'd": "i would",
    "you'd": "you would",
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
    "than",  # "older than me": what it's compared with
}
_NEGATION = {"not", "never", "no"}
# Joining words (grammar, like the sets above): "Ariana and Cleo", "tea or coffee".
_CONJUNCTIONS = {"and", "or", "but", "nor", "because"}
# Words that start a statement inside another ("if it rains", "although it was cold").
_SUBORDINATING = {"if", "although", "though", "unless", "whereas"}
# Counting words (grammar): "how many cats", "some dogs".
_QUANTIFIERS = {"many", "much", "few", "several", "some", "any", "more", "most"}
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

    # ---- words he has taught her ("yeet means throw") -----------------------
    _taught: Optional[Dict[str, Dict[str, Any]]] = None
    _taught_lock = threading.Lock()

    @classmethod
    def _taught_path(cls) -> Optional[str]:
        try:
            from runtime_paths import runtime_file
            return runtime_file("taught_words.json")
        except Exception:
            return None

    @classmethod
    def taught_words(cls) -> Dict[str, Dict[str, Any]]:
        with cls._taught_lock:
            if cls._taught is None:
                cls._taught = {}
                path = cls._taught_path()
                if path:
                    try:
                        cls._taught = json.loads(Path(path).read_text(encoding="utf-8"))
                    except FileNotFoundError:
                        pass
                    except Exception as error:
                        print(f"⚠️  Language: couldn't read the words she was taught ({error})")
            return cls._taught

    def learn_taught_word(self, reading: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """"Yeet means throw": a word he teaches her, believed to mean what the
        words he gave mean (their dictionary senses), kept in her own file.
        Slang the dictionary doesn't have is learned this way."""
        clause = (reading.get("clauses") or [{}])[0]
        if str(clause.get("predicate_surface") or "") != "mean" or reading.get("speech_act") != "declarative":
            return None
        roles = clause.get("roles") or {}
        mentions = {m.get("mention_id"): m for m in reading.get("mentions") or []}
        word = str((mentions.get(roles.get("agent") or roles.get("theme")) or {}).get("surface") or "").casefold()
        means = str((mentions.get(roles.get("patient")) or {}).get("surface") or "").casefold()
        if not word or not means or " " in word or not word.isalpha():
            return None
        head = means.split()[-1]
        senses = [dict(x, taught=True) for x in self._lookup(head)] if head.isalpha() else []
        entry = {"means": means, "senses": senses}
        words = self.taught_words()
        with self._taught_lock:
            words[word] = entry
            path = self._taught_path()
            if path:
                try:
                    Path(path).write_text(json.dumps(words, indent=1), encoding="utf-8")
                except Exception as error:
                    print(f"⚠️  Language: couldn't save the word she was taught ({error})")
        self.__dict__.get("_readings", {}).clear()  # read again with the new word
        return {"word": word, **entry}

    def _lookup(self, surface: str, *, pos: Optional[str] = None) -> List[Dict[str, Any]]:
        taught = self.taught_words().get(str(surface or "").casefold())
        if taught and taught.get("senses"):
            # A word he taught her means what he said it means.
            return [x for x in taught["senses"] if pos is None or x.get("pos") == pos
                    or (pos == "a" and x.get("pos") == "s")]
        if self._lexicon_error:
            return []
        try:
            return lookup_senses(surface, pos=pos)
        except OfflineLexiconError:
            return []
        except Exception:
            return []

    def _lookup_adjective_senses(self, surface: str, *, max_senses: int = 4) -> List[Dict[str, Any]]:
        """Predicative-adjective senses: OEWN heads (a) + satellites (s), capped.

        pos="a" alone drops satellite readings (fine=satisfactory, awful=bad).
        If enough head senses exist (>=2), skip satellites — obscure ones
        (fast=impervious/immoral) pollute same-kind compete keys via quality.
        When heads are thin (awful/fine/red), pull satellites to fill.
        """
        if self._lexicon_error:
            return []
        seen = set()
        heads: List[Dict[str, Any]] = []
        for sense in self._lookup(surface, pos="a"):
            sid = str(sense.get("synset_id") or "")
            if not sid or sid in seen:
                continue
            seen.add(sid)
            heads.append(sense)
            if len(heads) >= min(3, max_senses):
                break
        out = list(heads)
        # Satellites when heads are thin (0–1), OR chromatic color satellites
        # even when heads are thick (green has political+unripe heads that would
        # otherwise hide the chromatic satellite needed for blue↔green).
        try:
            from lexicon.oewn_offline import sense_is_chromatic_adjective
        except Exception:
            sense_is_chromatic_adjective = lambda _sid: False  # type: ignore
        pull_sats = len(heads) < 2
        for sense in self._lookup(surface, pos="s"):
            sid = str(sense.get("synset_id") or "")
            if not sid or sid in seen:
                continue
            chromatic = bool(sense_is_chromatic_adjective(sid))
            if not pull_sats and not chromatic:
                continue
            if len(out) >= max_senses and not chromatic:
                continue
            # Chromatic may extend past max_senses by one slot when heads filled it.
            if len(out) >= max_senses + (1 if chromatic else 0):
                break
            seen.add(sid)
            out.append(sense)
        if not out:
            for sense in self._lookup(surface):
                if sense.get("pos") not in {"a", "s"}:
                    continue
                sid = str(sense.get("synset_id") or "")
                if not sid or sid in seen:
                    continue
                seen.add(sid)
                out.append(sense)
                if len(out) >= max_senses:
                    break
        return out

    def _lemma_candidates(self, surface: str) -> List[Dict[str, str]]:
        if self._lexicon_error:
            return []
        try:
            return lemma_and_pos_candidates(surface)
        except OfflineLexiconError:
            return []
        except Exception:
            return []

    @staticmethod
    def _spells(root: str, word: str) -> bool:
        """Does English regular spelling turn this root into this word?
        hate -> hates yes; hat -> hates no (it's hats)."""
        r, w = root.casefold(), word.casefold()
        if r == w:
            return True
        sibilant = r.endswith(("s", "x", "z", "ch", "sh", "o"))
        forms = {r + "es" if sibilant else r + "s", r + "ed" if not r.endswith("e") else r + "d",
                 r + "ing" if not r.endswith("e") or r.endswith("ee") else r[:-1] + "ing", r + "er", r + "est"}
        if r.endswith("y") and len(r) > 2 and r[-2] not in "aeiou":
            forms |= {r[:-1] + "ies", r[:-1] + "ied", r[:-1] + "ier", r[:-1] + "iest"}
        if len(r) >= 3 and r[-1] not in "aeiouwxy" and r[-2] in "aeiou" and r[-3] not in "aeiou":
            forms |= {r + r[-1] + "ed", r + r[-1] + "ing", r + r[-1] + "er", r + r[-1] + "est"}
        return w in forms

    def _lemma_order(self, low: str):
        return lambda c: (0 if str(c["lemma"]).casefold() == low else 1,
                          # irregular forms ("ran") still win when no regular one fits
                          0 if self._spells(str(c["lemma"]), low) else 1,
                          0 if str(c["lemma"])[:1].islower() else 1,
                          str(c["lemma"]))

    def lemma(self, token: str, *, prefer_pos: Optional[str] = None) -> str:
        """Best lemma for a token from OEWN/Morphy; fall back to surface lower."""
        low = token.lower()
        cands = self._lemma_candidates(low)
        if prefer_pos:
            preferred = [c for c in cands if c.get("pos") == prefer_pos]
            if preferred:
                # Exact word first, then a root whose regular spelling makes the
                # word, then lowercase/common over Proper-case entries.
                preferred.sort(key=self._lemma_order(low))
                return str(preferred[0]["lemma"])
        if cands:
            cands = list(cands)
            cands.sort(key=self._lemma_order(low))
            return str(cands[0]["lemma"])
        return low

    def _pos_set(self, token: str) -> Set[str]:
        return {c["pos"] for c in self._lemma_candidates(token.lower()) if c.get("pos")}

    def _has_pos(self, token: str, pos: str) -> bool:
        return pos in self._pos_set(token)

    def _predicative_complement_kind(self, token: str) -> Optional[str]:
        """Prefer OEWN primary sense POS for be-complements.

        Plastic's top OEWN sense is the material noun; adjective satellites
        (moldable) must not steal predicative kind. Round/long/heavy keep
        adjective because their top sense is a/s. Chromatic color: if OEWN
        has a satellite/head similar_to chromatic, prefer adjective so
        blue↔green compete as color (pigment noun alone would kind-mismatch
        green's adj). No material/color lemma bags — OEWN chromatic node only.
        """
        form = (token or "").strip()
        if not form:
            return None
        # Chromatic predicative reading (blue/green/red…): OEWN similar_to chromatic.
        if self._has_chromatic_adjective_sense(form):
            return "adjective"
        # Affective adjective reading (upset): OEWN may rank noun first
        # (disturbance/tool) while a/s anxiety senses are the be-complement.
        # OEWN sense_is_affective on a/s only — not a subject whitelist; materials
        # (plastic/brass) have no affective a/s and stay nominal.
        if self._has_affective_adjective_sense(form):
            return "adjective"
        senses = self._lookup(form)
        if senses:
            top = str(senses[0].get("pos") or "")
            if top == "n":
                return "nominal"
            if top in {"a", "s"}:
                return "adjective"
        pos_set = self._pos_set(form)
        if "a" in pos_set or "s" in pos_set:
            return "adjective"
        if "n" in pos_set:
            return "nominal"
        return None

    def _has_chromatic_adjective_sense(self, surface: str) -> bool:
        """True when an a/s sense is OEWN-similar to the chromatic adjective head."""
        if self._lexicon_error:
            return False
        try:
            from lexicon.oewn_offline import sense_is_chromatic_adjective
        except Exception:
            return False
        for pos in ("a", "s"):
            for sense in self._lookup(surface, pos=pos):
                if sense_is_chromatic_adjective(str(sense.get("synset_id") or "")):
                    return True
        return False

    def _has_affective_adjective_sense(self, surface: str) -> bool:
        """True when an OEWN a/s sense reaches emotion/feeling (upset, not plastic)."""
        if self._lexicon_error:
            return False
        form = (surface or "").strip()
        if not form:
            return False
        for pos in ("a", "s"):
            for sense in self._lookup(form, pos=pos):
                if sense_is_affective(
                    str(sense.get("synset_id") or ""),
                    str(sense.get("definition") or ""),
                    surface=form,
                ):
                    return True
        return False

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
        if low in _CONJUNCTIONS:
            return "conjunction", low, [], True
        if low in _SUBORDINATING:
            return "subordinator", low, [], True
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
        # Possessive "dog's" / "Matthew's" / "witches'": the owner, marking whose.
        possessive = re.fullmatch(r"([a-z]+)'s|([a-z]+s)'", low)
        if possessive:
            base = possessive.group(1) or possessive.group(2)
            base_senses = self._lookup(base, pos="n")
            base_lemma = self.lemma(base, prefer_pos="n") if base_senses else base
            return "possessive", base_lemma, base_senses, True

        senses = self._lookup(low)
        cands = self._lemma_candidates(low)
        if low in self.taught_words() and senses:
            # A word he taught her: its kinds are the kinds of what it means.
            cands = [{"lemma": low, "pos": p} for p in dict.fromkeys(str(x.get("pos")) for x in senses)]
        # Spelled differently from an acronym, it isn't that word: "Sam" (a name)
        # is not SAM (a missile), "it" is not IT. Only the way he wrote it counts.
        if not original.isupper():
            def _acronym(lemmas: Any) -> bool:
                same = [str(l) for l in lemmas or [] if str(l).casefold() == low]
                return bool(same) and all(l.isupper() and len(l) > 1 for l in same)
            senses = [x for x in senses if not _acronym(x.get("lemmas"))]
            cands = [c for c in cands if not (str(c.get("lemma") or "").isupper() and len(str(c.get("lemma") or "")) > 1)]
        # A lowercase word is not a place or person name: "nice" is not Nice, France.
        if original[:1].islower():
            proper_only = [c for c in cands if c.get("pos") == "n" and str(c["lemma"])[:1].isupper()]
            common_nouns = [c for c in cands if c.get("pos") == "n" and str(c["lemma"])[:1].islower()]
            if proper_only and not common_nouns and any(c.get("pos") != "n" for c in cands):
                cands = [c for c in cands if c.get("pos") != "n"]
                senses = [s for s in senses if s.get("pos") != "n"]
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
        # Adjectives: keep OEWN satellites (pos "s") with heads (pos "a").
        if primary_pos:
            if primary_pos == "a":
                filtered = [s for s in senses if s.get("pos") in {"a", "s"}]
            else:
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
            if t.lower() not in self._times() and t.lower() not in _NEGATION
            and t.lower() not in (getattr(self, "_how_now", None) or set())
        ]
        while raw and raw[0].lower() in _PREPOSITIONS:
            raw.pop(0)
        # "maybe she", "probably Lily": a sentence word like maybe isn't part of who.
        while len(raw) > 1 and self._pos_set(raw[0]) == {"r"}:
            raw.pop(0)
            start += 1
        kept_end = None
        if len(raw) >= 3 and raw[-1].lower() in _PREPOSITIONS \
                and "to" in [t.lower() for t in raw[:-2]] and self._has_pos(raw[-2], "v"):
            # "a lot to work on", "someone to talk to": the word after the action
            # belongs to it; it isn't left over.
            kept_end = raw[-1]
            raw = raw[:-1]
        while raw and raw[-1].lower() in _PREPOSITIONS:
            raw.pop()
        if not raw:
            return None
        if kept_end:
            raw.append(kept_end)

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
        head_senses = self._lookup(head, pos="n") or self._lookup(head)
        written = str(raw[-1]) if raw else head
        if head_lemma.isupper() and len(head_lemma) > 1 and not written.isupper():
            # "Sam" as he wrote it is not the acronym SAM.
            head_lemma = head
            head_senses = [x for x in head_senses
                           if not all(str(l).isupper() for l in x.get("lemmas") or []
                                      if str(l).casefold() == head)]
        concept_surface = " ".join(low[:-1] + [head_lemma]) if len(low) > 1 else head_lemma

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
            and t.lower() not in self._times()
            and t.lower() not in _WH
        ]
        raw_before = [
            t
            for t in tokens[:idx]
            if not re.fullmatch(r"[.!?,;:]", t)
        ]
        # Sole preverbal demonstrative/pronoun = subject NP ("That looks awful"),
        # not a determiner attaching to the verb. Do not noun-penalize the verb.
        # "her" (like me/him/us/them) is never a subject: "her dog" is the dog
        # that belongs to her, so "dog" is a noun here, not the verb.
        sole_deictic_subject = (
            len(raw_before) == 1
            and raw_before[0].lower() in (_DEMONSTRATIVES | _PRONOUNS | _WH)
            and raw_before[0].lower() not in {"me", "him", "her", "us", "them"}
            # "that joke was...": a word followed by is/was is what "that" points to.
            and not (raw_before[0].lower() in _DEMONSTRATIVES and idx + 1 < len(tokens)
                     and tokens[idx + 1].lower() in _AUX_RAW)
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
        # Right after a modal ("might give", "might not give", "will not send"),
        # the base form is the verb slot, even when the word also reads as a noun.
        back = idx - 1
        while back >= 0 and tokens[back].lower() in _NEGATION:
            back -= 1
        if back >= 0 and tokens[back].lower() in _MODALS and "v" in pos_set:
            score += 6
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
            | set(self._times())
            | _CONJUNCTIONS  # joining words are never the action ("my sister and I went")
            | _SUBORDINATING
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

        lexical_now = getattr(self, "_lexical_now", None) or []
        if len(lexical_now) == len(tokens):
            for idx, entry in enumerate(lexical_now):
                if entry.get("measure"):
                    # "Max is 10 years old": what's said of him is "old", by 10 years.
                    return idx, str(entry.get("lemma") or tokens[idx]).lower(), False, True
        known_candidates: List[Tuple[int, str, int]] = []
        hinted = {i: e.get("kind") for i, e in enumerate(lexical_now)
                  if str(e.get("read_as") or "").startswith("read again")} if len(lexical_now) == len(tokens) else {}
        owning = {i for i, e in enumerate(lexical_now) if e.get("read_as") == "have: owning"} \
            if len(lexical_now) == len(tokens) else set()
        naming = {i for i, e in enumerate(lexical_now) if e.get("kind") == "participle"} \
            if len(lexical_now) == len(tokens) else set()
        for idx, token in enumerate(tokens):
            low = token.lower()
            if idx in owning:
                known_candidates.append((idx, "have", 8))  # "I have a dog": owning is the action
                continue
            if idx in naming:
                continue  # "a dog named Pixel": what it's called, not what's done
            if low in closed:
                continue
            if hinted.get(idx) == "noun":
                continue  # read again: Reasoning says this is a thing, not the action
            if hinted.get(idx) == "verb":
                known_candidates.append((idx, self.lemma(token, prefer_pos="v"), 9))
                continue
            if not self._has_pos(token, "v"):
                continue
            if idx > 0 and (lows[idx - 1] in _NUMBER_WORDS or lows[idx - 1] in _QUANTIFIERS
                            or re.fullmatch(r"\d+", lows[idx - 1])):
                continue  # "two cats": a thing after a number, never the verb
            lemma = self.lemma(token, prefer_pos="v")
            if lemma in _AUX_LEMMAS:
                continue
            score = self._verb_score(token, idx, tokens)
            if score >= 3:
                known_candidates.append((idx, lemma, score))

        if not known_candidates:
            # "Magnus has a sword": have is the main verb when no verb follows
            # it (as a helper it comes before one: "has gone").
            for idx, low in enumerate(lows):
                if low not in {"have", "has", "had"}:
                    continue
                nxt = idx + 1
                while nxt < len(tokens) and lows[nxt] in _NEGATION:
                    nxt += 1
                if nxt < len(tokens) and lows[nxt] not in _DETERMINERS and self._has_pos(tokens[nxt], "v") \
                        and not self._has_pos(tokens[nxt], "n"):
                    continue
                if nxt < len(tokens) and not re.fullmatch(r"[.!?,;:]", tokens[nxt]):
                    known_candidates.append((idx, "have", 5))
                    break

        known = None
        if known_candidates:
            # Highest verb score wins (looks=4 beats weather=3 in
            # "Denver weather looks awful"). Tie-break: later token
            # (predicate after compound subject), then earlier.
            clear = [c for c in known_candidates if c[2] >= 5]
            pool = clear if clear else known_candidates
            known = max(pool, key=lambda c: (c[2], c[0]))


        # Right after the subject ("my sister", "the kids", "Tom") comes its
        # verb; a later verb-looking word is what it acts on ("likes cats",
        # "play games", "drives trucks").
        after_subject = self._verb_after_subject(tokens)
        if after_subject is not None and (known is None or known[0] < after_subject or (
                known[0] > after_subject and self._has_pos(tokens[known[0]], "n"))):
            # (A "verb" picked inside the subject, like "Cleo", isn't one.)
            known = (after_subject, self.lemma(tokens[after_subject], prefer_pos="v"), 5)

        # Copula: be-AUX + complement (adjective OR nominal).
        # "Matthew is happy" / "The gasket is aluminum" / "No, the gasket is steel".
        # Prefer this over noun-with-accidental-verb-reading as the complement itself.
        be_complement = None  # (idx, lemma, kind) kind in {"adjective","nominal"}
        for idx, token in enumerate(lows):
            if token not in _AUX_RAW or self.lemma(token, prefer_pos="v") != "be":
                continue
            next_idx = idx + 1
            while next_idx < len(tokens) - 1 and (lows[next_idx] in _NEGATION or self._pos_set(tokens[next_idx]) == {"r"} or ("r" in self._pos_set(tokens[next_idx]) and self._has_pos(tokens[next_idx + 1], "a"))):  # "is not", "is probably", "is very sick"
                next_idx += 1
            if next_idx >= len(tokens):
                continue
            while next_idx < len(tokens) - 1 and re.fullmatch(r"[a-z]+'s|[a-z]+s'", lows[next_idx]):
                next_idx += 1  # "is Matthew's wife": the complement is "wife"
            # "is a knight" / "is an animal" / "is the one": the complement is
            # the word after the article.
            while next_idx < len(tokens) - 1 and lows[next_idx] in (_DETERMINERS - _DEMONSTRATIVES):
                next_idx += 1  # "is my wife": the complement is "wife"
            cand = tokens[next_idx]
            cand_low = cand.lower()
            if cand_low in _PRONOUNS or cand_low in _DETERMINERS:
                continue
            if cand_low in _PREPOSITIONS:
                # "The switch is on/off": OEWN a/s operational reading beats prep.
                prep_senses = self._lookup(cand_low)
                if not any(str(s.get("pos") or "") in {"a", "s"} for s in prep_senses):
                    continue
            if re.fullmatch(r"[.!?,;:]", cand):
                continue
            kind = self._predicative_complement_kind(cand)
            if kind == "adjective":
                lemma = self.lemma(cand, prefer_pos="a")
                be_complement = (next_idx, lemma, "adjective")
                break
            if kind == "nominal":
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
            now = getattr(self, "_lexical_now", None) or []
            if c_idx < len(now) and now[c_idx].get("kind") == "verb" \
                    and str(now[c_idx].get("surface") or "").endswith("ing"):
                # "she is working", "you are getting better": what's going on is
                # the action, not a description after "is".
                return c_idx, self.lemma(tokens[c_idx], prefer_pos="v"), False, True
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

        # Unknown earlier than known (Steve florbed the dog) wins, but a name is
        # never the verb ("where does Cleo live?").
        lexical_now = getattr(self, "_lexical_now", None) or []
        if unknown is not None and unknown[0] < len(lexical_now) \
                and lexical_now[unknown[0]].get("kind") == "proper_noun":
            unknown = None
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
            if low in self._times() or re.fullmatch(r"[.!?;]", tokens[idx]):
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
        # Prepositional dative: "gave Jester to Matthew" -> recipient after "to".
        lows_span = [t.lower() for t in tokens[start:end]]
        if "to" in lows_span:
            to_idx = start + lows_span.index("to")
            if start < to_idx < end - 1:
                return (to_idx + 1, end), (start, to_idx)
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
                if h in self._times() or h in self._DEGREE_ADVERBS:
                    return None
                if not allow_emotion and surface_is_affective(h):
                    return None
                return h
            concept = (mention.concept_surface or mention.surface or "").strip()
            parts = [p for p in concept.lower().split() if p.isalpha()]
            parts = [p for p in parts if p not in self._times() and p not in self._DEGREE_ADVERBS]
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
            if token in self._times():
                q.update(self._times()[token])
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
            and first not in (getattr(self, "_hinted_things", None) or set())  # read again: it's who, not a command
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
        predicative: bool = False,
    ) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        surf = (surface or "").strip()
        bag = [s for s in (senses or []) if isinstance(s, dict)]
        if predicative:
            # Selected sense for the clause — not any-sense-in-the-bag.
            # No subject whitelist: top a/s + physical-attribute demotion.
            for sense in selected_affective_senses(bag, surface=surf):
                hits.append(
                    {
                        "synset_id": sense.get("synset_id"),
                        "definition": sense.get("definition"),
                    }
                )
            return hits
        for sense in bag:
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
        # Affect evidence requires a real OEWN sense that reaches emotion/feeling.
        # Do NOT stamp synset_id=None via surface_is_affective lemma→verb bridges
        # (that made long/yearn and heavy's unused senses mark affect_share on
        # object topics). Hungry/angry/worried still hit via actual sense ids.
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
                predicative_adjective.get("senses") or [],
                surface=adj_surf,
                predicative=True,
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
        # Adjective / adverb tokens only (predicative or modifiers) — not bare verbs/nouns.
        # Adjectives use predicative sense selection so heavy/cold psych senses do not
        # override a physical top reading when the token is the clause complement.
        for entry in lexical:
            if entry.get("kind") not in {"adjective", "adverb"}:
                continue
            tok_surf = str(entry.get("surface") or entry.get("lemma") or "")
            for hit in self._affect_from_senses(
                entry.get("senses") or [],
                surface=tok_surf,
                predicative=(entry.get("kind") == "adjective"),
            ):
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

    _READINGS_KEPT = 256

    def analyze(self, text: str, hints: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Read a sentence. The same sentence reads the same way, so recent
        readings are kept (memory and reasoning both ask about each line).
        hints: what Reasoning says didn't make sense the first time, as
        [{"word": "dogs", "fits_better": "a thing (the doer)"}] -> read again
        with those words taken that way."""
        import copy
        if hints:
            self._hints_now = [h for h in hints if isinstance(h, dict) and h.get("word")]
            try:
                reading = self._analyze_uncached(text)
            finally:
                self._hints_now = None
            reading["read_again_with"] = [str(h.get("word")) for h in hints if isinstance(h, dict)]
            return reading
        key = str(text or "").strip()
        cache = self.__dict__.setdefault("_readings", {})
        if key in cache:
            return copy.deepcopy(cache[key])
        reading = self._analyze_uncached(text)
        cache[key] = copy.deepcopy(reading)
        if len(cache) > self._READINGS_KEPT:
            cache.pop(next(iter(cache)))
        return reading

    @staticmethod
    def _can_stand_alone(verb: str) -> bool:
        """Does any dictionary frame of this verb take nothing after it
        ("Somebody ----s")? "run" does; "amaze" always amazes somebody."""
        try:
            from lexicon.oewn_offline import get_wordnet
            for sense in get_wordnet().senses(verb, pos="v"):
                if any(str(f).strip().endswith(("----s", "----ing")) for f in sense.frames()):
                    return True
        except Exception:
            return True  # can't tell: keep the verb reading
        return False

    _SUBJECT_FORMS = ("i", "you", "he", "she", "we", "they")

    def _times(self) -> Dict[str, Dict[str, str]]:
        """Words that say when: the usual ones, and this sentence's own time
        phrase ("last time")."""
        now = getattr(self, "_time_now", None)
        return {**_TIME, **now} if now else _TIME

    def _how_after_action(self, lexical: List[Dict[str, Any]]) -> None:
        """"I didn't sleep well", "she runs fast": last, after an action that
        needs nothing after it, a word the dictionary has as an adverb says how."""
        words = [e for e in lexical if e.get("kind") != "punctuation"]
        if len(words) < 2:
            return
        verb_at = max((n for n, e in enumerate(words) if e.get("kind") == "verb"), default=None)
        if verb_at is None:
            return
        # The words at the end, after the action (and what it acts on), that the
        # dictionary has as adverbs: "so much", "well", "fast", "a lot"? (only adverbs).
        trailing = []
        for e in reversed(words[verb_at + 1:]):
            adverb = [x for x in self._lookup(e["surface"]) if x.get("pos") == "r"
                      and str(e["surface"]).casefold() in {l.casefold() for l in x.get("lemmas") or []}]
            if not adverb or e.get("kind") not in ("noun", "adjective", "adverb"):
                break
            trailing.append((e, adverb))
        if not trailing:
            return
        first_kept = words.index(trailing[-1][0])
        acts_on = [e for e in words[verb_at + 1:first_kept] if e.get("kind") in ("noun", "pronoun", "proper_noun")]
        if not acts_on and not self._can_stand_alone(str(words[verb_at].get("lemma") or "")):
            return  # "I like fast": the word is what it acts on
        for e, adverb in trailing:
            e.update({"kind": "adverb", "lemma": e["surface"], "senses": adverb,
                      "sense_count": len(adverb), "read_as": "how, after the action"})
            self._how_now.add(str(e["surface"]).casefold())

    def _time_phrase(self, lexical: List[Dict[str, Any]]) -> None:
        """"Last time I charged it", "this morning we left": a word before a
        noun the dictionary files under time, right before who did it, says
        when, not who."""
        # At the end, after what happened: "my dog died last week".
        rest = [e for e in lexical if e.get("kind") != "punctuation"]
        if len(rest) >= 4 and rest[-1].get("kind") == "noun" and rest[-2].get("kind") in ("adjective", "determiner", "noun") \
                and any(e.get("kind") == "verb" for e in rest[:-2]) and str(rest[-2].get("surface")).casefold() not in ("a", "an", "the"):
            try:
                from lexicon.oewn_offline import get_wordnet
                senses = get_wordnet().synsets(rest[-1]["surface"], pos="n")[:3]
                timed = any(x.lexfile() == "noun.time" for x in senses)
            except Exception:
                timed = False
            if timed:
                text = f"{rest[-2]['surface']} {rest[-1]['surface']}"
                for entry in (rest[-2], rest[-1]):
                    entry.update({"kind": "temporal", "read_as": "when", "time_text": text})
                    self._time_now[str(entry["surface"]).casefold()] = {"event_time_text": text}
        for idx in range(len(lexical) - 2):
            first, noun, after = lexical[idx], lexical[idx + 1], lexical[idx + 2]
            if idx and lexical[idx - 1].get("kind") not in ("punctuation", "conjunction"):
                continue
            if first.get("kind") not in ("adjective", "determiner", "noun") or noun.get("kind") != "noun":
                continue
            if after.get("kind") not in ("pronoun", "proper_noun") and str(after.get("surface")) != "," \
                    and not (idx == 0 and after.get("kind") in ("determiner", "possessive")):
                continue
            try:
                from lexicon.oewn_offline import get_wordnet
                timed = any(x.lexfile() == "noun.time" for x in get_wordnet().synsets(noun["surface"], pos="n"))
            except Exception:
                timed = False
            if timed:
                text = f"{first['surface']} {noun['surface']}"
                for entry in (first, noun):
                    entry.update({"kind": "temporal", "read_as": "when", "time_text": text})
                    self._time_now[str(entry["surface"]).casefold()] = {"event_time_text": text}

    def _take_hints(self, lexical: List[Dict[str, Any]]) -> None:
        """Reading again: take the words Reasoning pointed out the way it says
        they fit better ("a thing" or "an action"), if the dictionary has them so."""
        self._hinted_things = set()
        for hint in getattr(self, "_hints_now", None) or []:
            word = str(hint.get("word") or "").casefold()
            better = str(hint.get("fits_better") or "")
            pos, kind = ("n", "noun") if "thing" in better else ("v", "verb") if "action" in better else ("", "")
            if pos == "n":
                self._hinted_things.add(word)
            if not pos:
                continue
            for entry in lexical:
                if str(entry.get("surface") or "").casefold() != word:
                    continue
                senses = self._lookup(entry["surface"], pos=pos)
                if senses:
                    entry.update({"kind": kind, "lemma": self.lemma(entry["surface"], prefer_pos=pos),
                                  "senses": senses, "sense_count": len(senses), "read_as": "read again: " + better})

    def _action_after_subject(self, lexical: List[Dict[str, Any]]) -> None:
        """Right after a subject ("I", "you", "they"...), a word the dictionary
        also knows as a verb is the action: "I hate you", "they love music".
        (A word that can't be a verb keeps its reading.)

        "have" with a thing right after it is owning, not a helper word:
        "I have a dog", "she has two cats". And a word like "named"/"called"
        between a thing and a name says what the thing is called ("a dog named
        Pixel"); it isn't what anyone does."""
        for idx, entry in enumerate(lexical[:-1]):
            nxt = lexical[idx + 1]
            if entry.get("kind") == "auxiliary" and str(entry.get("lemma")) == "have" \
                    and nxt.get("kind") in ("determiner", "noun", "number", "adjective", "proper_noun"):
                entry.update({"kind": "verb", "read_as": "have: owning"})
        for idx, entry in enumerate(lexical[1:-1], start=1):
            before, nxt = lexical[idx - 1], lexical[idx + 1]
            if entry.get("kind") == "verb" and before.get("kind") == "noun" and nxt.get("kind") == "proper_noun" \
                    and str(entry.get("surface") or "").casefold() != str(entry.get("lemma") or "").casefold() \
                    and self._names_something(str(entry.get("lemma") or "")):
                entry.update({"kind": "participle", "read_as": "says what the thing before it is called",
                              "names": True})
        for idx, entry in enumerate(lexical):
            if idx == 0 or entry.get("kind") != "noun":
                continue
            before = lexical[idx - 1]
            if before.get("kind") != "pronoun" or str(before.get("lemma")) not in self._SUBJECT_FORMS:
                continue
            if idx >= 2 and lexical[idx - 2].get("kind") in ("verb", "preposition", "auxiliary"):
                continue  # "I told you stories": "you" is not the subject here
            verb = [s for s in self._lookup(entry["surface"], pos="v")]
            if not verb:
                continue
            entry.update({"kind": "verb", "lemma": self.lemma(entry["surface"], prefer_pos="v"),
                          "senses": verb, "sense_count": len(verb), "read_as": "action after its subject"})

    def _names_something(self, verb: str) -> bool:
        """"name", "call", "dub": the dictionary files these with "name" as
        what they do (giving or having a name)."""
        if verb.casefold() == "name":
            return True
        try:
            from lexicon.oewn_offline import get_wordnet
            for x in list(get_wordnet().synsets(verb, pos="v"))[:3]:
                if "name" in {str(l).casefold() for l in x.lemmas()}:
                    return True
        except Exception:
            return False
        return False

    def _verb_after_subject(self, tokens: Sequence[str]) -> Optional[int]:
        """Index of the verb in a sentence that opens with its subject ("my
        sister likes cats", "the kids watch movies", "Tom drives trucks").
        The verb agrees with the subject: one sister likes, many kids watch."""
        lexical = getattr(self, "_lexical_now", None) or []
        if len(lexical) != len(tokens):
            return None
        if len(lexical) > 2 and lexical[0].get("kind") == "pronoun" \
                and str(lexical[0].get("lemma")) in self._SUBJECT_FORMS and lexical[1].get("kind") == "verb":
            return 1  # "I yeet rocks": right after "I" comes what I do; "rocks" is what
        # "I don't like spiders" / "she didn't go": after do (and not) comes the verb.
        for i, entry in enumerate(lexical[:-1]):
            if entry.get("kind") == "auxiliary" and str(entry.get("lemma")) == "do" and i > 0 \
                    and lexical[i - 1].get("kind") in ("pronoun", "noun", "proper_noun"):
                j = i + 1
                while j < len(lexical) and lexical[j].get("kind") == "negation":
                    j += 1
                if j < len(lexical) and self._has_pos(tokens[j], "v"):
                    return j
        idx = 0
        helped = False  # "what does my sister like?": after do/does/can the verb is plain
        while idx < len(lexical) and lexical[idx].get("kind") in ("wh", "auxiliary", "modal"):
            if lexical[idx].get("kind") == "auxiliary" and str(lexical[idx].get("lemma")) == "be":
                return None  # "is my dog...": no verb of this kind follows
            helped = True
            idx += 1
        opened = idx
        if helped and idx < len(lexical) - 1 and lexical[idx].get("kind") == "pronoun":
            # "do I hate dogs?", "can you swim?": after the helper and its subject, the verb.
            if self._has_pos(tokens[idx + 1], "v"):
                return idx + 1
            return None
        while idx < len(lexical) and lexical[idx].get("kind") in ("determiner", "possessive"):
            idx += 1
        if idx == opened and not (idx < len(lexical) and lexical[idx].get("kind") == "proper_noun"):
            return None  # no "my/the" and no name: not this shape
        while idx < len(lexical) and lexical[idx].get("kind") == "adjective":
            idx += 1
        start = idx
        group = False  # "Tom and Ben", "my sister and I": more than one doing it
        for pos in range(start + 1, len(lexical)):
            word, before = tokens[pos].lower(), tokens[pos - 1].lower()
            if word == "and" and pos + 1 < len(lexical) and lexical[pos + 1].get("kind") in (
                    "pronoun", "proper_noun", "determiner", "possessive", "noun"):
                group = True
                continue
            if group and lexical[pos].get("kind") in ("pronoun", "proper_noun", "determiner", "possessive"):
                continue
            if lexical[pos].get("kind") in ("auxiliary", "modal", "preposition", "punctuation",
                                            "conjunction", "negation", "wh"):
                return None
            if group and self._has_pos(tokens[pos], "v") and lexical[pos - 1].get("kind") in (
                    "pronoun", "proper_noun", "noun") and (not word.endswith("s") or word.endswith("ss")):
                return pos  # more than one: "Tom and Ben play"
            if not self._has_pos(tokens[pos], "v") or not self._has_pos(tokens[pos - 1], "n") \
                    and lexical[pos - 1].get("kind") != "proper_noun":
                continue
            many = before.endswith("s") and not before.endswith("ss") and self.lemma(before, prefer_pos="n") != before
            agrees = (word.endswith(("s", "ed")) and not many) or (many and not word.endswith("s")) \
                or word.endswith("ed") or (helped and self.lemma(word, prefer_pos="v") == word)
            if agrees:
                return pos
        return None

    # How sure the speaker is, from the dictionary's senses of the words that
    # say so: "maybe/perhaps/possibly" (by chance), "probably/likely".
    _UNSURE_SENSES = {"oewn-00301501-r": 0.4, "oewn-00139421-r": 0.7}

    def _certainty(self, lexical: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for entry in lexical:
            for sense in entry.get("senses") or []:
                sure = self._UNSURE_SENSES.get(str(sense.get("synset_id") or ""))
                if sure is not None:
                    return {"word": entry.get("surface"), "sure": sure}
        return None

    def _tense(self, lexical: List[Dict[str, Any]], verb_idx: Optional[int]) -> Optional[str]:
        """When it happens, from the grammar: "will" -> future; "did", "was",
        or a verb in its past form ("went", "chased") -> past."""
        for entry in lexical:
            surface = str(entry.get("surface") or "")
            if entry.get("kind") == "modal" and surface in ("will", "shall", "'ll"):
                return "future"
            if entry.get("kind") == "auxiliary" and surface in ("did", "was", "were", "had"):
                return "past"
        if isinstance(verb_idx, int) and 0 <= verb_idx < len(lexical):
            entry = lexical[verb_idx]
            surface, lemma = str(entry.get("surface") or ""), str(entry.get("lemma") or "")
            helper_now = any(str(e.get("surface")) in ("is", "are", "am", "has", "have")
                             for e in lexical[:verb_idx] if e.get("kind") == "auxiliary")
            if entry.get("kind") == "verb" and surface != lemma and not surface.endswith(("s", "ing")) \
                    and not helper_now:  # "is named", "has gone": not the past
                return "past"
        return None

    def _thing_after_number(self, lexical: List[Dict[str, Any]]) -> None:
        """After a number ("two cats", "3 dogs") comes a thing, not a verb."""
        for idx in range(1, len(lexical)):
            entry, before = lexical[idx], lexical[idx - 1]
            counting = before.get("kind") == "number" or str(before.get("surface")) in _QUANTIFIERS
            if counting and entry.get("kind") in ("verb", "adjective"):
                nouns = self._lookup(entry["surface"], pos="n")
                if nouns:
                    entry.update({"kind": "noun", "lemma": self.lemma(entry["surface"], prefer_pos="n"),
                                  "senses": nouns, "read_as": "a thing after a number"})

    def _describing_before_noun(self, lexical: List[Dict[str, Any]]) -> None:
        """Between "the/a/my" and a noun, a word the dictionary also knows as an
        adjective describes that noun: "the old dog", "a new car"."""
        for idx in range(1, len(lexical) - 1):
            entry, before, after = lexical[idx], lexical[idx - 1], lexical[idx + 1]
            if entry.get("kind") not in ("noun", "verb") or before.get("kind") not in ("determiner", "possessive"):
                continue
            if after.get("kind") not in ("noun", "proper_noun"):
                continue
            adjective = [x for x in self._lookup(entry["surface"]) if x.get("pos") in ("a", "s")]
            if adjective:
                entry.update({"kind": "adjective", "lemma": entry["surface"], "senses": adjective,
                              "sense_count": len(adjective), "read_as": "describing the noun after it"})

    def _degree_before_describing(self, lexical: List[Dict[str, Any]]) -> None:
        """After "is/are", a word that can be an adverb followed by one that can
        be an adjective is a degree word and what it describes: "very kind",
        "really tall" (not "a very" of a "kind")."""
        for idx in range(1, len(lexical) - 1):
            before, entry, after = lexical[idx - 1], lexical[idx], lexical[idx + 1]
            if before.get("kind") != "auxiliary" or before.get("lemma") != "be":
                continue
            if not any(x.get("pos") == "r" for x in self._lookup(entry["surface"])):
                continue
            adjective = [x for x in self._lookup(after["surface"]) if x.get("pos") in ("a", "s")]
            if not adjective or (idx + 2 < len(lexical) and lexical[idx + 2].get("kind") in ("noun", "proper_noun")):
                continue
            entry.update({"kind": "adverb", "lemma": entry["surface"],
                          "senses": [x for x in self._lookup(entry["surface"]) if x.get("pos") == "r"]})
            after.update({"kind": "adjective", "lemma": after["surface"], "senses": adjective,
                          "sense_count": len(adjective), "read_as": "describing after a degree word"})

    def _describing_after_be(self, lexical: List[Dict[str, Any]]) -> None:
        """Right after "is/are/was", a word the dictionary also knows as an
        adjective, with nothing after it for it to act on, describes the
        subject: "you are amazing", "he is boring", "you are stupid".
        ("you are amazing me" keeps the verb: it has something to act on.)
        With a measure: "Max is 10 years old", "the wall is 6 feet tall": the
        last word describes, and how much ("10 years") goes with it."""
        for idx, entry in enumerate(lexical[:-2]):
            if idx == 0 or entry.get("kind") != "number":
                continue
            before, unit, word = lexical[idx - 1], lexical[idx + 1], lexical[idx + 2]
            if before.get("kind") != "auxiliary" or before.get("lemma") != "be" or unit.get("kind") != "noun":
                continue
            if idx + 3 < len(lexical) and lexical[idx + 3].get("kind") not in ("punctuation",):
                continue
            adjective = [x for x in self._lookup(word["surface"]) if x.get("pos") in ("a", "s")]
            if adjective:
                word.update({"kind": "adjective", "lemma": word["surface"], "senses": adjective,
                             "sense_count": len(adjective), "read_as": "describing after be, with a measure",
                             "measure": f"{entry['surface']} {unit['surface']}"})
                unit["read_as"] = "measure"
        for idx, entry in enumerate(lexical):
            if idx == 0 or entry.get("kind") not in ("verb", "noun"):
                continue
            before = lexical[idx - 1]
            if before.get("kind") in ("pronoun", "proper_noun", "noun") and idx >= 2 \
                    and lexical[idx - 2].get("kind") == "auxiliary" and lexical[idx - 2].get("lemma") == "be" \
                    and (idx == 2 or lexical[idx - 3].get("kind") in ("wh", "punctuation")):
                before = lexical[idx - 2]  # "are you tired?", "why am I tired?": asked the other way round
            if before.get("kind") != "auxiliary" or before.get("lemma") != "be":
                continue
            after = lexical[idx + 1] if idx + 1 < len(lexical) else None
            if after is not None and after.get("kind") in (
                    "pronoun", "determiner", "noun", "proper_noun", "possessive", "number"):
                continue
            adjective = [s for s in self._lookup(entry["surface"]) if s.get("pos") in ("a", "s")]
            if not adjective:
                continue
            if entry.get("kind") == "verb" and str(entry["surface"]).endswith("ing") \
                    and self._can_stand_alone(str(entry.get("lemma") or "")):
                continue  # "I am running": an action that needs nothing to act on
            entry.update({"kind": "adjective", "lemma": entry["surface"], "senses": adjective,
                          "sense_count": len(adjective), "read_as": "describing after be"})

    _phrase_cache: Dict[str, List[Dict[str, Any]]] = {}

    def _phrase_senses(self, phrase: str) -> List[Dict[str, Any]]:
        """The dictionary's meanings of a set phrase ("give up", "piece of
        cake", "kick the bucket", "by the way"), if it has the phrase."""
        cache = LanguageComprehensionEngine._phrase_cache
        if phrase in cache:
            return cache[phrase]
        found: List[Dict[str, Any]] = []
        try:
            from lexicon.oewn_offline import get_wordnet
            for x in get_wordnet().synsets(phrase):
                found.append({"synset_id": x.id, "pos": x.pos, "definition": str(x.definition() or ""),
                              "lemmas": [str(l) for l in x.lemmas()]})
        except Exception:
            found = []
        cache[phrase] = found
        return found

    def _set_phrases(self, lexical: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Words that go together as one meaning the dictionary has: "gave up"
        (give up), "work on", "a piece of cake", "by the way". The first word
        of a phrase that acts is matched by its base form ("gave" -> give)."""
        phrases: List[Dict[str, Any]] = []
        i = 0
        while i < len(lexical):
            found = None
            for size in (4, 3, 2):
                window = lexical[i:i + size]
                if len(window) < size or any(e.get("kind") in ("punctuation", "pronoun", "proper_noun")
                                             for e in window[1:]):
                    continue
                words = [str(e.get("surface") or "").casefold() for e in window]
                if not all(w.replace("'", "").isalpha() for w in words):
                    continue
                for first in dict.fromkeys([words[0], self.lemma(words[0], prefer_pos="v"),
                                            self.lemma(words[0], prefer_pos="n")]):
                    phrase = " ".join([first] + words[1:])
                    senses = self._phrase_senses(phrase)
                    if senses:
                        found = (size, phrase, senses)
                        break
                if found:
                    break
            if not found:
                i += 1
                continue
            size, phrase, senses = found
            pos = senses[0].get("pos")
            after = lexical[i + size] if i + size < len(lexical) else None
            if pos == "v" and after is not None and after.get("kind") in (
                    "determiner", "possessive", "noun", "proper_noun", "pronoun", "number"):
                # "lived in Ohio": "live in" (living where one works) takes nothing
                # after it, so here it's "live" + "in Ohio". "work on cars" takes something.
                try:
                    from lexicon.oewn_offline import get_wordnet
                    frames = [str(f) for x in senses for sense in get_wordnet().synset(x["synset_id"]).senses()
                              for f in sense.frames()]
                except Exception:
                    frames = []
                if frames and not any("something" in f or "somebody" in f.split("----", 1)[-1] for f in frames):
                    i += 1
                    continue
            phrases.append({"phrase": phrase, "start": i, "end": i + size, "pos": pos,
                            "meaning": senses[0].get("definition"), "senses": senses})
            lexical[i]["phrase"] = phrase
            lexical[i]["phrase_senses"] = senses
            for e in lexical[i + 1:i + size]:
                e["in_phrase"] = phrase
            i += size
        return phrases

    def _action_in_progress(self, lexical: List[Dict[str, Any]]) -> None:
        """After "is/are/was", an -ing word the dictionary knows as a verb is
        what's going on: "you are getting better", "she is working". (One that
        describes, like "amazing", was already read as describing.)"""
        for idx in range(1, len(lexical)):
            entry, before = lexical[idx], lexical[idx - 1]
            if before.get("kind") != "auxiliary" or before.get("lemma") != "be":
                continue
            surface = str(entry.get("surface") or "")
            if entry.get("kind") not in ("noun", "unknown") or not surface.endswith("ing"):
                continue
            verb = self._lookup(surface, pos="v")
            if verb:
                entry.update({"kind": "verb", "lemma": self.lemma(surface, prefer_pos="v"), "senses": verb,
                              "sense_count": len(verb), "read_as": "what is going on"})

    def _action_after_to(self, lexical: List[Dict[str, Any]]) -> None:
        """After "to", a word that is an action: "a lot to work on", "something
        to do", "I want to swim". It's an action when something follows it that
        an action takes (on, a thing, someone), or when the dictionary knows it
        more as an action than a thing ("to swim"; "to school" stays a place)."""
        for idx in range(1, len(lexical)):
            entry, before = lexical[idx], lexical[idx - 1]
            if str(before.get("surface")) != "to" or entry.get("kind") not in ("noun", "unknown"):
                continue
            surface = str(entry.get("surface") or "")
            verb, noun = self._lookup(surface, pos="v"), self._lookup(surface, pos="n")
            if not verb:
                continue
            after = lexical[idx + 1] if idx + 1 < len(lexical) else None
            takes_something = after is not None and after.get("kind") in (
                "preposition", "determiner", "possessive", "pronoun", "proper_noun")
            if takes_something or len(verb) > len(noun):
                entry.update({"kind": "verb", "lemma": self.lemma(surface, prefer_pos="v"), "senses": verb,
                              "sense_count": len(verb), "read_as": "an action after to"})

    _structure_reader = None

    def _structure(self):
        """Language's own small pattern reader (language_structure.py), with
        the sentence shapes she has learned kept in her runtime folder."""
        if LanguageComprehensionEngine._structure_reader is None:
            from language_structure import SentenceStructure, ShapeMemory
            try:
                from runtime_paths import runtime_file
                path = runtime_file("sentence_shapes.json")
            except Exception:
                path = None
            LanguageComprehensionEngine._structure_reader = SentenceStructure(ShapeMemory(path))
        return LanguageComprehensionEngine._structure_reader

    def _statements(self, lexical: List[Dict[str, Any]], original: str,
                    surfaces: Optional[Sequence[str]]) -> Dict[str, Any]:
        """The simple statements in what was said, and how they're linked."""
        from language_structure import words_of
        sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", original.strip()) if x.strip()]
        if len(sentences) > 1:
            # Separate sentences ("I am tired. I worked all day.") are separate statements.
            parts: List[str] = []
            for sentence in sentences:
                parts += self.analyze(sentence).get("parts") or [sentence.rstrip(".!")]
            return {"parts": parts, "joins": [""] * (len(parts) - 1), "links": [], "frames": [], "opener": None,
                    "positions": [], "single": ""}
        read = self._structure().read([e for e in lexical if not (
            e.get("kind") == "punctuation" and str(e.get("surface")) in (".", "!", "?"))])
        pieces = read["pieces"]
        texts = [words_of(p, surfaces) for p in pieces]
        links = [l for l in read["links"] if l.get("from") is not None and l.get("to") is not None]
        joins = []
        for i in range(len(texts) - 1):
            link = next((l for l in links if l["from"] == i and l["to"] == i + 1), None) \
                or next((l for l in links if l["to"] == i + 1), None)
            joins.append(str((link or {}).get("word") or ""))
        positions = [[e.get("index") for e in p["words"]] for p in pieces]
        return {"parts": texts if len(texts) > 1 else [], "joins": joins if len(texts) > 1 else [],
                "positions": positions if len(texts) > 1 else [],
                "links": [{**l, "thing": l.get("thing")} for l in links],
                "frames": read["frames"], "opener": read["opener"], "single": texts[0] if texts else ""}

    def _whole_from_parts(self, reading: Dict[str, Any], positions: List[List[Any]]) -> None:
        """A sentence of several statements, read as the statements it's made
        of: each statement's clause and the things in it, placed at their own
        words in the whole sentence. The first statement is the main one."""
        clauses: List[Dict[str, Any]] = []
        mentions: List[Dict[str, Any]] = []
        main: Dict[str, Any] = {}
        for n, part in enumerate(reading.get("parts") or []):
            inner = self.analyze(part)
            where = positions[n] if n < len(positions) else []
            words = [t for t in inner.get("tokens") or []]
            place = {k: where[k] for k in range(len(words))} if len(words) == len(where) else {}
            rename = {}
            for m in inner.get("mentions") or []:
                m = dict(m)
                old_id = m.get("mention_id")
                m["mention_id"] = f"p{n + 1}{old_id}"
                rename[old_id] = m["mention_id"]
                start, end = m.get("start"), m.get("end")
                if isinstance(start, int) and isinstance(end, int) and start in place and (end - 1) in place:
                    m["start"], m["end"] = place[start], place[end - 1] + 1
                else:
                    m["start"], m["end"] = None, None
                m["statement"] = n
                mentions.append(m)
            for c in inner.get("clauses") or []:
                c = dict(c)
                c["roles"] = {r: rename.get(v, v) for r, v in (c.get("roles") or {}).items()}
                c["clause_id"] = f"clause_{len(clauses) + 1}"
                c["statement"] = n
                clauses.append(c)
            if n == 0:
                main = inner
        if not clauses:
            return
        reading["clauses"] = clauses
        reading["mentions"] = mentions
        # His feelings, from each statement ("... and I am so happy": happy).
        evidence = []
        for part in reading.get("parts") or []:
            for e in (self.analyze(part).get("affect") or {}).get("evidence") or []:
                if e not in evidence:
                    evidence.append(e)
        affect = dict(main.get("affect") or {})
        affect["evidence"] = evidence
        affect["present"] = bool(evidence) or any(
            (self.analyze(part).get("affect") or {}).get("present") for part in reading.get("parts") or [])
        reading["affect"] = affect
        # Words she doesn't know: the ones in its statements, not a misreading of the whole.
        unknown: List[str] = []
        for part in reading.get("parts") or []:
            for w in self.analyze(part).get("unknown_words") or []:
                if w not in unknown:
                    unknown.append(w)
        reading["unknown_words"] = unknown
        for key in ("assertion", "topic_head", "predicative_complement", "tense", "modal", "certainty"):
            reading[key] = main.get(key)
        if isinstance(reading.get("assertion"), dict):
            reading["assertion"] = dict(reading["assertion"])
        reading["statements"] = len(reading.get("parts") or [])

    def _analyze_uncached(self, text: str) -> Dict[str, Any]:
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
            if kind == "proper_noun" and senses:
                # "Ariana" may be a person, not the Tunisian city the dictionary lists.
                entry["name_senses_uncertain"] = True
                entry["ambiguous"] = True
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

        phrases = self._set_phrases(lexical)
        self._time_now = {}
        self._how_now = set()
        self._time_phrase(lexical)
        self._thing_after_number(lexical)
        self._describing_before_noun(lexical)
        self._degree_before_describing(lexical)
        self._describing_after_be(lexical)
        self._action_in_progress(lexical)
        self._action_after_to(lexical)
        self._action_after_subject(lexical)
        self._take_hints(lexical)
        self._measure_now = {i: e["measure"] for i, e in enumerate(lexical) if e.get("measure")}
        self._lexical_now = lexical
        try:
            verb_idx, predicate, passive, predicate_known = self._find_main_verb(tokens)
        finally:
            self._lexical_now = None
        if isinstance(verb_idx, int) and 0 <= verb_idx < len(lexical) and not passive \
                and lexical[verb_idx].get("kind") in ("noun", "verb") and predicate \
                and predicate != "be" and self._lookup(lexical[verb_idx]["surface"], pos="v") \
                and self.lemma(lexical[verb_idx]["surface"], prefer_pos="v") == predicate \
                and not (verb_idx > 0 and lexical[verb_idx - 1].get("kind") in ("determiner", "number")):
            # (After "a/the/my" a word is never the verb: "is a doctor".)
            # The word chosen as the verb is read as one; things after it that
            # can be nouns are what it acts on ("play games").
            verb_entry = lexical[verb_idx]
            if verb_entry.get("kind") != "verb":
                verb_entry.update({"kind": "verb", "lemma": predicate or verb_entry.get("lemma"),
                                   "senses": self._lookup(verb_entry["surface"], pos="v") or verb_entry.get("senses")})
            for entry in lexical[:verb_idx]:
                # The subject before it is a thing, not a verb ("the kids watch").
                i = lexical.index(entry)
                if entry.get("kind") == "verb" and self._lookup(entry["surface"], pos="n") \
                        and i > 0 and lexical[i - 1].get("kind") in ("determiner", "possessive", "adjective"):
                    entry.update({"kind": "noun", "lemma": self.lemma(entry["surface"], prefer_pos="n"),
                                  "senses": self._lookup(entry["surface"], pos="n")})
            rest_after = lexical[verb_idx + 1:]
            for n, entry in enumerate(rest_after):
                nxt = rest_after[n + 1] if n + 1 < len(rest_after) else {}
                if (entry.get("kind") in ("conjunction", "subordinator", "wh")
                        or str(entry.get("surface")) in (",", ";", "that", "who", "which")) \
                        and (nxt.get("kind") in ("pronoun", "determiner", "possessive", "proper_noun", "auxiliary")
                             or (nxt.get("kind") == "verb" and (str(nxt.get("surface") or "").endswith("ed")
                                                               or not self._lookup(str(nxt.get("surface") or ""), pos="n")))):
                    break  # "... and he works at a bank": the next statement has its own verb
                    # ("cats and dogs" goes on: dogs are liked too)
                if entry.get("kind") == "verb" and self._lookup(entry["surface"], pos="n"):
                    entry.update({"kind": "noun", "lemma": self.lemma(entry["surface"], prefer_pos="n"),
                                  "senses": self._lookup(entry["surface"], pos="n")})
        self._how_after_action(lexical)
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
            # A passive ("was chased by") uses be as its auxiliary; the main verb is
            # the participle, so the clause is not copular.
            copular = (not passive) and self._has_be_auxiliary_before(tokens, verb_idx) \
                and not (pred_token_kind == "verb" and tokens[verb_idx].lower().endswith("ing"))
            # ("she is working": an action going on, not "she" described as "working")
            pred_kind = (
                self._predicative_complement_kind(tokens[verb_idx]) if copular else None
            )
            is_pred_adj = bool(
                copular
                and (
                    pred_kind == "adjective"
                    or (
                        pred_kind is None
                        and (
                            pred_token_kind == "adjective"
                            or "a" in pos_at_pred
                            or "s" in pos_at_pred
                        )
                    )
                )
            )
            is_pred_nom = bool(
                copular
                and not is_pred_adj
                and (
                    pred_kind == "nominal"
                    or "n" in pos_at_pred
                    or pred_token_kind in {"noun", "unknown"}
                )
            )
            if is_pred_adj:
                predicate_senses = (
                    self._lookup_adjective_senses(tokens[verb_idx])
                    or self._lookup_adjective_senses(predicate)
                )
                predicative_adjective = {
                    "surface": tokens[verb_idx],
                    "lemma": predicate,
                    "senses": predicate_senses,
                }
                measure = (getattr(self, "_measure_now", None) or {}).get(verb_idx)
                if measure:
                    # How much goes with it, kept as he said it: "10 years old".
                    predicative_adjective.update(surface=f"{measure} {tokens[verb_idx]}",
                                                 lemma=f"{measure} {predicate}", measure=measure)
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
                skipped_prep = None
                while object_start < len(tokens) and tokens[object_start].lower() in (
                    _NEGATION | _PREPOSITIONS
                ):
                    if tokens[object_start].lower() in _PREPOSITIONS:
                        skipped_prep = tokens[object_start].lower()
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
                                "senses": self._lookup_adjective_senses(cand),
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
                        # "lives in a castle": the castle is where, not what is
                        # lived (the preposition was stepped over above).
                        place_prep = skipped_prep if skipped_prep not in (None, "about") else None
                        obj = (
                            self._noun_phrase(
                                tokens, object_start, obj_end, f"m{len(mentions)+1}"
                            )
                            if object_start < obj_end
                            else None
                        )
                        if place_prep and obj:
                            mentions.append(obj)
                            roles[f"prep_{place_prep}"] = obj.mention_id
                            qualifiers.setdefault("prepositions", []).append(
                                {"preposition": place_prep, "mention_id": obj.mention_id})
                            obj = None
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
        statements = self._statements(lexical, original,
                                      original_tokens if len(original_tokens) == len(tokens) else None)
        if (statements["opener"] or statements["frames"]) and not statements["parts"] and statements["single"] \
                and statements["single"].casefold() != original.casefold().rstrip(".!?"):
            # "No wait, my dog is named Max" / "I think that you are getting
            # better": the statement, read on its own, with what opened it
            # ("no wait") or who holds it ("I think") kept.
            inner = self.analyze(statements["single"] + ("?" if original.rstrip().endswith("?") else ""))
            inner["raw_text"] = original
            inner["opener"] = statements["opener"] or inner.get("opener")
            inner["frames"] = statements["frames"] + (inner.get("frames") or [])
            return inner
        if statements["parts"] and speech_act == "question" and not original.rstrip().endswith("?") \
                and any(l.get("kind") in ("when", "why", "on_condition", "unless", "despite")
                        for l in statements["links"]):
            # "When I was a kid I lived in Ohio": not a question; it says when.
            speech_act = self.analyze(statements["parts"][0]).get("speech_act") or "declarative"
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

        # Predicative complement structure for cross-turn correction (Conversation).
        # Nominal: roles["attribute"] mention. Adjective: predicative_adjective dict.
        # Not a cue list — grammar/roles only.
        predicative_complement: Optional[Dict[str, Any]] = None
        if predicative_nominal and roles.get("attribute"):
            attr_m = next(
                (m for m in mentions if m.mention_id == roles["attribute"]),
                None,
            )
            if attr_m is not None:
                head = (attr_m.properties or {}).get("head_lemma") or (
                    attr_m.properties or {}
                ).get("head")
                lemma_n = str(head or attr_m.concept_surface or attr_m.surface or "").strip().lower()
                senses_n = list(attr_m.senses or [])
                predicative_complement = {
                    "kind": "nominal",
                    "surface": attr_m.surface,
                    "lemma": lemma_n,
                    "mention_id": attr_m.mention_id,
                    "senses": senses_n,
                    "compete_keys": complement_compete_keys(
                        lemma_n or str(attr_m.surface or ""),
                        senses_n,
                        kind="nominal",
                    ),
                }
        elif predicative_adjective and isinstance(predicative_adjective, dict):
            lemma_a = str(
                predicative_adjective.get("lemma")
                or predicative_adjective.get("surface")
                or ""
            ).strip().lower()
            senses_a = list(predicative_adjective.get("senses") or [])
            predicative_complement = {
                "kind": "adjective",
                "surface": str(predicative_adjective.get("surface") or ""),
                "lemma": lemma_a,
                "mention_id": None,
                "senses": senses_a,
                "compete_keys": complement_compete_keys(
                    lemma_a or str(predicative_adjective.get("surface") or ""),
                    senses_a,
                    kind="adjective",
                ),
            }

        theme_mid = roles.get("theme") or roles.get("experiencer") or roles.get("patient")
        theme_m = next((m for m in mentions if m.mention_id == theme_mid), None) if theme_mid else None
        theme_is_deictic = bool(
            theme_m is not None
            and (theme_m.pronoun or theme_m.unresolved_reference)
        )
        theme_unresolved = bool(theme_m is not None and theme_m.unresolved_reference)
        theme_concept = None
        if theme_m is not None:
            theme_concept = (
                theme_m.concept_surface
                or (None if theme_m.unresolved_reference else theme_m.surface)
            )
            if isinstance(theme_concept, str):
                theme_concept = theme_concept.strip().lower() or None

        # Assertion frame: prior-proposition material Conversation compares across turns.
        # assertable when there is a predicative complement to replace (copular attrs).
        assertion = {
            "topic_head": topic_head,
            "theme_mention_id": theme_mid,
            "theme_is_deictic": theme_is_deictic,
            "theme_unresolved": theme_unresolved,
            "theme_concept": theme_concept,
            "predicate_lemma": str(predicate).lower() if predicate else None,
            "complement": predicative_complement,
            # Clause polarity only (not/never). Fronted "No," is rejection_particle,
            # not negation of this complement — Conversation must not treat it as retract.
            "polarity": (
                "negative"
                if isinstance(contrast, dict) and contrast.get("contrastive_negation")
                else "positive"
            ),
            "copular": bool(
                copular or bool(predicative_adjective) or predicative_nominal
            ),
            "assertable": bool(predicative_complement is not None),
        }

        clause = None
        if predicate:
            clause = {
                "clause_id": "clause_1",
                "predicate_surface": predicate,
                "predicate_known": predicate_known,
                "predicate_senses": predicate_senses,
                "predicative_adjective": bool(predicative_adjective),
                "predicative_nominal": predicative_nominal,
                "predicative_complement": predicative_complement,
                "copular": copular or bool(predicative_adjective) or predicative_nominal,
                "voice": "passive" if passive else "active",
                "roles": dict(roles),
                "qualifiers": qualifiers,
                "confidence": clause_confidence,
                "speech_act": speech_act,
                "clause_type": speech_act,
                "topic_head": topic_head,
                "assertion": assertion,
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

        reading = {
            "contract": "language_understanding_v1",
            "raw_text": original,
            "normalized_text": normalized,
            "tokens": lexical,
            "mentions": [m.to_public() for m in mentions],
            "clauses": [clause] if clause else [],
            "unknown_words": unknown_words,
            "certainty": self._certainty(lexical),
            "tense": self._tense(lexical, verb_idx),
            "modal": next((str(e.get("surface")) for e in lexical if e.get("kind") == "modal"
                           and str(e.get("surface")) not in ("will", "shall", "'ll")), None),
            "phrases": phrases,
            "parts": statements["parts"],
            "joins": statements["joins"],
            "links": statements["links"],
            "frames": statements["frames"],
            "opener": statements["opener"],
            "unresolved_references": unresolved_references,
            "ambiguous_words": ambiguous_words,
            "speech_act": speech_act,
            "speech_act_features": speech_features,
            "clause_type": speech_act,
            "contrast": contrast,
            "affect": affect,
            "topic_head": topic_head if verb_idx is not None else None,
            "predicative_complement": predicative_complement if verb_idx is not None else None,
            "assertion": assertion if verb_idx is not None else None,
            "confidence": overall,
            "lexicon": {
                "name": "oewn",
                "version": "2024",
                "offline": True,
                "error": self._lexicon_error,
            },
            "boundary": self.HARD_BOUNDARY,
        }
        if reading["parts"]:
            self._whole_from_parts(reading, statements.get("positions") or [])
        reading["asks_her"] = self._asks_her(reading)
        reading["asks_her_to_do"] = self._asks_her_to_do(reading)
        return reading

    def _asks_her(self, reading: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """"Tell me about my brother", "describe my sister", "explain why I am
        sad": he's asking her to say something. A request (no subject) whose
        verb the dictionary files under communicating, about something."""
        if reading.get("speech_act") == "question":
            return self._asks_what_she_knows(reading)
        if reading.get("speech_act") != "imperative":
            return None
        clause = (reading.get("clauses") or [{}])[0]
        verb = str(clause.get("predicate_surface") or "")
        try:
            from lexicon.oewn_offline import get_wordnet
            senses = list(get_wordnet().synsets(verb, pos="v"))[:3]
        except Exception:
            senses = []
        if not any(str(x.lexfile()) == "verb.communication" for x in senses):
            return None
        roles = clause.get("roles") or {}
        raw = str(reading.get("raw_text") or "")
        first_meaning = str(senses[0].definition() or "").casefold() if senses else ""
        saying = "express in words" in first_meaning or " say" in f" {first_meaning}"
        if saying and not roles.get("about") and not roles.get("recipient"):
            # "Say hello", "repeat after me: I am Monday": the words to say are
            # what comes after the verb, as he wrote them.
            words = raw.split(":", 1)[1] if ":" in raw else raw.split(None, 1)[1] if len(raw.split()) > 1 else ""
            words = words.strip().strip('"\'“”').strip()
            if words.casefold().startswith("after me"):
                words = words[8:].strip(" ,:").strip('"\'“”')
            if words:
                return {"verb": verb, "say": words}
        target = roles.get("about") or roles.get("patient") or roles.get("theme")
        mention = next((m for m in reading.get("mentions") or [] if m.get("mention_id") == target), None)
        if not mention:
            return None
        return {"verb": verb, "about": str(mention.get("surface") or "")}


    def _asks_what_she_knows(self, reading: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """"Do you remember anything about me?", "what do you know about Sam?":
        asked what she knows (a verb the dictionary files under knowing and
        thinking) about something. Same as "tell me about me"."""
        clause = (reading.get("clauses") or [{}])[0]
        roles = clause.get("roles") or {}
        mentions = {m.get("mention_id"): m for m in reading.get("mentions") or [] if isinstance(m, dict)}
        tokens = reading.get("tokens") or []
        if not any(str(t.get("surface") or "").casefold() == "you" for t in tokens):
            return None
        about_id = roles.get("about") or next((mid for r, mid in roles.items() if r == "prep_about"), None)
        if not about_id:
            # "what do you know about me": "about me" may be read as what's known.
            about_at = next((int(t.get("index", -1)) for t in tokens if str(t.get("surface") or "").casefold() == "about"), None)
            about_id = next((mid for mid, m in mentions.items() if about_at is not None and m.get("start") == about_at + 1), None)
        if not about_id:
            return None
        verb = str(clause.get("predicate_surface") or "")
        try:
            from lexicon.oewn_offline import get_wordnet
            knowing = any(x.lexfile() == "verb.cognition" for x in list(get_wordnet().synsets(verb, pos="v"))[:3])
        except Exception:
            knowing = False
        if not knowing:
            return None
        return {"verb": "tell", "about": str((mentions.get(about_id) or {}).get("surface") or "")}

    def _asks_her_to_do(self, reading: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """"Can you help me?", "could you remind me", "will you call Sam?": he
        asks her to do something. Who she'd do it for, and to what, as he said
        it (what she does about it isn't Language's to decide)."""
        tokens = [t for t in reading.get("tokens") or [] if t.get("kind") != "punctuation"]
        if len(tokens) < 3:
            return None
        first, second = tokens[0], tokens[1]
        if first.get("kind") != "modal" or str(second.get("surface") or "").casefold() != "you":
            return None  # ("do you like dogs?" asks about her, not for something)
        verb = next((t for t in tokens[2:] if t.get("kind") == "verb"), None)
        if verb is None:
            return None
        rest = [t for t in tokens if int(t.get("index", -1)) > int(verb.get("index", -1))]
        what = " ".join((str(t.get("surface") or "").capitalize() if t.get("kind") == "proper_noun"
                         else str(t.get("surface") or "")) for t in rest
                        if str(t.get("surface") or "").casefold() not in ("me", "us", "please"))
        for_him = any(str(t.get("surface") or "").casefold() in ("me", "us") for t in rest)
        if not for_him:
            return None  # "can you swim?" asks what she can do, not for something
        return {"do": str(verb.get("lemma") or verb.get("surface") or "").casefold(),
                "for_him": True, "what": what.strip()}


__all__ = ["LanguageComprehensionEngine", "LinguisticMention"]
