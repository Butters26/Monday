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


_FAVORITE_FACT = re.compile(
    r"\bmy\s+(?P<attribute>favorite\s+[a-z][a-z ]{0,40}?)\s+is\s+"
    r"(?P<value>[a-z0-9][a-z0-9 -]{0,80}?)(?:[.!?]|$)",
    re.IGNORECASE,
)
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

    @classmethod
    def _evidence(cls, memories: List[Dict[str, Any]], user_input: str) -> List[Dict[str, Any]]:
        evidence = []
        for memory in memories:
            normalized = cls._normalise_favorite_fact(memory["content"])
            if normalized:
                evidence.append({"role": "fact", "content": normalized})
            else:
                evidence.append(memory)
        fact = cls._normalise_favorite_fact(user_input)
        if fact:
            evidence.append({"role": "fact", "content": fact})
        return evidence

    @staticmethod
    def _usable_conclusion(
        thinking: Dict[str, Any], understanding: Dict[str, Any]
    ) -> Optional[str]:
        composed = thinking.get("composed_response")
        if not isinstance(composed, str) or not composed.strip():
            return None
        theories = thinking.get("theories", [])
        grounded = any(
            isinstance(theory, dict) and theory.get("components")
            for theory in theories
        )
        if grounded or understanding.get("intent") == "greeting":
            return composed.strip()
        # Legacy composition can turn an evidence-free question into a word bag;
        # that is not a conclusion. Let Thalamus use its emergency fallback.
        return None

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if message.get("type") == "health":
            return {"status": "success", "content": {"healthy": self.running}}
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
        memories = self._clean_memories(raw_memories, user_input)
        evidence = self._evidence(memories, user_input)
        learned_guidance = payload.get("learned_guidance", []) if isinstance(payload, dict) else []
        learned_guidance = [
            item.strip()
            for item in learned_guidance
            if isinstance(item, str) and item.strip()
        ]
        if learned_guidance:
            evidence.extend({"role": "fact", "content": item} for item in learned_guidance)
        emotional_state = direct_input.get("emotion_result", {})
        emotional_state = emotional_state if isinstance(emotional_state, dict) else {}
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
            "learned_guidance": learned_guidance,
        }
        thinking = self.reasoner.think_about(legacy_input)
        if not isinstance(thinking, dict):
            thinking = {}
        answer = self._usable_conclusion(thinking, understanding)
        semantic_input = {
            "intent": understanding.get("intent", "conversation"),
            "certainty": understanding.get("confidence", 0.5),
            "emotion": emotional_state.get("current_emotion", "neutral"),
            "memory_context": evidence,
            "learned_guidance": learned_guidance,
        }
        if answer is not None:
            semantic_input.update(
                {"answer": answer, "conclusion": answer, "propositions": [answer]}
            )
        elif learned_guidance:
            semantic_input.update(
                {
                    "conclusion": learned_guidance[0],
                    "propositions": learned_guidance,
                }
            )
        return {
            "status": "success",
            "content": {
                "thinking": thinking,
                "semantic_input": semantic_input,
                "composed_response": thinking.get("composed_response"),
                "learned_guidance_used": bool(learned_guidance),
            },
        }

    def shutdown(self) -> None:
        self.running = False
        shutdown = getattr(self.reasoner, "shutdown", None)
        if callable(shutdown):
            shutdown()
