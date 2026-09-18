"""Safe, deterministic response realization for the direct core.

The direct runtime intentionally does not assume an external language model.
Providers receive structured understanding and clean, user-scoped memory only.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, List, Optional, Protocol


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
    """A credential-free provider backed by stored facts and a small verified set."""

    _greeting: re.Pattern[str] = re.compile(
        r"^\s*(?:hello|hi|hey|sup|yo|hiya|howdy)(?:\s+(?:there|you|friend))?(?:\s*[!.,]*)?\s*$",
        re.IGNORECASE,
    )
    _gravity: re.Pattern[str] = re.compile(r"\bgravity\b", re.IGNORECASE)
    _memory: re.Pattern[str] = re.compile(r"\bmemory\b", re.IGNORECASE)
    _transcript: re.Pattern[str] = re.compile(r"^\s*(?:user|abin)\s*:", re.IGNORECASE)
    _name_question: re.Pattern[str] = re.compile(
        r"\bwhat(?:'s|\s+is)\s+my\s+([a-z][a-z ]{0,40}?)(?:'s|s')?\s+name\b",
        re.IGNORECASE,
    )
    _favorite_question: re.Pattern[str] = re.compile(
        r"\bwhat(?:'s|\s+is)\s+my\s+(favorite\s+[a-z][a-z ]{0,40}?)\b",
        re.IGNORECASE,
    )
    _named_fact: re.Pattern[str] = re.compile(
        r"\b(?:remember\s+(?:that\s+)?)?my\s+([a-z][a-z ]{0,40}?)\s+is\s+named\s+"
        r"([A-Za-z0-9][\w-]{0,40})\b",
        re.IGNORECASE,
    )
    _name_is_fact: re.Pattern[str] = re.compile(
        r"\b(?:remember\s+(?:that\s+)?)?my\s+([a-z][a-z ]{0,40}?)(?:'s|s')\s+name\s+is\s+"
        r"([A-Za-z0-9][\w-]{0,40})\b",
        re.IGNORECASE,
    )
    _favorite_fact: re.Pattern[str] = re.compile(
        r"\bmy\s+(favorite\s+[a-z][a-z ]{0,40}?)\s+is\s+"
        r"([a-z0-9][a-z0-9 -]{0,80}?)(?:[.!?]|$)",
        re.IGNORECASE,
    )

    def _safe_memories(self, memories: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        clean: List[Dict[str, Any]] = []
        for memory in memories:
            if not isinstance(memory, dict):
                continue
            role = memory.get("role")
            content = memory.get("content")
            if role not in {"user", "fact", "note"}:
                continue
            if not isinstance(content, str) or not content.strip():
                continue
            if "How it felt:" in content:
                continue
            if self._transcript.match(content):
                continue
            clean.append(memory)
        return clean

    def _answer_from_facts(self, user_input: str, memories: List[Dict[str, Any]]) -> Optional[str]:
        facts = [
            m["content"].strip()
            for m in memories
            if m.get("role") == "fact" and isinstance(m.get("content"), str)
        ]
        # Also treat well-formed user statements already normalized as facts
        for m in memories:
            content = m.get("content")
            if not isinstance(content, str):
                continue
            if content.strip().lower().startswith("your ") and " is " in content.lower():
                if content.strip() not in facts:
                    facts.append(content.strip())

        q = self._name_question.search(user_input or "")
        if q:
            noun = " ".join(q.group(1).lower().split())
            needle = f"your {noun}'s name is "
            for fact in facts:
                if needle in fact.casefold():
                    return fact if fact.endswith(".") else fact + "."
                if noun in fact.casefold() and "name is" in fact.casefold():
                    return fact if fact.endswith(".") else fact + "."

        fav = self._favorite_question.search(user_input or "")
        if fav:
            attr = " ".join(fav.group(1).lower().split())
            needle = f"your {attr} is "
            for fact in facts:
                if needle in fact.casefold():
                    return fact if fact.endswith(".") else fact + "."
        return None

    def _teaching_ack(self, user_input: str) -> Optional[str]:
        for pattern, kind in (
            (self._name_is_fact, "name"),
            (self._named_fact, "name"),
            (self._favorite_fact, "favorite"),
        ):
            match = pattern.search(user_input or "")
            if not match:
                continue
            if kind == "name":
                noun = " ".join(match.group(1).lower().split())
                value = match.group(2).strip(" .!?")
                return f"Got it — your {noun}'s name is {value}."
            attr = " ".join(match.group(1).lower().split())
            value = match.group(2).strip(" .!?")
            return f"Got it — your {attr} is {value}."
        return None

    def render(
        self,
        user_input: str,
        understanding: Dict[str, Any],
        memories: Iterable[Dict[str, Any]],
    ) -> str:
        """Realize intent from the prompt and grounded fact memories."""
        clean_memories = self._safe_memories(memories)

        if self._greeting.fullmatch(user_input or ""):
            return "Hello! How can I help?"

        if re.search(
            r"\b(?:are you okay|how are you|how(?:'s| is) it going)\b",
            user_input or "",
            re.IGNORECASE,
        ):
            return "I'm here — thanks for checking in. How are you?"

        teaching = self._teaching_ack(user_input or "")
        if teaching:
            return teaching

        fact_answer = self._answer_from_facts(user_input or "", clean_memories)
        if fact_answer:
            return fact_answer

        if self._gravity.search(user_input or ""):
            return (
                "Gravity is the force of attraction between masses. "
                "It pulls objects toward each other, which is why objects fall toward Earth."
            )
        if self._memory.search(user_input or ""):
            return "Memory is information retained so it can be retrieved and used later."

        intent = understanding.get("intent") if isinstance(understanding, dict) else None
        if intent in {"question", "request"} or re.search(
            r"\b(?:tell me|explain|what|who|where|when|why|how)\b",
            user_input or "",
            re.IGNORECASE,
        ):
            return (
                "I do not have enough grounded information to answer that. "
                "Please provide more context or a fact I can reason from."
            )
        return "I understand. Please tell me more about what you would like to discuss."
