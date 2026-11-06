"""Parts of direct_reasoning.py that fed the old engine (moved Nov 6, 2026).

The old engine (reasoning.py, now legacy/reasoning_old_engine_legacy.py) was
called every turn for a prose conclusion; Language builds every reply now and
nothing used its output. Kept for the record; nothing uses it.
"""


class _OldParts:
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

