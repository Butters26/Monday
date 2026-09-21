"""
ExecutiveControlLobe — control lobe for Monday's live prompted path.

Sets/holds a current goal and priority, inhibits off-goal moves (curiosity
follow-up / speak-worthy aside when the goal is fact-answer), and steers
Attention salience toward that goal.

Distinct from Meta-cognition (watcher of reasoning/language quality):
Executive is the priority / inhibition / goal-steering lobe — not another
epistemic watcher. Does not invent facts; does not rebuild Meta-cognition
or finished lobes.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Set


# One replaceable Attention competitor for the held Executive goal.
# Never mint a new id per historical goal (avoids stale fact_answer outranking).
CURRENT_GOAL_SIGNAL_ID = "executive:current_goal"
_LEGACY_GOAL_SIGNAL_PREFIX = "executive:goal:"

# Goals that demand a tight answer path — block curiosity / aside spam.
_FACT_ANSWER_GOALS = frozenset(
    {
        "fact_answer",
        "question",
        "monday_speech_ask",
    }
)

# Actions Executive can inhibit on the live path.
_INHIBITABLE_ACTIONS = frozenset(
    {
        "curiosity_follow_up",
        "speak_worthy_aside",
        "aside",
        "curiosity",
        "motor_action",
    }
)

# Conversation intents → executive goals.
_INTENT_TO_GOAL = {
    "question": "fact_answer",
    "monday_speech_ask": "fact_answer",
    "fact_teach": "teach_ack",
    "greeting": "social",
    "goodbye": "social",
    "emotional_share": "emotional_support",
    "topic_shift": "open_explore",
    "request": "fulfill_request",
    "statement": "open_explore",
    "conversation": "open_explore",
}


class ExecutiveControlLobe:
    """Hold goal/priority, inhibit off-goal actions, steer Attention."""

    def __init__(self, thalamus: Any = None) -> None:
        self.thalamus = thalamus
        self.current_goal: Optional[str] = None
        self.goal_priority: float = 0.0
        self.goal_detail: str = ""
        self.goal_source: str = ""
        self.goal_set_at: float = 0.0
        self.inhibited_actions: Set[str] = set()
        self.last_inhibition: Optional[Dict[str, Any]] = None
        self.last_steer: Optional[Dict[str, Any]] = None
        self._goal_history: List[Dict[str, Any]] = []
        self._turn_count: int = 0
        # Legacy task queue kept for message compatibility (not live-path control).
        self.task_list: List[Any] = []
        self.inhibition_state: bool = False

    # --- goal --------------------------------------------------------------

    def set_goal(
        self,
        goal: str,
        priority: float = 0.8,
        source: str = "explicit",
        detail: str = "",
    ) -> Dict[str, Any]:
        """Set/hold the current goal. Higher priority replaces lower unless equal+same."""
        goal_s = (goal or "").strip() or "idle"
        try:
            pri = float(priority)
        except (TypeError, ValueError):
            pri = 0.5
        pri = max(0.0, min(1.0, pri))
        self.current_goal = goal_s
        self.goal_priority = pri
        self.goal_detail = detail if isinstance(detail, str) else str(detail or "")
        self.goal_source = source if isinstance(source, str) else str(source or "")
        self.goal_set_at = time.time()
        self._refresh_inhibited_actions()
        record = {
            "goal": self.current_goal,
            "priority": self.goal_priority,
            "source": self.goal_source,
            "detail": self.goal_detail,
            "inhibited_actions": sorted(self.inhibited_actions),
            "set_at": self.goal_set_at,
        }
        self._goal_history.append(record)
        if len(self._goal_history) > 32:
            self._goal_history = self._goal_history[-32:]
        return dict(record)

    def clear_goal(self) -> Dict[str, Any]:
        self.current_goal = None
        self.goal_priority = 0.0
        self.goal_detail = ""
        self.goal_source = ""
        self.goal_set_at = 0.0
        self.inhibited_actions.clear()
        return {"goal": None, "priority": 0.0, "inhibited_actions": []}

    def get_goal(self) -> Dict[str, Any]:
        return {
            "goal": self.current_goal,
            "priority": self.goal_priority,
            "detail": self.goal_detail,
            "source": self.goal_source,
            "set_at": self.goal_set_at,
            "inhibited_actions": sorted(self.inhibited_actions),
        }

    def _refresh_inhibited_actions(self) -> None:
        """Derive default inhibitions from the held goal."""
        goal = (self.current_goal or "").strip().lower()
        inhibited: Set[str] = set()
        if goal in _FACT_ANSWER_GOALS:
            inhibited.update(
                {
                    "curiosity_follow_up",
                    "speak_worthy_aside",
                    "aside",
                    "curiosity",
                    "motor_action",
                }
            )
        elif goal == "teach_ack":
            # Teaching ack: block curiosity about the fact itself / aside spam.
            inhibited.update({"curiosity_follow_up", "curiosity"})
        self.inhibited_actions = inhibited

    def set_goal_from_turn(
        self,
        user_input: str = "",
        understanding: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Derive and hold goal from Conversation intent (live-path entry)."""
        self._turn_count += 1
        understanding = understanding if isinstance(understanding, dict) else {}
        intent = understanding.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            intent = self._heuristic_intent(user_input)
        intent = intent.strip().lower()
        slots = understanding.get("slots") if isinstance(understanding.get("slots"), dict) else {}
        ask_kind = slots.get("ask_kind") if isinstance(slots.get("ask_kind"), str) else ""

        goal = _INTENT_TO_GOAL.get(intent, "open_explore")
        if ask_kind in ("fact_ask", "question") or intent in ("question", "monday_speech_ask"):
            goal = "fact_answer"
        # Priority: fact answers and emotional support outrank open explore.
        priority_map = {
            "fact_answer": 0.95,
            "teach_ack": 0.85,
            "emotional_support": 0.90,
            "fulfill_request": 0.80,
            "social": 0.55,
            "open_explore": 0.45,
            "idle": 0.1,
        }
        priority = priority_map.get(goal, 0.5)
        detail = user_input.strip()[:120] if isinstance(user_input, str) else ""
        return self.set_goal(
            goal,
            priority=priority,
            source=f"conversation:{intent}",
            detail=detail,
        )

    @staticmethod
    def _heuristic_intent(user_input: str) -> str:
        text = (user_input or "").strip().lower()
        if not text:
            return "conversation"
        if text.endswith("?") or text.startswith(
            ("what ", "why ", "how ", "when ", "where ", "who ", "which ")
        ):
            return "question"
        if text.startswith(("hi", "hello", "hey")):
            return "greeting"
        return "conversation"

    # --- inhibition --------------------------------------------------------

    def should_inhibit(self, action: str) -> Dict[str, Any]:
        """Return whether an action is off-goal and must be blocked."""
        action_s = (action or "").strip().lower()
        # Normalize aliases.
        if action_s in ("aside", "speak_worthy", "spoken_aside"):
            action_s = "speak_worthy_aside"
        if action_s in ("curiosity", "curiosity_question", "follow_up"):
            action_s = "curiosity_follow_up"
        if action_s in ("motor", "motor_execute", "execute_action", "plan_action"):
            action_s = "motor_action"

        inhibited = False
        reason = "allowed"
        if self.inhibition_state and action_s in _INHIBITABLE_ACTIONS:
            inhibited = True
            reason = "global_inhibition_state"
        elif action_s in self.inhibited_actions:
            inhibited = True
            reason = f"off_goal:{self.current_goal or 'none'}"
        elif (
            (self.current_goal or "").strip().lower() in _FACT_ANSWER_GOALS
            and action_s in _INHIBITABLE_ACTIONS
        ):
            inhibited = True
            reason = f"off_goal:{self.current_goal}"

        result = {
            "action": action_s or action,
            "inhibited": inhibited,
            "allowed": not inhibited,
            "reason": reason,
            "goal": self.current_goal,
            "priority": self.goal_priority,
        }
        self.last_inhibition = dict(result)
        return result

    # --- attention steer ---------------------------------------------------

    def attention_steer_signals(self) -> List[Dict[str, Any]]:
        """Build Attention signals that boost on-goal focus / demote distractions."""
        goal = (self.current_goal or "idle").strip() or "idle"
        pri = float(self.goal_priority or 0.0)
        signals: List[Dict[str, Any]] = [
            {
                "id": CURRENT_GOAL_SIGNAL_ID,
                "text": f"executive goal: {goal} {self.goal_detail}".strip(),
                "source": "executive_control",
                "modality": "control",
                "priority": min(1.0, 0.55 + 0.40 * pri),
                "concepts": ["executive", "goal", goal],
            }
        ]
        if goal in _FACT_ANSWER_GOALS:
            # Boost answering the user; demote novelty spam / ambient.
            signals.append(
                {
                    "id": "user_input",
                    "text": self.goal_detail or "answer the user question",
                    "source": "executive_control",
                    "modality": "control",
                    "priority": min(1.0, 0.70 + 0.25 * pri),
                    "concepts": ["fact_answer", "user"],
                }
            )
            signals.append(
                {
                    "id": "ambient_noise",
                    "text": "ambient room tone",
                    "source": "executive_control",
                    "modality": "control",
                    "priority": 0.0,
                }
            )
            signals.append(
                {
                    "id": "novelty_score",
                    "text": "novelty demoted under fact_answer goal",
                    "source": "executive_control",
                    "modality": "control",
                    "priority": 0.05,
                    "novelty_score": 0.0,
                }
            )
        return signals

    def steer_attention(self) -> Dict[str, Any]:
        """Push goal steer signals into Attention when thalamus+attention exist."""
        signals = self.attention_steer_signals()
        result: Dict[str, Any] = {
            "steered": False,
            "goal": self.current_goal,
            "signals": signals,
            "reason": "no_thalamus",
        }
        if not self.thalamus:
            self.last_steer = result
            return result
        with getattr(self.thalamus, "lobe_handlers_lock", _NullCM()):
            handlers = getattr(self.thalamus, "lobe_handlers", None) or {}
            has_attention = "attention" in handlers
        if not has_attention:
            result["reason"] = "attention_offline"
            self.last_steer = result
            return result
        # Drop legacy per-goal ids (executive:goal:*) so only one competitor remains.
        try:
            self.thalamus.send_and_wait(
                "attention",
                "remove_signals",
                {"prefix": _LEGACY_GOAL_SIGNAL_PREFIX},
                source="executive_control",
            )
        except Exception:
            pass
        try:
            resp = self.thalamus.send_and_wait(
                "attention",
                "replace_signals",
                {"signals": signals},
                source="executive_control",
            )
        except Exception as exc:
            result["reason"] = f"send_failed:{exc}"
            self.last_steer = result
            return result
        if resp.get("status") != "success":
            result["reason"] = f"attention_error:{resp.get('message')}"
            self.last_steer = result
            return result
        body = resp.get("content") if isinstance(resp.get("content"), dict) else {}
        salience = body.get("salience_map") or resp.get("salience_map") or {}
        # Also re-select focus so ranking reflects the steer.
        try:
            focus_resp = self.thalamus.send_and_wait(
                "attention", "select_focus", {}, source="executive_control"
            )
            focus = (
                (focus_resp.get("content") or {}).get("focus")
                if isinstance(focus_resp.get("content"), dict)
                else focus_resp.get("focus")
            )
        except Exception:
            focus = None
        result.update(
            {
                "steered": True,
                "reason": "salience_updated",
                "salience_sample": {
                    k: salience.get(k)
                    for k in list(salience.keys())[:8]
                    if k in salience
                }
                if isinstance(salience, dict)
                else {},
                "focus": focus,
                "goal_signal_present": bool(
                    isinstance(salience, dict) and CURRENT_GOAL_SIGNAL_ID in salience
                ),
            }
        )
        # Prefer reporting the goal key explicitly when present.
        if isinstance(salience, dict):
            goal_keys = [
                k
                for k in salience
                if isinstance(k, str)
                and (
                    k == CURRENT_GOAL_SIGNAL_ID
                    or k.startswith(_LEGACY_GOAL_SIGNAL_PREFIX)
                )
            ]
            if goal_keys:
                result["goal_signal_keys"] = goal_keys
                result["goal_signal_present"] = CURRENT_GOAL_SIGNAL_ID in salience
                meta = {}
                try:
                    # Surface text/concepts of the stable current-goal signal when available.
                    att = None
                    with getattr(self.thalamus, "lobe_handlers_lock", _NullCM()):
                        handlers = getattr(self.thalamus, "lobe_handlers", None) or {}
                        att = handlers.get("attention")
                    signal_meta = getattr(att, "signal_meta", None) or {}
                    meta = signal_meta.get(CURRENT_GOAL_SIGNAL_ID) or {}
                except Exception:
                    meta = {}
                if meta:
                    result["goal_signal_text"] = meta.get("text")
                    result["goal_signal_concepts"] = list(meta.get("concepts") or [])
                    result["goal_signal_priority"] = meta.get("priority")
        self.last_steer = result
        return result

    # --- status / legacy ---------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        return {
            "goal": self.current_goal,
            "priority": self.goal_priority,
            "detail": self.goal_detail,
            "source": self.goal_source,
            "inhibited_actions": sorted(self.inhibited_actions),
            "last_inhibition": self.last_inhibition,
            "last_steer": {
                k: self.last_steer.get(k)
                for k in ("steered", "reason", "goal", "goal_signal_present", "focus")
            }
            if isinstance(self.last_steer, dict)
            else None,
            "turn_count": self._turn_count,
            "history_len": len(self._goal_history),
            "inhibition_state": self.inhibition_state,
            "task_count": len(self.task_list),
        }

    def add_task(self, task: Any) -> None:
        self.task_list.append(task)

    def execute_next_task(self) -> Any:
        if self.inhibition_state or not self.task_list:
            return None
        return self.task_list.pop(0)

    def set_inhibition(self, state: bool) -> None:
        self.inhibition_state = bool(state)
        if self.inhibition_state:
            self.inhibited_actions.update(_INHIBITABLE_ACTIONS)
        else:
            self._refresh_inhibited_actions()

    def reset(self) -> None:
        self.clear_goal()
        self.task_list.clear()
        self.inhibition_state = False
        self.last_inhibition = None
        self.last_steer = None
        self._goal_history.clear()
        self._turn_count = 0

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

        if msg_type in ("set_goal", "hold_goal"):
            record = self.set_goal(
                content.get("goal") or content.get("current_goal") or "idle",
                priority=content.get("priority", 0.8),
                source=str(content.get("source") or "message"),
                detail=str(content.get("detail") or content.get("user_input") or ""),
            )
            return {"status": "success", "content": record, **record}

        if msg_type in ("set_goal_from_turn", "derive_goal", "update_from_turn"):
            record = self.set_goal_from_turn(
                user_input=str(content.get("user_input") or content.get("text") or ""),
                understanding=content.get("understanding")
                if isinstance(content.get("understanding"), dict)
                else content,
            )
            return {"status": "success", "content": record, **record}

        if msg_type in ("get_goal", "current_goal"):
            body = self.get_goal()
            return {"status": "success", "content": body, **body}

        if msg_type == "clear_goal":
            body = self.clear_goal()
            return {"status": "success", "content": body, **body}

        if msg_type in ("should_inhibit", "inhibit_check", "check_inhibition"):
            body = self.should_inhibit(str(content.get("action") or ""))
            return {"status": "success", "content": body, **body}

        if msg_type in ("steer_attention", "steer"):
            body = self.steer_attention()
            return {"status": "success", "content": body, **body}

        if msg_type in ("get_status", "status"):
            status = self.get_status()
            return {"status": "success", "content": status, **status}

        if msg_type == "add_task":
            task = content.get("task")
            if task is None:
                return {"status": "error", "message": "Missing task"}
            self.add_task(task)
            return {"status": "success", "message": "Task added"}

        if msg_type == "execute_next":
            task = self.execute_next_task()
            if task is None:
                return {
                    "status": "success",
                    "message": "No task executed (inhibited or empty)",
                }
            return {"status": "success", "task": task}

        if msg_type == "set_inhibition":
            self.set_inhibition(bool(content.get("state", False)))
            return {
                "status": "success",
                "inhibition": self.inhibition_state,
                "inhibited_actions": sorted(self.inhibited_actions),
            }

        if msg_type == "select_action":
            # Minimal real selection: prefer candidates aligned with current goal.
            candidates = content.get("candidates") or []
            if not candidates:
                return {"status": "error", "message": "No candidates provided"}
            goal = (self.current_goal or "").lower()
            best = None
            best_score = -1.0
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                score = float(candidate.get("confidence") or candidate.get("score") or 0.5)
                ctype = str(candidate.get("type") or candidate.get("action") or "").lower()
                if goal in _FACT_ANSWER_GOALS and ctype in (
                    "curiosity",
                    "aside",
                    "curiosity_follow_up",
                    "speak_worthy_aside",
                ):
                    score -= 1.0
                if goal in _FACT_ANSWER_GOALS and ctype in (
                    "answer",
                    "fact_answer",
                    "reason",
                ):
                    score += 0.5
                if score > best_score:
                    best_score = score
                    best = candidate
            if best is None:
                return {"status": "error", "message": "No candidate could be selected"}
            return {
                "status": "success",
                "selected_id": best.get("id"),
                "score": best_score,
                "goal": self.current_goal,
            }

        if msg_type == "reset":
            self.reset()
            return {
                "status": "success",
                "content": {"message": "ExecutiveControlLobe reset"},
            }

        if msg_type == "health":
            return {"status": "success", "healthy": True, "content": {"healthy": True}}

        return {
            "status": "error",
            "message": f"Unknown message type: {msg_type}",
            "content": {},
        }


class _NullCM:
    """No-op context manager when thalamus has no lobe_handlers_lock."""

    def __enter__(self) -> "_NullCM":
        return self

    def __exit__(self, *args: Any) -> None:
        return None
