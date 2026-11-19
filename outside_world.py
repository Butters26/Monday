"""Whoever is talking to her from outside (the chat window, the terminal).

Not a lobe and not part of her brain. It does two things: hands what was
typed to her senses (Perception), and hears what she says (what Output
announces as delivered). Nothing in between is its business: her lobes take
it from there on their own.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from lobe_inbox import ANSWER_TIMEOUT_SEC

try:
    import trace_monitor as _tracer
except Exception:  # tracer is optional
    _tracer = None

UNKNOWN_PERSON = "unknown person 1"  # nobody is assumed to be Matthew


class Outside:
    name = "outside"

    def __init__(self, thalamus: Any) -> None:
        self.thalamus = thalamus
        self._cond = threading.Condition()
        self._said: Dict[str, List[str]] = {}   # what she said, per person, not yet collected

    # --- joined to the Thalamus only so it can hear what she says ------------
    def on_joined(self, name: str) -> None:
        self.name = name
        listen = getattr(self.thalamus, "listen", None)
        if callable(listen):
            listen(name, "delivered")

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if message.get("type") == "delivered":
            content = message.get("content") if isinstance(message.get("content"), dict) else {}
            text = str(content.get("text") or "").strip()
            user_id = self._who(content.get("user_id"))
            with self._cond:
                self._said.setdefault(user_id, []).append(text)
                self._cond.notify_all()
            return {"status": "success", "content": {"heard": True}}
        if message.get("type") == "health":
            return {"status": "success", "content": {"healthy": True}}
        return {"status": "error", "message": f"Unknown message type: {message.get('type')}", "content": {}}

    @staticmethod
    def _who(user_id: Any) -> str:
        user_id = str(user_id or "").strip()
        return UNKNOWN_PERSON if not user_id or user_id == "default" else user_id

    # --- talking to her ----------------------------------------------------------
    def say(self, text: str, user_id: str = "", timeout: float = ANSWER_TIMEOUT_SEC) -> str:
        """Say something to her and return what she says back ("" if nothing)."""
        if not isinstance(text, str) or not text.strip():
            return ""
        user_id = self._who(user_id)
        turn = _tracer.turn_started(text, user_id) if _tracer is not None else None
        started = time.perf_counter()
        reply, cause, error = "", None, None
        try:
            with self._cond:
                # Anything she said earlier that nobody collected is kept for take_unprompted.
                already = len(self._said.get(user_id) or [])
            sensed = self.thalamus.send_and_wait(
                "perception", "sense", {"modality": "text", "text": text, "user_id": user_id},
                source="outside")
            if sensed.get("status") != "success":
                cause = f"her senses didn't take it in: {sensed.get('message') or 'no reason given'}"
                return ""
            deadline = time.monotonic() + timeout
            quiet_since: Optional[int] = None
            while time.monotonic() < deadline:
                with self._cond:
                    heard = self._said.get(user_id) or []
                    spoken = next((i for i in range(already, len(heard)) if heard[i]), None)
                    if spoken is not None:
                        reply = heard[spoken]
                        del heard[already:spoken + 1]
                        return reply
                    self._cond.wait(0.01)
                # Has every lobe finished without her saying anything?
                carried = getattr(self.thalamus, "_carried", None)
                if self.thalamus.is_quiet() and carried == getattr(self.thalamus, "_carried", None):
                    if quiet_since == carried:
                        with self._cond:
                            heard = self._said.get(user_id) or []
                            if any(heard[already:]):
                                continue
                            said_nothing = len(heard) > already
                            del heard[already:]
                        cause = None if said_nothing else (
                            "nothing came out: every lobe finished and none of them spoke")
                        return ""
                    quiet_since = carried
                else:
                    quiet_since = None
            cause = f"no reply in {timeout:g}s: her lobes were still working"
            return ""
        except Exception as exc:
            import traceback
            error = "".join(traceback.format_exception(exc))[-2000:]
            raise
        finally:
            if _tracer is not None:
                _tracer.turn_ended(turn, reply, started, cause=cause, error=error)

    def take_unprompted(self, user_id: str = "") -> List[str]:
        """What she said on her own that nobody has collected yet."""
        user_id = self._who(user_id)
        with self._cond:
            items = [t for t in self._said.get(user_id) or [] if t]
            self._said[user_id] = []
        return items


__all__ = ["Outside", "UNKNOWN_PERSON"]
