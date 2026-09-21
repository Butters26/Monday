#!/usr/bin/env python3
"""Direct-call coordinator for Monday's prompted core path.

Every lobe receives the same envelope::

    {"type": str, "content": dict, "source": str, "message_id": str}

`content` is the only payload field.  Responses retain legacy top-level fields
for callers that use them, while their canonical payload is always `content`.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import re
import time
import threading
import uuid
from typing import Any, Dict, Iterable, List, Optional

from direct_response import (
    DeterministicResponseProvider,
    ResponseProvider,
    answer_from_grounded_memories,
    content_tokens,
    honest_curiosity_question,
    is_mild_social_turn,
    prose_answer_to_structures,
    relevance_score,
    structures_from_grounded_memories,
    _asks_about_monday_own_speech,
    _attribute_asked,
    _fact_covers_attribute,
    _MONDAY_ROLES,
)
from learning.lobe_learning_store import LobeLearningStore


_LEARNING_ROUTE_TYPES = {
    "learn",
    "recall",
    "teach_skill",
    "list_skills",
    "reinforce_learning",
    "contradict_learning",
    "forget_learning",
    "learning_stats",
}
_LESSON_TYPE_PATTERNS = {
    "correction": re.compile(
        r"\b(wrong|instead|don't|do not|stop|fix|correct|should not)\b", re.IGNORECASE
    ),
    "feedback": re.compile(
        r"\b(feedback|constructive|tone|rude|respectful|polite|calm|kind)\b", re.IGNORECASE
    ),
    "skill": re.compile(
        r"\b(learn|teach|how to|skill|math|grammar|pattern|piano|music|logic|reason)\b",
        re.IGNORECASE,
    ),
}
_LOBE_LEARNING_RULES = {
    "reasoning": {"skill", "correction", "feedback"},
    "language": {"skill", "correction", "feedback"},
    "conversation": {"skill", "correction", "feedback"},
    "output": {"feedback", "correction"},
    "emotion": {"feedback", "correction"},
    "pattern": {"skill", "correction"},
    "perception": {"skill", "correction"},
    "novelty": {"skill", "feedback"},
    "attention": {"skill", "feedback"},
    "meta_cognition": {"correction", "feedback", "skill"},
    "executive_control": {"skill", "correction"},
    "social_context": {"feedback", "correction"},
    "sensory_integration": {"skill"},
    "motor_action": {"skill"},
    "speech": {"feedback", "correction"},
    "autonomous": {"skill", "feedback", "correction"},
    "representation": {"skill"},
    "reflection": {"feedback", "correction"},
    "experience": {"skill", "feedback"},
    "reinforcement": {"skill", "feedback", "correction"},
}


class Thalamus:
    """Synchronously route direct calls between registered lobes."""

    def __init__(self, response_provider: Optional[ResponseProvider] = None) -> None:
        self.running = True
        self.lobe_handlers: Dict[str, Any] = {}
        self.lobe_handlers_lock = threading.RLock()
        self.lobe_status: Dict[str, str] = {}
        self.message_routes: deque = deque(maxlen=100)
        self.response_provider = response_provider or DeterministicResponseProvider()
        # Rate-limit rare speak-worthy asides attached to user-turn replies.
        self._last_spoken_aside_time: float = 0.0
        self._spoken_aside_cooldown_sec: float = 45.0
        # Curiosity follow-ups (emotion/conversation/direct_response).
        # Novelty lobe supplies novelty_score; it does not own the question text.
        self._last_curiosity_time: float = 0.0
        self._curiosity_cooldown_sec: float = 25.0
        self._force_curiosity_follow_up: bool = False
        # Last Output lobe reply envelope (expression + delivery metadata).
        self.last_output_envelope: Optional[Dict[str, Any]] = None
        self.last_grounded_structures: Optional[List[Dict[str, Any]]] = None
        self.last_language_sentence: Optional[str] = None
        # Complete final reply text assembled before Output (asides + curiosity).
        self._last_pre_output_final_text: Optional[str] = None
        # Last Meta-cognition verdict (epistemic watch on reasoning/language).
        self.last_meta_cognition: Optional[Dict[str, Any]] = None
        # Last Executive control snapshot (goal / inhibition / steer).
        self.last_executive: Optional[Dict[str, Any]] = None

    def register_lobe(self, name: str, lobe: Any) -> Dict[str, Any]:
        if not name or lobe is None:
            return {"status": "error", "message": "A lobe name and handler are required"}
        if not callable(getattr(lobe, "process_message", None)) and not callable(
            getattr(lobe, "process_message_safe", None)
        ):
            return {"status": "error", "message": f"{name} has no message handler"}
        with self.lobe_handlers_lock:
            self.lobe_handlers[name] = lobe
            self.lobe_status[name] = "online"
        if name != "notus" and not hasattr(lobe, "_lobe_learning_store"):
            setattr(lobe, "_lobe_learning_store", LobeLearningStore(name))
        return {"status": "success", "content": {"registered": name}, "registered": name}

    @staticmethod
    def _learning_memory_type(destination: str) -> str:
        return f"lobe_learning:{destination}"

    @staticmethod
    def _learning_text(payload: Dict[str, Any]) -> Optional[str]:
        for key in ("fact", "content", "text", "value"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _skill_key(payload: Dict[str, Any]) -> str:
        raw_skill = payload.get("skill", payload.get("name", payload.get("key", "custom")))
        if not isinstance(raw_skill, str) or not raw_skill.strip():
            raw_skill = "custom"
        safe = "".join(
            char.lower() if char.isalnum() or char in {"_", "-", ":"} else "_"
            for char in raw_skill.strip()
        ).strip("_")
        return f"skill:{safe or 'custom'}"

    @classmethod
    def _skill_fact(cls, payload: Dict[str, Any]) -> Optional[str]:
        behavior = payload.get("behavior", payload.get("fact", payload.get("content")))
        if not isinstance(behavior, str) or not behavior.strip():
            return None
        trigger = payload.get("trigger")
        outcome = payload.get("outcome")
        parts = [f"Skill behavior: {behavior.strip()}"]
        if isinstance(trigger, str) and trigger.strip():
            parts.append(f"Trigger context: {trigger.strip()}")
        if isinstance(outcome, str) and outcome.strip():
            parts.append(f"Expected outcome: {outcome.strip()}")
        return " | ".join(parts)

    def _learned_guidance_for_message(
        self, destination: str, msg_type: str, content: Dict[str, Any], source: str
    ) -> list[str]:
        if msg_type in _LEARNING_ROUTE_TYPES or msg_type == "health":
            return []
        user_id = content.get("user_id", "default")
        if not isinstance(user_id, str) or not user_id.strip():
            user_id = "default"
        query_terms = [
            msg_type,
            content.get("query", ""),
            content.get("text", ""),
            content.get("user_input", ""),
            content.get("input", ""),
        ]
        query = " ".join(term for term in query_terms if isinstance(term, str) and term.strip()).strip()
        def _recall(query_text: str) -> list[Dict[str, Any]]:
            recalled = self._handle_lobe_learning(
                destination,
                "recall",
                {
                    "user_id": user_id,
                    "query": query_text,
                    "min_confidence": 0.55,
                    "limit": 5,
                    "mark_used": True,
                },
                source=f"{source}:{destination}:guidance",
            )
            if recalled.get("status") != "success":
                return []
            memories = self._content(recalled).get("memories", [])
            return memories if isinstance(memories, list) else []

        memories = _recall(query)
        if not memories:
            memories = _recall("")
        if not isinstance(memories, list):
            return []
        return [
            memory.get("fact", memory.get("content", ""))
            for memory in memories
            if isinstance(memory, dict)
            and isinstance(memory.get("fact", memory.get("content", "")), str)
            and memory.get("fact", memory.get("content", "")).strip()
        ]

    @staticmethod
    def _classify_lesson_type(lesson_text: str) -> str:
        if _LESSON_TYPE_PATTERNS["correction"].search(lesson_text):
            return "correction"
        if _LESSON_TYPE_PATTERNS["feedback"].search(lesson_text):
            return "feedback"
        if _LESSON_TYPE_PATTERNS["skill"].search(lesson_text):
            return "skill"
        return "skill"

    @staticmethod
    def _skill_name_from_lesson(lesson_text: str, lesson_type: str) -> str:
        words = [
            "".join(ch for ch in token.lower() if ch.isalnum())
            for token in lesson_text.split()
        ]
        words = [word for word in words if word]
        base = "_".join(words[:4]) if words else lesson_type
        return f"{lesson_type}_{base}"[:80]

    @staticmethod
    def _behavior_from_lesson(lesson_text: str, lesson_type: str) -> str:
        if lesson_type == "correction":
            return f"Correction to apply: {lesson_text}"
        if lesson_type == "feedback":
            return f"Feedback behavior to apply: {lesson_text}"
        return f"Skill behavior to apply: {lesson_text}"

    def _learning_targets_for_lesson(self, lesson_type: str, lesson_text: str) -> list[str]:
        with self.lobe_handlers_lock:
            registered = list(self.lobe_handlers.keys())
        candidates = [name for name in registered if name not in {"notus"}]
        if not candidates:
            return []
        lesson_lower = lesson_text.lower()
        matched: list[str] = []
        for lobe in candidates:
            allowed_types = _LOBE_LEARNING_RULES.get(
                lobe, {"skill", "feedback", "correction"}
            )
            if lesson_type not in allowed_types:
                continue
            if lobe == "pattern" and not any(
                word in lesson_lower for word in ("pattern", "math", "number", "equation")
            ):
                if lesson_type == "skill":
                    continue
            if lobe == "language" and not any(
                word in lesson_lower for word in ("grammar", "word", "tone", "speak", "write")
            ):
                if lesson_type in {"skill", "feedback"}:
                    continue
            if lobe == "emotion" and lesson_type == "skill":
                continue
            matched.append(lobe)
        if matched:
            return matched
        return candidates

    def teach_monday(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        lesson = payload.get("lesson", payload.get("text", payload.get("content", "")))
        if not isinstance(lesson, str) or not lesson.strip():
            return {"status": "error", "message": "teach_monday requires lesson text"}
        lesson_text = lesson.strip()
        user_id = payload.get("user_id", "default")
        if not isinstance(user_id, str) or not user_id.strip():
            user_id = "default"
        lesson_type = self._classify_lesson_type(lesson_text)
        skill_name = self._skill_name_from_lesson(lesson_text, lesson_type)
        behavior = self._behavior_from_lesson(lesson_text, lesson_type)
        targets = self._learning_targets_for_lesson(lesson_type, lesson_text)
        taught = []
        failed = []
        for destination in targets:
            result = self._handle_lobe_learning(
                destination,
                "teach_skill",
                {
                    "skill": skill_name,
                    "behavior": behavior,
                    "trigger": payload.get("trigger", lesson_text),
                    "outcome": payload.get("outcome", "Apply lesson on relevant future tasks."),
                    "user_id": user_id,
                    "confidence": payload.get("confidence", 0.75),
                    "lesson_type": lesson_type,
                },
                source="teach_monday",
            )
            if result.get("status") == "success":
                taught.append(
                    {
                        "lobe": destination,
                        "key": result.get("key"),
                        "confidence": result.get("confidence"),
                    }
                )
            else:
                failed.append({"lobe": destination, "message": result.get("message", "unknown error")})

        status = "success" if taught else "error"
        return {
            "status": status,
            "content": {
                "lesson_type": lesson_type,
                "skill": skill_name,
                "lesson": lesson_text,
                "taught": taught,
                "failed": failed,
                "target_count": len(targets),
                "applied_count": len(taught),
            },
            "lesson_type": lesson_type,
            "skill": skill_name,
            "taught": taught,
            "failed": failed,
        }

    def learning_overview(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        user_id = payload.get("user_id", "default")
        if not isinstance(user_id, str) or not user_id.strip():
            user_id = "default"
        try:
            limit = int(payload.get("limit", 5))
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, 50))
        with self.lobe_handlers_lock:
            registered = list(self.lobe_handlers.keys())
        lobes = [name for name in registered if name not in {"notus"}]
        overview = []
        for lobe in lobes:
            stats = self._handle_lobe_learning(
                lobe, "learning_stats", {"user_id": user_id}, source="learning_overview"
            )
            skills = self._handle_lobe_learning(
                lobe,
                "list_skills",
                {"user_id": user_id, "limit": limit},
                source="learning_overview",
            )
            if stats.get("status") != "success":
                continue
            stats_content = self._content(stats)
            skills_content = self._content(skills) if skills.get("status") == "success" else {}
            overview.append(
                {
                    "lobe": lobe,
                    "stats": stats_content,
                    "skills": skills_content.get("memories", []),
                }
            )
        return {"status": "success", "content": {"user_id": user_id, "lobes": overview}, "lobes": overview}

    def _handle_lobe_learning(
        self, destination: str, msg_type: str, payload: Dict[str, Any], source: str
    ) -> Dict[str, Any]:
        with self.lobe_handlers_lock:
            lobe = self.lobe_handlers.get(destination)
        if lobe is None:
            return {"status": "error", "message": f"Unknown destination: {destination}"}
        store = getattr(lobe, "_lobe_learning_store", None)
        if store is None:
            store = LobeLearningStore(destination)
            setattr(lobe, "_lobe_learning_store", store)
        if not isinstance(store, LobeLearningStore):
            return {"status": "error", "message": f"{destination} has invalid learning store"}

        user_id = payload.get("user_id", "default")
        memory_type = self._learning_memory_type(destination)

        if msg_type in {"learn", "teach_skill"}:
            payload_to_store = dict(payload)
            if msg_type == "teach_skill":
                skill_fact = self._skill_fact(payload)
                if skill_fact is None:
                    return {
                        "status": "error",
                        "message": "teach_skill requires behavior/fact/content",
                    }
                payload_to_store["fact"] = skill_fact
                payload_to_store["key"] = self._skill_key(payload)
            learned = store.learn(
                {
                    **payload_to_store,
                    "user_id": user_id,
                    "source": f"{source}:{destination}",
                }
            )
            if learned.get("status") != "success":
                return learned
            content = self._content(learned)
            content.setdefault("destination", destination)
            content.setdefault("memory_type", memory_type)
            flattened = {
                key: value
                for key, value in content.items()
                if key not in {"status", "message", "content"}
            }
            return {"status": "success", "content": content, **flattened}

        operation_map = {
            "recall": "recall_lobe_facts",
            "list_skills": "recall_lobe_facts",
            "reinforce_learning": "reinforce_lobe_fact",
            "contradict_learning": "contradict_lobe_fact",
            "forget_learning": "forget_lobe_fact",
            "learning_stats": "lobe_learning_stats",
        }
        target_operation = operation_map.get(msg_type)
        if target_operation is None:
            return {"status": "error", "message": f"Unknown learning operation: {msg_type}"}

        routed_payload = {
            **payload,
            "user_id": user_id,
            **({"key_prefix": "skill:"} if msg_type == "list_skills" else {}),
        }
        if target_operation == "recall_lobe_facts":
            outcome = store.recall(routed_payload)
        elif target_operation == "reinforce_lobe_fact":
            outcome = store.adjust(routed_payload, "reinforce")
        elif target_operation == "contradict_lobe_fact":
            outcome = store.adjust(routed_payload, "contradict")
        elif target_operation == "forget_lobe_fact":
            outcome = store.adjust(routed_payload, "forget")
        elif target_operation == "lobe_learning_stats":
            outcome = store.stats(routed_payload)
        else:
            return {"status": "error", "message": f"Unsupported operation: {target_operation}"}
        if outcome.get("status") != "success":
            return outcome
        content = self._content(outcome)
        content.setdefault("destination", destination)
        content.setdefault("memory_type", memory_type)
        flattened = {
            key: value
            for key, value in content.items()
            if key not in {"status", "message", "content"}
        }
        return {"status": "success", "content": content, **flattened}

    def _auto_adapt_from_interaction(
        self,
        destination: str,
        msg_type: str,
        content: Dict[str, Any],
        response: Dict[str, Any],
        source: str,
    ) -> None:
        if msg_type in _LEARNING_ROUTE_TYPES or msg_type == "health":
            return
        user_id = content.get("user_id", "default")
        if not isinstance(user_id, str) or not user_id.strip():
            user_id = "default"
        behavior_key = f"behavior:{msg_type}"
        if response.get("status") == "success":
            self._handle_lobe_learning(
                destination,
                "learn",
                {
                    "user_id": user_id,
                    "key": behavior_key,
                    "fact": (
                        f"For message type '{msg_type}', keep behavior that returns "
                        f"status success with stable content."
                    ),
                    "confidence": 0.7,
                    "reinforcement": 0.8,
                },
                source=f"{source}:auto_adapt",
            )
            return

        self._handle_lobe_learning(
            destination,
            "contradict_learning",
            {
                "user_id": user_id,
                "key": behavior_key,
                "penalty": 0.2,
            },
            source=f"{source}:auto_adapt",
        )
        self._handle_lobe_learning(
            destination,
            "learn",
            {
                "user_id": user_id,
                "key": f"recovery:{msg_type}",
                "fact": (
                    f"When '{msg_type}' fails, validate inputs and return a safe, "
                    "non-crashing fallback response."
                ),
                "confidence": 0.6,
            },
            source=f"{source}:auto_adapt",
        )

    def send_message(
        self,
        destination: str,
        msg_type: str,
        content: Optional[Dict[str, Any]] = None,
        source: str = "thalamus",
    ) -> Dict[str, Any]:
        """Deliver one envelope synchronously and return its normalized response."""
        if not isinstance(content, dict):
            return {"status": "error", "message": "Message content must be a dictionary"}
        if msg_type in _LEARNING_ROUTE_TYPES:
            return self._handle_lobe_learning(destination, msg_type, content, source)
        with self.lobe_handlers_lock:
            lobe = self.lobe_handlers.get(destination)
        if lobe is None:
            self.lobe_status[destination] = "offline"
            return {"status": "error", "message": f"Unknown destination: {destination}"}

        envelope_content = dict(content)
        learned_guidance = self._learned_guidance_for_message(
            destination, msg_type, envelope_content, source
        )
        if learned_guidance:
            envelope_content["learned_guidance"] = learned_guidance
            envelope_content["applied_learning"] = {
                "count": len(learned_guidance),
                "for_message_type": msg_type,
            }
        envelope = {
            "type": msg_type,
            "content": envelope_content,
            "source": source,
            "message_id": str(uuid.uuid4()),
        }
        try:
            handler = getattr(lobe, "process_message", None) or getattr(
                lobe, "process_message_safe"
            )
            response = handler(envelope)
            if not isinstance(response, dict):
                response = {"status": "success", "content": {"result": response}}
            response.setdefault("status", "success")
            if "content" not in response:
                response["content"] = {
                    key: value
                    for key, value in response.items()
                    if key not in {"status", "message"}
                }
            self.lobe_status[destination] = "online"
        except Exception as exc:
            self.lobe_status[destination] = "error"
            response = {"status": "error", "message": f"{destination}: {exc}", "content": {}}

        self._auto_adapt_from_interaction(destination, msg_type, content, response, source)
        self.message_routes.append(
            {
                "from": source,
                "to": destination,
                "type": msg_type,
                "status": response["status"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return response

    def send_and_wait(self, destination: str, msg_type: str,
                      content: Optional[Dict[str, Any]] = None,
                      source: str = "thalamus") -> Dict[str, Any]:
        """Compatibility name for direct calls, which are always synchronous."""
        return self.send_message(destination, msg_type, content or {}, source)

    def broadcast_message(
        self, destinations: Iterable[str], msg_type: str,
        content: Optional[Dict[str, Any]] = None, source: str = "thalamus"
    ) -> Dict[str, Dict[str, Any]]:
        return {
            destination: self.send_message(destination, msg_type, content or {}, source)
            for destination in destinations
        }

    @staticmethod
    def _content(response: Dict[str, Any]) -> Dict[str, Any]:
        content = response.get("content", {})
        return content if isinstance(content, dict) else {}

    @staticmethod
    def _first_usable_text(*candidates: Any) -> Optional[str]:
        """Select a reasoning conclusion without replacing it with a provider response."""
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate
            if isinstance(candidate, (list, tuple)):
                propositions = [
                    proposition
                    for proposition in candidate
                    if isinstance(proposition, str) and proposition.strip()
                ]
                if propositions:
                    return " ".join(propositions)
        return None

    def _reasoning_answer(self, reasoning: Dict[str, Any]) -> tuple[Dict[str, Any], Optional[str]]:
        content = self._content(reasoning)
        semantic_input = content.get("semantic_input", {})
        semantic_input = semantic_input.copy() if isinstance(semantic_input, dict) else {}
        for key in ("answer", "conclusion", "propositions"):
            if key not in semantic_input:
                value = content.get(key, reasoning.get(key))
                if value is not None:
                    semantic_input[key] = value
        answer = self._first_usable_text(
            semantic_input.get("answer"),
            semantic_input.get("conclusion"),
            semantic_input.get("propositions"),
        )
        return semantic_input, answer


    @staticmethod
    def _build_attention_signals(
        user_input: str,
        perception_payload: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
    ) -> List[Dict[str, Any]]:
        """Build competing live-path signals for AttentionLobe (user + perception + ambient)."""
        perception_payload = perception_payload if isinstance(perception_payload, dict) else {}
        signals: List[Dict[str, Any]] = []
        text = user_input if isinstance(user_input, str) else ""
        try:
            novelty_score = float(perception_payload.get("novelty_score") or 0.0)
        except (TypeError, ValueError):
            novelty_score = 0.0
        signals.append(
            {
                "id": "user_input",
                "text": text,
                "source": "user",
                "modality": "text",
                "priority": 0.55,
                "novelty_flags": list(perception_payload.get("novelty_flags") or []),
                "novelty_score": novelty_score,
                "emotions": list(
                    (perception_payload.get("raw_meta") or {}).get("emotions")
                    or perception_payload.get("emotions")
                    or []
                ),
                "entities": list(perception_payload.get("entities") or []),
                "concepts": list(perception_payload.get("concepts") or perception_payload.get("words") or []),
                "user_id": user_id,
            }
        )
        # Perception envelope as its own competing signal when present.
        if perception_payload:
            perc_text = (
                perception_payload.get("text")
                or perception_payload.get("normalized_text")
                or text
            )
            signals.append(
                {
                    "id": "perception_envelope",
                    "text": perc_text if isinstance(perc_text, str) else text,
                    "source": "perception",
                    "modality": str(perception_payload.get("modality") or "text"),
                    "priority": 0.25,
                    "novelty_flags": list(perception_payload.get("novelty_flags") or []),
                    "novelty_score": novelty_score,
                    "emotions": list(
                        (perception_payload.get("raw_meta") or {}).get("emotions")
                        or perception_payload.get("emotions")
                        or []
                    ),
                    "entities": list(perception_payload.get("entities") or []),
                    "concepts": list(
                        perception_payload.get("concepts")
                        or perception_payload.get("words")
                        or []
                    ),
                }
            )
            # SensoryIntegration multi-modal competitors (already fused on stream).
            for sig in perception_payload.get("attention_signals") or []:
                if isinstance(sig, dict) and sig.get("id"):
                    signals.append(dict(sig))
            for idx, ent in enumerate(perception_payload.get("entities") or []):
                if not isinstance(ent, str) or not ent.strip():
                    continue
                signals.append(
                    {
                        "id": f"entity:{ent.strip()}",
                        "text": ent.strip(),
                        "source": "perception",
                        "modality": "text",
                        "priority": 0.20,
                        "entities": [ent.strip()],
                    }
                )
                if idx >= 4:
                    break
            for idx, flag in enumerate(perception_payload.get("novelty_flags") or []):
                if not flag:
                    continue
                signals.append(
                    {
                        "id": f"novelty:{flag}",
                        "text": str(flag),
                        "source": "perception",
                        "modality": "text",
                        "priority": 0.30,
                        "novelty_flags": [str(flag)],
                        "novelty_score": novelty_score,
                    }
                )
                if idx >= 3:
                    break
            if novelty_score >= 0.45:
                signals.append(
                    {
                        "id": "novelty_score",
                        "text": f"novelty_score:{novelty_score:.3f}",
                        "source": "novelty",
                        "modality": "text",
                        "priority": min(0.55, 0.25 + 0.35 * novelty_score),
                        "novelty_score": novelty_score,
                        "novelty_flags": list(perception_payload.get("novelty_flags") or [])[:4],
                    }
                )
        # Low-salience ambient competitor so ranking is real, not a single dead entry.
        signals.append(
            {
                "id": "ambient_noise",
                "text": "ambient room tone",
                "source": "ambient",
                "modality": "text",
                "priority": 0.0,
            }
        )
        return signals

    def _attend_live_signals(
        self,
        user_input: str,
        perception_payload: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """Send competing signals through attention; return ranking payload or {}."""
        with self.lobe_handlers_lock:
            has_attention = "attention" in self.lobe_handlers
        if not has_attention:
            return {}
        signals = self._build_attention_signals(user_input, perception_payload, user_id)
        response = self.send_and_wait(
            "attention",
            "evaluate",
            {"signals": signals, "user_id": user_id},
            source="thalamus",
        )
        if response.get("status") != "success":
            return {}
        payload = self._content(response)
        # Honest route: push focus to reasoning when registered (soft ack).
        if payload.get("focus"):
            self.send_and_wait(
                "attention",
                "route_focus",
                {},
                source="thalamus",
            )
        return payload

    def process_sensory_input(
        self,
        modality: str,
        *,
        text: Optional[str] = None,
        path: Optional[str] = None,
        audio_bytes: Optional[bytes] = None,
        image_bytes: Optional[bytes] = None,
        user_id: str = "default",
        continue_conversation: bool = True,
        extra_inputs: Optional[List[Any]] = None,
    ) -> Any:
        """Route sensory intake via SensoryIntegration (when registered) then conversation.

        Modalities: text | audio/hearing | vision/visual/image | multimodal.
        File/buffer paths are first-class. ``extra_inputs`` lets callers attach
        sibling modality dicts so SI fuses one multi-modal stream. Returns reply
        string when continue_conversation, else the unified stream envelope.
        Falls back to direct Perception when SensoryIntegration is absent.
        """
        modality_l = (modality or "text").strip().lower()
        with self.lobe_handlers_lock:
            has_perception = "perception" in self.lobe_handlers
            has_si = "sensory_integration" in self.lobe_handlers
        if not has_perception:
            if modality_l == "text" and isinstance(text, str) and text.strip():
                return self.process_user_input(text, user_id=user_id)
            return {"status": "error", "message": "perception lobe not registered"}

        # Preferred live path: SensoryIntegration unifies → Attention → Conversation.
        if has_si:
            bundle: List[Any] = []
            if modality_l in ("text", "chat", "language"):
                if not isinstance(text, str) or not text.strip():
                    return {"status": "error", "message": "text modality requires text="}
                bundle.append({"modality": "text", "text": text.strip()})
            elif modality_l in ("audio", "hearing", "sound"):
                item: Dict[str, Any] = {"modality": "audio"}
                if path:
                    item["path"] = path
                if audio_bytes is not None:
                    item["audio_bytes"] = audio_bytes
                # No path/bytes → Perception will attempt mic and fail honestly.
                bundle.append(item)
            elif modality_l in ("vision", "visual", "image", "sight"):
                item = {"modality": "vision"}
                if path:
                    item["path"] = path
                if image_bytes is not None:
                    item["image_bytes"] = image_bytes
                bundle.append(item)
            elif modality_l in ("multimodal", "bundle", "fused"):
                # Caller supplies the full input list via extra_inputs (and optional text).
                if isinstance(text, str) and text.strip():
                    bundle.append({"modality": "text", "text": text.strip()})
            else:
                return {"status": "error", "message": f"unknown modality: {modality}"}

            if extra_inputs:
                for extra in extra_inputs:
                    if extra is not None:
                        bundle.append(extra)

            if not bundle:
                return {
                    "status": "error",
                    "message": "sensory bundle empty — provide modality inputs",
                }

            # Attention-once: when continue_conversation, Thalamus.process_user_input
            # owns the single Attention evaluate/route via _attend_live_signals.
            # SI only routes Attention when returning the stream alone (no live path).
            si_resp = self.send_and_wait(
                "sensory_integration",
                "ingest",
                {
                    "inputs": bundle,
                    "user_id": user_id,
                    "route_attention": not continue_conversation,
                    "primary_modality": modality_l,
                },
                source="thalamus",
            )
            if si_resp.get("status") != "success":
                msg = si_resp.get("message") or "sensory integration failed"
                if not continue_conversation:
                    return si_resp
                return f"I couldn't integrate that sensory input ({msg})."

            stream = self._content(si_resp)
            if not isinstance(stream, dict):
                stream = si_resp.get("stream") if isinstance(si_resp.get("stream"), dict) else {}

            # Honest hard-fail when the only requested modality is unavailable.
            honesty = (stream.get("raw_meta") or {}).get("honesty") or {}
            active = list(stream.get("modalities_active") or [])
            if modality_l in ("audio", "hearing", "sound") and "audio" not in active and "hearing" not in active:
                err = (honesty.get("audio") or {}).get("error") or "audio perception failed"
                if not continue_conversation:
                    return {
                        "status": "error",
                        "message": err,
                        "content": stream,
                    }
                return f"I couldn't hear that ({err})."
            if modality_l in ("vision", "visual", "image", "sight") and not any(
                m in active for m in ("vision", "visual", "image", "sight")
            ):
                err = (honesty.get("vision") or {}).get("error") or "vision perception failed"
                if not continue_conversation:
                    return {
                        "status": "error",
                        "message": err,
                        "content": stream,
                    }
                return f"I couldn't see that ({err})."

            if not continue_conversation:
                return stream

            spoken = stream.get("text") or stream.get("normalized_text")
            if isinstance(spoken, str) and spoken.strip():
                return self.process_user_input(
                    spoken.strip(), user_id=user_id, perception_payload=stream
                )
            # Multi-modal / acoustic-only: enter live path with an honest note.
            mods = ",".join(stream.get("modalities") or [modality_l])
            note = (
                f"[{mods}] "
                + ", ".join(str(c) for c in (stream.get("concepts") or [])[:6])
            )
            return self.process_user_input(
                note, user_id=user_id, perception_payload=stream
            )

        # Fallback when SensoryIntegration is not registered: direct Perception.
        if modality_l in ("text", "chat", "language"):
            if not isinstance(text, str) or not text.strip():
                return {"status": "error", "message": "text modality requires text="}
            if continue_conversation:
                return self.process_user_input(text, user_id=user_id)
            resp = self.send_and_wait(
                "perception", "perceive_text", {"text": text, "user_id": user_id}
            )
            return self._content(resp) if resp.get("status") == "success" else resp

        if modality_l in ("audio", "hearing", "sound"):
            content = {"user_id": user_id}
            if path:
                content["path"] = path
            if audio_bytes is not None:
                content["audio_bytes"] = audio_bytes
            if not path and audio_bytes is None:
                content["use_mic"] = True
            resp = self.send_and_wait("perception", "perceive_audio", content)
            if resp.get("status") != "success":
                return resp if not continue_conversation else (
                    f"I couldn't hear that ({resp.get('message') or 'audio perception failed'})."
                )
            envelope = self._content(resp)
            if not continue_conversation:
                return envelope
            spoken = envelope.get("text")
            if isinstance(spoken, str) and spoken.strip():
                return self.process_user_input(
                    spoken.strip(), user_id=user_id, perception_payload=envelope
                )
            note = (
                "[hearing] "
                + ", ".join(str(c) for c in (envelope.get("concepts") or [])[:6])
            )
            return self.process_user_input(
                note, user_id=user_id, perception_payload=envelope
            )

        if modality_l in ("vision", "visual", "image", "sight"):
            content = {"user_id": user_id}
            if path:
                content["path"] = path
            if image_bytes is not None:
                content["image_bytes"] = image_bytes
            if not path and image_bytes is None:
                content["use_camera"] = True
            resp = self.send_and_wait("perception", "perceive_vision", content)
            if resp.get("status") != "success":
                return resp if not continue_conversation else (
                    f"I couldn't see that ({resp.get('message') or 'vision perception failed'})."
                )
            envelope = self._content(resp)
            if not continue_conversation:
                return envelope
            note = envelope.get("text") or (
                "[vision] "
                + ", ".join(str(c) for c in (envelope.get("concepts") or [])[:6])
            )
            return self.process_user_input(
                str(note), user_id=user_id, perception_payload=envelope
            )

        return {"status": "error", "message": f"unknown modality: {modality}"}


    def _meta_cognition_watch_reasoning(
        self,
        user_input: str,
        semantic_input: Dict[str, Any],
        reasoning_answer: Any,
        memories: Any,
    ) -> Dict[str, Any]:
        """Tiny glue: Meta-cognition observes reasoning before Language.

        Applies force-refusal / uncertainty flags onto semantic_input when
        the lobe is registered. No-op when offline. Does not invent facts.
        """
        with self.lobe_handlers_lock:
            has_meta = "meta_cognition" in self.lobe_handlers
        if not has_meta:
            return semantic_input
        try:
            watched = self.send_and_wait(
                "meta_cognition",
                "monitor_reasoning",
                {
                    "user_input": user_input,
                    "semantic_input": semantic_input,
                    "reasoning_answer": reasoning_answer,
                    "memories": memories,
                    "apply": True,
                },
            )
        except Exception:
            return semantic_input
        if watched.get("status") != "success":
            return semantic_input
        body = self._content(watched)
        verdict = body.get("verdict") or watched.get("verdict")
        if isinstance(verdict, dict):
            self.last_meta_cognition = verdict
        applied = body.get("semantic_input") or watched.get("semantic_input")
        if isinstance(applied, dict):
            return applied
        # Still attach a thin meta tag even if apply returned nothing
        if isinstance(verdict, dict):
            out = dict(semantic_input)
            out["meta_cognition"] = {
                "path": verdict.get("path"),
                "findings": list(verdict.get("findings") or []),
                "signals": dict(verdict.get("signals") or {}),
                "limits": verdict.get("limits"),
            }
            return out
        return semantic_input

    def _meta_cognition_watch_language(
        self,
        sentence: str,
        semantic_input: Dict[str, Any],
    ) -> str:
        """Tiny glue: second look after Language; may force grounded refusal."""
        with self.lobe_handlers_lock:
            has_meta = "meta_cognition" in self.lobe_handlers
        if not has_meta:
            return sentence
        try:
            watched = self.send_and_wait(
                "meta_cognition",
                "monitor_language",
                {
                    "sentence": sentence,
                    "semantic_input": semantic_input,
                    "prior_verdict": self.last_meta_cognition,
                },
            )
        except Exception:
            return sentence
        if watched.get("status") != "success":
            return sentence
        body = self._content(watched)
        verdict = body.get("verdict") or watched.get("verdict")
        if isinstance(verdict, dict):
            self.last_meta_cognition = verdict
            corrected = verdict.get("corrected_sentence")
            if isinstance(corrected, str) and corrected.strip():
                return corrected.strip()
        return sentence

    def _executive_set_goal_from_turn(
        self,
        user_input: str,
        understanding: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Tiny glue: Executive holds current goal from Conversation intent."""
        with self.lobe_handlers_lock:
            has_exec = "executive_control" in self.lobe_handlers
        if not has_exec:
            return None
        try:
            resp = self.send_and_wait(
                "executive_control",
                "set_goal_from_turn",
                {"user_input": user_input, "understanding": understanding},
            )
        except Exception:
            return None
        if resp.get("status") != "success":
            return None
        body = self._content(resp)
        goal_info = {
            "goal": body.get("goal") or resp.get("goal"),
            "priority": body.get("priority", resp.get("priority")),
            "detail": body.get("detail") or resp.get("detail"),
            "source": body.get("source") or resp.get("source"),
            "inhibited_actions": list(
                body.get("inhibited_actions") or resp.get("inhibited_actions") or []
            ),
        }
        # Steer Attention toward the held goal (real salience update).
        try:
            steer = self.send_and_wait(
                "executive_control", "steer_attention", {}, source="thalamus"
            )
            if steer.get("status") == "success":
                steer_body = self._content(steer)
                goal_info["steer"] = {
                    "steered": bool(steer_body.get("steered", steer.get("steered"))),
                    "reason": steer_body.get("reason") or steer.get("reason"),
                    "goal_signal_present": bool(
                        steer_body.get("goal_signal_present", steer.get("goal_signal_present"))
                    ),
                    "focus": steer_body.get("focus", steer.get("focus")),
                    "goal_signal_keys": list(
                        steer_body.get("goal_signal_keys")
                        or steer.get("goal_signal_keys")
                        or []
                    ),
                }
        except Exception:
            pass
        self.last_executive = goal_info
        return goal_info

    def _refresh_attention_payload_post_executive(
        self, prior: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Same-turn handoff: rebuild attention_payload after Executive re-selects focus.

        Executive.steer_attention calls select_focus but does not route_focus, and the
        early evaluate snapshot would otherwise remain what Reasoning.think receives.
        Re-route to Reasoning (soft ack) and refresh focus/ranked from live Attention.
        """
        payload: Dict[str, Any] = dict(prior) if isinstance(prior, dict) else {}
        with self.lobe_handlers_lock:
            has_attention = "attention" in self.lobe_handlers
        if not has_attention:
            return payload
        routed_payload: Dict[str, Any] = {}
        try:
            route_resp = self.send_and_wait(
                "attention", "route_focus", {}, source="thalamus"
            )
            if route_resp.get("status") == "success":
                body = self._content(route_resp)
                candidate = body.get("payload") if isinstance(body, dict) else None
                if isinstance(candidate, dict):
                    routed_payload = candidate
        except Exception:
            routed_payload = {}
        if routed_payload.get("focus"):
            payload["focus"] = routed_payload.get("focus")
            payload["focus_text"] = routed_payload.get("focus_text")
            payload["focus_score"] = routed_payload.get("score")
            payload["focus_source"] = routed_payload.get("source")
        else:
            try:
                status_resp = self.send_and_wait(
                    "attention", "get_status", {}, source="thalamus"
                )
                if status_resp.get("status") == "success":
                    status = self._content(status_resp)
                    focus = status.get("current_focus")
                    if focus:
                        payload["focus"] = focus
                        top = status.get("top") or []
                        if isinstance(top, list) and top:
                            head = top[0] if isinstance(top[0], dict) else {}
                            if head.get("id") == focus:
                                payload["focus_text"] = head.get("text")
                                payload["focus_score"] = head.get("score")
                                payload["focus_source"] = head.get("source")
            except Exception:
                pass
        try:
            rank_resp = self.send_and_wait(
                "attention", "rank", {}, source="thalamus"
            )
            if rank_resp.get("status") == "success":
                ranked = self._content(rank_resp).get("ranked")
                if ranked is None:
                    ranked = rank_resp.get("ranked")
                if isinstance(ranked, list):
                    payload["ranked"] = ranked
                    # Keep focus fields coherent with refreshed ranking when missing text.
                    focus_id = payload.get("focus")
                    if focus_id:
                        match = next(
                            (
                                r
                                for r in ranked
                                if isinstance(r, dict) and r.get("id") == focus_id
                            ),
                            None,
                        )
                        if match:
                            payload.setdefault("focus_text", match.get("text"))
                            payload.setdefault("focus_score", match.get("score"))
                            payload.setdefault("focus_source", match.get("source"))
        except Exception:
            pass
        return payload

    def _executive_should_inhibit(self, action: str) -> bool:
        """Tiny glue: ask Executive whether an off-goal action must be blocked."""
        with self.lobe_handlers_lock:
            has_exec = "executive_control" in self.lobe_handlers
        if not has_exec:
            return False
        try:
            resp = self.send_and_wait(
                "executive_control",
                "should_inhibit",
                {"action": action},
                source="thalamus",
            )
        except Exception:
            return False
        if resp.get("status") != "success":
            return False
        body = self._content(resp)
        inhibited = bool(body.get("inhibited", resp.get("inhibited")))
        if inhibited:
            snap = dict(self.last_executive) if isinstance(self.last_executive, dict) else {}
            snap["last_inhibition"] = {
                "action": body.get("action") or action,
                "inhibited": True,
                "reason": body.get("reason") or resp.get("reason"),
                "goal": body.get("goal") or resp.get("goal") or snap.get("goal"),
            }
            self.last_executive = snap
        return inhibited


    def _build_pattern_observation(
        self,
        user_input: str,
        perception_payload: Optional[Dict[str, Any]] = None,
        attention_payload: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None,
        emotional_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Assemble Pattern.observe data from live Perception/Attention/Conversation/Emotion."""
        perception_payload = perception_payload if isinstance(perception_payload, dict) else {}
        attention_payload = attention_payload if isinstance(attention_payload, dict) else {}
        understanding = understanding if isinstance(understanding, dict) else {}
        emotional_state = emotional_state if isinstance(emotional_state, dict) else {}

        items: List[str] = []
        concepts = perception_payload.get("concepts")
        if isinstance(concepts, list):
            for concept in concepts:
                if isinstance(concept, str) and concept.strip():
                    items.append(concept.strip())
                elif isinstance(concept, dict):
                    name = concept.get("name") or concept.get("text") or concept.get("word")
                    if name is not None and str(name).strip():
                        items.append(str(name).strip())
        elif isinstance(concepts, dict):
            for word in concepts.get("words") or []:
                if word is not None and str(word).strip():
                    items.append(str(word).strip())

        words: List[str] = []
        for word in perception_payload.get("words") or []:
            if word is not None and str(word).strip():
                words.append(str(word).strip())
        if not words:
            words = list(items)

        topics: List[str] = []
        focus = attention_payload.get("focus_text") or attention_payload.get("focus")
        if focus is not None and str(focus).strip():
            topics.append(str(focus).strip())
        for ranked in attention_payload.get("ranked") or []:
            if isinstance(ranked, dict):
                rid = ranked.get("id") or ranked.get("text")
                if rid is not None and str(rid).strip():
                    topics.append(str(rid).strip())
            elif ranked is not None and str(ranked).strip():
                topics.append(str(ranked).strip())
        intent = understanding.get("intent")
        if intent is not None and str(intent).strip():
            topics.append(str(intent).strip())
        for topic in understanding.get("topics") or []:
            if topic is not None and str(topic).strip():
                topics.append(str(topic).strip())

        emotions: Dict[str, float] = {}
        emotion_name = (
            emotional_state.get("current_emotion")
            or emotional_state.get("emotion")
            or emotional_state.get("mood")
        )
        if emotion_name is not None and str(emotion_name).strip():
            try:
                intensity = float(
                    emotional_state.get("intensity")
                    or emotional_state.get("emotion_intensity")
                    or 0.5
                )
            except (TypeError, ValueError):
                intensity = 0.5
            emotions[str(emotion_name).strip()] = intensity

        if not items and isinstance(user_input, str):
            # Fallback: tokenize so numeric sequences still reach Pattern.
            items = [
                token
                for token in re.findall(r"[A-Za-z0-9]+", user_input)
                if token
            ]
            if not words:
                words = list(items)

        # Dedup while preserving order.
        def _dedupe(values: List[str]) -> List[str]:
            seen = set()
            out: List[str] = []
            for value in values:
                key = value.casefold()
                if key in seen:
                    continue
                seen.add(key)
                out.append(value)
            return out

        return {
            "items": _dedupe(items),
            "words": _dedupe(words),
            "statement": user_input if isinstance(user_input, str) else "",
            "emotions": emotions,
            "topics": _dedupe(topics),
        }

    def _run_pattern_live(
        self,
        user_input: str,
        perception_payload: Optional[Dict[str, Any]] = None,
        attention_payload: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None,
        emotional_state: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """Observe + harvest significant_patterns as the existing pattern_result interface.

        Pattern discovers; it does not answer. Discoveries are handed to Reasoning
        (and optionally Attention) via pattern_result.
        """
        with self.lobe_handlers_lock:
            has_pattern = "pattern" in self.lobe_handlers
        if not has_pattern:
            return {}

        observation = self._build_pattern_observation(
            user_input,
            perception_payload=perception_payload,
            attention_payload=attention_payload,
            understanding=understanding,
            emotional_state=emotional_state,
        )
        try:
            observed = self.send_and_wait(
                "pattern",
                "observe",
                observation,
                source="thalamus",
            )
        except Exception:
            observed = {"status": "error"}
        if observed.get("status") != "success":
            return {"status": "error", "significant_patterns": {}}

        try:
            significant_resp = self.send_and_wait(
                "pattern",
                "get_significant",
                {},
                source="thalamus",
            )
        except Exception:
            significant_resp = {"status": "error"}

        body = self._content(significant_resp) if significant_resp.get("status") == "success" else {}
        significant = (
            significant_resp.get("significant_patterns")
            or body.get("significant_patterns")
            or {}
        )
        if not isinstance(significant, dict):
            significant = {}

        pattern_result = {
            "status": "success",
            "significant_patterns": significant,
            "observed_patterns": self._content(observed).get("patterns")
            or observed.get("patterns")
            or {},
        }

        # Soft Attention priority when Pattern found something worth noticing.
        has_signal = any(
            bool(significant.get(key))
            for key in (
                "strong_co_occurrences",
                "reliable_sequences",
                "behavioral_patterns",
                "contradictions",
                "meta_patterns",
            )
        )
        if has_signal:
            with self.lobe_handlers_lock:
                has_attention = "attention" in self.lobe_handlers
            if has_attention:
                seq_bits = []
                for seq in significant.get("reliable_sequences") or []:
                    if isinstance(seq, dict) and seq.get("steps"):
                        seq_bits.append("→".join(str(s) for s in seq.get("steps") or []))
                text = (
                    "pattern:" + (", ".join(seq_bits) if seq_bits else "significant discovery")
                )
                try:
                    self.send_and_wait(
                        "attention",
                        "update_salience",
                        {
                            "signals": [
                                {
                                    "id": "pattern:discovery",
                                    "text": text,
                                    "source": "pattern",
                                    "modality": "internal",
                                    "priority": 0.55,
                                    "user_id": user_id,
                                }
                            ]
                        },
                        source="thalamus",
                    )
                except Exception:
                    pass

        return pattern_result

    def process_user_input(
        self,
        user_input: str,
        user_id: str = "default",
        perception_payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Run the sole prompted path: perception → attention → conversation → Notus → emotion → Pattern → reasoning → language → (aside/curiosity) → output → Notus monday speech."""
        if not isinstance(user_input, str) or not user_input.strip():
            return "Please send a message."

        # Text perception first when registered: normalize + concepts before chat.
        # Callers that already ran Perception (audio/vision) may pass the envelope.
        if perception_payload is None:
            perception_payload = {}
            with self.lobe_handlers_lock:
                has_perception = "perception" in self.lobe_handlers
            if has_perception:
                perception = self.send_and_wait(
                    "perception",
                    "perceive_text",
                    {"text": user_input, "user_id": user_id},
                )
                if perception.get("status") != "success":
                    return "I'm having trouble perceiving that right now."
                perception_payload = self._content(perception)
                normalized = (
                    perception_payload.get("text")
                    or perception_payload.get("normalized_text")
                    or user_input
                )
                if isinstance(normalized, str) and normalized.strip():
                    user_input = normalized.strip()
        else:
            # Precomputed envelope from audio/vision — do not re-run text perceive.
            perception_payload = dict(perception_payload)

        # SensoryIntegration: fold this turn's envelope into the shared multi-modal
        # stream (and pull recent cross-modal context) without rebuilding Perception.
        with self.lobe_handlers_lock:
            has_si = "sensory_integration" in self.lobe_handlers
        if has_si and isinstance(perception_payload, dict) and perception_payload:
            # Skip re-absorb when the payload is already an SI unified stream.
            already_si = (perception_payload.get("raw_meta") or {}).get("source") == "sensory_integration"
            if not already_si:
                try:
                    si_abs = self.send_and_wait(
                        "sensory_integration",
                        "absorb",
                        {
                            "envelope": perception_payload,
                            "user_id": user_id,
                            "route_attention": False,
                        },
                        source="thalamus",
                    )
                    if si_abs.get("status") == "success":
                        merged = self._content(si_abs)
                        if isinstance(merged, dict) and merged:
                            perception_payload = merged
                            normalized = (
                                perception_payload.get("text")
                                or perception_payload.get("normalized_text")
                                or user_input
                            )
                            if isinstance(normalized, str) and normalized.strip():
                                # Keep user_input as the conversational text; stream
                                # may prefer an older audio transcript — only adopt
                                # when this turn had no usable text yet.
                                if not user_input.strip():
                                    user_input = normalized.strip()
                except Exception:
                    pass

        # Novelty: consolidate real novelty_score against familiar patterns.
        # Perception flags remain evidence; Novelty owns the live-path score.
        novelty_payload: Dict[str, Any] = {}
        with self.lobe_handlers_lock:
            has_novelty = "novelty" in self.lobe_handlers
        if has_novelty:
            try:
                novelty_payload = {}
                # Perception may have signaled Novelty this turn — consume that
                # one-shot assessment so we do not re-score against just-committed
                # tokens. True repeats (no fresh signal) re-assess and drop.
                fresh = self.send_and_wait(
                    "novelty", "take_fresh_assessment", {}, source="thalamus"
                )
                fresh_body = self._content(fresh) if fresh.get("status") == "success" else {}
                reuse = bool(fresh.get("fresh") or fresh_body.get("stimulus"))
                if reuse and str(fresh_body.get("stimulus") or "") == user_input[:240]:
                    novelty_payload = fresh_body
                    nov_resp = {"status": "success", "content": fresh_body}
                else:
                    nov_resp = self.send_and_wait(
                        "novelty",
                        "assess_experience",
                        {
                            "text": user_input,
                            "perception": perception_payload,
                            "source": "live_path",
                            "user_id": user_id,
                        },
                        source="thalamus",
                    )
                if nov_resp.get("status") == "success":
                    if not novelty_payload:
                        novelty_payload = self._content(nov_resp)
                    if not isinstance(novelty_payload, dict):
                        novelty_payload = {}
                    # Merge into perception envelope for attention / conversation.
                    perception_payload = dict(perception_payload or {})
                    score = novelty_payload.get("novelty_score")
                    try:
                        perception_payload["novelty_score"] = float(score if score is not None else 0.0)
                    except (TypeError, ValueError):
                        perception_payload["novelty_score"] = 0.0
                    perception_payload["novelty_is_novel"] = bool(
                        novelty_payload.get("is_novel")
                    )
                    # Union flags: perception local + novelty consolidated.
                    merged_flags = list(perception_payload.get("novelty_flags") or [])
                    for f in novelty_payload.get("novelty_flags") or []:
                        if f and f not in merged_flags:
                            merged_flags.append(f)
                    perception_payload["novelty_flags"] = merged_flags
                    perception_payload["novelty"] = {
                        "score": perception_payload["novelty_score"],
                        "is_novel": perception_payload["novelty_is_novel"],
                        "novel_tokens": list(novelty_payload.get("novel_tokens") or []),
                        "familiar_overlap": novelty_payload.get("familiar_overlap"),
                        "nearest_similarity": novelty_payload.get("nearest_similarity"),
                    }
            except Exception:
                novelty_payload = {}

        # Attention: score competing signals, decay stale focus, rank priority.
        attention_payload: Dict[str, Any] = self._attend_live_signals(
            user_input, perception_payload, user_id=user_id
        )
        # Promote high-salience perception concepts when attention ranked them.
        if attention_payload and perception_payload:
            ranked_ids = [
                str(r.get("id") or "")
                for r in (attention_payload.get("ranked") or [])
                if isinstance(r, dict)
            ]
            concepts = perception_payload.get("concepts")
            if isinstance(concepts, list) and concepts and ranked_ids:
                # Keep order stable but note priority list on the envelope.
                perception_payload = dict(perception_payload)
                perception_payload["attention_priority"] = ranked_ids[:8]
                perception_payload["attention_focus"] = attention_payload.get("focus")

        # Tell autonomous which user is present BEFORE aside mint/memory grounding.
        with self.lobe_handlers_lock:
            _has_auto_early = "autonomous" in self.lobe_handlers
        if _has_auto_early:
            try:
                self.send_message(
                    "autonomous",
                    "user_active",
                    {"user_id": user_id, "text": user_input},
                    source="thalamus",
                )
            except Exception:
                pass

        # Capture speak-worthy inner-life BEFORE this turn's emotion process_input
        # can wash intensity / unresolved context. Her own prior feelings stay eligible
        # to surface as a second beat appended before the Output envelope step.
        pre_turn_intensity = 0.5
        preloaded_aside = None
        try:
            with self.lobe_handlers_lock:
                has_emotion = "emotion" in self.lobe_handlers
                has_autonomous = "autonomous" in self.lobe_handlers
            if has_emotion:
                pre_state = self.send_and_wait("emotion", "get_state", {})
                if pre_state.get("status") == "success":
                    body = self._content(pre_state)
                    raw = pre_state.get("intensity", body.get("intensity", 0.5))
                    try:
                        pre_turn_intensity = float(raw if raw is not None else 0.5)
                    except (TypeError, ValueError):
                        pre_turn_intensity = 0.5
                    unresolved = (
                        pre_state.get("unresolved_appraisals")
                        or body.get("unresolved_appraisals")
                        or []
                    )
                    if has_autonomous and unresolved:
                        preloaded_aside = self._pop_speak_worthy_candidate()
                        if preloaded_aside is None:
                            # Mint only when cooldown would allow attach — avoids
                            # appraise spam while still letting sitting-with surface.
                            now = time.time()
                            cooled = (now - float(getattr(self, "_last_spoken_aside_time", 0.0) or 0.0)) >= float(
                                getattr(self, "_spoken_aside_cooldown_sec", 45.0)
                            )
                            if cooled:
                                preloaded_aside = self._mint_speak_worthy_from_inner_life()
            elif has_autonomous:
                preloaded_aside = self._pop_speak_worthy_candidate()
        except Exception:
            preloaded_aside = None

        conversation = self.send_and_wait(
            "conversation",
            "understand",
            {
                "user_input": user_input,
                "user_id": user_id,
                "perception": perception_payload,
                "attention": attention_payload,
                "context": {
                    "perception": perception_payload,
                    "attention": attention_payload,
                },
            },
        )
        if conversation["status"] != "success":
            return "I'm having trouble understanding right now."
        understanding = self._content(conversation).get("understanding", {})

        # Executive: set/hold current goal from intent; steer Attention toward it.
        self._executive_set_goal_from_turn(user_input, understanding)
        # Same-turn handoff: Executive may have re-selected focus — refresh
        # attention_payload + re-route so Reasoning.think sees post-Executive focus.
        attention_payload = self._refresh_attention_payload_post_executive(
            attention_payload
        )

        memory = self.send_and_wait(
            "notus", "store", {"role": "user", "content": user_input, "user_id": user_id}
        )
        if memory["status"] != "success":
            return "I'm having trouble remembering that right now."

        # Prefer query_context so durable facts ride with memories.
        memory_context = self.send_and_wait(
            "notus",
            "query_context",
            {"query": user_input, "user_id": user_id, "limit": 15},
        )
        if memory_context["status"] != "success":
            # Fallback to plain query if an older Notus build lacks query_context.
            memory_context = self.send_and_wait(
                "notus", "query", {"query": user_input, "user_id": user_id, "limit": 15}
            )
        if memory_context["status"] != "success":
            return "I'm having trouble retrieving context right now."

        emotion = self.send_and_wait(
            "emotion", "process_input", {"user_input": user_input}
        )
        if emotion["status"] != "success":
            return "I'm having trouble processing that right now."
        emotional_state = self._content(emotion)
        # Ensure unresolved appraisals are visible for curiosity gating.
        if not (emotional_state.get("unresolved_appraisals") or []):
            try:
                st = self.send_and_wait("emotion", "get_state", {})
                if st.get("status") == "success":
                    body = self._content(st)
                    unresolved = (
                        st.get("unresolved_appraisals")
                        or body.get("unresolved_appraisals")
                        or []
                    )
                    if unresolved:
                        emotional_state = dict(emotional_state)
                        emotional_state["unresolved_appraisals"] = unresolved
            except Exception:
                pass

        ctx = self._content(memory_context)
        memories = list(ctx.get("memories") or [])
        # Ensure facts are visible even if a backend forgot to merge them.
        for fact in ctx.get("facts") or []:
            if not isinstance(fact, dict):
                continue
            content = fact.get("content") or fact.get("text")
            if not content:
                pred = str(fact.get("predicate", "") or "")
                obj = str(fact.get("object", "") or "")
                sub = str(fact.get("subject", "") or "user")
                if pred and obj:
                    try:
                        from notus_memory import NotusMemorySystem

                        content = NotusMemorySystem.format_personal_fact(
                            sub, pred, obj
                        )
                    except Exception:
                        if pred.endswith("_name"):
                            noun = pred[:-5].replace("_", " ")
                            content = f"Your {noun}'s name is {obj}."
                        elif pred == "lives_in":
                            content = f"You live in {obj}."
                        elif pred.startswith("work_"):
                            prep = pred[5:] or "as"
                            content = f"You work {prep} {obj}."
                        else:
                            content = f"Your {pred.replace('_', ' ')} is {obj}."
            if not content:
                continue
            memories.append({**fact, "role": "fact", "content": content})
        # Drop experience-poison blobs before they reach reasoning / provider.
        memories = [
            m
            for m in memories
            if not (
                isinstance(m, dict)
                and isinstance(m.get("content"), str)
                and "How it felt:" in m["content"]
                and (
                    str(m.get("role", "")) == "system"
                    or "What it meant:" in m["content"]
                )
            )
        ]
        # Own-speech asks: ensure recent monday/assistant/abin lines are in
        # evidence even when query_context AND-gates bury them behind fillers
        # like "thing" / "exact words" / "earlier".
        # Prefer Conversation-owned intent; keep helper as fallback.
        _speech_ask = (
            (isinstance(understanding, dict) and understanding.get("intent") == "monday_speech_ask")
            or _asks_about_monday_own_speech(user_input)
        )
        if _speech_ask:
            try:
                recent = self.send_and_wait(
                    "notus",
                    "get_recent",
                    {"user_id": user_id, "limit": 25},
                )
            except Exception:
                recent = {"status": "error"}
            if recent.get("status") == "success":
                have = {
                    str(m.get("content") or "").strip().casefold()
                    for m in memories
                    if isinstance(m, dict)
                }
                for m in self._content(recent).get("memories") or []:
                    if not isinstance(m, dict):
                        continue
                    role = str(m.get("role") or "").strip().lower()
                    if role in {"assistant", "abin"}:
                        role = "monday"
                    if role not in _MONDAY_ROLES:
                        continue
                    content = str(m.get("content") or "").strip()
                    if not content:
                        continue
                    key = content.casefold()
                    if key in have or key == (user_input or "").strip().casefold():
                        continue
                    memories.append({**m, "role": "monday"})
                    have.add(key)
        ctx = dict(ctx)
        ctx["memories"] = memories

        # Pattern: continuous observe from Perception/Attention/Conversation/Emotion,
        # then distribute significant_patterns as the existing pattern_result interface.
        pattern_result = self._run_pattern_live(
            user_input,
            perception_payload=perception_payload,
            attention_payload=attention_payload,
            understanding=understanding,
            emotional_state=emotional_state,
            user_id=user_id,
        )

        reasoning = self.send_and_wait(
            "reasoning",
            "think",
            {
                "input": {
                    "user_input": user_input,
                    "user_id": user_id,
                    "understanding": understanding,
                    "memory_context": ctx,
                    "emotion_result": emotional_state,
                    "perception": perception_payload,
                    "attention": attention_payload,
                    "pattern_result": pattern_result,
                },
            },
        )
        if reasoning["status"] != "success":
            return "I'm having trouble thinking right now."
        semantic_input, reasoning_answer = self._reasoning_answer(reasoning)
        # Drop reasoning answers that don't overlap the prompt / asked attribute.
        # Empathic / teaching acks are allowed without token overlap.
        if isinstance(reasoning_answer, str) and reasoning_answer.strip():
            q_toks = content_tokens(user_input)
            attr = _attribute_asked(user_input)
            bad = False
            low_ans = reasoning_answer.lstrip().lower()
            empathic_ok = low_ans.startswith(
                ("that sounds", "i hear", "i can feel", "i'm here", "i am here", "got it")
            ) or "i am sitting with" in low_ans or "i'm sitting with" in low_ans
            if attr and not _fact_covers_attribute(reasoning_answer, attr):
                bad = True
            elif (
                not empathic_ok
                and q_toks
                and relevance_score(user_input, reasoning_answer) < 0.34
            ):
                if not (q_toks & content_tokens(reasoning_answer)):
                    bad = True
            if bad:
                grounded = answer_from_grounded_memories(user_input, memories)
                reasoning_answer = grounded
        early_structures = semantic_input.get("grounded_structures")
        has_structures = isinstance(early_structures, list) and bool(early_structures)
        if reasoning_answer is None and not has_structures:
            # Provider fallback — pass emotion so empathic path can fire.
            # Skip when Reasoning already supplied grounded structures for Language.
            try:
                understanding_with_emotion = dict(understanding) if isinstance(understanding, dict) else {}
                understanding_with_emotion["emotion_result"] = emotional_state
                reasoning_answer = self.response_provider.render(
                    user_input, understanding_with_emotion, memories
                )
            except Exception:
                reasoning_answer = None
            reasoning_answer = self._first_usable_text(reasoning_answer)
            if reasoning_answer is None:
                # Last chance: structured facts from memories before hard inability.
                try:
                    salvage_structs = structures_from_grounded_memories(user_input, memories)
                except Exception:
                    salvage_structs = None
                if salvage_structs:
                    semantic_input["grounded_structures"] = salvage_structs
                    has_structures = True
                else:
                    reasoning_answer = "I am unable to formulate a response right now."
        semantic_input.setdefault(
            "intent", understanding.get("intent", "conversation")
        )
        # Prefer structured grounded meaning over finished prose for Language.
        grounded_structures = semantic_input.get("grounded_structures")
        if not isinstance(grounded_structures, list) or not grounded_structures:
            grounded_structures = None
            # Reasoning may still have handed finished fact prose — strip it.
            prose_candidates = []
            for key in ("answer", "conclusion"):
                val = semantic_input.get(key)
                if isinstance(val, str) and val.strip():
                    prose_candidates.append(val)
            if isinstance(reasoning_answer, str) and reasoning_answer.strip():
                prose_candidates.append(reasoning_answer)
            for prose in prose_candidates:
                low = prose.strip().lower()
                if low.startswith(
                    ("got it", "hello", "hi ", "hey", "i do not have enough grounded",
                     "i am unable", "i'm unable", "that sounds", "i hear", "i'm here",
                     "i am here", "i am sitting", "i'm sitting")
                ):
                    continue
                stripped = prose_answer_to_structures(prose)
                if stripped:
                    grounded_structures = stripped
                    break
            if grounded_structures is None:
                # Live salvage: memories may hold triples even when reasoning prose failed.
                try:
                    grounded_structures = structures_from_grounded_memories(
                        user_input, memories
                    )
                except Exception:
                    grounded_structures = None
        if grounded_structures:
            semantic_input["grounded_structures"] = grounded_structures
            semantic_input["propositions"] = grounded_structures
            # Clear finished prose so Language must compose from structures.
            semantic_input["answer"] = ""
            semantic_input.pop("conclusion", None)
            reasoning_answer = None
        else:
            if reasoning_answer is not None:
                semantic_input.setdefault("answer", reasoning_answer)
                semantic_input.setdefault("propositions", [reasoning_answer])
        # Tiny glue: Language owns composition from user text + emotion tone cues.
        semantic_input["user_input"] = user_input
        if emotional_state.get("emotional_tone") is not None:
            semantic_input.setdefault(
                "emotional_tone", emotional_state.get("emotional_tone")
            )
        if emotional_state.get("intensity") is not None:
            semantic_input.setdefault(
                "emotional_intensity", emotional_state.get("intensity")
            )
        if emotional_state.get("current_emotion") or emotional_state.get("emotion"):
            semantic_input.setdefault(
                "emotion",
                emotional_state.get(
                    "current_emotion", emotional_state.get("emotion", "neutral")
                ),
            )

        self.last_grounded_structures = (
            list(grounded_structures) if grounded_structures else None
        )
        # Meta-cognition: watch reasoning envelope; steer Language via signals.
        semantic_input = self._meta_cognition_watch_reasoning(
            user_input, semantic_input, reasoning_answer, memories
        )
        # Meta control: contradiction → Language cleared, diagnostics kept;
        # force_refusal → structures cleared entirely.
        if isinstance(semantic_input.get("meta_cognition"), dict):
            meta = semantic_input["meta_cognition"]
            sigs = meta.get("signals") or {}
            if meta.get("contradiction_blocked"):
                # Do not compose either conflicting value; preserve for diagnosis.
                conflicting = meta.get("conflicting_structures")
                if isinstance(conflicting, list) and conflicting:
                    self.last_grounded_structures = [
                        dict(item) if isinstance(item, dict) else item
                        for item in conflicting
                    ]
                if isinstance(self.last_meta_cognition, dict):
                    merged = dict(self.last_meta_cognition)
                    if isinstance(conflicting, list):
                        merged["conflicting_structures"] = list(conflicting)
                    merged["contradiction_blocked"] = True
                    self.last_meta_cognition = merged
                reasoning_answer = semantic_input.get("answer")
            elif sigs.get("force_grounded_refusal"):
                grounded_structures = None
                self.last_grounded_structures = None
                reasoning_answer = semantic_input.get("answer")
        language = self.send_and_wait("language", "generate", {"semantic_input": semantic_input})
        if language["status"] != "success":
            return "I'm having trouble finding the words right now."
        response_text = self._content(language).get("sentence", "")
        if isinstance(response_text, str):
            response_text = self._meta_cognition_watch_language(
                response_text, semantic_input
            )
        self.last_language_sentence = (
            response_text if isinstance(response_text, str) else None
        )

        # Let autonomous inner-life know the user is present (own-feelings pacing).
        with self.lobe_handlers_lock:
            has_autonomous = "autonomous" in self.lobe_handlers
        if has_autonomous:
            try:
                self.send_message(
                    "autonomous",
                    "user_active",
                    {"user_id": user_id, "text": user_input},
                    source="thalamus",
                )
            except Exception:
                pass

        # Build the complete final reply text BEFORE Output so asides and
        # curiosity follow-ups cannot bypass the Output envelope boundary.
        # Prefer pre-turn intensity so a mild follow-up does not erase prior feelings.
        try:
            post_intensity = float(emotional_state.get("intensity", 0.5) or 0.5)
        except (TypeError, ValueError):
            post_intensity = 0.5
        turn_intensity = max(post_intensity, float(pre_turn_intensity or 0.5))
        final_text = response_text if isinstance(response_text, str) else ""
        final_text = self._maybe_attach_speak_worthy_aside(
            final_text,
            turn_intensity=turn_intensity,
            preloaded_aside=preloaded_aside,
            user_input=user_input,
        )
        final_text = self._maybe_attach_curiosity_follow_up(
            final_text,
            user_input=user_input,
            emotional_state=emotional_state,
            understanding=understanding,
        )
        # Proof / diagnostics: text that will enter Output (asides+curiosity included).
        self._last_pre_output_final_text = final_text

        # Output shapes the complete final reply with current ExpressionState/prosody.
        output = self.send_and_wait(
            "output",
            "generate_output",
            {
                "text": final_text,
                "emotion": emotional_state.get(
                    "current_emotion", emotional_state.get("emotion", "neutral")
                ),
                "intensity": emotional_state.get("intensity", 0.5),
                "voice_prosody": emotional_state.get("voice_prosody") or {},
                "emotional_tone": emotional_state.get("emotional_tone"),
                "emphasis": emotional_state.get("emphasis") or [],
                "expression": emotional_state.get("expression") or {},
                "pleasure": emotional_state.get("pleasure"),
                "arousal": emotional_state.get("arousal"),
                "dominance": emotional_state.get("dominance"),
                "user_input": user_input,
                "user_id": user_id,
                "preserve_text": True,
                "meta_cognition": self.last_meta_cognition,
                "uncertainty_flagged": bool(
                    isinstance(self.last_meta_cognition, dict)
                    and (self.last_meta_cognition.get("signals") or {}).get(
                        "flag_uncertainty"
                    )
                ),
            },
        )
        output_body = self._content(output)
        # Live path uses the Output envelope: text + expression delivery metadata.
        envelope = output_body.get("envelope") or output.get("envelope")
        if not isinstance(envelope, dict):
            envelope = {
                "text": output_body.get("text", final_text),
                "expression": output_body.get("expression")
                or emotional_state.get("expression")
                or {},
                "delivery": output_body.get("delivery") or {},
                "emotional_tone": output_body.get("emotional_tone")
                or emotional_state.get("emotional_tone"),
                "voice_prosody": output_body.get("voice_prosody")
                or emotional_state.get("voice_prosody")
                or {},
                "emotion": emotional_state.get(
                    "current_emotion", emotional_state.get("emotion", "neutral")
                ),
                "intensity": emotional_state.get("intensity", 0.5),
            }
        self.last_output_envelope = envelope
        reply = envelope.get("text") or output_body.get("text", final_text)

        # Persist exact envelope text — continuous someone, not user-only amnesia.
        if isinstance(reply, str) and reply.strip():
            try:
                self.send_and_wait(
                    "notus",
                    "store",
                    {
                        "role": "monday",
                        "content": reply.strip(),
                        "user_id": user_id,
                        "memory_type": "conversation",
                        "tag": "Spoken",
                        "importance": 6.5,
                        "mode": "memory",
                    },
                )
            except Exception:
                pass
        return reply

    def _requeue_speak_worthy(self, autonomous, aside: Dict[str, Any], now: float = 0.0) -> None:
        """Put a speak-worthy aside back on the autonomous queue if possible."""
        if autonomous is None or not isinstance(aside, dict):
            return
        try:
            lock = getattr(autonomous, "lock", None)
            queue = getattr(autonomous, "thought_queue", None)
            if queue is None:
                return
            # Rebuild a lightweight thought-like object if the queue expects dataclasses.
            ThoughtCls = None
            try:
                from autonomous_thinking import AutonomousThought
                ThoughtCls = AutonomousThought
            except Exception:
                ThoughtCls = None
            item = aside
            if ThoughtCls is not None:
                try:
                    item = ThoughtCls(
                        id=str(aside.get("id") or f"aside_{int(now*1000)}"),
                        content=str(aside.get("content") or ""),
                        thought_type=str(aside.get("thought_type") or "feeling"),
                        trigger=str(aside.get("trigger") or ""),
                        intensity=float(aside.get("intensity", 0.5) or 0.5),
                        speak_worthy=True,
                        timestamp=float(aside.get("timestamp") or now or time.time()),
                        mode=str(aside.get("mode") or ""),
                        topic_key=str(aside.get("topic_key") or ""),
                        source_memory_id=aside.get("source_memory_id"),
                        source_appraisal=aside.get("source_appraisal"),
                        satiation_score=float(aside.get("satiation_score", 0.0) or 0.0),
                        speak_satiation_score=float(aside.get("speak_satiation_score", 0.0) or 0.0),
                        relevance_gate_reason=str(aside.get("relevance_gate_reason") or ""),
                    )
                except Exception:
                    item = aside
            if lock is not None:
                with lock:
                    queue.insert(0, item)
            else:
                queue.insert(0, item)
        except Exception:
            pass

    def _pop_speak_worthy_candidate(self) -> Optional[Dict[str, Any]]:

        """Pop one pending speak-worthy thought without attaching it yet."""
        with self.lobe_handlers_lock:
            autonomous = self.lobe_handlers.get("autonomous")
        if autonomous is None:
            return None
        pop = getattr(autonomous, "pop_spoken_aside", None) or getattr(
            autonomous, "get_speak_worthy_thought", None
        )
        if callable(pop):
            try:
                aside = pop()
                return aside if isinstance(aside, dict) else None
            except Exception:
                return None
        return None

    def _mint_speak_worthy_from_inner_life(self) -> Optional[Dict[str, Any]]:
        """If unresolved feelings exist and queue is empty, generate one speak-worthy thought."""
        with self.lobe_handlers_lock:
            autonomous = self.lobe_handlers.get("autonomous")
        if autonomous is None:
            return None
        generate = getattr(autonomous, "_generate_thought", None)
        accept = getattr(autonomous, "_accept_thought", None)
        if not callable(generate):
            return None
        try:
            thought = generate()
            if thought is None:
                return None
            # Do not force speak_worthy — relevance gate at attach time decides.
            # Only bump intensity slightly if unresolved mint and already speak-eligible.
            try:
                if getattr(thought, "speak_worthy", False):
                    if float(getattr(thought, "intensity", 0.0) or 0.0) < 0.55:
                        thought.intensity = 0.6
            except Exception:
                pass
            if callable(accept):
                accept(thought)
            else:
                lock = getattr(autonomous, "lock", None)
                queue = getattr(autonomous, "thought_queue", None)
                if queue is not None:
                    if lock is not None:
                        with lock:
                            queue.append(thought)
                    else:
                        queue.append(thought)
            return self._pop_speak_worthy_candidate()
        except Exception:
            return None

    def _maybe_attach_speak_worthy_aside(
        self, reply: str, turn_intensity: float = 0.5,
        preloaded_aside: Optional[Dict[str, Any]] = None,
        user_input: str = "",
    ) -> str:
        """Optionally append one speak-worthy autonomous thought as a second beat.

        Speak-worthy aside rule (keep rare — she must not dump every thought):
        After a successful main reply, at most one pending speak-worthy thought may
        append ("\n\n" + content) when (1) autonomous is registered, (2) the thought
        intensity is >= 0.55 OR this turn's emotion intensity is >= 0.65, and
        (3) we have not attached an aside within `_spoken_aside_cooldown_sec`
        (~45s). Prefer autonomous.pop_spoken_aside / message type pop_spoken_aside.
        Most thoughts stay internal.
        """
        with self.lobe_handlers_lock:
            autonomous = self.lobe_handlers.get("autonomous")
        if autonomous is None and preloaded_aside is None:
            return reply
        # Executive inhibition: block speak-worthy aside when off-goal (e.g. fact_answer).
        if self._executive_should_inhibit("speak_worthy_aside"):
            if isinstance(preloaded_aside, dict) and autonomous is not None:
                self._requeue_speak_worthy(autonomous, preloaded_aside, time.time())
            return reply
        now = time.time()
        if (now - float(getattr(self, "_last_spoken_aside_time", 0.0) or 0.0)) < float(
            getattr(self, "_spoken_aside_cooldown_sec", 45.0)
        ):
            # Preserve preloaded aside for a later turn when possible.
            if isinstance(preloaded_aside, dict) and autonomous is not None:
                self._requeue_speak_worthy(autonomous, preloaded_aside, now)
            return reply

        aside = preloaded_aside if isinstance(preloaded_aside, dict) else None
        if aside is None and autonomous is not None:
            pop = getattr(autonomous, "pop_spoken_aside", None) or getattr(
                autonomous, "get_speak_worthy_thought", None
            )
            if callable(pop):
                try:
                    aside = pop()
                except Exception:
                    aside = None
            if aside is None:
                try:
                    result = self.send_message(
                        "autonomous", "pop_spoken_aside", {}, source="thalamus"
                    )
                    if result.get("status") == "success":
                        content = self._content(result)
                        aside = (
                            result.get("aside")
                            or result.get("thought")
                            or content.get("aside")
                            or content.get("thought")
                        )
                except Exception:
                    aside = None
        if not isinstance(aside, dict):
            return reply
        content = aside.get("content")
        if not isinstance(content, str) or not content.strip():
            return reply
        try:
            thought_intensity = float(aside.get("intensity", 0.5) or 0.5)
        except (TypeError, ValueError):
            thought_intensity = 0.5
        trigger = str(aside.get("trigger", "") or "")
        unresolvedish = trigger.startswith("unresolved_") or trigger.startswith("memory_unresolved_")
        # Intensity gate: thought strong enough, turn hot, or unresolved/memory sitting-with.
        min_thought = 0.50 if unresolvedish else 0.55
        min_turn = 0.55 if unresolvedish else 0.65
        if thought_intensity < min_thought and turn_intensity < min_turn:
            # Put it back if possible so a hotter turn can use it later.
            if autonomous is not None:
                self._requeue_speak_worthy(autonomous, aside, now)
            return reply

        # Hard relevance gate: light/unrelated turns must not drag stale rumination.
        gate_fn = getattr(autonomous, "aside_passes_relevance_gate", None) if autonomous else None
        if callable(gate_fn):
            try:
                allowed, gate_reason = gate_fn(aside, user_text=user_input or "")
            except Exception:
                allowed, gate_reason = True, "gate_error_allow"
            if not allowed:
                demote = getattr(autonomous, "demote_aside_to_internal", None)
                if callable(demote):
                    try:
                        demote(aside)
                    except Exception:
                        pass
                # Do not requeue as speak-worthy — keep internal.
                try:
                    aside["speak_worthy"] = False
                    aside["relevance_gate_reason"] = gate_reason
                except Exception:
                    pass
                return reply
            try:
                aside["relevance_gate_reason"] = gate_reason
            except Exception:
                pass

        # Speak-satiation bookkeeping when we actually surface.
        bump = getattr(autonomous, "_bump_speak_satiation", None) if autonomous else None
        if callable(bump):
            try:
                bump(str(aside.get("topic_key") or ""))
            except Exception:
                pass

        self._last_spoken_aside_time = now
        return f"{reply.rstrip()}\n\n{content.strip()}"


    def _maybe_attach_curiosity_follow_up(
        self,
        reply: str,
        user_input: str = "",
        emotional_state: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Append at most one honest curiosity question when affect warrants it.

        Owned by emotion/conversation/direct_response. Novelty lobe supplies
        novelty_score (via understanding/perception) as an eligibility signal;
        it does not generate the question text here.
        Mild hello/social turns never force a question.
        """
        if not isinstance(reply, str) or not reply.strip():
            return reply
        emotional_state = emotional_state if isinstance(emotional_state, dict) else {}
        understanding = understanding if isinstance(understanding, dict) else {}
        # Executive inhibition: block curiosity spam when goal is fact-answer.
        # Even _force_curiosity_follow_up cannot bypass a held fact_answer goal.
        if self._executive_should_inhibit("curiosity_follow_up"):
            if bool(getattr(self, "_force_curiosity_follow_up", False)):
                self._force_curiosity_follow_up = False
            return reply
        force = bool(getattr(self, "_force_curiosity_follow_up", False))
        # Teaching ack already grounded — do not invent a follow-up about the fact itself.
        if not force and reply.lstrip().lower().startswith("got it"):
            return reply

        now = time.time()
        if not force and (now - float(getattr(self, "_last_curiosity_time", 0.0) or 0.0)) < float(
            getattr(self, "_curiosity_cooldown_sec", 25.0)
        ):
            return reply

        question = None
        with self.lobe_handlers_lock:
            conversation = self.lobe_handlers.get("conversation")
        maybe = getattr(conversation, "maybe_curiosity_follow_up", None) if conversation else None
        if callable(maybe):
            try:
                question = maybe(
                    user_input,
                    emotional_state,
                    understanding,
                    force=force,
                )
            except Exception:
                question = None
        if not question:
            # Fallback without conversation lobe (stubbed smokes still prove path).
            intent = understanding.get("intent")
            try:
                intensity = float(emotional_state.get("intensity", 0.0) or 0.0)
            except (TypeError, ValueError):
                intensity = 0.0
            unresolved = emotional_state.get("unresolved_appraisals") or []
            if force or (
                not is_mild_social_turn(user_input, intent)
                and (unresolved or intensity >= 0.70)
            ):
                if force or unresolved:
                    try:
                        question = honest_curiosity_question(user_input, emotional_state)
                    except Exception:
                        question = None

        if not isinstance(question, str) or not question.strip():
            return reply
        q = question.strip()
        if q in reply:
            return reply
        # Avoid stacking a second question if the main reply already ends with one
        # unless we were forced (smoke / unresolved proof).
        if not force and reply.rstrip().endswith("?") and not (
            emotional_state.get("unresolved_appraisals") or []
        ):
            return reply

        self._last_curiosity_time = now
        if force:
            self._force_curiosity_follow_up = False
        return f"{reply.rstrip()}" + "\n\n" + q


    def handle_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Small compatibility entry point for direct callers."""
        msg_type = message.get("type")
        payload = message.get("content", message)
        if msg_type == "process_input":
            response = self.process_user_input(payload.get("user_input", ""))
            return {"status": "success", "content": {"response": response}, "response": response}
        if msg_type == "teach_monday":
            return self.teach_monday(payload if isinstance(payload, dict) else {})
        if msg_type == "learning_overview":
            return self.learning_overview(payload if isinstance(payload, dict) else {})
        if msg_type == "health":
            return {
                "status": "success",
                "content": {"thalamus_healthy": True, "lobes": self.lobe_status.copy()},
            }
        if msg_type == "pop_spoken_aside":
            with self.lobe_handlers_lock:
                autonomous = self.lobe_handlers.get("autonomous")
            if autonomous is None:
                return {"status": "error", "message": "autonomous not registered", "content": {}}
            pop = getattr(autonomous, "pop_spoken_aside", None)
            aside = pop() if callable(pop) else None
            return {
                "status": "success",
                "aside": aside,
                "thought": aside,
                "content": {"aside": aside, "thought": aside},
            }
        return {"status": "error", "message": f"Unknown type: {msg_type}", "content": {}}

    def start(self) -> "Thalamus":
        """Direct routing has no listener or background loop to start."""
        self.running = True
        return self

    def shutdown(self) -> None:
        self.running = False


_thalamus_instance: Optional[Thalamus] = None
_thalamus_lock = threading.Lock()


def get_thalamus() -> Thalamus:
    global _thalamus_instance
    with _thalamus_lock:
        if _thalamus_instance is None:
            _thalamus_instance = Thalamus()
        return _thalamus_instance
