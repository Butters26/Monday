#!/usr/bin/env python3
"""Deterministic Language comprehension for Mercy Phase 3.

Language owns linguistic comprehension and expression. This module is the
comprehension half: it converts observed text into a linguistic meaning packet.
It does NOT decide truth, importance, emotion, memory policy, reasoning results,
or conversational intent.

The first live slice is deliberately bounded and testable. It handles a useful
core of English clauses (active/passive, common transitive/ditransitive verbs,
negation, modality, temporal markers, quantities, noun phrases, pronoun
references, and unknown words) and fails unresolved instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+(?:\.\d+)?|[^\w\s]", re.UNICODE)


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
        }


class LanguageComprehensionEngine:
    """Small deterministic English comprehension core owned by Language."""

    HARD_BOUNDARY = (
        "Language may determine lexical/syntactic/semantic language structure, "
        "but may not decide truth, memory, emotion, attention, reasoning, or intent."
    )

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

    _IRREGULAR = {
        "gave": "give",
        "given": "give",
        "bought": "buy",
        "brought": "bring",
        "sent": "send",
        "told": "tell",
        "shown": "show",
        "showed": "show",
        "made": "make",
        "took": "take",
        "taken": "take",
        "dropped": "drop",
        "chased": "chase",
        "liked": "like",
        "loved": "love",
        "hated": "hate",
        "wanted": "want",
        "preferred": "prefer",
        "failed": "fail",
        "slipped": "slip",
        "saw": "see",
        "seen": "see",
        "heard": "hear",
        "knew": "know",
        "known": "know",
        "thought": "think",
        "said": "say",
        "was": "be",
        "were": "be",
        "is": "be",
        "are": "be",
        "am": "be",
        "been": "be",
        "has": "have",
        "had": "have",
        "does": "do",
        "did": "do",
    }

    _VERBS = {
        "give", "buy", "bring", "send", "tell", "show", "hand", "lend", "offer",
        "make", "take", "drop", "chase", "like", "love", "hate", "want", "prefer",
        "fail", "slip", "see", "hear", "know", "think", "say", "be", "have", "do",
        "eat", "find", "use", "build", "open", "close", "move", "hit", "help", "call",
    }
    _DITRANSITIVE = {"give", "send", "tell", "show", "hand", "lend", "offer"}
    _EXPERIENCER = {"like", "love", "hate", "want", "prefer", "know", "see", "hear"}
    _THEME_SUBJECT = {"fail", "slip"}

    _AUX = {"be", "do", "have"}
    _RAW_AUX = {"am", "is", "are", "was", "were", "be", "been", "do", "does", "did", "have", "has", "had"}
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
    _DETERMINERS = {"a", "an", "the", "this", "that", "these", "those", "my", "your", "his", "her", "our", "their"}
    _PREPOSITIONS = {"to", "from", "with", "at", "in", "on", "into", "onto", "for", "of", "by", "about", "under", "over"}
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
    _KNOWN_NOUNS = {
        "dog", "cat", "ball", "pizza", "panel", "control", "control panel", "compressor",
        "steve", "matthew", "mercy", "user", "bank", "workshop", "car", "door", "book",
    }
    _MULTIWORD = {"control panel"}

    def normalize(self, text: str) -> str:
        raw = " ".join(str(text or "").strip().split())
        if not raw:
            return ""
        low = raw.lower()
        for contraction, expanded in sorted(self._CONTRACTIONS.items(), key=lambda item: -len(item[0])):
            low = re.sub(rf"\b{re.escape(contraction)}\b", expanded, low)
        return low

    def tokenize(self, text: str) -> List[str]:
        return _WORD_RE.findall(text)

    def lemma(self, token: str) -> str:
        low = token.lower()
        if low in self._IRREGULAR:
            return self._IRREGULAR[low]
        if low in self._VERBS:
            return low
        if low.endswith("ies") and len(low) > 3:
            candidate = low[:-3] + "y"
            if candidate in self._VERBS:
                return candidate
        if low.endswith("es") and len(low) > 2:
            for candidate in (low[:-2], low[:-1]):
                if candidate in self._VERBS:
                    return candidate
        if low.endswith("s") and len(low) > 1 and low[:-1] in self._VERBS:
            return low[:-1]
        if low.endswith("ed") and len(low) > 3:
            for candidate in (low[:-2], low[:-1], low[:-2] + "e"):
                if candidate in self._VERBS:
                    return candidate
        if low.endswith("ing") and len(low) > 4:
            stem = low[:-3]
            for candidate in (stem, stem + "e"):
                if candidate in self._VERBS:
                    return candidate
        return low

    def _lexical_kind(self, token: str, original: str) -> str:
        low = token.lower()
        lemma = self.lemma(low)
        if low in self._MODALS:
            return "modal"
        if low in self._NEGATION:
            return "negation"
        if low in self._TIME:
            return "temporal"
        if low in self._DETERMINERS:
            return "determiner"
        if low in self._PREPOSITIONS:
            return "preposition"
        if low in self._PRONOUNS:
            return "pronoun"
        if low in self._NUMBER_WORDS or re.fullmatch(r"\d+(?:\.\d+)?", low):
            return "number"
        if lemma in self._VERBS:
            return "verb"
        if original[:1].isupper() and original.isalpha():
            return "proper_noun"
        if low in self._KNOWN_NOUNS:
            return "noun"
        if re.fullmatch(r"[.!?,;:]", low):
            return "punctuation"
        return "unknown"

    def _number_value(self, token: str) -> Optional[float]:
        low = token.lower()
        if low in self._NUMBER_WORDS:
            return float(self._NUMBER_WORDS[low])
        try:
            return float(low)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _strip_punctuation(tokens: Sequence[str]) -> List[str]:
        return [t for t in tokens if not re.fullmatch(r"[.!?,;:]", t)]

    def _noun_phrase(self, tokens: Sequence[str], start: int, end: int, mention_id: str) -> Optional[LinguisticMention]:
        raw = list(tokens[start:end])
        raw = self._strip_punctuation(raw)
        raw = [t for t in raw if t.lower() not in self._TIME and t.lower() not in self._NEGATION]
        while raw and raw[0].lower() in self._PREPOSITIONS:
            raw.pop(0)
        while raw and raw[-1].lower() in self._PREPOSITIONS:
            raw.pop()
        if not raw:
            return None

        surface = " ".join(raw)
        low = [t.lower() for t in raw]
        quantity = None
        if low and (low[0] in self._NUMBER_WORDS or re.fullmatch(r"\d+(?:\.\d+)?", low[0])):
            quantity = self._number_value(low[0])
            raw = raw[1:]
            low = low[1:]
        while low and low[0] in self._DETERMINERS:
            raw = raw[1:]
            low = low[1:]
        if not raw:
            return None

        if len(raw) == 1 and low[0] in self._PRONOUNS:
            pronoun = low[0]
            concept_surface = self._DEICTIC.get(pronoun)
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
            )

        concept_surface = " ".join(low)
        if len(low) > 1 and concept_surface not in self._MULTIWORD:
            # Noun phrases keep meaningful multi-word surfaces. Determiners and
            # quantities were already removed; no n-gram discovery happens here.
            concept_surface = " ".join(low)
        # Conservative singular fold for known simple nouns only.
        if concept_surface.endswith("s") and concept_surface[:-1] in self._KNOWN_NOUNS:
            concept_surface = concept_surface[:-1]

        return LinguisticMention(
            mention_id=mention_id,
            surface=surface,
            concept_surface=concept_surface,
            start=start,
            end=end,
            kind="proper_noun" if raw[0][:1].isupper() else "nominal",
            quantity=quantity,
            pronoun=False,
            unresolved_reference=False,
        )

    def _find_main_verb(self, tokens: Sequence[str]) -> Tuple[Optional[int], Optional[str], bool]:
        lows = [t.lower() for t in tokens]
        # Passive: be AUX + lexical past participle + by.
        for idx, token in enumerate(lows[:-1]):
            if token not in self._RAW_AUX or self.lemma(token) != "be":
                continue
            next_idx = idx + 1
            while next_idx < len(tokens) and lows[next_idx] in self._NEGATION:
                next_idx += 1
            if next_idx < len(tokens):
                lemma = self.lemma(tokens[next_idx])
                if lemma in self._VERBS and lemma != "be" and "by" in lows[next_idx + 1 :]:
                    return next_idx, lemma, True

        # Main lexical verb; auxiliaries/modals are skipped.
        for idx, token in enumerate(tokens):
            low = token.lower()
            lemma = self.lemma(token)
            if low in self._MODALS or low in self._NEGATION:
                continue
            if lemma in self._VERBS and lemma not in self._AUX:
                return idx, lemma, False

        # Unknown predicate shape: simple Subject + WORD ... . Mark unresolved.
        content = [i for i, t in enumerate(tokens) if not re.fullmatch(r"[.!?,;:]", t)]
        if len(content) >= 2:
            idx = content[1]
            low = tokens[idx].lower()
            if low not in self._DETERMINERS | self._PREPOSITIONS | self._PRONOUNS:
                return idx, low, False
        return None, None, False

    def _subject_end(self, tokens: Sequence[str], verb_idx: int) -> int:
        end = verb_idx
        for idx in range(verb_idx):
            low = tokens[idx].lower()
            if low in self._MODALS or low in self._RAW_AUX or low in self._NEGATION:
                end = min(end, idx)
        return end

    def _trim_object_end(self, tokens: Sequence[str], start: int) -> int:
        end = len(tokens)
        for idx in range(start, len(tokens)):
            low = tokens[idx].lower()
            if low in self._TIME or re.fullmatch(r"[.!?;]", tokens[idx]):
                end = idx
                break
        return end

    def _split_ditransitive(self, tokens: Sequence[str], start: int, end: int) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
        # First object may be "the dog", second normally begins at another
        # determiner/number/pronoun/proper noun: "the dog a ball".
        for idx in range(start + 1, end):
            low = tokens[idx].lower()
            if low in self._DETERMINERS or low in self._NUMBER_WORDS or re.fullmatch(r"\d+(?:\.\d+)?", low):
                return (start, idx), (idx, end)
            if low in self._PRONOUNS:
                return (start, idx), (idx, end)
        return None

    def _qualifiers(self, tokens: Sequence[str]) -> Dict[str, Any]:
        lows = [t.lower() for t in tokens]
        q: Dict[str, Any] = {"polarity": "negative" if any(t in self._NEGATION for t in lows) else "positive"}
        for token in lows:
            if token in self._MODALS:
                q["modality"] = self._MODALS[token]
                q["modality_text"] = token
                break
        for token in lows:
            if token in self._TIME:
                q.update(self._TIME[token])
                break
        return q

    def analyze(self, text: str) -> Dict[str, Any]:
        original = str(text or "").strip()
        normalized = self.normalize(original)
        tokens = self.tokenize(normalized)
        original_tokens = self.tokenize(original)
        lexical: List[Dict[str, Any]] = []
        unknown_words: List[str] = []
        for idx, token in enumerate(tokens):
            original_token = original_tokens[idx] if idx < len(original_tokens) else token
            kind = self._lexical_kind(token, original_token)
            lemma = self.lemma(token)
            lexical.append({"index": idx, "surface": token, "lemma": lemma, "kind": kind})
            if kind == "unknown" and token.isalpha() and token not in unknown_words:
                unknown_words.append(token)

        verb_idx, predicate, passive = self._find_main_verb(tokens)
        mentions: List[LinguisticMention] = []
        roles: Dict[str, str] = {}
        qualifiers = self._qualifiers(tokens)
        unresolved_references: List[Dict[str, Any]] = []
        clause_confidence = 0.0

        if verb_idx is not None and predicate:
            subject_end = self._subject_end(tokens, verb_idx)
            subject = self._noun_phrase(tokens, 0, subject_end, "m1")
            if subject:
                mentions.append(subject)
                if subject.unresolved_reference:
                    unresolved_references.append({"mention_id": subject.mention_id, "surface": subject.surface})

            if passive:
                lows = [t.lower() for t in tokens]
                by_idx = lows.index("by", verb_idx + 1)
                agent = self._noun_phrase(tokens, by_idx + 1, self._trim_object_end(tokens, by_idx + 1), f"m{len(mentions)+1}")
                if agent:
                    mentions.append(agent)
                    if agent.unresolved_reference:
                        unresolved_references.append({"mention_id": agent.mention_id, "surface": agent.surface})
                if subject:
                    roles["patient"] = subject.mention_id
                if agent:
                    roles["agent"] = agent.mention_id
                clause_confidence = 0.92 if subject and agent else 0.68
            else:
                object_start = verb_idx + 1
                while object_start < len(tokens) and tokens[object_start].lower() in self._NEGATION | self._PREPOSITIONS:
                    object_start += 1
                object_end = self._trim_object_end(tokens, object_start)

                if predicate in self._DITRANSITIVE and object_start < object_end:
                    split = self._split_ditransitive(tokens, object_start, object_end)
                    if split:
                        (a0, a1), (b0, b1) = split
                        recipient = self._noun_phrase(tokens, a0, a1, f"m{len(mentions)+1}")
                        theme = self._noun_phrase(tokens, b0, b1, f"m{len(mentions)+2}")
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
                        clause_confidence = 0.94 if subject and recipient and theme else 0.65
                    else:
                        obj = self._noun_phrase(tokens, object_start, object_end, f"m{len(mentions)+1}")
                        if obj:
                            mentions.append(obj)
                        if subject:
                            roles["agent"] = subject.mention_id
                        if obj:
                            roles["theme"] = obj.mention_id
                        clause_confidence = 0.72
                else:
                    obj = self._noun_phrase(tokens, object_start, object_end, f"m{len(mentions)+1}") if object_start < object_end else None
                    if obj:
                        mentions.append(obj)
                    if predicate in self._EXPERIENCER:
                        if subject:
                            roles["experiencer"] = subject.mention_id
                        if obj:
                            roles["theme"] = obj.mention_id
                    elif predicate in self._THEME_SUBJECT:
                        if subject:
                            roles["theme"] = subject.mention_id
                    else:
                        if subject:
                            roles["agent"] = subject.mention_id
                        if obj:
                            roles["patient"] = obj.mention_id
                    clause_confidence = 0.90 if subject else 0.55

            for mention in mentions:
                if mention.unresolved_reference and not any(x.get("mention_id") == mention.mention_id for x in unresolved_references):
                    unresolved_references.append({"mention_id": mention.mention_id, "surface": mention.surface})
                if mention.quantity is not None:
                    role = next((r for r, mid in roles.items() if mid == mention.mention_id), None)
                    if role:
                        qualifiers.setdefault("quantities", {})[role] = mention.quantity

        predicate_known = bool(predicate and predicate in self._VERBS)
        if predicate and not predicate_known and predicate not in unknown_words:
            unknown_words.append(predicate)

        clause = None
        if predicate:
            clause = {
                "clause_id": "clause_1",
                "predicate_surface": predicate,
                "predicate_known": predicate_known,
                "voice": "passive" if passive else "active",
                "roles": dict(roles),
                "qualifiers": qualifiers,
                "confidence": clause_confidence,
            }

        overall = clause_confidence
        if unresolved_references:
            overall = min(overall or 0.5, 0.60)
        if not predicate_known and predicate:
            overall = min(overall or 0.4, 0.40)

        return {
            "contract": "language_understanding_v1",
            "raw_text": original,
            "normalized_text": normalized,
            "tokens": lexical,
            "mentions": [m.to_public() for m in mentions],
            "clauses": [clause] if clause else [],
            "unknown_words": unknown_words,
            "unresolved_references": unresolved_references,
            "confidence": overall,
            "boundary": self.HARD_BOUNDARY,
        }


__all__ = ["LanguageComprehensionEngine", "LinguisticMention"]
