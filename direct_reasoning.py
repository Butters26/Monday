"""Reasoning, on the team.

Reasoning is the explainer (Matthew, Nov 3): each moment it works out what's
going on, what follows and why, from what the other lobes know, and tells
them (reasoning_understanding.py); it judges Language's replies against what
she knows and the situation (review_reply), and thinks things through when
asked (work_out). The old 3,000-line engine (reasoning.py) is in legacy/.
"""

from __future__ import annotations

import re
from typing import Tuple, Any, Callable, Dict, Iterable, List, Optional

from direct_response import (
    answer_from_grounded_memories,
    content_tokens,
    format_predicate_fact,
    looks_like_teaching_turn,
    looks_questionish,
    prose_answer_to_structures,
    relevance_score,
    structures_from_grounded_memories,
    _attribute_asked,
    _fact_covers_attribute,
)


_FAVORITE_FACT = re.compile(
    r"\bmy\s+(?P<attribute>favorite\s+[a-z][a-z ]{0,40}?)\s+is\s+"
    r"(?P<value>[a-z0-9][a-z0-9 -]{0,80}?)(?:[.!?]|$)",
    re.IGNORECASE,
)
_NAMED_FACT = re.compile(
    r"\b(?:remember\s+(?:that\s+)?)?my\s+(?P<noun>[a-z]+(?:\s+[a-z]+){0,3})\s+is\s+named\s+"
    r"(?P<value>[A-Za-z0-9][\w-]{0,40})\b",
    re.IGNORECASE,
)
_NAME_IS_FACT = re.compile(
    r"\b(?:remember\s+(?:that\s+)?)?my\s+(?P<noun>[a-z]+(?:\s+[a-z]+){0,3})(?:'s|s')\s+name\s+is\s+"
    r"(?P<value>[A-Za-z0-9][\w-]{0,40})\b",
    re.IGNORECASE,
)
_NAME_QUESTION = re.compile(
    r"\bwhat(?:'s|\s+is)\s+my\s+(?P<noun>[a-z][a-z ]{0,40}?)(?:'s|s')?\s+name\b",
    re.IGNORECASE,
)
_POISON_MARKERS = ("How it felt:", "What it meant:")
_MERCY_ROLES = {"monday", "assistant", "abin", "mercy"}


class DirectReasoningAdapter:
    """Make the full legacy reasoner safe and usable on the prompted path."""

    def __init__(self, thalamus: Any = None, reasoner_factory: Any = None) -> None:
        # (The old 3,000-line engine, reasoning.py, is in legacy/ since Nov 6:
        # presets and hacks, outside reasoning's job. reasoner_factory is
        # accepted and ignored so old callers still start.)
        self.running = True
        self.thalamus = thalamus

    @staticmethod
    def _response_content(response: Dict[str, Any]) -> Dict[str, Any]:
        content = response.get("content") if isinstance(response, dict) else None
        return content if isinstance(content, dict) else (response if isinstance(response, dict) else {})

    @staticmethod
    def _dedupe_memories(memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        out: List[Dict[str, Any]] = []
        for memory in memories:
            if not isinstance(memory, dict):
                continue
            content = str(memory.get("content") or memory.get("text") or "").strip()
            role = str(memory.get("role") or "").strip().lower()
            key = (role, content.casefold())
            if not content or key in seen:
                continue
            seen.add(key)
            out.append(dict(memory))
        return out

    def _prepare_memory_context(self, direct_input: Dict[str, Any]) -> Dict[str, Any]:
        """Reasoning owns evidence preparation; Thalamus only routes Notus output."""
        raw = direct_input.get("memory_context")
        context = dict(raw) if isinstance(raw, dict) else {}
        memories = [
            dict(item)
            for item in (context.get("memories") or [])
            if isinstance(item, dict)
        ]

        working_set = context.get("working_set")
        if isinstance(working_set, dict):
            for turn in working_set.get("turns") or []:
                if isinstance(turn, dict):
                    memories.append(dict(turn))

        understanding = direct_input.get("understanding")
        understanding = understanding if isinstance(understanding, dict) else {}
        if understanding.get("intent") == "monday_speech_ask" and self.thalamus is not None:
            try:
                recent = self.thalamus.send_message(
                    "notus",
                    "get_recent",
                    {
                        "user_id": str(direct_input.get("user_id") or "default"),
                        "limit": 25,
                    },
                    source="reasoning",
                )
            except Exception:
                recent = {"status": "error"}
            if isinstance(recent, dict) and recent.get("status") == "success":
                body = self._response_content(recent)
                current = str(direct_input.get("user_input") or "").strip().casefold()
                for memory in body.get("memories") or []:
                    if not isinstance(memory, dict):
                        continue
                    role = str(memory.get("role") or "").strip().lower()
                    if role not in _MERCY_ROLES:
                        continue
                    content = str(memory.get("content") or "").strip()
                    if not content or content.casefold() == current:
                        continue
                    item = dict(memory)
                    item["role"] = "monday"
                    memories.append(item)

        context["memories"] = self._dedupe_memories(memories)
        return context

    @staticmethod
    def _route_expression_context(
        semantic_input: Dict[str, Any], direct_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Attach already-owned context to Reasoning's semantic handoff."""
        out = dict(semantic_input)
        out["user_input"] = str(direct_input.get("user_input") or "")

        social = direct_input.get("social_context")
        if isinstance(social, dict) and social:
            out["social_context"] = dict(social)

        emotion = direct_input.get("emotion_result")
        emotion = emotion if isinstance(emotion, dict) else {}
        if emotion.get("emotional_tone") is not None:
            out.setdefault("emotional_tone", emotion.get("emotional_tone"))
        if emotion.get("intensity") is not None:
            out.setdefault("emotional_intensity", emotion.get("intensity"))
        if emotion.get("current_emotion") or emotion.get("emotion"):
            out.setdefault(
                "emotion",
                emotion.get("current_emotion", emotion.get("emotion", "neutral")),
            )

        representation = direct_input.get("representation_result")
        representation = representation if isinstance(representation, dict) else {}
        if representation.get("status") == "success":
            out["representation_concept_ids"] = list(representation.get("concept_ids") or [])
            out["representation_referent_ids"] = list(representation.get("referent_ids") or [])
            out["input_representation_proposition_ids"] = list(
                representation.get("proposition_ids") or []
            )
            if isinstance(representation.get("language_understanding"), dict):
                out["language_understanding"] = representation["language_understanding"]

        out["native_semantics_finalized"] = True
        out["semantic_owner"] = "reasoning"
        return out

    @staticmethod
    def _surface(value: Any) -> Optional[str]:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            return text or None
        return None

    def _resolve_shared_concept(self, value: Any) -> Optional[str]:
        surface = self._surface(value)
        if not surface or self.thalamus is None:
            return None
        response = self.thalamus.send_message(
            "shared_representation",
            "resolve_terms",
            {"terms": [surface], "activate": False},
            source="reasoning",
        )
        if not isinstance(response, dict) or response.get("status") != "success":
            return None
        body = self._response_content(response)
        ids = body.get("concept_ids") or []
        return str(ids[0]) if isinstance(ids, list) and ids else None

    def _register_grounded_structures(
        self,
        structures: Any,
        *,
        turn_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Publish Reasoning-owned meaning to SR; SR stores but does not infer it."""
        if not isinstance(structures, list) or self.thalamus is None:
            return []
        registered: List[Dict[str, Any]] = []
        for structure in structures:
            if not isinstance(structure, dict):
                continue
            predicate_surface = self._surface(
                structure.get("predicate") or structure.get("relation")
            )
            if not predicate_surface:
                continue
            predicate_id = self._resolve_shared_concept(predicate_surface)
            if not predicate_id:
                continue

            roles: Dict[str, str] = {}
            supplied_roles = structure.get("roles")
            if isinstance(supplied_roles, dict):
                for role, target in supplied_roles.items():
                    role_name = str(role or "").strip()
                    target_id = self._resolve_shared_concept(target)
                    if role_name and target_id:
                        roles[role_name] = target_id
            else:
                subject_id = self._resolve_shared_concept(structure.get("subject"))
                object_id = self._resolve_shared_concept(
                    structure.get("object", structure.get("value"))
                )
                if subject_id:
                    roles["subject"] = subject_id
                if object_id:
                    roles["object"] = object_id
            if not roles:
                continue

            try:
                certainty = max(0.0, min(1.0, float(structure.get("certainty", 1.0))))
            except (TypeError, ValueError):
                certainty = 1.0
            qualifiers = (
                dict(structure.get("qualifiers") or {})
                if isinstance(structure.get("qualifiers"), dict)
                else {}
            )
            qualifiers.setdefault("certainty", certainty)
            response = self.thalamus.send_message(
                "shared_representation",
                "register_proposition",
                {
                    "predicate_id": predicate_id,
                    "roles": roles,
                    "qualifiers": qualifiers,
                    "user_id": user_id,
                    "provenance": {
                        "producer_lobe": "reasoning",
                        "source_type": "reasoning_grounded_structure",
                        "turn_id": turn_id,
                        "confidence": certainty,
                    },
                },
                source="reasoning",
            )
            if not isinstance(response, dict) or response.get("status") != "success":
                continue
            body = self._response_content(response)
            if body.get("proposition_id") or body.get("id"):
                registered.append(dict(body))
        return registered

    @staticmethod
    def _clean_memories(memories: Any, user_input: str) -> List[Dict[str, Any]]:
        if not isinstance(memories, Iterable) or isinstance(memories, (str, bytes, dict)):
            return []
        cleaned = []
        for memory in memories:
            if not isinstance(memory, dict):
                continue
            content = memory.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            role = str(memory.get("role", "") or "")
            # Drop experience-poison blobs (role=system "How it felt:" rows).
            if any(marker in content for marker in _POISON_MARKERS) and (
                role == "system" or all(m in content for m in _POISON_MARKERS)
            ):
                continue
            # The current prompt is stored before reasoning. It is not evidence
            # for answering itself, but older user-scoped memories are.
            if content.strip().casefold() == user_input.strip().casefold():
                continue
            cleaned.append(dict(memory))
        return cleaned

    @staticmethod
    def _normalise_favorite_fact(text: str) -> Optional[str]:
        match = _FAVORITE_FACT.search(text)
        if not match:
            return None
        attribute = " ".join(match.group("attribute").lower().split())
        value = match.group("value").strip(" .!?")
        return f"Your {attribute} is {value}." if value else None

    @staticmethod
    def _normalise_personal_facts(text: str) -> List[str]:
        """Extract one or more clean fact sentences from teaching / memory text."""
        if not isinstance(text, str) or not text.strip():
            return []
        parts: List[str] = []
        own_name = re.search(
            r"(?i)\b(?:remember\s+(?:that\s+)?)?my\s+name\s+is\s+"
            r"([A-Za-z][\w-]{0,40})(?=\s+and\b|[.!?,]|$)",
            text,
        )
        if own_name:
            parts.append(f"Your name is {own_name.group(1).strip()}.")
        for pattern in (_NAME_IS_FACT, _NAMED_FACT):
            match = pattern.search(text)
            if match:
                noun = " ".join(match.group("noun").lower().split())
                value = match.group("value").strip(" .!?")
                if noun and value and not re.search(r"\b(?:is|are|and|named)\b", noun):
                    parts.append(f"Your {noun}'s name is {value}.")
        fav = DirectReasoningAdapter._normalise_favorite_fact(text)
        if fav:
            parts.append(fav)
        live = re.search(
            r"(?i)\b(?:remember\s+(?:that\s+)?)?i\s+live\s+in\s+"
            r"([A-Za-z0-9][A-Za-z0-9\s,.-]{0,60}?)(?=\s+and\s+i\b|[.!?]|$)",
            text,
        )
        if live:
            place = live.group(1).strip(" .!?")
            if place and not re.search(r"(?i)\band\s+i\b", place):
                parts.append(f"You live in {place}.")
        work = re.search(
            r"(?i)\b(?:remember\s+(?:that\s+)?)?i\s+work\s+(as|at|in)\s+"
            r"([A-Za-z0-9][A-Za-z0-9\s,.-]{0,60}?)(?=\s+and\s+i\b|[.!?]|$)",
            text,
        )
        if work:
            job = work.group(2).strip(" .!?")
            if job and not re.search(r"(?i)\band\s+i\b", job):
                parts.append(f"You work {work.group(1).lower()} {job}.")
        if not parts:
            generic = re.search(
                r"(?i)\b(?:remember\s+(?:that\s+)?)?my\s+([a-z]+(?:\s+[a-z]+){0,3})\s+is\s+"
                r"([a-z0-9][a-z0-9 -]{0,80}?)(?=\s+and\s+(?:i|my)\b|[.!?]|$)",
                text,
            )
            if generic:
                noun = " ".join(generic.group(1).lower().split())
                value = generic.group(2).strip(" .!?")
                if (
                    noun
                    and value
                    and not noun.startswith("favorite ")
                    and "name" not in noun
                    and not value.lower().startswith("named ")
                    and not re.search(r"\b(?:is|are|and|named)\b", noun)
                ):
                    parts.append(f"Your {noun} is {value}.")
        # Dedup
        seen = set()
        out = []
        for p in parts:
            key = p.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
        return out

    @staticmethod
    def _normalise_personal_fact(text: str) -> Optional[str]:
        facts = DirectReasoningAdapter._normalise_personal_facts(text)
        if not facts:
            return None
        if len(facts) == 1:
            return facts[0]
        # Combine two clean facts for compound teaching acks.
        a = facts[0].rstrip(".")
        b = facts[1][0].lower() + facts[1][1:] if facts[1] else facts[1]
        return f"{a}, and {b}"

    @classmethod
    def _evidence(cls, memories: List[Dict[str, Any]], user_input: str) -> List[Dict[str, Any]]:
        evidence = []
        for memory in memories:
            content = memory.get("content", "")
            if isinstance(content, str):
                norms = cls._normalise_personal_facts(content)
            else:
                norms = []
            if norms:
                for normalized in norms:
                    evidence.append({"role": "fact", "content": normalized})
            elif str(memory.get("role", "")) == "fact":
                evidence.append(dict(memory))
            else:
                evidence.append(memory)
        for fact in cls._normalise_personal_facts(user_input):
            evidence.append({"role": "fact", "content": fact})
        return evidence

    @classmethod
    def _answer_from_facts(cls, evidence: List[Dict[str, Any]], user_input: str) -> Optional[str]:
        """Answer questions from stored facts and relevant user memories."""
        return answer_from_grounded_memories(user_input or "", evidence)


    @classmethod
    def _teaching_ack(cls, user_input: str) -> Optional[str]:
        """Acknowledge remembered personal facts (hello-monday / DirectNotus idea)."""
        fact = cls._normalise_personal_fact(user_input or "")
        if not fact:
            return None
        # "Your dog's name is Pixel." -> "Got it — your dog's name is Pixel."
        body = fact[0].lower() + fact[1:] if fact else fact
        return f"Got it — {body}"

    @staticmethod
    def _looks_like_raw_triple(text: str) -> bool:
        t = (text or "").strip()
        if re.match(r"^user\s+[\w]+\s+\S+$", t, re.IGNORECASE):
            return True
        if re.match(r"^[\w]+\s+[\w_]+\s+\S+$", t) and " " not in t.split()[-1]:
            # e.g. "user dog_name Pixel" / "user favorite_color blue"
            parts = t.split()
            if len(parts) == 3 and "_" in parts[1]:
                return True
        return False

    @staticmethod
    def _significant_patterns(pattern_result: Any) -> Dict[str, Any]:
        if not isinstance(pattern_result, dict):
            return {}
        if pattern_result.get("status") != "success":
            return {}
        patterns = pattern_result.get("significant_patterns") or {}
        return patterns if isinstance(patterns, dict) else {}

    @classmethod
    def _infer_next_from_sequence(cls, steps: Any) -> Optional[str]:
        """Reasoning job: given Pattern's discovered sequence, infer the next item.

        Pattern only identifies the relationship; it does not extrapolate.
        """
        if not isinstance(steps, (list, tuple)) or len(steps) < 2:
            return None
        values: List[float] = []
        as_ints = True
        for step in steps:
            try:
                number = float(str(step).strip())
            except (TypeError, ValueError):
                return None
            values.append(number)
            if not float(number).is_integer():
                as_ints = False
        deltas = [values[i + 1] - values[i] for i in range(len(values) - 1)]
        if not deltas:
            return None
        # Constant delta (arithmetic progression) — e.g. 2,4,6,8 → 10.
        if all(abs(delta - deltas[0]) < 1e-9 for delta in deltas):
            nxt = values[-1] + deltas[0]
            if as_ints:
                return str(int(nxt))
            return str(nxt)
        # Constant ratio (geometric) when ratios are stable and non-zero.
        if all(abs(v) > 1e-12 for v in values[:-1]):
            ratios = [values[i + 1] / values[i] for i in range(len(values) - 1)]
            if all(abs(ratio - ratios[0]) < 1e-9 for ratio in ratios):
                nxt = values[-1] * ratios[0]
                if as_ints and float(nxt).is_integer():
                    return str(int(nxt))
                return str(nxt)
        return None


    @classmethod
    def _answer_from_patterns(
        cls, pattern_result: Any, user_input: str
    ) -> Optional[str]:
        """Use Pattern discoveries (pattern_result) without Pattern doing the inference.

        Pattern owns discovery; Reasoning may infer next. Spoken sequence narration
        is only for explicit sequence/next asks — never the mouth for fact recall,
        social/emotion, motor, or ordinary conversation.
        """
        patterns = cls._significant_patterns(pattern_result)
        if not patterns:
            return None
        text = (user_input or "").strip().lower()
        asks_next = any(
            cue in text
            for cue in (
                "what comes next",
                "what's next",
                "whats next",
                "next in the",
                "next number",
                "what follows",
                "continue the",
                "what is next",
            )
        ) or ("next" in text and ("sequence" in text or "pattern" in text))
        # Not a sequence ask → do not speak Pattern. Still available as pattern_result.
        if not asks_next:
            return None
        sequences = patterns.get("reliable_sequences") or []
        input_tokens = {
            tok for tok in __import__("re").findall(r"[a-z0-9]+", text) if tok
        }

        ranked = []
        for seq in sequences:
            if not isinstance(seq, dict):
                continue
            steps = seq.get("steps") or []
            if not isinstance(steps, (list, tuple)) or len(steps) < 2:
                continue
            try:
                conf = float(seq.get("confidence") or 0.0)
            except (TypeError, ValueError):
                conf = 0.0
            nxt = cls._infer_next_from_sequence(steps)
            step_tokens = {str(s).strip().lower() for s in steps}
            overlap = len(step_tokens & input_tokens) if input_tokens else 0
            # Reject wraparound loops (first == last) unless that is all we have.
            wraps = len(steps) >= 3 and str(steps[0]).strip() == str(steps[-1]).strip()
            ranked.append(
                {
                    "seq": seq,
                    "steps": list(steps),
                    "conf": conf,
                    "next": nxt,
                    "length": len(steps),
                    "overlap": overlap,
                    "wraps": wraps,
                    "inferable": nxt is not None,
                }
            )
        if not ranked:
            return None

        # Prefer sequences that overlap the ask; never narrate unrelated sequences.
        with_overlap = [row for row in ranked if row["overlap"] > 0]
        if with_overlap:
            ranked = with_overlap
        else:
            # Ask mentions a sequence but none of our discoveries overlap — stay silent.
            return None

        # Prefer inferable non-wrap sequences that overlap the prompt, then longer/higher conf.
        ranked.sort(
            key=lambda row: (
                1 if row["inferable"] else 0,
                0 if row["wraps"] else 1,
                row["overlap"],
                row["length"],
                row["conf"],
            ),
            reverse=True,
        )
        best = ranked[0]
        steps = best["steps"]
        nxt = best["next"]
        joined = ", ".join(str(s) for s in steps)
        if nxt is None:
            return (
                f"I see a sequence pattern ({joined}), "
                f"but I cannot confidently infer the next item yet."
            )
        return f"The pattern is {joined}, so the next item is {nxt}."


    # ------------------------------------------------------------------
    # Reply review: Language builds a reply; Reasoning judges whether it makes
    # sense (understandable, fits the situation, matches what memory holds)
    # and says exactly why when it doesn't, so Language can redo it.
    # ------------------------------------------------------------------

    _GREETING_SENSE = "oewn-06645018-n"  # dictionary sense: "an expression of greeting"
    _FAREWELL_SENSE = "oewn-06642117-n"  # dictionary sense: "a farewell remark"
    _CONTENT_KINDS = {"noun", "proper_noun", "verb", "adjective", "adverb", "possessive"}
    _NOT_CONTENT = {"be", "do", "have", "can", "will", "would", "could", "should", "may",
                    "might", "must", "shall", "not"}

    def _analyze(self, text: str) -> Dict[str, Any]:
        """Ask Language to read a sentence (Language owns understanding words).
        A reading is kept for a while, so checking several facts against the
        same question doesn't ask Language to read it again each time."""
        if self.thalamus is None:
            return {}
        cache = getattr(self, "_readings", None)
        if cache is None:
            cache = self._readings = {}
        key = str(text or "")
        if key in cache:
            return cache[key]
        response = self.thalamus.send_message("language", "analyze", {"text": text}, source="reasoning")
        if not isinstance(response, dict) or response.get("status") != "success":
            return {}
        reading = self._response_content(response).get("understanding") or {}
        cache[key] = reading
        if len(cache) > 128:
            cache.pop(next(iter(cache)))
        return reading

    @classmethod
    def _content_lemmas(cls, analysis: Dict[str, Any]) -> set:
        out = set()
        for token in analysis.get("tokens") or []:
            lemma = str(token.get("lemma") or "").casefold()
            kind = token.get("kind")
            if lemma.endswith("'s"):
                lemma = lemma[:-2]  # "dog's" is about the dog (read as unknown by comprehension)
                if kind == "unknown":
                    kind = "noun"
            if kind in cls._CONTENT_KINDS and lemma and lemma not in cls._NOT_CONTENT:
                out.add(lemma)
        return out

    @classmethod
    def _has_greeting(cls, analysis: Dict[str, Any]) -> bool:
        for token in analysis.get("tokens") or []:
            for sense in token.get("senses") or []:
                if sense.get("synset_id") == cls._GREETING_SENSE:
                    return True
        return False

    @staticmethod
    def _names_in(meaning: Any, out: Optional[set] = None) -> set:
        out = set() if out is None else out
        if isinstance(meaning, dict):
            for key, value in meaning.items():
                if key == "name" and isinstance(value, str):
                    out.update(w.casefold() for w in re.findall(r"[A-Za-z]+", value))
                else:
                    DirectReasoningAdapter._names_in(value, out)
        elif isinstance(meaning, list):
            for item in meaning:
                DirectReasoningAdapter._names_in(item, out)
        return out

    def _fact_in_memory(self, fact: Dict[str, Any], user_id: str) -> bool:
        if self.thalamus is None:
            return False
        response = self.thalamus.send_message(
            "notus", "query_facts",
            {"query": f"{fact.get('predicate', '')} {fact.get('object', '')}", "user_id": user_id, "limit": 20},
            source="reasoning",
        )
        facts = self._response_content(response).get("facts") if isinstance(response, dict) else None
        for row in facts or []:
            if (str(row.get("predicate")).casefold() == str(fact.get("predicate")).casefold()
                    and str(row.get("object")).casefold() == str(fact.get("object")).casefold()):
                return True
        return False

    # ------------------------------------------------------------------
    # On the team: reasoning signs up for what memory brings up on its own,
    # so it knows what she remembers about what was just said.
    # ------------------------------------------------------------------

    def on_joined(self, name: str) -> None:
        listen = getattr(self.thalamus, "listen", None)
        if callable(listen):
            listen(name, "remembered")
            listen(name, "social_read")  # what social context makes of each moment

    def _hear_social(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.__dict__.setdefault("_social_reads", {})[str(payload.get("user_id") or "default")] = dict(payload)
        return {"status": "success", "content": {"heard": True}}

    def _ask_lobe(self, lobe: str, msg_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.thalamus is None:
            return {}
        try:
            response = self.thalamus.send_message(lobe, msg_type, payload, source="reasoning")
        except Exception:
            return {}
        if not isinstance(response, dict) or response.get("status") not in ("success", None):
            return {}
        body = response.get("content") if isinstance(response.get("content"), dict) else response
        return body if isinstance(body, dict) else {}

    def _understand_moment(self, user_input: str, user_id: str, direct_input: Dict[str, Any]) -> Dict[str, Any]:
        """What's going on, from what every lobe knows, and what follows
        (reasoning_understanding.py). Conclusions go to memory as concluded;
        the whole understanding is announced for any lobe that listens."""
        from reasoning_understanding import Understanding
        if not user_input.strip():
            return {}
        social = (self.__dict__.get("_social_reads") or {}).get(user_id) or {}
        if str(social.get("said") or "").strip() != user_input.strip():
            social = self._ask_lobe("social_context", "get_context", {"user_id": user_id})
            if str(social.get("said") or "").strip() != user_input.strip():
                social = {}
        facts = self._facts_for(user_input, user_id)
        emotion = direct_input.get("emotion_result") if isinstance(direct_input.get("emotion_result"), dict) else {}
        if not emotion.get("monday_emotion"):
            emotion = self._ask_lobe("emotion", "get_state", {}) or emotion
        novelty_body = self._ask_lobe("novelty", "get_assessment", {})
        novelty = novelty_body.get("novelty_score", novelty_body.get("score"))
        attention = direct_input.get("attention") if isinstance(direct_input.get("attention"), dict) else {}
        focus = (getattr(self, "_last_attention_focus", None) or {}).get("focus_text") or attention.get("focus_text")
        reading = self._analyze(user_input)
        # She hears the same words Language does: if Language's reading of them
        # doesn't make sense, she says why and asks Language to read it again.
        misread = Understanding.reading_problems(user_input, reading)
        if misread:
            again = self._ask_lobe("language", "read_again", {"text": user_input, "problems": misread})
            better = again.get("understanding") if isinstance(again.get("understanding"), dict) else {}
            if better.get("tokens") and not Understanding.reading_problems(user_input, better):
                reading, misread = better, []
        thinker = Understanding(self._ask_lobe)
        understood = thinker.understand(
            user_input, user_id, social, facts, emotion,
            float(novelty) if isinstance(novelty, (int, float)) else None, focus,
            patterns=direct_input.get("pattern_result") if isinstance(direct_input.get("pattern_result"), dict) else {},
            reading=reading)
        if misread:
            understood["reading_problems"] = misread
            understood.setdefault("unsure", []).extend(
                f"Language read '{m['word']}' as {m['read_as']}, but it fits better as {m['fits_better']}: "
                f"{m['why']}" for m in misread)
        solved = thinker.solution_in(reading)
        if solved:
            # A way he found to fix something: kept, to suggest when it comes up again.
            understood.setdefault("conclusions", []).append(solved)
        # What follows from this moment: guesses she already made and said
        # aren't new because she worked them out again.
        before = self.__dict__.setdefault("_concluded_before", {}).setdefault(user_id, set())
        fresh = []
        for c in understood.get("conclusions") or []:
            k = (str(c.get("subject")).casefold(), c.get("predicate"), str(c.get("object")).casefold(), c.get("value"))
            if k not in before:
                before.add(k)
                fresh.append(c)
        understood["conclusions"] = fresh
        for c in understood.get("conclusions") or []:
            if (c.get("value") and not str(c.get("value")).startswith("said:")) or c.get("modal"):
                # Memory's store_conclusion drops the value ("than Ben") and the
                # "can", so it would file a different fact; she works these out
                # again from what he told her instead (on Memory's list).
                continue
            kept = self._ask_lobe("notus", "store_conclusion", {**c, "user_id": user_id})
            fact = kept.get("fact") if isinstance(kept.get("fact"), dict) else {}
            same = all(str(fact.get(k) or "").casefold() == str(c.get(k) or "").casefold()
                       for k in ("subject", "predicate", "object"))
            if fact.get("id") is not None and same:
                Understanding.remember_concluded(fact["id"])
        self.__dict__.setdefault("_understood", {})[user_id] = understood
        announce = getattr(self.thalamus, "announce", None)
        if callable(announce):
            try:
                announce("understood", understood, "reasoning")
            except Exception:
                pass
        return understood

    def _hear_remembered(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        about = str(payload.get("about") or "").strip().casefold()
        user = str(payload.get("user_id") or "default")
        if not hasattr(self, "_remembered"):
            self._remembered = {}
        self._remembered[(user, about)] = payload
        if len(self._remembered) > 64:
            self._remembered.pop(next(iter(self._remembered)))
        return {"status": "success", "content": {"heard": True}}

    def _facts_for(self, text: str, user_id: str) -> List[Dict[str, Any]]:
        if self.thalamus is None:
            return []
        response = self.thalamus.send_message("notus", "query_facts", {"query": text, "user_id": user_id,
                                                                       "limit": 10}, source="reasoning")
        if not isinstance(response, dict) or response.get("status") != "success":
            return []
        body = response.get("content") if isinstance(response.get("content"), dict) else response
        return [f for f in body.get("facts") or [] if isinstance(f, dict)]

    def _remembered_about(self, user_input: str, user_id: str) -> Dict[str, Any]:
        return (getattr(self, "_remembered", {}) or {}).get((user_id, user_input.strip().casefold())) or {}

    @staticmethod
    def _is_a_kind_of(verb: str, general: str) -> bool:
        """Is doing `verb` a kind of doing `general`, in the dictionary? Visiting
        is a kind of going; going isn't necessarily visiting."""
        try:
            from lexicon.oewn_offline import get_wordnet
            wn = get_wordnet()
            targets = {s.id for s in wn.synsets(general, pos="v")}
            frontier = list(wn.synsets(verb, pos="v"))[:2]
            if {s.id for s in frontier} & targets:
                return True  # the same meaning (travel = go)
            for _ in range(4):
                nxt = [up for s in frontier for up in s.hypernyms()]
                if {s.id for s in nxt} & targets:
                    return True
                frontier = nxt
        except Exception:
            return False
        return False

    @staticmethod
    def _feeling_words_meet(his: set, hers: set) -> bool:
        """Does a word in her reply mean his feeling, by the dictionary: one is
        in the other's meaning ("glad": "...made happy")?"""
        try:
            from lexicon.oewn_offline import get_wordnet
            wn = get_wordnet()
        except Exception:
            return False
        def meanings(word):
            return " ".join(str(s.definition() or "") for s in wn.synsets(word, pos="a")
                            + wn.synsets(word, pos="s")).casefold()
        for mine in hers:
            if not mine.isalpha():
                continue
            for felt in his:
                if felt in meanings(mine).split() or mine in meanings(felt).split():
                    return True
        return False

    @staticmethod
    def _is_number_word(word: str) -> bool:
        """A word the dictionary files first as a quantity ("two", "twelve")."""
        try:
            from lexicon.oewn_offline import get_wordnet
            synsets = list(get_wordnet().synsets(word))
        except Exception:
            return False
        return bool(synsets) and str(synsets[0].lexfile()) == "noun.quantity"

    @staticmethod
    def _fact_words(fact: Dict[str, Any]) -> set:
        """What a fact is about: its relation ("dog name"), and who it's about
        unless that's him ("user" is the person asking: "my")."""
        from notus_fact_text import FactText
        predicate = str(fact.get("predicate") or "")
        predicate = predicate[4:] if predicate.startswith("not_") else predicate
        predicate = predicate[2:] if predicate.startswith("v:") else predicate
        predicate = predicate.replace("@", " ").replace("_", " ")
        subject = str(fact.get("subject") or "")
        subject = "" if subject.casefold() == "user" else subject.replace("user's ", "")
        words = FactText._content_tokens(f"{predicate} {subject}")
        if not words:
            # "You are tired", "you have two cats": only what it says is left.
            obj = str(fact.get("object") or "")
            words = FactText._content_tokens(obj if obj != "(nothing)" else "")
        return words

    def _fact_fits(self, fact: Dict[str, Any], question: str) -> bool:
        """Is this fact about what he asked? Both ways: every word the fact is
        about ("dog name") was asked about, allowing words that mean the same
        ("called" = "name"; asking "who" asks for a name), and every thing he
        asked about (the nouns: "cat") is in the fact."""
        from notus_fact_text import FactText
        asked = FactText._expand_tokens(FactText._content_tokens(question))
        reading = self._analyze(question)
        if any(str(t.get("lemma") or "").casefold() == "who" for t in reading.get("tokens") or []):
            asked |= FactText._alias_set("name")
        about = self._fact_words(fact)
        lows = [str(t.get("surface") or "").casefold() for t in reading.get("tokens") or []]
        subject = str(fact.get("subject") or "")
        clause = (reading.get("clauses") or [{}])[0]
        obj = str(fact.get("object") or "")
        if lows and lows[0] in ("who", "what") and obj[:1].isupper() and obj.casefold() in lows:
            # "Who is called Max?": the fact that has Max in it says who.
            return True
        about_at = next((int(t.get("index", -1)) for t in reading.get("tokens") or []
                         if str(t.get("surface") or "").casefold() == "about"), None)
        if str(clause.get("predicate_surface") or "") == "know" and about_at is not None:
            # "What do you know about my brother?": everything she knows about him.
            mention = next((m for m in reading.get("mentions") or []
                            if isinstance(m.get("end"), int) and m["end"] > about_at), {})
            wanted = FactText._content_tokens(str(mention.get("surface") or "")) - {"my", "user"}
            filed = FactText._content_tokens(subject.replace("user's ", ""))
            if subject == "user" and not str(fact.get("predicate") or "").startswith(("v:", "is", "not_")):
                # "Your dog is Rex" is filed under him with "dog" as what it's about.
                filed |= FactText._content_tokens(str(fact.get("predicate") or "").replace("_", " "))
                subject = "user's " + str(fact.get("predicate") or "")
            return bool(wanted) and wanted <= filed and ("my" not in str(mention.get("surface") or "").split()
                                                          or subject.startswith("user's "))
        names = FactText._alias_set("name")
        if any(w in names for w in lows) and not (about & names) and not str(fact.get("object") or "")[:1].isupper():
            return False  # "what is my dog named?" asks for a name, not that the dog is loud
        if "my" in lows and subject.casefold().startswith(("the ", "a ")):
            return False  # "my dog" isn't "the dog" someone else has
        if " and " in subject:
            # "my sister and I bought apples" answers "what did my sister buy?"
            # and "what did we buy?": asking about any of them asks about the group.
            members = [m.strip() for m in subject.split(" and ")]
            member_words = set()
            for m in members:
                member_words |= FactText._content_tokens(m.replace("user's ", "")) - {"user", "monday"}
            about -= (member_words - asked) | {"user", "monday"}  # the ones he didn't name needn't be asked
            named = bool(asked & member_words) or (
                "user" in members and any(w in ("we", "us", "our") for w in lows))
            if not named:
                return False
        if any(a == "how" and b in ("many", "much") for a, b in zip(lows, lows[1:])):
            # "How many cats?" asks for the number: the fact's number is the answer.
            about = {w for w in about if not (w.isdigit() or self._is_number_word(w))}
        if lows and lows[0] == "why" and not str(fact.get("because") or "").strip():
            return False  # "why?" is only answered by a fact that has a reason
        if lows and lows[0] == "when" and not str(fact.get("when_said") or "").strip():
            return False  # "when?" is only answered by a fact that says when
        # The time asked about must be the fact's time: "where will I go?" isn't
        # answered by where he went.
        q = ((reading.get("clauses") or [{}])[0].get("qualifiers") or {})
        asked_when = reading.get("tense") or ("past" if q.get("temporal_relation") == "before_now" else (
            "future" if q.get("modality") == "future" else None))
        if asked_when and fact.get("tense") in ("past", "future") and fact.get("tense") != asked_when:
            return False
        if not asked_when and fact.get("tense") in ("past", "future") \
                and reading.get("speech_act") == "question":
            return False  # "where do I live?" isn't answered by where he lived
        if asked_when == "past" and not fact.get("tense") \
                and str(fact.get("when_said") or "").strip().casefold() == "now":
            return False  # "where did I live?" isn't answered by where he lives now
        asks_who = any(str(t.get("lemma") or "").casefold() in ("who", "what")
                       for t in (reading.get("tokens") or [])[:1])
        if asks_who and str(fact.get("subject") or "").casefold() not in ("user", "monday"):
            # "Who has a cat?": the person is the answer, so the question needn't name them.
            subject_words = FactText._content_tokens(str(fact.get("subject") or ""))
            unnamed = {w for w in about if w not in subject_words}
            if not (subject_words & asked):
                about = unnamed
                if not about:
                    # Only the person was left: what he asked about (the cat) has
                    # to be what the fact is about, checked below.
                    about = {"_who_"}
        if about == {"_who_"}:
            pass
        elif not about or not all(FactText._alias_set(word) & asked
                                  or any(self._is_a_kind_of(word, q) for q in asked) for word in about):
            return False
        # What he asked about may also be what the fact says ("Is Lily brave?").
        about_all = FactText._expand_tokens(about | FactText._content_tokens(
            str(fact.get("object") or "") + " " + str(fact.get("value") or "").replace(":", " ")))
        if str(fact.get("object") or "")[:1].isupper():
            about_all |= FactText._alias_set("name")  # "my cat is Luna": Luna is the cat's name
        # What he asked someone does ("what does Sam have?") must be what the fact
        # says they do, not something else about them ("Sam is your friend").
        words = [t for t in reading.get("tokens") or [] if t.get("kind") != "punctuation"]
        verbs = [str(t.get("lemma") or "").casefold() for t in words if t.get("kind") == "verb"]
        if not verbs and words and words[-1].get("kind") == "auxiliary" \
                and str(words[-1].get("lemma") or "") == "have":
            verbs = ["have"]  # "what does Sam have?": have is the verb asked about
        asked_verb = verbs[-1] if verbs else ""
        if words and words[0].get("kind") == "auxiliary" and str(words[0].get("lemma") or "") == "be":
            asked_verb = ""  # "is Mary tired?" asks what Mary is, not what she does
        if not verbs and len(words) > 1 and str(words[0].get("lemma") or "").casefold() == "who" \
                and str(words[1].get("lemma") or "") == "be" \
                and str(fact.get("predicate") or "").startswith(("v:", "not_v:")):
            return False  # "who is Sam?" asks what Sam is (your friend), not what Sam does
        if asked_verb and asked_verb not in ("be", "do", "name", "call", "named", "called"):
            predicate = str(fact.get("predicate") or "")
            predicate = predicate[4:] if predicate.startswith("not_") else predicate
            fact_verb = predicate[2:].split("@", 1)[0] if predicate.startswith("v:") else predicate
            if fact_verb.casefold() != asked_verb and not self._is_a_kind_of(fact_verb, asked_verb):
                return False
        for token in reading.get("tokens") or []:
            if token.get("kind") not in ("noun", "proper_noun", "possessive"):
                continue
            for word in FactText._content_tokens(str(token.get("lemma") or "").replace("'s", "")):
                if not (FactText._alias_set(word) & about_all):
                    return False
        return True

    _POS = {"verb": "v", "noun": "n", "adjective": "a", "adverb": "r"}

    @classmethod
    def _meant_words(cls, meaning: Any, out: Optional[Dict[str, set]] = None) -> Dict[str, set]:
        """The words the meaning was built from, by kind."""
        out = out if out is not None else {"v": set(), "n": set(), "a": set()}
        if isinstance(meaning, dict):
            if isinstance(meaning.get("verb"), str):
                out["v"].add(meaning["verb"].casefold())
            if isinstance(meaning.get("noun"), str):
                out["n"].add(meaning["noun"].casefold())
            for adj in meaning.get("adjectives") or []:
                if isinstance(adj, str):
                    out["a"].add(adj.casefold())
            for key, value in meaning.items():
                if not str(key).startswith("_") and isinstance(value, (dict, list)):
                    cls._meant_words(value, out)
        elif isinstance(meaning, list):
            for item in meaning:
                cls._meant_words(item, out)
        return out

    @classmethod
    def _rare_stand_in(cls, meaning: Dict[str, Any], reply: Dict[str, Any]):
        """A word in the reply that stands in for a meant word but is far rarer
        (has far fewer dictionary meanings): 'cognize' for 'know'."""
        try:
            from lexicon.oewn_offline import meaning_count
        except Exception:
            return None
        from lexicon.oewn_offline import get_wordnet
        meant = cls._meant_words(meaning)
        every_meant = {w for words in meant.values() for w in words}
        for token in reply.get("tokens") or []:
            if token.get("kind") in ("punctuation", "determiner", "pronoun", "proper_noun", "auxiliary"):
                continue
            # Compare the word itself, whatever kind it was read as
            # ("colouring" read as a verb still stands in for the noun "color").
            for form in {str(token.get("surface") or "").casefold(), str(token.get("lemma") or "").casefold()}:
                if not form or form in every_meant or form in cls._NOT_CONTENT:
                    continue
                for pos, words in meant.items():
                    for word in words:
                        try:
                            used_ids = {str(ss.id) for ss in get_wordnet().synsets(form, pos=pos)}
                            word_ids = {str(ss.id) for ss in get_wordnet().synsets(word, pos=pos)}
                        except Exception:
                            continue
                        if not (used_ids & word_ids):
                            continue  # not standing in for this word
                        common, rare_count = meaning_count(word, pos), meaning_count(form, pos)
                        if common >= 3 and rare_count * 2 <= common:
                            return form, word, pos
        return None

    @staticmethod
    def _verb_frames(verb: str) -> List[Tuple[str, str]]:
        """What the dictionary says a verb can take, from its sentence frames
        ("Somebody ----s something", "It is ----ing"): (who does it, what follows)."""
        try:
            from lexicon.oewn_offline import get_wordnet
            senses = [sense for ss in get_wordnet().synsets(verb, pos="v") for sense in ss.senses()]
        except Exception:
            return []
        out = []
        for sense in senses:
            if str(sense.word().lemma()).casefold() != verb.casefold():
                continue
            try:
                frames = sense.frames()
            except Exception:
                continue
            for frame in frames:
                words = str(frame).split()
                if len(words) < 2:
                    continue
                doer = words[0].casefold()
                rest = " ".join(w for w in words[1:] if "----" not in w and w.casefold() != "is").casefold()
                out.append((doer, rest))
        return out

    @classmethod
    def _noun_is_person(cls, noun: str) -> bool:
        """Is this noun a living doer in the dictionary (filed under people or
        animals: wife, doctor, fool, dog)? The dictionary's "somebody" means one."""
        if not noun:
            return False
        try:
            from lexicon.oewn_offline import get_wordnet
            synsets = list(get_wordnet().synsets(noun, pos="n"))
        except Exception:
            return False
        return any(str(ss.lexfile()) in ("noun.person", "noun.animal") for ss in synsets)

    @classmethod
    def _verb_makes_sense(cls, meaning: Dict[str, Any]) -> Optional[str]:
        """None if the verb can be used this way, else why not ("people don't
        rain"; "love needs who or what")."""
        verb = str(meaning.get("verb") or "").casefold()
        if not verb or verb in ("be", "have", "do") or "_" in verb:
            return None
        frames = cls._verb_frames(verb)
        if not frames:
            return None
        subject = meaning.get("subject") if isinstance(meaning.get("subject"), dict) else {}
        person = bool(subject.get("ref") in ("speaker", "addressee") or subject.get("name")
                      or subject.get("pronoun") in ("he", "she", "they")
                      or cls._noun_is_person(str(subject.get("noun") or "")))
        it = subject.get("pronoun") == "it"
        doers = {"it"} if it else ({"somebody"} if person else {"something"})
        has_object = bool(meaning.get("object"))
        has_place = bool(meaning.get("modifiers"))
        fitting_doer = [rest for doer, rest in frames if doer in doers]
        if not fitting_doer:
            who = "people" if person else "things"
            return f"{who} can't '{verb}' (the dictionary only has: " + "; ".join(
                sorted({f"{d} {verb}s {r}".strip() for d, r in frames})[:3]) + ")"
        for rest in fitting_doer:
            needs_object = any(w in rest for w in ("something", "somebody", "clause", "infinitive", "adjective"))
            needs_place = "pp" in rest
            if (needs_object == has_object or (has_object and needs_place)) and (not needs_place or has_place or has_object):
                return None
            if not rest and not has_object:
                return None
        if not has_object:
            return f"'{verb}' needs who or what (somebody {verb}s something)"
        return f"'{verb}' isn't used with something after it like that"

    def _his_names(self, user_id: str) -> set:
        response = self.thalamus.send_message("notus", "query_facts", {"query": "what is my name",
                                              "user_id": user_id, "limit": 5}, source="reasoning") if self.thalamus else {}
        body = self._response_content(response) if isinstance(response, dict) else {}
        return {str(f.get("object") or "").casefold() for f in body.get("facts") or []
                if isinstance(f, dict) and f.get("predicate") == "name" and str(f.get("subject") or "") == "user"}

    @staticmethod
    def _says_nothing(meaning: Dict[str, Any], reply: Dict[str, Any]) -> bool:
        """'A dog is a dog': calling something itself tells nobody anything."""
        def head(part: Any) -> str:
            if not isinstance(part, dict):
                return ""
            entity = part.get("entity") if isinstance(part.get("entity"), dict) else part
            return str(entity.get("noun") or entity.get("name") or entity.get("pronoun") or "").casefold()
        if str(meaning.get("verb") or "") == "be":
            subject, complement = head(meaning.get("subject")), head(meaning.get("complement"))
            if subject and subject == complement:
                return True
        complement = reply.get("predicative_complement") or {}
        assertion = reply.get("assertion") or {}
        theme = str(assertion.get("theme_concept") or reply.get("topic_head") or "").casefold()
        return bool(theme) and theme == str(complement.get("lemma") or "").casefold()

    # Who a sentence's doer is, seen from the other speaker's side.
    _TURNED = {"i": "you", "me": "you", "you": "i", "we": "you", "us": "you"}

    # His words for who, said from her side ("my sister" -> "your sister"; his
    # "we" is still "we": the two of them).
    _HER_SIDE = {"i": "you", "me": "you", "my": "your", "mine": "yours", "you": "i", "your": "my",
                 "we": "we", "us": "we", "our": "our"}

    def _subject_words(self, reading: Dict[str, Any], turn: bool = False) -> set:
        """Who a statement is about, as words: everything before its verb that
        names someone ("my sister and I" -> {my, sister, i}), including whose."""
        out = set()
        tokens = [t for t in reading.get("tokens") or [] if t.get("kind") != "punctuation"]
        while tokens and tokens[0].get("kind") in ("auxiliary", "modal", "wh", "negation"):
            tokens = tokens[1:]  # a question: "Did your dog die?" -> "your dog"
        has_head, before = False, ""
        for token in tokens:
            kind = token.get("kind")
            if kind in ("verb", "auxiliary", "modal"):
                break
            if has_head and before != "and" and kind in ("determiner", "possessive", "pronoun", "proper_noun"):
                break  # "Is your dog Rex?": "Rex" is what's asked, not who it's about
            before = str(token.get("surface") or "").casefold()
            if kind in ("pronoun", "noun", "proper_noun"):
                has_head = True
            word = str(token.get("surface") if kind in ("pronoun", "proper_noun", "determiner", "possessive")
                       else token.get("lemma") or token.get("surface") or "").casefold()
            if kind in ("pronoun", "noun", "proper_noun") or word in self._HER_SIDE \
                    or kind == "possessive":
                out.add(self._HER_SIDE.get(word, word) if turn else word)
        return out - {"a", "an", "the", "and"}

    def _doer(self, reading: Dict[str, Any], turn: bool = False) -> str:
        for token in reading.get("tokens") or []:
            kind = token.get("kind")
            if kind in ("verb", "auxiliary", "modal"):
                break
            if kind in ("pronoun", "noun", "proper_noun"):
                word = str(token.get("lemma") or token.get("surface") or "").casefold()
                return self._TURNED.get(word, word) if turn else word
        return ""

    def _moved_description(self, meaning: Dict[str, Any], reply: Dict[str, Any], heard: str) -> Optional[str]:
        """A describing word he used stays with what he described: in "I have a
        new car" the car is new, not him ("Are you new?")."""
        complement = meaning.get("complement") if isinstance(meaning.get("complement"), dict) else {}
        adjectives = [str(a).casefold() for a in complement.get("adjectives") or []]
        if str(meaning.get("verb") or "") != "be" or not adjectives:
            return None
        his = [t for t in self._analyze(str(heard)).get("tokens") or [] if t.get("kind") != "punctuation"]
        for i, token in enumerate(his):
            if token.get("kind") != "adjective" or str(token.get("lemma") or "").casefold() not in adjectives:
                continue
            after = his[i + 1] if i + 1 < len(his) else {}
            if after.get("kind") in ("noun", "proper_noun"):
                described = str(after.get("lemma") or "").casefold()
                if described and described != self._topic(reply):
                    return (f"he said the {described} is {token.get('lemma')}, "
                            f"not {self._topic(reply) or 'that'}")
        return None

    def _topic(self, reading: Dict[str, Any], turn: bool = False) -> str:
        """Who or what a sentence is about: the last name, noun or pronoun before
        its verb ("my sister Cleo is..." -> cleo); in a question, after the
        helper verb that opens it ("Is Cleo a painter?" -> cleo)."""
        tokens = [t for t in reading.get("tokens") or [] if t.get("kind") != "punctuation"]
        question = bool(tokens) and tokens[0].get("kind") in ("auxiliary", "modal", "wh")
        while tokens and tokens[0].get("kind") in ("auxiliary", "modal", "wh"):
            tokens = tokens[1:]
        found = ""
        for token in tokens:
            kind = token.get("kind")
            if kind in ("verb", "auxiliary", "modal"):
                break
            if kind in ("pronoun", "noun", "proper_noun"):
                found = str(token.get("surface") if kind == "proper_noun" else
                            token.get("lemma") or token.get("surface") or "").casefold()
                if question:
                    break  # "Are you Cleo?": the one asked about comes first
        return self._TURNED.get(found, found) if turn else found

    def _says_back(self, reply: Dict[str, Any], his: Dict[str, Any]) -> bool:
        """Her reply says what he told her, from her side: the same doer
        (his "I" is her "you"), the same content words, the same yes/no."""
        if not reply or not his:
            return False
        if reply.get("parts"):
            # Her reply says several things: each must be something he said.
            return all(self._says_back(self._analyze(part), his) for part in reply["parts"])
        if his.get("parts"):
            # A long sentence is several statements: saying back is saying one of them.
            return any(self._says_back(reply, self._analyze(part)) for part in his["parts"])
        said, told = self._content_lemmas(reply), self._content_lemmas(his)
        if (reply.get("tense") or "now") != (his.get("tense") or "now"):
            return False  # "it was cold" isn't said back as "it is cold"
        mine = (reply.get("clauses") or [{}])[0]
        theirs = (his.get("clauses") or [{}])[0]
        if bool(mine.get("copular")) != bool(theirs.get("copular")) or (
                not mine.get("copular") and str(mine.get("predicate") or mine.get("predicate_surface") or "")
                != str(theirs.get("predicate") or theirs.get("predicate_surface") or "")):
            return False  # "A sister is a store" doesn't say "my sister went to the store"
        # All of it, or part of it about the same one ("Joe is a farmer" for
        # "my uncle Joe is a farmer"): nothing she adds that he didn't say.
        if not told or not said or not said <= told or (said != told and len(said) < 2):
            return False
        before_verb = []
        for t in his.get("tokens") or []:
            if t.get("kind") in ("verb", "auxiliary", "modal"):
                break
            before_verb.append(str(t.get("surface") or "").casefold())
        both_of_them = bool({"i", "me"} & set(before_verb)) and "you" in before_verb
        mine_who, his_who = self._subject_words(reply), self._subject_words(his, turn=True)
        if both_of_them:
            his_who = (his_who - {"i", "you", "me"}) | {"we"} if mine_who == {"we"} else his_who
        if mine_who != his_who:
            # Said back about the same one, the way he said it: "your dog", not
            # "a dog" for "my dog"; "you and your sister" for "my sister and I".
            return False
        if mine.get("copular"):
            # What she says it is must be what he said it is: "Lily is Ben"
            # doesn't say "Lily is older than Ben".
            def what_it_is(r: Dict[str, Any]) -> str:
                seen_verb = False
                for t in r.get("tokens") or []:
                    kind = t.get("kind")
                    if kind in ("verb", "auxiliary"):
                        seen_verb = True
                    elif seen_verb and kind in ("noun", "proper_noun", "adjective", "adverb"):
                        return str(t.get("lemma") or t.get("surface") or "").casefold()
                return ""
            if what_it_is(reply) != what_it_is(his):
                return False
        negative = lambda r: str((r.get("assertion") or {}).get("polarity") or "") == "negative" or any(
            t.get("kind") == "negation" for t in r.get("tokens") or [])
        return negative(reply) == negative(his)

    def _calls_someone_a_thing(self, meaning: Dict[str, Any]) -> Optional[str]:
        """"Are you a music?": a person is a person-kind of thing (a doctor, a
        fool), never music or a table. The dictionary files each noun."""
        if str(meaning.get("verb") or "") != "be":
            return None
        subject = meaning.get("subject") if isinstance(meaning.get("subject"), dict) else {}
        complement = meaning.get("complement") if isinstance(meaning.get("complement"), dict) else {}
        noun = str(complement.get("noun") or "")
        person = subject.get("ref") in ("speaker", "addressee") or bool(subject.get("name")) \
            or subject.get("pronoun") in ("he", "she", "we")
        if subject.get("name") and person:
            # A name isn't always a person: what she knows about it says ("Rex is a dog").
            from reasoning_understanding import kind_of
            for fact in self._facts_for(str(subject["name"]), self.__dict__.get("_reviewing_for", "default")):
                if str(fact.get("subject") or "").casefold() == str(subject["name"]).casefold() \
                        and fact.get("predicate") == "is_a" and kind_of(str(fact.get("object") or "")) not in (None, "person"):
                    person = False
                    break
        if person and noun and not self._noun_is_person(noun):
            return f"a person isn't {noun}: the dictionary doesn't have '{noun}' as a kind of person"
        return None

    def _dropped_what_he_said_it_about(self, meaning: Dict[str, Any], user_input: str) -> Optional[str]:
        """She reuses his verb without the someone/something he used it on
        ("I hate you" -> "You hate."): that's a different meaning of the verb."""
        verb = str(meaning.get("verb") or "").casefold()
        if not verb or verb in ("be", "have", "do") or meaning.get("object") or meaning.get("complement"):
            return None  # ("stay home": what came after the verb is still there, as a complement)
        tokens = [t for t in self._analyze(user_input).get("tokens") or [] if t.get("kind") != "punctuation"]
        for idx, token in enumerate(tokens[:-1]):
            if token.get("kind") == "verb" and str(token.get("lemma") or "").casefold() == verb \
                    and tokens[idx + 1].get("kind") in ("pronoun", "noun", "proper_noun", "determiner", "possessive"):
                return verb
        return None

    def _asks_how(self, text: str) -> bool:
        """A "how" question: asking about the manner or state of something."""
        return any(str(t.get("lemma") or t.get("surface") or "").casefold() == "how"
                   for t in self._analyze(text).get("tokens") or [])

    def review_reply(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Does this reply make sense? Returns {"ok": bool, "reason": str}."""
        sentence = str(payload.get("sentence") or "").strip()
        situation = str(payload.get("situation") or "statement")
        meaning = payload.get("meaning") if isinstance(payload.get("meaning"), dict) else {}
        user_input = str(payload.get("user_input") or "")
        user_id = str(payload.get("user_id") or "default")
        self._reviewing_for = user_id

        def no(reason: str, wanted: str = "") -> Dict[str, Any]:
            # wanted: the kind of reply that would fit (never the words).
            return {"ok": False, "reason": reason, "wanted": wanted}

        if payload.get("chosen_silence"):
            if situation == "greeting":
                return no("he greeted her and she stayed quiet", "greet_back")
            if situation == "question":
                return no("he asked her something and she stayed quiet", "not_silence")
            if situation == "emotional_share":
                return no("he shared how he feels and she stayed quiet", "respond_to_feeling")
            if situation == "farewell":
                return no("he said goodbye and she stayed quiet", "farewell_back")
            return {"ok": True, "reason": "staying quiet fits here"}
        if not sentence:
            return no("nothing was said")
        problems = [str(p) for p in payload.get("problems") or []]
        if problems:
            return no("the sentence is incomplete: " + "; ".join(problems))
        words = re.findall(r"[A-Za-z']+", sentence.casefold())
        for first, second in zip(words, words[1:]):
            if first == second:
                return no(f"gibberish: the word '{first}' is repeated")

        reply = self._analyze(sentence)
        if not reply:
            return no("could not read the reply to check it")
        understood = (self.__dict__.get("_understood") or {}).get(user_id) or {}
        misread = understood.get("reading_problems") if str(understood.get("said") or "").strip() \
            == user_input.strip() else None
        if misread and self._content_lemmas(reply) & self._content_lemmas(self._analyze(user_input)):
            # Language misread what he said; built from that reading, the reply
            # carries the mistake ("Does bark dog bark?" for "dogs bark").
            return no("Language misread what he said (" + "; ".join(
                f"'{m['word']}' is {m['fits_better']}, not {m['read_as']}" for m in misread)
                + "), so a reply built from it repeats the mistake", "misheard")
        names = self._names_in(meaning)
        taught = set(re.findall(r"[a-z']+", str(payload.get("expected_reply") or "").casefold()))
        # Words she was taught to say ("hey") aren't gibberish even if the dictionary lacks them.
        unknown = [w for w in reply.get("unknown_words") or [] if w.casefold() not in names
                   and w.casefold() not in taught]
        if unknown:
            return no("gibberish: unknown word(s) " + ", ".join(unknown))

        if self._says_nothing(meaning, reply):
            return no("it says nothing: it calls a thing itself")
        rare = self._rare_stand_in(meaning, reply)
        if rare:
            used, meant, pos = rare
            return no(f"'{used}' is a rare word for '{meant}'; it doesn't sound natural",
                      f"plain_word:{pos}:{meant}")

        reply_is_question = sentence.endswith("?") or reply.get("speech_act") == "question"
        purpose = str(meaning.get("_purpose") or "")
        act = str(meaning.get("act") or "")
        understood = (self.__dict__.get("_understood") or {}).get(user_id) or {}
        if understood.get("said", "").strip() != user_input.strip():
            understood = {}
        if act in ("state", "ask"):
            # Is there a reason, in what's going on, to say something unkind to him?
            hers = self._ask_lobe("social_context", "how_meant", {"text": sentence})
            his_now = self._analyze(str(payload.get("resolved_input") or user_input))
            his_words = self._content_lemmas(his_now) | {str(t.get("surface") or "").casefold()
                                                         for t in his_now.get("tokens") or []}
            asked_words = {str(t.get("surface") or "").casefold() for t in reply.get("tokens") or []
                           if t.get("kind") in self._CONTENT_KINDS}
            said_back_his = self._says_back(reply, his_now) or (
                act == "ask" and bool(asked_words) and asked_words <= his_words)  # "Are you tired?" for "I am tired"
            if hers.get("about") == "her" and float(hers.get("good") or 0.0) < -0.2 and not said_back_his:
                # (Saying back what he told her, "you are tired", isn't calling him anything.)
                social = (self.__dict__.get("_social_reads") or {}).get(user_id) or {}
                feeling = understood.get("her_feeling") or {}
                provoked = str(social.get("move") or "") == "insult" or (
                    feeling.get("fits_now") and str(feeling.get("feeling") or "") in
                    ("hurt", "angry", "frustrated", "contemptuous", "disgusted"))
                if not provoked:
                    return no("there's no reason to say something unkind to him: nothing he said or did "
                              "calls for it" + (f" (he {social.get('move')})" if social.get("move") else ""))
        her_feeling = str(payload.get("her_feeling") or "").strip()
        if purpose == "own_feeling" and her_feeling:
            said_feeling = {str(w).casefold() for w in words}
            if her_feeling.casefold() not in said_feeling \
                    and not self._feeling_words_meet({her_feeling.casefold()}, said_feeling):
                return no(f"she doesn't feel that right now; she feels {her_feeling}", "say_own_feeling")
        first = next((t for t in reply.get("tokens") or [] if t.get("kind") != "punctuation"), {})
        first_senses = {str(s.get("synset_id")) for s in first.get("senses") or []}
        addressee = meaning.get("addressee") if isinstance(meaning.get("addressee"), dict) else {}
        if act in ("greet", "farewell") and addressee.get("name") \
                and str(addressee["name"]).casefold() not in self._his_names(user_id):
            return no(f"she doesn't know '{addressee['name']}' is his name", "no_name")
        nonsense = self._verb_makes_sense(meaning) if act in ("state", "ask") else None
        if nonsense:
            return no("it doesn't make sense: " + nonsense,
                      "complete_it" if "needs who or what" in nonsense else "")
        moved = self._moved_description(meaning, reply, payload.get("resolved_input") or user_input) \
            if act in ("state", "ask") else None
        if moved:
            return no(moved)
        called = self._calls_someone_a_thing(meaning) if act in ("state", "ask") else None
        if called:
            return no(called)
        dropped = self._dropped_what_he_said_it_about(meaning, user_input) if act in ("state", "ask") else None
        if dropped:
            return no(f"he said '{dropped}' about someone or something; with nothing after it, "
                      "it means something else", "complete_it")
        subject = meaning.get("subject") if isinstance(meaning.get("subject"), dict) else {}
        if act == "ask" and subject.get("ref") == "speaker" and purpose != "admit_unknown":
            return no("she's asking him about herself, which he can't know better than she does",
                      "not_about_herself")
        if purpose == "own_feeling" and (act == "ask" or reply_is_question):
            return no("she knows how she feels; asking him about it doesn't make sense", "state_not_ask")
        if act == "greet" and situation != "greeting":
            return no("he didn't greet her, so greeting him doesn't fit", "not_greeting")
        if act == "farewell" and situation != "farewell":
            return no("he isn't leaving, so saying goodbye doesn't fit", "not_farewell")
        if situation == "farewell":
            if act != "farewell" or self._FAREWELL_SENSE not in first_senses:
                return no("he said goodbye and the reply doesn't say goodbye back", "farewell_back")
        if situation == "social_reply":
            # Social context's belief says what this moment calls for.
            expected = str(payload.get("expected_reply") or "")
            want = self._content_lemmas(self._analyze(expected)) if expected else set()
            if expected and not want:
                # Words the dictionary doesn't have ("hey"): the words themselves.
                same = re.findall(r"[a-z']+", expected.casefold()) == re.findall(r"[a-z']+", sentence.casefold())
                if not same:
                    return no(f"he made a social move; what she believes fits is '{expected}'", "say_expected")
            elif want and (self._content_lemmas(reply) != want or sentence.endswith("?")):
                return no(f"he made a social move; what she believes fits is '{expected}'", "say_expected")
            return {"ok": True, "reason": f"it's what she believes fits ('{expected}')"}
        if situation in ("statement", "emotional_share"):
            # (Sharing a feeling is also telling her something: what she says
            # back or asks about it is checked the same way.)
            said = self._content_lemmas(reply)
            his = self._content_lemmas(self._analyze(str(payload.get("resolved_input") or user_input)))
            used = meaning.get("_fact") if isinstance(meaning.get("_fact"), dict) else None
            if act == "state" and purpose == "own_feeling" and situation == "emotional_share":
                pass  # how she feels about what he shared is hers to say (checked below)
            elif act == "state":
                # Saying back what he just told her shows she took it in; any other
                # claim is something she doesn't know is true.
                if purpose == "own_feeling" and self._topic(self._analyze(user_input), turn=True) in ("i", "me"):
                    # He said something about her ("you are stupid"); how she feels
                    # about it is hers to say, and true.
                    return {"ok": True, "reason": "she says how what he said about her makes her feel"}
                if self._topic(reply) in ("i", "me") and purpose != "own_feeling":
                    # "You are stupid" -> "I am stupid." would be her claiming it
                    # about herself on his word.
                    return no("saying it back would be her claiming it about herself", "not_about_herself")
                resolved = str(payload.get("resolved_input") or "")
                said_back = self._says_back(reply, self._analyze(user_input)) or (
                    bool(resolved) and resolved != user_input
                    and self._says_back(reply, self._analyze(resolved)))  # "Tom loves the dog" for "he loves it"
                if not said_back and (not used or not self._fact_fits(used, user_input)):
                    return no("she's claiming something she doesn't know; she can say back what he "
                              "told her or ask about it", "restate_or_ask")
            elif act == "ask" and his and not (said <= his) and not (
                    {str(t.get("surface") or "").casefold() for t in reply.get("tokens") or []
                     if t.get("kind") in self._CONTENT_KINDS}
                    <= {str(t.get("surface") or "").casefold()
                        for t in self._analyze(str(payload.get("resolved_input") or user_input)).get("tokens") or []}):
                # (the words as he wrote them count too: "tired" read two ways is still his word)
                # Asking back uses what he just said, nothing else ("Ben is not
                # tall" -> not "Is Ben a pilot?").
                return no("the question isn't about what he said", "about_what_he_said")
            elif act == "ask" and self._analyze(user_input).get("tense") != reply.get("tense") \
                    and self._analyze(user_input).get("tense") in ("past", "future"):
                # "I went to Denver": asking back keeps it in the past ("Did you go...?").
                return no("the question changes when it happened", "about_what_he_said")
            elif act == "ask":
                # Asking back is about the one he talked about ("Is Cleo a
                # painter?"), not someone else ("Are you Cleo?").
                his_reading = self._analyze(str(payload.get("resolved_input") or user_input))
                parts = his_reading.get("parts") or []
                asked_parts = [self._content_lemmas(self._analyze(q)) for q in reply.get("parts") or []] or [said]
                if parts and not all(any(a <= self._content_lemmas(self._analyze(p)) for p in parts)
                                     for a in asked_parts):
                    # "I like cats and I hate dogs": not "Do you like dogs?"
                    return no("the question mixes two different things he said", "about_what_he_said")
                # The question is about the one he said did it, said his way:
                # "my dog died" -> "Did your dog die?", not "Do you die?" or "a dog".
                questions = [self._analyze(q) for q in reply.get("parts") or []] or [reply]
                statements = [self._analyze(p) for p in parts] or [his_reading]
                for q in questions:
                    asked = self._content_lemmas(q)
                    match = next((st for st in statements if asked <= self._content_lemmas(st)), statements[0])
                    asked_who, said_who = self._subject_words(q), self._subject_words(match, turn=True)
                    his_words = {str(t.get("surface") or "").casefold() for t in match.get("tokens") or []}
                    if asked_who and all(w in his_words for w in asked_who) and any(
                            str(t.get("kind")) == "proper_noun" and str(t.get("surface") or "").casefold() in asked_who
                            for t in q.get("tokens") or []):
                        continue  # "Is Rex a dog?" for "my dog is named Rex": Rex is his dog
                    if asked_who and said_who and asked_who != said_who:
                        return no(f"he talked about {' '.join(sorted(said_who))}, and the question is about "
                                  f"{' '.join(sorted(asked_who))}", "about_what_he_said")
        if situation == "greeting":
            if not self._has_greeting(reply):
                return no("he greeted her and the reply does not greet him back", "greet_back")
            first = next((t for t in reply.get("tokens") or [] if t.get("kind") != "punctuation"), {})
            if not any(sense.get("synset_id") == self._GREETING_SENSE for sense in first.get("senses") or []):
                return no("the greeting word is used as a thing in the sentence, not to greet him", "greet_back")
        elif situation == "question":
            # Who he/she/they mean, as Language worked it out ("her dog" -> "Ariana's dog").
            question = str(payload.get("resolved_input") or user_input)
            if reply_is_question:
                return no("he asked a question and the reply asks another question instead of answering", "answer_not_ask")
            used = meaning.get("_fact") if isinstance(meaning.get("_fact"), dict) else None
            for other in meaning.get("_facts") or []:
                if isinstance(other, dict) and not self._fact_fits(other, question):
                    return no("one of the things in the reply is about something else ("
                              + " ".join(sorted(self._fact_words(other))) + "), not what he asked", "about_what_he_asked")
            if used and not self._fact_fits(used, question):
                return no("the fact in the reply is about something else ("
                          + " ".join(sorted(self._fact_words(used))) + "), not what he asked",
                          "other_fact_or_dont_know")
            remembered = self._remembered_about(question, user_id)
            if not remembered and question != user_input:
                # Memory brought things up for his words ("he"); ask it about who he meant.
                remembered = {"facts": self._facts_for(question, user_id)}
            known = [f for f in remembered.get("facts") or []
                     if isinstance(f, dict) and self._fact_fits(f, question)]
            if known and not meaning.get("_fact"):
                best = known[0]
                return no("she remembers something about this (" + str(best.get("content") or best.get("object"))
                          + ") and the reply doesn't use it", "use_memory")
            asked_her = any(str(t.get("lemma") or t.get("surface") or "").casefold() == "you"
                            for t in self._analyze(user_input).get("tokens") or [])
            if purpose == "own_feeling" and not asked_her:
                return no("he didn't ask how she feels", "say_dont_know")
            her_feeling = str(payload.get("her_feeling") or "").strip()
            if purpose == "admit_unknown" and asked_her and her_feeling \
                    and not known and self._asks_how(user_input):
                return no(f"he asked how she is and she knows how she feels ({her_feeling})",
                          "say_own_feeling")
            if not meaning.get("_fact") and purpose not in ("admit_unknown", "own_feeling"):
                # Answering needs knowing: use what she remembers, or say she doesn't know.
                return no("she doesn't know the answer, and the reply makes something up instead of saying so",
                          "say_dont_know")
            if purpose not in ("admit_unknown", "own_feeling") and not used:
                asked = self._content_lemmas(self._analyze(user_input))
                said = self._content_lemmas(reply)
                if asked and not (asked & said):
                    return no("the reply does not answer what he asked about ("
                              + ", ".join(sorted(asked)) + ")")
        elif situation == "emotional_share":
            said_by_him = self._analyze(user_input)
            if not any(str(t.get("lemma") or "").casefold() in {"i", "me", "myself"}
                       for t in said_by_him.get("tokens") or []):
                return no("he did not say he feels that; the feeling is about something else")
            felt = {str(w).casefold() for w in meaning.get("_feeling_words") or []}
            if felt and purpose != "own_feeling" and not (felt & {w.casefold() for w in words}) \
                    and not self._feeling_words_meet(felt, {w.casefold() for w in words}):
                return no("he shared a feeling and the reply does not respond to it", "respond_to_feeling")
            subject = meaning.get("subject") if isinstance(meaning.get("subject"), dict) else {}
            if subject.get("ref") != "addressee" and felt & {w.casefold() for w in words}:
                who = "her" if subject.get("ref") == "speaker" else "something else"
                return no(f"the reply puts his feeling on {who}; it should be about him", "about_him")

        fact = meaning.get("_fact") if isinstance(meaning.get("_fact"), dict) else None
        if fact:
            if not self._fact_in_memory(fact, user_id):
                return no("the reply states something memory does not hold")
            # "user's key" is said to him as "your key".
            thing = str(fact.get("object", "")).casefold().replace("user's ", "")
            if thing != "(nothing)" and thing not in sentence.casefold():
                return no(f"the reply leaves out the fact ({fact.get('object')})")
        feeling = understood.get("her_feeling") or {}
        if feeling.get("note"):
            return {"ok": True, "reason": "makes sense; " + str(feeling["note"])}
        return {"ok": True, "reason": "makes sense"}

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if message.get("type") == "health":
            return {"status": "success", "content": {"healthy": self.running}}
        if message.get("type") == "attention_focus":
            # Soft ack from AttentionLobe.route_focus — live think also gets attention.
            payload = message.get("content", {}) if isinstance(message.get("content"), dict) else {}
            self._last_attention_focus = payload
            return {
                "status": "success",
                "content": {"acknowledged": True, "focus": payload.get("focus")},
            }
        if message.get("type") == "remembered":
            payload = message.get("content", {}) if isinstance(message.get("content"), dict) else {}
            return self._hear_remembered(payload)
        if message.get("type") == "social_read":
            payload = message.get("content", {}) if isinstance(message.get("content"), dict) else {}
            return self._hear_social(payload)
        if message.get("type") in ("work_out", "think_through"):
            # Another lobe (Autonomous Thinking, Executive Control...) asks her to
            # think something through: what she knows about it, what follows, why.
            from reasoning_understanding import Understanding
            payload = message.get("content", {}) if isinstance(message.get("content"), dict) else {}
            question = str(payload.get("question") or payload.get("text") or "").strip()
            user_id = str(payload.get("user_id") or "default")
            if not question:
                return {"status": "error", "message": "work_out needs a question"}
            facts = self._facts_for(question, user_id)
            thinker = Understanding(self._ask_lobe)
            thinker._user_id = user_id
            reading = self._analyze(question)
            known = thinker.recall_around(question, facts, user_id)
            result = {"question": question, "knows": [f.get("content") or f"{f.get('subject')} {f.get('predicate')} {f.get('object')}"
                                                      for f in facts[:6]],
                      "conclusions": thinker.conclude(known, user_id), "explanations": thinker.explain(known)}
            problem = thinker.problem_in(reading, facts)
            if problem:
                result["problem"] = problem
            if not facts:
                result["unsure"] = "she doesn't know anything about this yet"
            return {"status": "success", "content": result}
        if message.get("type") == "get_understanding":
            payload = message.get("content", {}) if isinstance(message.get("content"), dict) else {}
            return {"status": "success",
                    "content": (self.__dict__.get("_understood") or {}).get(str(payload.get("user_id") or "default"), {})}
        if message.get("type") == "review_reply":
            payload = message.get("content", {}) if isinstance(message.get("content"), dict) else {}
            verdict = self.review_reply(payload)
            return {"status": "success", "content": verdict}
        if message.get("type") != "think":
            return {"status": "error", "message": "Unknown message type", "content": {}}

        payload = message.get("content", {})
        direct_input = payload.get("input", {}) if isinstance(payload, dict) else {}
        if not isinstance(direct_input, dict):
            direct_input = {}
        direct_input = dict(direct_input)
        direct_input["memory_context"] = self._prepare_memory_context(direct_input)
        user_input = direct_input.get("user_input", "")
        user_input = user_input if isinstance(user_input, str) else ""
        try:
            self._understand_moment(user_input, str(direct_input.get("user_id") or "default"), direct_input)
        except Exception as error:
            print(f"⚠️  Reasoning: couldn't put together what's going on ({error})")
        understanding = direct_input.get("understanding", {})
        understanding = understanding if isinstance(understanding, dict) else {}
        memory_context = direct_input.get("memory_context", {})
        raw_memories = (
            memory_context.get("memories", memory_context.get("results", []))
            if isinstance(memory_context, dict)
            else []
        )
        raw_facts = (
            memory_context.get("facts", [])
            if isinstance(memory_context, dict)
            else []
        )
        # Fold durable facts into the memory list before cleaning.
        if isinstance(raw_facts, list):
            for fact in raw_facts:
                if not isinstance(fact, dict):
                    continue
                content = fact.get("content") or fact.get("text")
                pred = str(fact.get("predicate", "") or "")
                obj = str(fact.get("object", "") or "")
                sub = str(fact.get("subject", "") or "user")
                if pred and obj:
                    # Always prefer correct readable formatting over mangled rows.
                    content = format_predicate_fact(pred, obj, sub)
                if content:
                    raw_memories = list(raw_memories) + [
                        {**fact, "role": "fact", "content": content}
                    ]
        memories = self._clean_memories(raw_memories, user_input)
        evidence = self._evidence(memories, user_input)
        emotional_state = direct_input.get("emotion_result", {})
        emotional_state = emotional_state if isinstance(emotional_state, dict) else {}
        attention_payload = direct_input.get("attention", {})
        attention_payload = attention_payload if isinstance(attention_payload, dict) else {}
        # Prefer soft-routed Attention.route_focus when present (post-Executive re-route).
        last_focus = getattr(self, "_last_attention_focus", None)
        if isinstance(last_focus, dict) and last_focus.get("focus"):
            attention_payload = dict(attention_payload)
            attention_payload["focus"] = last_focus.get("focus")
            if last_focus.get("focus_text") is not None:
                attention_payload["focus_text"] = last_focus.get("focus_text")
            if last_focus.get("score") is not None:
                attention_payload["focus_score"] = last_focus.get("score")
            if last_focus.get("source") is not None:
                attention_payload["focus_source"] = last_focus.get("source")
        pattern_result = direct_input.get("pattern_result", {})
        if not isinstance(pattern_result, dict):
            pattern_result = {}
        # Prefer teaching ack / fact answers over legacy composition noise.
        teaching = self._teaching_ack(user_input)
        fact_structures = structures_from_grounded_memories(user_input or "", evidence)
        fact_answer = None if fact_structures else self._answer_from_facts(evidence, user_input)
        usable = None  # (no old-engine composition: Language builds every reply)
        # No canned comfort lines: Language builds every reply (Reasoning reviews it).
        empathic = None
        pattern_answer = None
        if not teaching and not fact_structures and not fact_answer and not empathic:
            pattern_answer = self._answer_from_patterns(pattern_result, user_input)
        answer = teaching or fact_answer or empathic or pattern_answer or usable
        # If usable/teaching still produced finished fact prose, prefer structures.
        if not fact_structures and isinstance(answer, str) and answer.strip():
            stripped = prose_answer_to_structures(answer)
            # Only strip when the whole answer parses as fact structures (not acks).
            if stripped and not str(answer).strip().lower().startswith("got it"):
                fact_structures = stripped
                answer = None
        semantic_input = {
            "intent": understanding.get("intent", "conversation"),
            "certainty": understanding.get("confidence", 0.5),
            "emotion": emotional_state.get("current_emotion", "neutral"),
            "memory_context": evidence,
        }
        if pattern_result:
            semantic_input["pattern_result"] = pattern_result
            significant = self._significant_patterns(pattern_result)
            if significant:
                semantic_input["discovered_patterns"] = significant
        if attention_payload:
            semantic_input["attention_focus"] = attention_payload.get("focus")
            semantic_input["attention_focus_text"] = attention_payload.get("focus_text")
            semantic_input["attention_ranked"] = list(attention_payload.get("ranked") or [])[:5]
        representation_result = direct_input.get("representation_result") or {}
        if isinstance(representation_result, dict) and representation_result.get("status") == "success":
            semantic_input["representation_concept_ids"] = list(
                representation_result.get("concept_ids") or []
            )
            semantic_input["representation_referent_ids"] = list(
                representation_result.get("referent_ids") or []
            )
            semantic_input["input_representation_proposition_ids"] = list(
                representation_result.get("proposition_ids") or []
            )
            semantic_input["representation_highly_active"] = list(
                representation_result.get("highly_active_concepts") or []
            )[:12]
            if isinstance(representation_result.get("language_understanding"), dict):
                semantic_input["language_understanding"] = representation_result[
                    "language_understanding"
                ]
        if fact_structures:
            # Reasoning owns grounded meaning — Language owns sentence construction.
            semantic_input["grounded_structures"] = fact_structures
            semantic_input["propositions"] = fact_structures
            semantic_input["certainty"] = min(
                float(semantic_input.get("certainty") or 0.5),
                min(float(s.get("certainty", 1.0) or 1.0) for s in fact_structures),
            )
            # Do not hand Language finished prose for these facts.
            semantic_input.pop("answer", None)
            semantic_input.pop("conclusion", None)
        elif answer is not None:
            semantic_input.update(
                {"answer": answer, "conclusion": answer, "propositions": [answer]}
            )
        semantic_input = self._route_expression_context(semantic_input, direct_input)
        structures = semantic_input.get("grounded_structures")
        if isinstance(structures, list) and structures:
            user_id = str(direct_input.get("user_id") or "default")
            registered = self._register_grounded_structures(
                structures,
                turn_id=str(message.get("message_id")) if message.get("message_id") else None,
                user_id=user_id,
            )
            if registered:
                semantic_input["representation_proposition_ids"] = [
                    str(item.get("proposition_id") or item.get("id"))
                    for item in registered
                    if item.get("proposition_id") or item.get("id")
                ]
                semantic_input["representation_propositions"] = registered
                semantic_input["representation_contract"] = "shared_representation_native"
                semantic_input["representation_user_id"] = user_id

        return {
            "status": "success",
            "content": {
                "thinking": (self.__dict__.get("_understood") or {}).get(str(direct_input.get("user_id") or "default"), {}),
                "semantic_input": semantic_input,
                "composed_response": None,
                "native_semantics_finalized": True,
            },
            "native_semantics_finalized": True,
        }

    def shutdown(self) -> None:
        self.running = False


# Legacy alias — old name was theater.
DirectMaximumSophisticationAdapter = DirectReasoningAdapter
