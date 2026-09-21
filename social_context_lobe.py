"""
SocialContextLobe — track social context across turns on the live path.

Owns per-user social state: cues, relationship stance, greeting continuity.
Consumes Conversation-owned intent (+ mild social text markers); emits a
compact social_context envelope for Thalamus to feed Reasoning/Language.

Does not classify intent (Conversation), compose sentences (Language),
answer facts (Reasoning), or set goals (Executive).
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

try:
    from direct_response import is_mild_social_turn
except Exception:  # pragma: no cover - defensive
    def is_mild_social_turn(user_input: str, intent: Optional[str] = None) -> bool:
        return False


# Conversation intents that are social cues Social tracks (does not re-classify).
_INTENT_TO_CUE = {
    "greeting": "greeting",
    "goodbye": "goodbye",
    "emotional_share": "emotional_share",
}

_CHECK_IN_RE = re.compile(
    r"(?i)\b(?:"
    r"how are you|how's it going|how is it going|what's up|whats up|"
    r"you there|still with me|are you there"
    r")\b"
)

_GOODBYE_RE = re.compile(
    r"(?i)^\s*(?:bye|goodbye|good\s*bye|see you|later|farewell)\b"
)


class SocialContextLobe:
    """Track interlocutor social stance/cues; distribute compact context."""

    def __init__(self, thalamus: Any = None) -> None:
        self.thalamus = thalamus
        # Per-user state (in-memory for this process).
        self._users: Dict[str, Dict[str, Any]] = {}
        self.context_state: Dict[str, Any] = {}  # last distributed snapshot
        self.social_cues: List[Any] = []  # legacy flat cue log (bounded)
        self.last_context: Optional[Dict[str, Any]] = None
        self._observe_count: int = 0

    # --- internals ---------------------------------------------------------

    def _user_state(self, user_id: str) -> Dict[str, Any]:
        uid = (user_id or "default").strip() or "default"
        state = self._users.get(uid)
        if state is None:
            state = {
                "user_id": uid,
                "stance": "new",
                "already_greeted": False,
                "greeting_count": 0,
                "social_turn_count": 0,
                "turn_count": 0,
                "last_cue": None,
                "recent_cues": [],
                "last_seen": 0.0,
                "last_continuity": "non_social",
                "last_was_social": False,
            }
            self._users[uid] = state
        return state

    def _extract_cue(
        self,
        user_input: str,
        understanding: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Map Conversation intent / mild social markers → cue. No intent theft."""
        understanding = understanding if isinstance(understanding, dict) else {}
        intent = str(understanding.get("intent") or "").strip().lower()
        if intent in _INTENT_TO_CUE:
            return _INTENT_TO_CUE[intent]
        text = user_input if isinstance(user_input, str) else ""
        if _GOODBYE_RE.match(text):
            return "goodbye"
        if _CHECK_IN_RE.search(text) and len(text.split()) <= 12:
            return "check_in"
        if is_mild_social_turn(text, intent or None):
            # Mild social without a more specific cue — treat as check_in/greeting.
            if intent == "greeting" or not text.strip():
                return "greeting"
            return "check_in"
        return None

    def _continuity_label(
        self,
        state: Dict[str, Any],
        cue: Optional[str],
        *,
        greeted_before: bool,
    ) -> str:
        if cue == "greeting":
            if greeted_before:
                return "re_greeting"
            return "first_contact"
        if cue in {"goodbye", "check_in", "emotional_share"}:
            return "ongoing_social"
        if state.get("turn_count", 0) > 0:
            return "ongoing"
        return "non_social"

    def _stance_after(
        self,
        state: Dict[str, Any],
        cue: Optional[str],
        *,
        greeted_before: bool,
        prior_turns: int = 0,
    ) -> str:
        if cue == "greeting" and greeted_before:
            return "returning"
        if greeted_before or prior_turns > 0:
            return "ongoing"
        if cue:
            return "new"
        return str(state.get("stance") or "new")

    def _snapshot(
        self,
        state: Dict[str, Any],
        *,
        cue: Optional[str],
        continuity: str,
        is_social_turn: bool,
    ) -> Dict[str, Any]:
        return {
            "user_id": state["user_id"],
            "stance": state.get("stance") or "new",
            "already_greeted": bool(state.get("already_greeted")),
            "greeting_count": int(state.get("greeting_count") or 0),
            "social_turn_count": int(state.get("social_turn_count") or 0),
            "turn_count": int(state.get("turn_count") or 0),
            "last_cue": cue if cue is not None else state.get("last_cue"),
            "recent_cues": list(state.get("recent_cues") or [])[-8:],
            "continuity": continuity,
            "is_social_turn": bool(is_social_turn),
            "last_seen": float(state.get("last_seen") or 0.0),
        }

    # --- public API --------------------------------------------------------

    def observe_turn(
        self,
        user_input: str = "",
        understanding: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """Update per-user social state from this turn; return distributed envelope."""
        state = self._user_state(user_id)
        understanding = understanding if isinstance(understanding, dict) else {}
        cue = self._extract_cue(user_input, understanding)
        greeted_before = bool(state.get("already_greeted"))
        is_social = cue is not None
        continuity = self._continuity_label(state, cue, greeted_before=greeted_before)

        # Stance/continuity from pre-update flags, then mutate.
        state["stance"] = self._stance_after(
            state, cue, greeted_before=greeted_before, prior_turns=int(state.get("turn_count") or 0)
        )
        state["turn_count"] = int(state.get("turn_count") or 0) + 1
        state["last_seen"] = time.time()
        state["last_continuity"] = continuity
        state["last_was_social"] = is_social
        if cue:
            state["last_cue"] = cue
            recent = list(state.get("recent_cues") or [])
            recent.append(cue)
            state["recent_cues"] = recent[-16:]
            self.social_cues.append({"user_id": state["user_id"], "cue": cue, "at": state["last_seen"]})
            if len(self.social_cues) > 64:
                self.social_cues = self.social_cues[-64:]
            state["social_turn_count"] = int(state.get("social_turn_count") or 0) + 1
            if cue == "greeting":
                state["greeting_count"] = int(state.get("greeting_count") or 0) + 1
                state["already_greeted"] = True

        snap = self._snapshot(
            state, cue=cue, continuity=continuity, is_social_turn=is_social
        )
        self.context_state = dict(snap)
        self.last_context = dict(snap)
        self._observe_count += 1
        return snap

    def get_context(self, user_id: str = "default") -> Dict[str, Any]:
        """Return current social_context for a user (no mutation)."""
        state = self._user_state(user_id)
        cue = state.get("last_cue")
        continuity = state.get("last_continuity")
        if not continuity:
            continuity = "non_social" if not state.get("turn_count") else "ongoing"
        return self._snapshot(
            state,
            cue=cue if isinstance(cue, str) else None,
            continuity=str(continuity),
            is_social_turn=bool(state.get("last_was_social")),
        )

    def update_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Merge explicit context keys into last / default user state (legacy)."""
        if not isinstance(context, dict):
            return {"status": "error", "message": "context must be a dict"}
        uid = str(context.get("user_id") or "default")
        state = self._user_state(uid)
        for key in (
            "stance",
            "already_greeted",
            "greeting_count",
            "social_turn_count",
            "last_cue",
        ):
            if key in context:
                state[key] = context[key]
        if isinstance(context.get("recent_cues"), list):
            state["recent_cues"] = list(context["recent_cues"])[-16:]
        snap = self.get_context(uid)
        self.context_state.update(snap)
        self.last_context = dict(snap)
        return snap

    def process_social_cue(self, cue: Any, user_id: str = "default") -> Dict[str, Any]:
        """Legacy cue hook — record cue without inventing Language/Reasoning calls."""
        if cue is None:
            return {"status": "error", "message": "Missing cue"}
        cue_s = cue if isinstance(cue, str) else str(cue)
        # Route through observe with a synthetic understanding so state stays coherent.
        intent_map = {
            "greeting": "greeting",
            "goodbye": "goodbye",
            "emotional_share": "emotional_share",
            "check_in": "conversation",
        }
        understanding = {"intent": intent_map.get(cue_s, "conversation")}
        # For check_in, supply mild text so extractor finds it.
        text = "how are you" if cue_s == "check_in" else cue_s
        snap = self.observe_turn(text, understanding=understanding, user_id=user_id)
        return {"status": "success", "message": "Cue processed", "social_context": snap}

    def reset(self, user_id: Optional[str] = None) -> None:
        if user_id:
            self._users.pop((user_id or "").strip() or "default", None)
        else:
            self._users.clear()
            self.social_cues.clear()
        self.context_state.clear()
        self.last_context = None

    def get_status(self) -> Dict[str, Any]:
        return {
            "observe_count": self._observe_count,
            "users_tracked": len(self._users),
            "last_context": dict(self.last_context) if self.last_context else None,
            "cue_log_len": len(self.social_cues),
        }

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        content = message.get("content", {})
        if not isinstance(content, dict):
            content = {}

        if msg_type in ("observe_turn", "observe", "update_from_turn"):
            snap = self.observe_turn(
                user_input=content.get("user_input") or content.get("text") or "",
                understanding=content.get("understanding")
                if isinstance(content.get("understanding"), dict)
                else {},
                user_id=str(content.get("user_id") or "default"),
            )
            return {"status": "success", "content": snap, "social_context": snap}

        if msg_type in ("get_context", "get_social_context"):
            snap = self.get_context(str(content.get("user_id") or "default"))
            return {"status": "success", "content": snap, "social_context": snap}

        if msg_type == "update_context":
            ctx = content.get("context", content)
            snap = self.update_context(ctx if isinstance(ctx, dict) else {})
            return {"status": "success", "content": snap, "context": snap}

        if msg_type == "social_cue":
            cue = content.get("cue")
            result = self.process_social_cue(
                cue, user_id=str(content.get("user_id") or "default")
            )
            if result.get("status") != "success":
                return result
            return {
                "status": "success",
                "message": "Cue processed",
                "content": result.get("social_context"),
                "social_context": result.get("social_context"),
            }

        if msg_type == "get_status":
            return {"status": "success", "content": self.get_status()}

        if msg_type == "reset":
            self.reset(content.get("user_id"))
            return {"status": "success", "message": "SocialContextLobe reset"}

        if msg_type == "health":
            return {"status": "success", "content": {"healthy": True}}

        return {"status": "error", "message": f"Unknown message type: {msg_type}"}
