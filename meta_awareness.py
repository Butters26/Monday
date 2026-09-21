#!/usr/bin/env python3
"""
MetaAwareness — process / dual-stream awareness on the live path.

Owns awareness of thinking PROCESS: wandering (spontaneous) vs focused
(controlled), notice/engage/dismiss of spontaneous thoughts, and a compact
meta_awareness envelope for Thalamus.

Distinct from MetaCognition (epistemic watcher of reasoning/language outputs):
  MetaCognition = "Is this thought epistemically OK?"
  MetaAwareness = "Which stream am I in, and is this spontaneous thought
                   worth engaging?"

Optional stream generators (ContinuousThoughtGenerator / ControlledThinking)
may be attached via set_spontaneous_system / set_controlled_system; MetaAwareness
remains awareness, not the generator owner.

Does not classify intent, invent facts, compose replies, plan actions,
synthesize speech, or replace MetaCognition.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class ThinkingMode(Enum):
    """Current mode of thinking (process awareness, not epistemic status)."""

    WANDERING = "wandering"  # Spontaneous stream flowing
    FOCUSED = "focused"  # Deliberately / user-driven controlled
    TRANSITION = "transition"  # Shifting between modes


@dataclass
class MetaState:
    """Meta-awareness process state (not MetaCognition epistemic verdict)."""

    mode: ThinkingMode = ThinkingMode.WANDERING
    awareness_level: float = 0.6  # How aware of own thinking (0-1)
    engagement_threshold: float = 0.65  # How interesting before engaging

    thoughts_noticed: int = 0
    thoughts_engaged: int = 0
    thoughts_dismissed: int = 0
    mode_shifts: int = 0


class MetaAwareness:
    """Observe and direct thinking-process / dual streams on the live path."""

    def __init__(self, thalamus: Any = None) -> None:
        self.thalamus = thalamus
        self.state = MetaState()
        self.spontaneous_system = None
        self.controlled_system = None
        self.last_envelope: Optional[Dict[str, Any]] = None
        self._observe_count: int = 0
        # Deterministic by default on live path (no flaky random for proofs).
        self._jitter: bool = False

        # What makes a thought worth engaging (process interest, not truth).
        self.engagement_factors = {
            "novelty": 0.3,
            "emotional_intensity": 0.2,
            "relevance": 0.25,
            "curiosity": 0.25,
        }

    # --- dual-stream hooks (optional generators feed streams) -------------

    def set_spontaneous_system(self, system: Any) -> None:
        """Connect to spontaneous thought generator (wandering stream)."""
        self.spontaneous_system = system

    def set_controlled_system(self, system: Any) -> None:
        """Connect to controlled thinking system (focused stream)."""
        self.controlled_system = system

    # --- core process awareness -------------------------------------------

    def notice_spontaneous_thought(
        self, thought: Dict[str, Any], *, jitter: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Notice a spontaneous thought; decide unnoticed / dismissed / engaged.
        Observational — does not own speech attach or Language wording.
        """
        use_jitter = self._jitter if jitter is None else bool(jitter)

        # Awareness gate — sometimes thoughts pass unnoticed.
        if use_jitter:
            import random

            if random.random() > self.state.awareness_level:
                return {
                    "action": "unnoticed",
                    "reason": "Passed by without conscious notice",
                }
        # Deterministic live path: always notice when awareness_level >= 0.5
        elif self.state.awareness_level < 0.5:
            return {
                "action": "unnoticed",
                "reason": "Awareness below notice threshold",
            }

        self.state.thoughts_noticed += 1
        engagement_score = self._evaluate_engagement(thought, jitter=use_jitter)
        meta_comment = self._generate_meta_comment(thought, engagement_score)

        if engagement_score >= self.state.engagement_threshold:
            self.state.thoughts_engaged += 1
            if self.state.mode == ThinkingMode.WANDERING:
                self.shift_to_focused(thought)
            return {
                "action": "engaged",
                "engagement_score": engagement_score,
                "topic": thought.get("topic"),
                "question": self._formulate_question(thought),
                "meta_comment": meta_comment,
            }

        self.state.thoughts_dismissed += 1
        return {
            "action": "dismissed",
            "engagement_score": engagement_score,
            "reason": (
                f"Not engaging (score: {engagement_score:.2f}, "
                f"threshold: {self.state.engagement_threshold:.2f})"
            ),
            "meta_comment": meta_comment,
        }

    def _evaluate_engagement(
        self, thought: Dict[str, Any], *, jitter: bool = False
    ) -> float:
        """How engaging this thought is (process interest)."""
        score = 0.0
        try:
            intensity = float(thought.get("intensity", 0.5) or 0.5)
        except (TypeError, ValueError):
            intensity = 0.5
        score += intensity * self.engagement_factors["emotional_intensity"]

        trigger = str(thought.get("trigger") or "")
        if trigger == "question":
            score += self.engagement_factors["curiosity"]
        if trigger in ("memory", "association"):
            score += self.engagement_factors["relevance"] * 0.7
        if trigger == "random":
            score += self.engagement_factors["novelty"] * 0.3
        # Novelty / relevance boosts from live turn envelopes.
        try:
            novelty = float(thought.get("novelty_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            novelty = 0.0
        if novelty > 0:
            score += min(0.3, novelty * self.engagement_factors["novelty"])
        if thought.get("user_driven") or thought.get("source") == "user_turn":
            score += self.engagement_factors["relevance"]

        if jitter:
            import random

            score += random.uniform(-0.1, 0.1)

        return max(0.0, min(1.0, score))

    def _generate_meta_comment(self, thought: Dict[str, Any], score: float) -> str:
        """Deterministic meta-process observation (not epistemic verdict)."""
        if score >= 0.8:
            return "This feels important"
        if score >= 0.6:
            return "Interesting..."
        if score >= 0.4:
            return "Aware but not pulled in"
        return "Letting that pass by"

    def _formulate_question(self, thought: Dict[str, Any]) -> str:
        topic = thought.get("topic") or thought.get("content") or "this"
        if isinstance(topic, str) and len(topic) > 48:
            topic = topic[:45] + "..."
        return f"What exactly is going on with {topic}?"

    def shift_to_focused(self, thought: Optional[Dict[str, Any]] = None) -> None:
        if self.state.mode != ThinkingMode.FOCUSED:
            self.state.mode = ThinkingMode.FOCUSED
            self.state.mode_shifts += 1

    def shift_to_wandering(self, reason: str = "") -> None:
        if self.state.mode != ThinkingMode.WANDERING:
            self.state.mode = ThinkingMode.WANDERING
            self.state.mode_shifts += 1

    def get_meta_state_summary(self) -> Dict[str, Any]:
        total = self.state.thoughts_noticed
        engagement_rate = (
            self.state.thoughts_engaged / total if total > 0 else 0.0
        )
        return {
            "mode": self.state.mode.value,
            "awareness_level": self.state.awareness_level,
            "thoughts_noticed": self.state.thoughts_noticed,
            "thoughts_engaged": self.state.thoughts_engaged,
            "thoughts_dismissed": self.state.thoughts_dismissed,
            "engagement_rate": engagement_rate,
            "mode_shifts": self.state.mode_shifts,
        }

    # --- live-path API ----------------------------------------------------

    def _envelope(
        self,
        *,
        prior_mode: str,
        engagement_action: str = "none",
        engagement_score: Optional[float] = None,
        meta_comment: str = "",
        user_id: str = "default",
        source: str = "observe_turn",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        mode = self.state.mode.value
        active = "controlled" if mode == ThinkingMode.FOCUSED.value else "spontaneous"
        env: Dict[str, Any] = {
            "mode": mode,
            "prior_mode": prior_mode,
            "active_stream": active,
            "dual_stream": {
                "spontaneous": True,  # always available as process concept
                "controlled": mode == ThinkingMode.FOCUSED.value,
            },
            "awareness_level": float(self.state.awareness_level),
            "engagement_action": engagement_action,
            "engagement_score": engagement_score,
            "meta_comment": meta_comment or "",
            "thoughts_noticed": int(self.state.thoughts_noticed),
            "thoughts_engaged": int(self.state.thoughts_engaged),
            "thoughts_dismissed": int(self.state.thoughts_dismissed),
            "mode_shifts": int(self.state.mode_shifts),
            "user_id": (user_id or "default").strip() or "default",
            "timestamp": time.time(),
            "source": source,
            # Explicit boundary marker vs MetaCognition epistemic watch.
            "job": "process_dual_stream",
            "not_epistemic": True,
        }
        if extra:
            env.update(extra)
        self.last_envelope = dict(env)
        return env

    def observe_turn(
        self,
        user_input: str = "",
        understanding: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
        novelty_score: float = 0.0,
        intensity: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Live-cycle entry: user turn → focused/controlled stream active.
        Records dual-stream envelope; does not steal Conversation intent.
        """
        understanding = understanding if isinstance(understanding, dict) else {}
        prior = self.state.mode.value
        # User-driven turn → controlled/focused stream.
        self.shift_to_focused(
            {
                "topic": (user_input or "")[:80],
                "source": "user_turn",
                "user_driven": True,
            }
        )
        intent = str(understanding.get("intent") or "").strip().lower()
        thought = {
            "topic": (user_input or "")[:80] or intent or "user_turn",
            "trigger": "question" if intent in ("question", "ask", "fact_query") else "association",
            "intensity": max(float(intensity or 0.5), 0.7),
            "novelty_score": novelty_score,
            "user_driven": True,
            "source": "user_turn",
            "content": user_input or "",
        }
        # User turn IS the controlled stream engaging — always notice + engage.
        # (Spontaneous asides still use notice_thought / threshold.)
        self.state.thoughts_noticed += 1
        self.state.thoughts_engaged += 1
        engagement_score = self._evaluate_engagement(thought, jitter=False)
        engagement_score = max(engagement_score, self.state.engagement_threshold)
        meta_comment = "Focusing on user-driven turn"
        question = self._formulate_question(thought)
        # Feed controlled stream generator if attached (smallest glue).
        controlled_extra: Dict[str, Any] = {}
        if self.controlled_system is not None:
            try:
                goal = (user_input or intent or "user_turn").strip()[:120] or "user_turn"
                start = getattr(self.controlled_system, "start_reasoning", None)
                if callable(start):
                    start(
                        goal_description=goal,
                        priority=7,
                        context={
                            "user_id": (user_id or "default").strip() or "default",
                            "source": "user_turn",
                            "intent": intent or None,
                        },
                    )
                controlled_extra = {
                    "controlled_fed": True,
                    "controlled_goal": goal,
                    "controlled_focused": bool(
                        getattr(self.controlled_system, "is_focused", True)
                    ),
                }
            except Exception:
                controlled_extra = {"controlled_fed": False, "controlled_error": True}
        else:
            controlled_extra = {"controlled_fed": False}
        env = self._envelope(
            prior_mode=prior,
            engagement_action="engaged",
            engagement_score=engagement_score,
            meta_comment=meta_comment,
            user_id=user_id,
            source="observe_turn",
            extra={
                "intent_seen": intent or None,  # consume, do not own
                "question": question,
                **controlled_extra,
            },
        )
        self._observe_count += 1
        return env

    def notice_thought(
        self,
        thought: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """Notice an external spontaneous thought (e.g. speak-worthy aside)."""
        prior = self.state.mode.value
        thought = thought if isinstance(thought, dict) else {}
        # Normalize aside-shaped payloads from Autonomous.
        if "content" in thought and "topic" not in thought:
            thought = dict(thought)
            thought["topic"] = str(thought.get("content") or "")[:80]
        if "trigger" not in thought:
            thought = dict(thought)
            thought["trigger"] = str(thought.get("trigger") or "association")
        notice = self.notice_spontaneous_thought(thought, jitter=False)
        env = self._envelope(
            prior_mode=prior,
            engagement_action=str(notice.get("action") or "none"),
            engagement_score=notice.get("engagement_score"),
            meta_comment=str(notice.get("meta_comment") or ""),
            user_id=user_id,
            source="notice_thought",
            extra={"question": notice.get("question"), "aside_topic": thought.get("topic")},
        )
        return env

    def release_to_wandering(
        self, reason: str = "turn_complete", user_id: str = "default"
    ) -> Dict[str, Any]:
        """After prompted turn completes, return toward spontaneous/wandering."""
        prior = self.state.mode.value
        self.shift_to_wandering(reason)
        # Feed spontaneous stream generator if attached (sample only — do not
        # re-engage/focus during release; that would fight wandering).
        spontaneous_extra: Dict[str, Any] = {}
        if self.spontaneous_system is not None:
            try:
                gen = getattr(self.spontaneous_system, "generate_thought", None)
                thought = gen() if callable(gen) else None
                if isinstance(thought, dict):
                    spontaneous_extra = {
                        "spontaneous_fed": True,
                        "spontaneous_trigger": thought.get("trigger"),
                        "spontaneous_text": str(thought.get("text") or "")[:120],
                    }
                else:
                    spontaneous_extra = {"spontaneous_fed": False}
            except Exception:
                spontaneous_extra = {"spontaneous_fed": False, "spontaneous_error": True}
        else:
            spontaneous_extra = {"spontaneous_fed": False}
        env = self._envelope(
            prior_mode=prior,
            engagement_action="none",
            engagement_score=None,
            meta_comment=f"Released to wandering ({reason})",
            user_id=user_id,
            source="release_to_wandering",
            extra=spontaneous_extra,
        )
        return env

    def get_status(self) -> Dict[str, Any]:
        summary = self.get_meta_state_summary()
        return {
            **summary,
            "observe_count": self._observe_count,
            "last_envelope": dict(self.last_envelope) if self.last_envelope else None,
            "has_spontaneous_system": self.spontaneous_system is not None,
            "has_controlled_system": self.controlled_system is not None,
            "job": "process_dual_stream",
        }

    def reset(self) -> None:
        self.state = MetaState()
        self.last_envelope = None
        self._observe_count = 0

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        content = message.get("content", {})
        if not isinstance(content, dict):
            content = {
                k: v
                for k, v in message.items()
                if k not in ("type", "_message_id", "message_id", "source")
            }

        if msg_type == "health":
            return {"status": "success", "healthy": True}

        if msg_type in ("observe_turn", "observe", "update_from_turn"):
            try:
                novelty = float(content.get("novelty_score", 0.0) or 0.0)
            except (TypeError, ValueError):
                novelty = 0.0
            try:
                intensity = float(content.get("intensity", 0.5) or 0.5)
            except (TypeError, ValueError):
                intensity = 0.5
            snap = self.observe_turn(
                user_input=str(content.get("user_input") or content.get("text") or ""),
                understanding=content.get("understanding")
                if isinstance(content.get("understanding"), dict)
                else {},
                user_id=str(content.get("user_id") or "default"),
                novelty_score=novelty,
                intensity=intensity,
            )
            return {
                "status": "success",
                "content": snap,
                "meta_awareness": snap,
            }

        if msg_type in ("notice_thought", "notice", "notice_spontaneous"):
            thought = content.get("thought")
            if not isinstance(thought, dict):
                thought = content
            snap = self.notice_thought(
                thought, user_id=str(content.get("user_id") or "default")
            )
            return {
                "status": "success",
                "content": snap,
                "meta_awareness": snap,
                "notice": {
                    "action": snap.get("engagement_action"),
                    "engagement_score": snap.get("engagement_score"),
                },
            }

        if msg_type in ("release_to_wandering", "release", "shift_to_wandering"):
            snap = self.release_to_wandering(
                reason=str(content.get("reason") or "turn_complete"),
                user_id=str(content.get("user_id") or "default"),
            )
            return {
                "status": "success",
                "content": snap,
                "meta_awareness": snap,
            }

        if msg_type in ("get_status", "status", "get_meta_state"):
            body = self.get_status()
            return {"status": "success", "content": body, **body}

        if msg_type == "get_meta_state_summary":
            body = self.get_meta_state_summary()
            return {"status": "success", "content": body, **body}

        if msg_type == "reset":
            self.reset()
            return {"status": "success", "message": "MetaAwareness reset"}

        return {"status": "error", "message": f"Unknown message type: {msg_type}"}
