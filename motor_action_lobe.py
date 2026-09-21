"""
MotorActionLobe — action planning / selection / queuing on the live path.

When Conversation reports an actionable intent (request) — or an explicit
plan_action message arrives — Motor plans a structured action envelope,
queues it per-user, and routes motor_output to Output.

Does not invent goals (Executive), classify intent (Conversation), compose
spoken replies (Language), or claim physical actuators. Honest statuses:
planned / queued / blocked_by_inhibit / no_actuator.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Dict, List, Optional

# Actionable Conversation intents → Motor may plan.
_ACTIONABLE_INTENTS = frozenset({"request"})

# Executive goals that authorize Motor planning on the live path.
_ACTIONABLE_GOALS = frozenset({"fulfill_request"})

_REMINDER_RE = re.compile(
    r"(?i)\b(?:remind(?:er)?|todo|to-do|schedule|checklist)\b"
)
_NOTE_RE = re.compile(r"(?i)\b(?:note|jot|write\s+down|log)\b")


class MotorActionLobe:
    """Plan / queue executable action envelopes; deliver honestly to Output."""

    def __init__(self, thalamus: Any = None) -> None:
        self.thalamus = thalamus
        # Per-user queues (in-memory for this process).
        self._queues: Dict[str, List[Dict[str, Any]]] = {}
        self.action_queue: List[Dict[str, Any]] = []  # legacy alias → default user
        self.last_action: Optional[Dict[str, Any]] = None
        self.last_blocked: Optional[Dict[str, Any]] = None
        self._plan_count: int = 0

    # --- internals ---------------------------------------------------------

    @staticmethod
    def _uid(user_id: Optional[str]) -> str:
        return (user_id or "default").strip() or "default"

    def _queue_for(self, user_id: Optional[str]) -> List[Dict[str, Any]]:
        uid = self._uid(user_id)
        q = self._queues.get(uid)
        if q is None:
            q = []
            self._queues[uid] = q
        # Keep legacy flat queue mirrored for default user.
        if uid == "default":
            self.action_queue = q
        return q

    @staticmethod
    def _kind_from_text(text: str) -> str:
        if _REMINDER_RE.search(text or ""):
            return "reminder"
        if _NOTE_RE.search(text or ""):
            return "note"
        return "generic_request"

    def _check_inhibit(self, action_name: str = "motor_action") -> Dict[str, Any]:
        """Query Executive should_inhibit; allow if Executive absent."""
        th = self.thalamus
        if th is None:
            return {"inhibited": False, "allowed": True, "reason": "no_thalamus"}
        try:
            with getattr(th, "lobe_handlers_lock", _NullLock()):
                has_exec = "executive_control" in getattr(th, "lobe_handlers", {})
        except Exception:
            has_exec = False
        if not has_exec:
            return {"inhibited": False, "allowed": True, "reason": "no_executive"}
        try:
            send = getattr(th, "send_and_wait", None)
            if not callable(send):
                return {"inhibited": False, "allowed": True, "reason": "no_send"}
            resp = send(
                "executive_control",
                "should_inhibit",
                {"action": action_name},
                source="motor_action",
            )
        except Exception as exc:
            return {
                "inhibited": False,
                "allowed": True,
                "reason": f"inhibit_check_error:{exc}",
            }
        body = resp.get("content") if isinstance(resp.get("content"), dict) else resp
        if not isinstance(body, dict):
            body = {}
        inhibited = bool(body.get("inhibited"))
        return {
            "inhibited": inhibited,
            "allowed": not inhibited,
            "reason": str(body.get("reason") or ("blocked" if inhibited else "allowed")),
            "goal": body.get("goal"),
            "priority": body.get("priority"),
        }

    def _current_goal(self) -> Dict[str, Any]:
        th = self.thalamus
        if th is None:
            return {}
        try:
            with getattr(th, "lobe_handlers_lock", _NullLock()):
                has_exec = "executive_control" in getattr(th, "lobe_handlers", {})
        except Exception:
            has_exec = False
        if not has_exec:
            return {}
        try:
            resp = th.send_and_wait(
                "executive_control", "get_goal", {}, source="motor_action"
            )
        except Exception:
            return {}
        body = resp.get("content") if isinstance(resp.get("content"), dict) else resp
        return body if isinstance(body, dict) else {}

    def _build_action(
        self,
        intent_text: str,
        *,
        user_id: str = "default",
        source_intent: str = "",
        goal_honored: str = "",
        status: str = "planned",
        inhibit_reason: str = "",
        kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        text = intent_text if isinstance(intent_text, str) else str(intent_text or "")
        action = {
            "id": str(uuid.uuid4()),
            "kind": kind or self._kind_from_text(text),
            "type": "motor",
            "intent_text": text[:240],
            "user_id": self._uid(user_id),
            "source_intent": source_intent or "",
            "goal_honored": goal_honored or "",
            "status": status,
            "actuator": "none",
            "timestamp": time.time(),
        }
        if inhibit_reason:
            action["inhibit_reason"] = inhibit_reason
        return action

    # --- public API --------------------------------------------------------

    @staticmethod
    def is_actionable(
        understanding: Optional[Dict[str, Any]] = None,
        goal: Optional[str] = None,
    ) -> bool:
        understanding = understanding if isinstance(understanding, dict) else {}
        intent = str(understanding.get("intent") or "").strip().lower()
        goal_s = (goal or "").strip().lower()
        return intent in _ACTIONABLE_INTENTS or goal_s in _ACTIONABLE_GOALS

    def plan_from_turn(
        self,
        user_input: str = "",
        understanding: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
        goal: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Live-path entry: plan when request / fulfill_request; honor inhibit."""
        understanding = understanding if isinstance(understanding, dict) else {}
        intent = str(understanding.get("intent") or "").strip().lower()
        goal_info = self._current_goal() if goal is None else {"goal": goal}
        goal_s = str(goal_info.get("goal") or goal or "").strip().lower()

        if not self.is_actionable(understanding, goal_s):
            return {
                "status": "success",
                "planned": False,
                "reason": "not_actionable",
                "intent": intent,
                "goal": goal_s or None,
                "action": None,
            }

        inhibit = self._check_inhibit("motor_action")
        text = user_input if isinstance(user_input, str) else ""
        if inhibit.get("inhibited"):
            blocked = self._build_action(
                text,
                user_id=user_id,
                source_intent=intent,
                goal_honored=goal_s,
                status="blocked_by_inhibit",
                inhibit_reason=str(inhibit.get("reason") or "inhibited"),
            )
            self.last_blocked = dict(blocked)
            self.last_action = dict(blocked)
            return {
                "status": "success",
                "planned": False,
                "blocked": True,
                "reason": blocked["inhibit_reason"],
                "action": blocked,
                "inhibit": inhibit,
            }

        action = self.plan_action(
            {
                "text": text,
                "intent": intent,
                "goal": goal_s,
                "user_id": user_id,
            },
            user_id=user_id,
        )
        return {
            "status": "success",
            "planned": True,
            "blocked": False,
            "action": action,
            "inhibit": inhibit,
        }

    def plan_action(self, intent: Any, user_id: str = "default") -> Dict[str, Any]:
        """Plan an action from intent text or dict; enqueue if not inhibited."""
        if isinstance(intent, dict):
            text = str(
                intent.get("text")
                or intent.get("intent_text")
                or intent.get("intent")
                or intent.get("user_input")
                or ""
            )
            source_intent = str(intent.get("intent") or intent.get("source_intent") or "")
            goal_honored = str(intent.get("goal") or intent.get("goal_honored") or "")
            uid = str(intent.get("user_id") or user_id or "default")
            kind = intent.get("kind") if isinstance(intent.get("kind"), str) else None
        else:
            text = str(intent or "")
            source_intent = ""
            goal_honored = ""
            uid = user_id
            kind = None

        inhibit = self._check_inhibit("motor_action")
        if inhibit.get("inhibited"):
            blocked = self._build_action(
                text,
                user_id=uid,
                source_intent=source_intent,
                goal_honored=goal_honored,
                status="blocked_by_inhibit",
                inhibit_reason=str(inhibit.get("reason") or "inhibited"),
                kind=kind,
            )
            self.last_blocked = dict(blocked)
            self.last_action = dict(blocked)
            return blocked

        action = self._build_action(
            text,
            user_id=uid,
            source_intent=source_intent,
            goal_honored=goal_honored,
            status="planned",
            kind=kind,
        )
        action["status"] = "queued"
        self._queue_for(uid).append(action)
        self.last_action = dict(action)
        self._plan_count += 1
        return dict(action)

    def execute_action(self, user_id: str = "default") -> Optional[Dict[str, Any]]:
        """Dequeue next action; mark no_actuator; route motor_output to Output.

        Honest: there are no physical actuators. 'Execute' means surface the
        planned envelope to Output with status no_actuator.
        """
        q = self._queue_for(user_id)
        if not q:
            return None

        # Re-check inhibit at delivery time.
        inhibit = self._check_inhibit("motor_action")
        action = q.pop(0)
        if inhibit.get("inhibited"):
            action = dict(action)
            action["status"] = "blocked_by_inhibit"
            action["inhibit_reason"] = str(inhibit.get("reason") or "inhibited")
            self.last_blocked = dict(action)
            self.last_action = dict(action)
            self._route_motor_output(action)
            return dict(action)

        action = dict(action)
        action["status"] = "no_actuator"
        action["delivered_at"] = time.time()
        self.last_action = dict(action)
        self._route_motor_output(action)
        return dict(action)

    def _route_motor_output(self, action: Dict[str, Any]) -> None:
        th = self.thalamus
        if th is None:
            return
        try:
            th.send_message(
                "output",
                "motor_output",
                {"action": action},
                source="motor_action",
            )
        except Exception:
            pass

    def get_queue(self, user_id: str = "default") -> List[Dict[str, Any]]:
        return [dict(a) for a in self._queue_for(user_id)]

    def get_status(self, user_id: str = "default") -> Dict[str, Any]:
        return {
            "queue_depth": len(self._queue_for(user_id)),
            "plan_count": self._plan_count,
            "last_action": dict(self.last_action) if self.last_action else None,
            "last_blocked": dict(self.last_blocked) if self.last_blocked else None,
            "users": sorted(self._queues.keys()),
        }

    def reset(self, user_id: Optional[str] = None) -> None:
        if user_id is None:
            self._queues.clear()
            self.action_queue = []
            self.last_action = None
            self.last_blocked = None
            self._plan_count = 0
            return
        uid = self._uid(user_id)
        self._queues.pop(uid, None)
        if uid == "default":
            self.action_queue = []

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        if "content" in message and isinstance(message.get("content"), dict):
            content = message["content"]
        else:
            content = {
                k: v
                for k, v in message.items()
                if k not in ("type", "_message_id", "message_id", "source")
            }

        if msg_type == "health":
            return {"status": "success", "healthy": True}

        if msg_type in ("plan_from_turn", "plan_turn"):
            body = self.plan_from_turn(
                user_input=str(content.get("user_input") or content.get("text") or ""),
                understanding=content.get("understanding")
                if isinstance(content.get("understanding"), dict)
                else {},
                user_id=str(content.get("user_id") or "default"),
                goal=content.get("goal"),
            )
            return {"status": "success", "content": body, **body}

        if msg_type == "plan_action":
            intent = content.get("intent")
            if intent is None:
                intent = content.get("text") or content.get("user_input")
            if intent is None:
                return {"status": "error", "message": "Missing intent"}
            action = self.plan_action(
                intent,
                user_id=str(content.get("user_id") or "default"),
            )
            return {"status": "success", "content": {"action": action}, "action": action}

        if msg_type in ("execute_next", "deliver", "execute_action"):
            action = self.execute_action(
                user_id=str(content.get("user_id") or "default")
            )
            if action is None:
                return {
                    "status": "success",
                    "content": {"action": None, "message": "No actions to execute"},
                    "message": "No actions to execute",
                }
            return {"status": "success", "content": {"action": action}, "action": action}

        if msg_type in ("get_status", "status"):
            body = self.get_status(str(content.get("user_id") or "default"))
            return {"status": "success", "content": body, **body}

        if msg_type == "get_queue":
            q = self.get_queue(str(content.get("user_id") or "default"))
            return {"status": "success", "content": {"queue": q}, "queue": q}

        if msg_type == "reset":
            self.reset(content.get("user_id"))
            return {"status": "success", "message": "MotorActionLobe reset"}

        return {"status": "error", "message": f"Unknown message type: {msg_type}"}


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False
