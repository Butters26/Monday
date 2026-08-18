"""Safe, deterministic response realization for the direct core.

The direct runtime intentionally does not assume an external language model.
Providers receive structured understanding and clean, user-scoped memory only.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, Optional, Protocol


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
    # Teaching patterns: "X equals Y", "X means Y", "X is (a/an) Y", "by X I mean Y"
    _teaching: re.Pattern[str] = re.compile(
        r"^\s*(.+?)\s+(?:equals?|means?|is\s+(?:a|an|the)?\s*)\s+(.+?)\s*[.!?]?\s*$"
        r"|^\s*by\s+(.+?)\s+i\s+mean\s+(.+?)\s*[.!?]?\s*$",
        re.IGNORECASE,
    )

    @staticmethod
    def _extract_teaching(user_input: str) -> Optional[str]:
        """Return a compact echo of a teaching statement, or None if not a teaching."""
        # "by X I mean Y"
        by_pattern = re.compile(
            r"^\s*by\s+(?P<word>.+?)\s+i\s+mean\s+(?P<val>.+?)\s*[.!?]?\s*$",
            re.IGNORECASE,
        )
        m = by_pattern.match(user_input.strip())
        if m:
            return f"Got it — {m.group('word').strip()} means {m.group('val').strip()}."

        # "X equals Y", "X means Y", "X is (a/an/the) Y", "X is Y"
        eq_pattern = re.compile(
            r"^\s*(?P<subj>.+?)\s+(?P<verb>equals?|means?|is\s+(?:a|an|the)?\s*|is)\s+(?P<pred>.+?)\s*[.!?]?\s*$",
            re.IGNORECASE,
        )
        m = eq_pattern.match(user_input.strip())
        if not m:
            return None
        subj = m.group("subj").strip()
        verb = re.sub(r"\s+", " ", m.group("verb").strip())
        pred = m.group("pred").strip()
        # Skip if subject is a long sentence fragment — probably not a teaching statement
        if len(subj.split()) > 6 or not pred:
            return None
        return f"Got it — {subj} {verb} {pred}."

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

        # Detect teaching statements before falling through to the generic response
        teaching_ack = self._extract_teaching(user_input)
        if teaching_ack:
            return teaching_ack

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
