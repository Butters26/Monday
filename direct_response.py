"""Safe, deterministic response realization for the direct core.

The direct runtime intentionally does not assume an external language model.
Providers receive structured understanding and clean, user-scoped memory only.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, List, Optional, Protocol



_STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "am",
        "i", "my", "me", "mine", "you", "your", "yours", "we", "our",
        "what", "whats", "who", "whom", "where", "when", "why", "how",
        "do", "does", "did", "can", "could", "would", "should", "please",
        "remember", "that", "this", "these", "those", "with", "from",
        "about", "tell", "of", "to", "in", "on", "at", "for", "and", "or",
        "it", "its", "have", "has", "had", "will", "just", "also", "so",
        "as", "if", "but", "not", "no", "yes", "ok", "okay", "hey", "hi",
        "hello", "named", "name", "got", "know",
    }
)

_QUESTIONISH = re.compile(
    r"\b(?:tell me|explain|what|who|where|when|why|how|which|do you remember|"
    r"can you remember|remind me)\b|\?",
    re.IGNORECASE,
)


def content_tokens(text: str) -> set:
    """Meaningful tokens for relevance scoring (stopwords stripped)."""
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def relevance_score(query: str, candidate: str) -> float:
    """Fraction of query content tokens that appear in the candidate."""
    qt = content_tokens(query)
    mt = content_tokens(candidate)
    if not qt or not mt:
        return 0.0
    return len(qt & mt) / float(len(qt))


def looks_questionish(text: str) -> bool:
    return bool(_QUESTIONISH.search(text or ""))


def rephrase_user_memory(content: str) -> str:
    """Turn a first-person user memory into a second-person answerable line."""
    text = (content or "").strip()
    if not text:
        return text
    text = re.sub(r"^(?:please\s+)?remember\s+(?:that\s+)?", "", text, flags=re.I).strip()
    m = re.match(
        r"^i\s+(live|work|am|was|have|had|like|love|hate|prefer)\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if m:
        return f"You {m.group(1).lower()} {m.group(2).strip(' .!?')}."
    m = re.match(r"^my\s+(.+)$", text, re.IGNORECASE)
    if m:
        body = m.group(1).strip(" .!?")
        return f"Your {body}." if body else text
    if text.endswith((".", "!", "?")):
        return text
    return text + "."


def answer_from_grounded_memories(
    user_input: str,
    memories: Iterable[Dict[str, Any]],
    *,
    min_score: float = 0.34,
) -> Optional[str]:
    """Build an answer from retrieved memories/facts when they match the question."""
    q = (user_input or "").strip()
    if not q:
        return None

    snippets = []
    seen = set()
    for memory in memories or []:
        if not isinstance(memory, dict):
            continue
        role = str(memory.get("role", "") or "")
        if role not in {"user", "fact", "note"}:
            continue
        content = memory.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if "How it felt:" in content or "What it meant:" in content:
            continue
        if re.match(r"^\s*(?:user|abin)\s*:", content, re.IGNORECASE):
            continue
        pred = str(memory.get("predicate", "") or "")
        obj = str(memory.get("object", "") or "")
        sub = str(memory.get("subject", "") or "")
        if pred and obj and (role == "fact" or sub.lower() in {"user", "i", "me"}):
            if pred.endswith("_name"):
                noun = pred[:-5].replace("_", " ").strip() or "thing"
                content = f"Your {noun}'s name is {obj}."
            elif pred.startswith("favorite_") or pred.startswith("favourite_"):
                content = f"Your {pred.replace('_', ' ')} is {obj}."
            elif not content.lower().startswith("your "):
                content = f"Your {pred.replace('_', ' ')} is {obj}."
        key = content.strip().casefold()
        if key in seen or key == q.casefold():
            continue
        seen.add(key)
        snippets.append((role if role else "user", content.strip()))

    if not snippets:
        return None

    name_q = re.search(
        r"\bwhat(?:'s|\s+is)\s+my\s+([a-z][a-z ]{0,40}?)(?:'s|s')?\s+name\b",
        q,
        re.IGNORECASE,
    )
    if name_q:
        noun = " ".join(name_q.group(1).lower().split())
        needle = f"your {noun}'s name is "
        for _role, fact in snippets:
            low = fact.casefold()
            if needle in low or (noun in low and "name is" in low):
                return fact if fact.endswith(".") else fact + "."

    fav_q = re.search(
        r"\bwhat(?:'s|\s+is)\s+my\s+(favorite\s+[a-z][a-z ]{0,40}?)\b",
        q,
        re.IGNORECASE,
    )
    if fav_q:
        attr = " ".join(fav_q.group(1).lower().split())
        needle = f"your {attr} is "
        for _role, fact in snippets:
            if needle in fact.casefold():
                return fact if fact.endswith(".") else fact + "."

    my_attr = re.search(
        r"\bwhat(?:'s|\s+is)\s+my\s+([a-z][a-z0-9 ]{0,40}?)\s*\??\s*$",
        q,
        re.IGNORECASE,
    )
    if my_attr:
        attr = " ".join(my_attr.group(1).lower().split())
        if attr and not attr.endswith(" name"):
            needle = f"your {attr} is "
            for _role, fact in snippets:
                if needle in fact.casefold():
                    return fact if fact.endswith(".") else fact + "."
            for _role, fact in snippets:
                low = fact.casefold()
                if low.startswith(f"my {attr} is ") or low.startswith(f"your {attr} is "):
                    return rephrase_user_memory(fact)

    if re.search(r"\bwhere\s+do\s+i\s+live\b", q, re.IGNORECASE) or re.search(
        r"\bwhat(?:'s|\s+is)\s+my\s+(?:city|hometown|address|location)\b",
        q,
        re.IGNORECASE,
    ):
        for _role, fact in snippets:
            low = fact.casefold()
            if any(
                key in low
                for key in (
                    "live in",
                    "lives in",
                    "living in",
                    "hometown is",
                    "city is",
                    "location is",
                )
            ):
                return rephrase_user_memory(fact)

    if re.search(r"\bwhere\s+do\s+i\s+work\b", q, re.IGNORECASE) or re.search(
        r"\bwhat(?:'s|\s+is)\s+my\s+(?:job|work|occupation|profession)\b",
        q,
        re.IGNORECASE,
    ):
        for _role, fact in snippets:
            low = fact.casefold()
            if any(
                key in low
                for key in (
                    "job is",
                    "work as",
                    "work at",
                    "work in",
                    "occupation is",
                    "profession is",
                )
            ):
                return rephrase_user_memory(fact)

    if not looks_questionish(q):
        return None

    ranked = []
    for role, text_snip in snippets:
        score = relevance_score(q, text_snip)
        if role == "fact" and score > 0:
            score += 0.05
        if score >= min_score:
            ranked.append((score, 0 if role == "fact" else 1, text_snip, role))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    _best_score, _, best_text, best_role = ranked[0]
    if not (content_tokens(q) & content_tokens(best_text)):
        return None
    if best_role == "fact" or best_text.casefold().startswith("your "):
        return best_text if best_text.endswith(".") else best_text + "."
    return rephrase_user_memory(best_text)


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
        return answer_from_grounded_memories(user_input, memories)

    def _teaching_ack(self, user_input: str) -> Optional[str]:
        text = user_input or ""
        for pattern, kind in (
            (self._name_is_fact, "name"),
            (self._named_fact, "name"),
            (self._favorite_fact, "favorite"),
        ):
            match = pattern.search(text)
            if not match:
                continue
            if kind == "name":
                noun = " ".join(match.group(1).lower().split())
                value = match.group(2).strip(" .!?")
                return f"Got it — your {noun}'s name is {value}."
            attr = " ".join(match.group(1).lower().split())
            value = match.group(2).strip(" .!?")
            return f"Got it — your {attr} is {value}."

        live = re.search(
            r"\b(?:remember\s+(?:that\s+)?)?i\s+live\s+in\s+"
            r"([A-Za-z0-9][A-Za-z0-9\s,.-]{0,60}?)(?:[.!?]|$)",
            text,
            re.IGNORECASE,
        )
        if live:
            return f"Got it — you live in {live.group(1).strip(' .!?')}."

        work = re.search(
            r"\b(?:remember\s+(?:that\s+)?)?i\s+work\s+(as|at|in)\s+"
            r"([A-Za-z0-9][A-Za-z0-9\s,.-]{0,60}?)(?:[.!?]|$)",
            text,
            re.IGNORECASE,
        )
        if work:
            return f"Got it — you work {work.group(1).lower()} {work.group(2).strip(' .!?')}."

        generic = re.search(
            r"\b(?:remember\s+(?:that\s+)?)?my\s+([a-z][a-z ]{0,40}?)\s+is\s+"
            r"([a-z0-9][a-z0-9 -]{0,80}?)(?:[.!?]|$)",
            text,
            re.IGNORECASE,
        )
        if generic:
            noun = " ".join(generic.group(1).lower().split())
            value = generic.group(2).strip(" .!?")
            if (
                noun
                and value
                and not noun.startswith("favorite ")
                and " name" not in noun
                and not value.lower().startswith("named ")
            ):
                return f"Got it — your {noun} is {value}."
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
        if intent in {"question", "request"} or looks_questionish(user_input or ""):
            return (
                "I do not have enough grounded information to answer that. "
                "Please provide more context or a fact I can reason from."
            )
        return "I understand. Please tell me more about what you would like to discuss."
