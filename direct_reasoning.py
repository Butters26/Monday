"""Grounded, dependency-free reasoning for Monday's direct prompted core."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


_TRANSCRIPT_PREFIX = re.compile(r"^\s*(?:user|abin)\s*:", re.IGNORECASE)
_FACT = re.compile(
    r"\bmy\s+(?P<attribute>favorite\s+[a-z][a-z ]{0,40}?)\s+is\s+"
    r"(?P<value>[a-z0-9][a-z0-9 -]{0,80}?)(?:[.!?]|$)",
    re.IGNORECASE,
)
_FACT_QUERY = re.compile(
    r"\b(?:what(?:'s| is)|tell me about)\s+my\s+"
    r"(?P<attribute>favorite\s+[a-z][a-z ]{0,40}?)(?:[?!.]|$)",
    re.IGNORECASE,
)
_GREETING = re.compile(
    r"^\s*(?:hello|hi|hey)(?:\s+(?:monday|abin))?[!,. ]*$", re.IGNORECASE
)


class DirectReasoningProcess:
    """Derive conclusions from the current understanding and scoped memory."""

    _knowledge: Tuple[Tuple[str, str], ...] = (
        (
            "gravity",
            "Gravity is the force of attraction between masses. It pulls objects toward each other, including objects toward Earth.",
        ),
        (
            "photosynthesis",
            "Photosynthesis is the process by which plants use light energy to turn water and carbon dioxide into glucose, releasing oxygen.",
        ),
        (
            "memory",
            "Memory is information retained so it can be retrieved and used later.",
        ),
    )

    def __init__(self, thalamus: Any = None) -> None:
        self.running = True
        self.thalamus = thalamus

    @staticmethod
    def _clean_memories(memories: Any) -> List[Dict[str, Any]]:
        if not isinstance(memories, Iterable) or isinstance(memories, (str, bytes, dict)):
            return []
        return [
            memory
            for memory in memories
            if isinstance(memory, dict)
            and memory.get("role") in {"user", "fact", "note"}
            and isinstance(memory.get("content"), str)
            and memory["content"].strip()
            and not _TRANSCRIPT_PREFIX.match(memory["content"])
        ]

    @staticmethod
    def _normalise_attribute(attribute: str) -> str:
        return " ".join(attribute.lower().split())

    @classmethod
    def _fact_from_text(cls, text: str) -> Optional[Tuple[str, str]]:
        match = _FACT.search(text)
        if not match:
            return None
        attribute = cls._normalise_attribute(match.group("attribute"))
        value = match.group("value").strip(" .!?")
        return (attribute, value) if value else None

    @classmethod
    def _requested_attribute(cls, text: str) -> Optional[str]:
        match = _FACT_QUERY.search(text)
        return cls._normalise_attribute(match.group("attribute")) if match else None

    @staticmethod
    def _request_intent(user_input: str, understood_intent: Any) -> str:
        lower = user_input.lower()
        if "?" in user_input or re.search(
            r"\b(?:explain|tell me|what|who|where|when|why|how)\b", lower
        ):
            return "question"
        return understood_intent if isinstance(understood_intent, str) else "conversation"

    def _derive(
        self, user_input: str, understanding: Dict[str, Any], memories: List[Dict[str, Any]]
    ) -> Tuple[str, List[str], str]:
        """Return conclusion, supporting propositions, and effective intent."""
        intent = self._request_intent(user_input, understanding.get("intent"))
        stated_fact = self._fact_from_text(user_input)
        if stated_fact:
            attribute, value = stated_fact
            conclusion = f"I will remember that your {attribute} is {value}."
            return conclusion, [f"Your {attribute} is {value}."], "statement"

        requested_attribute = self._requested_attribute(user_input)
        if requested_attribute:
            for memory in memories:
                fact = self._fact_from_text(memory["content"])
                if fact and fact[0] == requested_attribute:
                    attribute, value = fact
                    conclusion = f"Your {attribute} is {value}."
                    return conclusion, [conclusion], "question"
            conclusion = (
                f"I do not have a stored fact for your {requested_attribute} yet."
            )
            return conclusion, [conclusion], "question"

        lower = user_input.lower()
        for topic, conclusion in self._knowledge:
            if re.search(rf"\b{re.escape(topic)}\b", lower):
                return conclusion, [conclusion], intent

        if _GREETING.fullmatch(user_input):
            conclusion = "Hello! How can I help?"
            return conclusion, [conclusion], "greeting"

        if intent in {"question", "request"}:
            conclusion = (
                "I do not have enough grounded information to answer that. "
                "Please provide more context or a fact I can reason from."
            )
            return conclusion, [conclusion], intent

        conclusion = "I understand. Please tell me more about what you would like to discuss."
        return conclusion, [conclusion], intent

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if message.get("type") == "health":
            return {"status": "success", "content": {"healthy": self.running}}
        if message.get("type") != "think":
            return {"status": "error", "message": "Unknown message type"}

        payload = message.get("content", {})
        input_data = payload.get("input", {}) if isinstance(payload, dict) else {}
        understanding = input_data.get("understanding", {})
        if not isinstance(understanding, dict):
            understanding = {}
        memory_context = input_data.get("memory_context", {})
        memories = (
            memory_context.get("memories", memory_context.get("results", []))
            if isinstance(memory_context, dict)
            else []
        )
        clean_memories = self._clean_memories(memories)
        user_input = input_data.get("user_input", "")
        if not isinstance(user_input, str):
            user_input = ""
        conclusion, propositions, intent = self._derive(
            user_input, understanding, clean_memories
        )
        semantic_input = {
            "intent": intent,
            "answer": conclusion,
            "conclusion": conclusion,
            "propositions": propositions,
            "memory_context": clean_memories,
            "certainty": understanding.get("confidence", 0.5),
            "emotion": input_data.get("emotion_result", {}).get(
                "current_emotion", "neutral"
            ),
        }
        return {
            "status": "success",
            "content": {
                "semantic_input": semantic_input,
                "answer": conclusion,
                "conclusion": conclusion,
                "propositions": propositions,
            },
        }

    def shutdown(self) -> None:
        self.running = False
