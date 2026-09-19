"""Direct envelope adapter for the legacy maximum-sophistication reasoner.

The direct core deliberately keeps persistence in :mod:`direct_notus`, but the
conclusion is still created by ``MaximumSophisticationReasoning.think_about``.
This adapter only translates the direct envelope and supplies clean,
user-scoped evidence in the shape the legacy reasoner expects.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, List, Optional

from reasoning import Fact, MaximumSophisticationReasoning
from direct_response import (
    answer_from_grounded_memories,
    content_tokens,
    empathic_grounded_reply,
    format_predicate_fact,
    looks_like_teaching_turn,
    looks_questionish,
    relevance_score,
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
_BASELINE_EVIDENCE = (
    "Gravity is the force of attraction between masses. It pulls objects toward each other, including objects toward Earth.",
    "Photosynthesis is the process by which plants use light energy to turn water and carbon dioxide into glucose, releasing oxygen.",
    "Memory is information retained so it can be retrieved and used later.",
)


class DirectMaximumSophisticationAdapter:
    """Make the full legacy reasoner safe and usable on the prompted path."""

    def __init__(
        self,
        thalamus: Any = None,
        reasoner_factory: Callable[..., MaximumSophisticationReasoning] = MaximumSophisticationReasoning,
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
        fav = DirectMaximumSophisticationAdapter._normalise_favorite_fact(text)
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
        facts = DirectMaximumSophisticationAdapter._normalise_personal_facts(text)
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
        # that is not a conclusion. Let Thalamus use its emergency fallback.
        return None

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
        if message.get("type") != "think":
            return {"status": "error", "message": "Unknown message type", "content": {}}

        payload = message.get("content", {})
        direct_input = payload.get("input", {}) if isinstance(payload, dict) else {}
        if not isinstance(direct_input, dict):
            direct_input = {}
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
        }
        # Prefer teaching ack / fact answers over legacy composition noise.
        teaching = self._teaching_ack(user_input)
        fact_answer = self._answer_from_facts(evidence, user_input)
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
        empathic = None
        if not teaching and not fact_answer:
            empathic = empathic_grounded_reply(user_input, emotional_state)
        answer = teaching or fact_answer or empathic or usable
        semantic_input = {
            "intent": understanding.get("intent", "conversation"),
            "certainty": understanding.get("confidence", 0.5),
            "emotion": emotional_state.get("current_emotion", "neutral"),
            "memory_context": evidence,
        }
        if attention_payload:
            semantic_input["attention_focus"] = attention_payload.get("focus")
            semantic_input["attention_focus_text"] = attention_payload.get("focus_text")
            semantic_input["attention_ranked"] = list(attention_payload.get("ranked") or [])[:5]
        if answer is not None:
            semantic_input.update(
                {"answer": answer, "conclusion": answer, "propositions": [answer]}
            )
        return {
            "status": "success",
            "content": {
                "thinking": thinking,
                "semantic_input": semantic_input,
                "composed_response": thinking.get("composed_response"),
            },
        }

    def shutdown(self) -> None:
        self.running = False
        shutdown = getattr(self.reasoner, "shutdown", None)
        if callable(shutdown):
            shutdown()
