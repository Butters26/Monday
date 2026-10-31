"""Moved here Oct 31, 2026 (not run): canned lines no lobe may fall back on.

- empathic_grounded_reply: fixed comfort lines ("That sounds heavy - I am
  sitting with how frightening this is for you. I am here.") that Reasoning
  computed on emotional turns.
- honest_curiosity_question / maybe_curiosity_follow_up: a stock follow-up
  question Conversation could add.
- Thalamus._maybe_attach_curiosity_follow_up: thalamus deciding to glue that
  question onto her reply (nothing called it any more).

Language builds every reply from meaning; Reasoning reviews it. These are kept
only for reference.
"""

# from direct_response.py
def empathic_grounded_reply(
    user_input: str,
    emotional_state: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Brief empathic acknowledge for distress / hot affect — never invent facts."""
    state = emotional_state if isinstance(emotional_state, dict) else {}
    text = (user_input or "").strip()
    if not text or looks_questionish(text) or looks_like_teaching_turn(text):
        return None
    if is_mild_social_turn(text):
        return None
    try:
        intensity = float(state.get("intensity", 0.0) or 0.0)
    except (TypeError, ValueError):
        intensity = 0.0
    unresolved = state.get("unresolved_appraisals") or []
    emo_resp = state.get("response")
    distress = bool(_DISTRESS_RE.search(text))
    hot = intensity >= 0.55 or bool(unresolved) or distress
    if not hot:
        return None
    # Prefer emotion lobe's own line when it is a real sentence (not poison).
    if isinstance(emo_resp, str):
        cleaned = emo_resp.strip()
        if (
            cleaned
            and "How it felt:" not in cleaned
            and "What it meant:" not in cleaned
            and len(cleaned) >= 12
            and not cleaned.lower().startswith("i do not have enough grounded")
        ):
            return cleaned
    emotion = str(
        state.get("current_emotion") or state.get("emotion") or ""
    ).strip().lower()
    if distress or unresolved:
        if emotion in {"sad", "worried", "fearful", "anxious", "nostalgic"}:
            return (
                "That sounds heavy — I am sitting with how frightening this is for you. "
                "I am here."
            )
        return (
            "I hear how hard this is. I do not want to invent details — "
            "I am here with you in it."
        )
    if intensity >= 0.70:
        return "I can feel how much this matters. Tell me what you need from me right now."
    return None


# from direct_response.py
def honest_curiosity_question(
    user_input: str,
    emotional_state: Optional[Dict[str, Any]] = None,
) -> str:
    """One honest follow-up that asks instead of inventing facts.

    Owned by the live emotion/conversation/direct_response path — not novelty_lobe.
    """
    state = emotional_state if isinstance(emotional_state, dict) else {}
    unresolved = state.get("unresolved_appraisals") or []
    emotion = str(
        state.get("current_emotion")
        or state.get("emotion")
        or "this"
    ).strip() or "this"
    text = (user_input or "").strip()

    primary = None
    if isinstance(unresolved, list) and unresolved:
        try:
            primary = max(
                (u for u in unresolved if isinstance(u, dict)),
                key=lambda u: float(u.get("severity", 0.0) or 0.0),
                default=None,
            )
        except Exception:
            primary = next((u for u in unresolved if isinstance(u, dict)), None)

    if isinstance(primary, dict):
        et = str(primary.get("event_type") or "feeling").replace("_", " ").strip()
        return (
            f"What would help with this {et} - or is there more I should understand "
            f"before I guess?"
        )

    snippet = text
    if len(snippet) > 72:
        cut = snippet[:69].rsplit(" ", 1)[0]
        snippet = (cut or snippet[:69]) + "..."
    if snippet:
        # Ask about their words; do not invent missing details.
        safe = snippet.replace('"', "'")
        return (
            f'I do not want to invent details - can you tell me more about what you '
            f'meant by "{safe}"?'
        )
    return (
        f"I am feeling {emotion} about this and I do not want to invent an answer - "
        f"what am I missing?"
    )


# from conversation.py ConversationSystem
    def maybe_curiosity_follow_up(
        self,
        user_input: str,
        emotional_context: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None,
        *,
        force: bool = False,
    ) -> Optional[str]:
        """Maybe one honest follow-up when affect is hot, unresolved, or novel.

        Uses dialogue_move from Language-driven understanding. Does not invent
        questions from Novelty.
        """
        emotional_context = emotional_context if isinstance(emotional_context, dict) else {}
        understanding = understanding if isinstance(understanding, dict) else {}
        intent = understanding.get("intent")
        dialogue_move = understanding.get("dialogue_move")

        if (
            is_mild_social_turn(user_input, intent)
            or is_closing_social_turn(user_input, intent)
            or intent == "goodbye"
            or dialogue_move in {"social_open", "social_close", "social_fragment"}
        ) and not force:
            return None
        if looks_like_teaching_turn(user_input) and not force:
            return None
        if dialogue_move in {"assertion", "answer", "correction"} and looks_like_teaching_turn(
            user_input
        ):
            return None

        try:
            intensity = float(emotional_context.get("intensity", 0.0) or 0.0)
        except (TypeError, ValueError):
            intensity = 0.0
        try:
            novelty_score = float(understanding.get("novelty_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            novelty_score = 0.0
        unresolved = emotional_context.get("unresolved_appraisals") or []
        if not isinstance(unresolved, list):
            unresolved = []
        max_sev = 0.0
        if unresolved:
            try:
                max_sev = max(
                    float(u.get("severity", 0.0) or 0.0)
                    for u in unresolved
                    if isinstance(u, dict)
                )
            except Exception:
                max_sev = 0.55

        elevated_novelty = novelty_score >= 0.55
        eligible = (
            bool(force)
            or bool(unresolved)
            or intensity >= 0.70
            or elevated_novelty
        )
        if not eligible:
            return None

        if not force:
            if unresolved and (intensity >= 0.50 or max_sev >= 0.55):
                if random.random() >= 0.88:
                    return None
            elif elevated_novelty and novelty_score >= 0.70:
                if random.random() >= 0.70:
                    return None
            elif elevated_novelty:
                if random.random() >= 0.45:
                    return None
            elif intensity >= 0.70:
                if random.random() >= 0.55:
                    return None
            else:
                return None

        try:
            question = honest_curiosity_question(user_input, emotional_context)
        except Exception:
            return None
        if question:
            self.note_mercy_question(question, topic=understanding.get("topic"))
        return question


# from thalamus.py Thalamus
    def _maybe_attach_curiosity_follow_up(
        self,
        reply: str,
        user_input: str = "",
        emotional_state: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Conversation owns the question; Thalamus only attaches its returned text."""
        if not isinstance(reply, str) or not reply.strip():
            return reply
        if self._executive_should_inhibit("curiosity_follow_up"):
            self._force_curiosity_follow_up = False
            return reply

        with self.lobe_handlers_lock:
            conversation = self.lobe_handlers.get("conversation")
        decide = (
            getattr(conversation, "maybe_curiosity_follow_up", None)
            if conversation is not None
            else None
        )
        if not callable(decide):
            return reply

        force = bool(self._force_curiosity_follow_up)
        now = time.time()
        if not force and now - self._last_curiosity_time < self._curiosity_cooldown_sec:
            return reply
        try:
            question = decide(
                user_input,
                emotional_state if isinstance(emotional_state, dict) else {},
                understanding if isinstance(understanding, dict) else {},
                force=force,
            )
        except Exception:
            return reply
        if not isinstance(question, str) or not question.strip():
            return reply
        question = question.strip()
        if question in reply:
            return reply
        self._last_curiosity_time = now
        self._force_curiosity_follow_up = False
        return f"{reply.rstrip()}\n\n{question}"
