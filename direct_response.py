"""Safe, deterministic response realization for the direct core.

The direct runtime intentionally does not assume an external language model.
Providers receive structured understanding and clean, user-scoped memory only.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, Protocol


class ResponseProvider(Protocol):
    """Supplies a final, semantically grounded response for a user prompt."""

    def render(
        self,
        user_input: str,
        understanding: Dict[str, Any],
        memories: Iterable[Dict[str, Any]],
    ) -> str:
        """Return a complete user-facing response."""


@dataclass(frozen=True)
class DeterministicResponseProvider:
    """A credential-free provider backed by a small set of verified facts."""

    _greeting: re.Pattern[str] = re.compile(r"^\s*(?:hello|hi|hey)\b", re.IGNORECASE)
    _gravity: re.Pattern[str] = re.compile(r"\bgravity\b", re.IGNORECASE)
    _memory: re.Pattern[str] = re.compile(r"\bmemory\b", re.IGNORECASE)
    _transcript: re.Pattern[str] = re.compile(r"^\s*(?:user|abin)\s*:", re.IGNORECASE)

    def render(
        self,
        user_input: str,
        understanding: Dict[str, Any],
        memories: Iterable[Dict[str, Any]],
    ) -> str:
        """Realize intent from the prompt, never from transcript-shaped memory."""
        clean_memories = [
            memory
            for memory in memories
            if isinstance(memory, dict)
            and memory.get("role") in {"user", "fact", "note"}
            and isinstance(memory.get("content"), str)
            and not self._transcript.match(memory["content"])
        ]
        has_safe_context = bool(clean_memories)

        if self._greeting.fullmatch(user_input):
            return "Hello! How can I help?"
        if self._gravity.search(user_input):
            return (
                "Gravity is the force of attraction between masses. "
                "It pulls objects toward each other, which is why objects fall toward Earth."
            )
        if self._memory.search(user_input):
            return "Memory is information retained so it can be retrieved and used later."

        intent = understanding.get("intent") if isinstance(understanding, dict) else None
        if intent in {"question", "request"} or re.search(
            r"\b(?:tell me|explain|what|who|where|when|why|how)\b",
            user_input,
            re.IGNORECASE,
        ):
            if has_safe_context:
                return (
                    "I do not have enough grounded information to answer that. "
                    "Please provide more context or a fact I can reason from."
                )
            return (
                "I do not have enough grounded information to answer that. "
                "Please provide more context or a fact I can reason from."
            )
        return "I understand. Please tell me more about what you would like to discuss."
