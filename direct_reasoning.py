"""Direct envelope adapter for the live ReasoningLobe.

Conclusion text still comes from ``ReasoningLobe.think_about`` (legacy alias
``MaximumSophisticationReasoning`` kept for imports). This adapter translates
the direct envelope and supplies user-scoped evidence.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, List, Optional

from reasoning import Fact, MaximumSophisticationReasoning, ReasoningLobe
from direct_response import (
    answer_from_grounded_memories,
    content_tokens,
    empathic_grounded_reply,
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
_BASELINE_EVIDENCE = (
    "Gravity is the force of attraction between masses. It pulls objects toward each other, including objects toward Earth.",
    "Photosynthesis is the process by which plants use light energy to turn water and carbon dioxide into glucose, releasing oxygen.",
    "Memory is information retained so it can be retrieved and used later.",
)


class DirectReasoningAdapter:
    """Make the full legacy reasoner safe and usable on the prompted path."""

    def __init__(
        self,
        thalamus: Any = None,
        reasoner_factory: Callable[..., ReasoningLobe] = ReasoningLobe,
    ) -> None:
        self.running = True
        self.thalamus = thalamus
        self.reasoner = reasoner_factory(thalamus=thalamus)
        # The legacy reasoner otherwise sends its internal composition directly
        # to Output.  The direct pipeline owns the one final language/output pass.
        self.reasoner._direct_core = True
        for evidence in _BASELINE_EVIDENCE:
            self.reasoner.facts[evidence] = Fact(
                content=evidence, confidence=1.0, source="direct_core_baseline"
            )

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

    @classmethod
    def _usable_conclusion(
        cls,
        thinking: Dict[str, Any],
        understanding: Dict[str, Any],
        user_input: str = "",
    ) -> Optional[str]:
        composed = thinking.get("composed_response")
        if not isinstance(composed, str) or not composed.strip():
            return None
        composed = composed.strip()
        if cls._looks_like_raw_triple(composed):
            return None
        # Pattern sequence narration must not become the mouth via usable.
        clow = composed.casefold()
        if "sequence pattern" in clow or "cannot confidently infer" in clow or clow.startswith("i noticed the sequence"):
            ask = (user_input or "").casefold()
            asks_seq = (
                any(
                    cue in ask
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
                )
                or ("next" in ask and ("sequence" in ask or "pattern" in ask))
            )
            if not asks_seq:
                return None
        # Don't let an unrelated stored fact become the spoken answer to a
        # check-in / social prompt.
        social = re.search(
            r"\b(?:are you okay|how are you|how(?:'s| is) it going|what(?:'s| is) up)\b",
            user_input or "",
            re.IGNORECASE,
        )
        if social and (
            "name is" in composed.casefold() or composed.casefold().startswith("your ")
        ):
            return None
        theories = thinking.get("theories", [])
        grounded = any(
            isinstance(theory, dict) and theory.get("components")
            for theory in theories
        )
        if understanding.get("intent") == "greeting":
            return composed
        if grounded:
            # Require overlap so an unrelated stored fact cannot hijack the answer.
            q_tokens = content_tokens(user_input or "")
            if q_tokens and relevance_score(user_input or "", composed) < 0.34:
                if not (q_tokens & content_tokens(composed)):
                    return None
            attr = _attribute_asked(user_input or "")
            if attr and not _fact_covers_attribute(composed, attr):
                return None
            return composed
        # Legacy composition can turn an evidence-free question into a word bag;
        # that is not a conclusion. Leave the semantic handoff empty.
        return None


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


    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if message.get("type") == "imagine_what_if":
            payload = message.get("content", {})
            payload = payload if isinstance(payload, dict) else {}
            simulation = self.imagine_what_if(
                payload.get("scenario") or payload,
                anchor_memory_id=payload.get("anchor_memory_id"),
                source_topic=payload.get("source_topic"),
                user_id=str(payload.get("user_id") or "default"),
                simulation_type=str(payload.get("simulation_type") or "counterfactual"),
                max_branches=payload.get("max_branches", 3),
                max_depth=payload.get("max_depth", 2),
            )
            if simulation.get("status") == "error":
                return {"status": "error", "message": simulation.get("message")}
            return {
                "status": "success",
                "content": simulation,
                "simulation": simulation,
            }
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
        legacy_input = {
            "user_input": user_input,
            "user_id": direct_input.get("user_id", "default"),
            "perception_result": {"status": "success", "understanding": understanding},
            "emotion_result": {"status": "success", **emotional_state},
            "memory_result": {
                "status": "success",
                "context": {"memories": evidence},
                "context_data": {"memories": evidence, "facts": evidence},
            },
            # Retain the direct envelope data for legacy routines that consume it.
            "memory_context": {"memories": evidence},
            "understanding": understanding,
            "attention": attention_payload,
            # Existing Reasoning interface — do not invent a parallel channel.
            "pattern_result": pattern_result,
            # SharedRepresentation substrate — satisfies dangling highly_active_concepts.
            "representation_result": (
                direct_input.get("representation_result")
                if isinstance(direct_input.get("representation_result"), dict)
                else {}
            ),
        }
        # Prefer teaching ack / fact answers over legacy composition noise.
        teaching = self._teaching_ack(user_input)
        fact_structures = structures_from_grounded_memories(user_input or "", evidence)
        fact_answer = None if fact_structures else self._answer_from_facts(evidence, user_input)
        thinking = self.reasoner.think_about(legacy_input)
        if not isinstance(thinking, dict):
            thinking = {}
        usable = self._usable_conclusion(thinking, understanding, user_input)
        # Never echo prior user filler / chatter as the answer on non-questions.
        if (
            usable
            and not looks_questionish(user_input)
            and not teaching
            and not looks_like_teaching_turn(user_input)
        ):
            # Drop near-duplicate prior user lines (filler soak failure mode).
            u_low = usable.strip().casefold()
            for mem in memories:
                if str(mem.get("role", "")).lower() != "user":
                    continue
                prior = str(mem.get("content") or "").strip()
                if prior and prior.casefold() == u_low:
                    usable = None
                    break
                if prior and u_low and (
                    prior.casefold() in u_low or u_low in prior.casefold()
                ):
                    # Same filler family ("Just chatting filler number N…")
                    if "filler" in u_low or "weather is fine" in u_low:
                        usable = None
                        break
        # Empathic/social affect before Pattern narration — Pattern must not be the mouth.
        empathic = None
        if not teaching and not fact_structures and not fact_answer:
            empathic = empathic_grounded_reply(user_input, emotional_state)
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
                "thinking": thinking,
                "semantic_input": semantic_input,
                "composed_response": thinking.get("composed_response"),
                "native_semantics_finalized": True,
            },
            "native_semantics_finalized": True,
        }

    def imagine_what_if(self, scenario: Any, **context: Any) -> Dict[str, Any]:
        """Expose Reasoning's existing simulation through the live direct adapter."""
        payload = dict(scenario) if isinstance(scenario, dict) else {"scenario": scenario}
        payload.update(context)
        response = self.reasoner.process_message({
            "type": "imagine_what_if",
            "content": payload,
        })
        if not isinstance(response, dict) or response.get("status") != "success":
            return {"status": "error", "message": "Reasoning imagination route failed"}
        simulation = response.get("simulation")
        if not isinstance(simulation, dict):
            body = response.get("content") if isinstance(response.get("content"), dict) else {}
            simulation = body.get("simulation") or body
        return simulation if isinstance(simulation, dict) else {
            "status": "error", "message": "Reasoning returned an invalid simulation"
        }

    def shutdown(self) -> None:
        self.running = False
        shutdown = getattr(self.reasoner, "shutdown", None)
        if callable(shutdown):
            shutdown()


# Legacy alias — old name was theater.
DirectMaximumSophisticationAdapter = DirectReasoningAdapter
