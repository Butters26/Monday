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
from pathlib import Path
import re
import threading
import uuid
from typing import Any, Dict, Iterable, Optional

from direct_response import DeterministicResponseProvider, ResponseProvider
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

    def __init__(
        self,
        response_provider: Optional[ResponseProvider] = None,
        runtime_directory: Optional[str | Path] = None,
    ) -> None:
        self.running = True
        self.lobe_handlers: Dict[str, Any] = {}
        self.lobe_handlers_lock = threading.RLock()
        self.lobe_status: Dict[str, str] = {}
        self.message_routes: deque = deque(maxlen=100)
        self.response_provider = response_provider or DeterministicResponseProvider()
        self.learning_runtime_directory = (
            Path(runtime_directory)
            if isinstance(runtime_directory, (str, Path))
            else None
        )
        self._fallback_memory: Dict[str, deque] = {}
        self._fallback_memory_lock = threading.RLock()

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
            setattr(
                lobe,
                "_lobe_learning_store",
                LobeLearningStore(name, runtime_directory=self.learning_runtime_directory),
            )
        return {"status": "success", "content": {"registered": name}, "registered": name}

    @staticmethod
    def _normalised_user_id(content: Dict[str, Any]) -> str:
        candidates = []
        if isinstance(content, dict):
            candidates.append(content.get("user_id"))
            nested_input = content.get("input")
            if isinstance(nested_input, dict):
                candidates.append(nested_input.get("user_id"))
            semantic_input = content.get("semantic_input")
            if isinstance(semantic_input, dict):
                candidates.append(semantic_input.get("user_id"))
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return "default"

    @staticmethod
    def _query_candidates(msg_type: str, content: Dict[str, Any]) -> list[str]:
        candidates: list[str] = []

        def add(value: Any) -> None:
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned and cleaned not in candidates:
                    candidates.append(cleaned)

        add(content.get("query"))
        add(content.get("text"))
        add(content.get("user_input"))

        nested_input = content.get("input")
        if isinstance(nested_input, dict):
            add(nested_input.get("query"))
            add(nested_input.get("text"))
            add(nested_input.get("user_input"))

        semantic_input = content.get("semantic_input")
        if isinstance(semantic_input, dict):
            add(semantic_input.get("query"))
            add(semantic_input.get("text"))
            add(semantic_input.get("user_input"))
            add(semantic_input.get("answer"))

        if not candidates and isinstance(msg_type, str) and msg_type.strip():
            candidates.append(msg_type.strip())
        return candidates

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
        if destination == "notus" or msg_type in _LEARNING_ROUTE_TYPES or msg_type == "health":
            return []
        user_id = self._normalised_user_id(content)
        query_candidates = self._query_candidates(msg_type, content)

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

        memories: list[Dict[str, Any]] = []
        for query in query_candidates:
            memories = _recall(query)
            if memories:
                break
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
            store = LobeLearningStore(
                destination, runtime_directory=self.learning_runtime_directory
            )
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
        if destination == "notus" or msg_type in _LEARNING_ROUTE_TYPES or msg_type == "health":
            return
        user_id = self._normalised_user_id(content)
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

    def _record_fallback_memory(self, user_id: str, role: str, content: str) -> None:
        if not isinstance(content, str) or not content.strip():
            return
        safe_user = user_id.strip() if isinstance(user_id, str) and user_id.strip() else "default"
        with self._fallback_memory_lock:
            history = self._fallback_memory.setdefault(safe_user, deque(maxlen=100))
            history.append(
                {
                    "role": role,
                    "content": content.strip(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

    def _fallback_memory_context(self, user_id: str, query: str, limit: int = 15) -> Dict[str, Any]:
        safe_user = user_id.strip() if isinstance(user_id, str) and user_id.strip() else "default"
        terms = [term.lower() for term in query.split() if len(term) > 2] if isinstance(query, str) else []
        with self._fallback_memory_lock:
            records = list(self._fallback_memory.get(safe_user, []))
        if terms:
            matched = [
                record
                for record in records
                if isinstance(record.get("content"), str)
                and all(term in record["content"].lower() for term in terms)
            ]
        else:
            matched = records
        selected = matched[-max(1, limit):]
        return {"memories": selected, "count": len(selected), "source": "fallback"}

    def _probe_lobes_health(self) -> Dict[str, Any]:
        with self.lobe_handlers_lock:
            destinations = list(self.lobe_handlers.keys())
        health_report: Dict[str, Any] = {}
        for destination in destinations:
            probe = self.send_and_wait(
                destination,
                "health",
                {"probe": "thalamus_health"},
                source="thalamus_health",
            )
            content = self._content(probe)
            healthy_value = content.get("healthy", probe.get("healthy", False))
            healthy = bool(healthy_value) if probe.get("status") == "success" else False
            status = "online" if healthy else "error"
            self.lobe_status[destination] = status
            health_report[destination] = {
                "status": probe.get("status"),
                "healthy": healthy,
                **({"message": probe.get("message")} if probe.get("message") else {}),
            }
        return health_report

    def process_user_input(self, user_input: str, user_id: str = "default") -> str:
        """Run the sole prompted path: conversation → Notus → emotion → reasoning → language → output."""
        if not isinstance(user_input, str) or not user_input.strip():
            return "Please send a message."
        safe_user_id = user_id if isinstance(user_id, str) and user_id.strip() else "default"
        self._record_fallback_memory(safe_user_id, "user", user_input)

        conversation = self.send_and_wait(
            "conversation", "understand", {"user_input": user_input, "user_id": safe_user_id}
        )
        if conversation["status"] != "success":
            return "I'm having trouble understanding right now."
        understanding = self._content(conversation).get("understanding", {})

        memory = {"status": "error"}
        for _ in range(2):
            memory = self.send_and_wait(
                "notus",
                "store",
                {"role": "user", "content": user_input, "user_id": safe_user_id},
            )
            if memory.get("status") == "success":
                break

        memory_context = {"status": "error", "content": {}}
        for _ in range(2):
            memory_context = self.send_and_wait(
                "notus",
                "query",
                {"query": user_input, "user_id": safe_user_id, "limit": 15},
            )
            if memory_context.get("status") == "success":
                break
        if memory_context.get("status") != "success":
            memory_context = {
                "status": "success",
                "content": self._fallback_memory_context(safe_user_id, user_input, limit=15),
            }

        emotion = self.send_and_wait(
            "emotion", "process_input", {"user_input": user_input, "user_id": safe_user_id}
        )
        if emotion["status"] != "success":
            return "I'm having trouble processing that right now."
        emotional_state = self._content(emotion)

        reasoning = self.send_and_wait(
            "reasoning",
            "think",
            {
                "user_id": safe_user_id,
                "user_input": user_input,
                "input": {
                    "user_input": user_input,
                    "user_id": safe_user_id,
                    "understanding": understanding,
                    "memory_context": self._content(memory_context),
                    "emotion_result": emotional_state,
                },
            },
        )
        if reasoning["status"] != "success":
            return "I'm having trouble thinking right now."
        semantic_input, reasoning_answer = self._reasoning_answer(reasoning)
        memories = self._content(memory_context).get("memories", [])
        if reasoning_answer is None:
            try:
                reasoning_answer = self.response_provider.render(
                    user_input, understanding, memories
                )
            except Exception:
                reasoning_answer = None
            reasoning_answer = self._first_usable_text(reasoning_answer)
            if reasoning_answer is None:
                reasoning_answer = "I am unable to formulate a response right now."
        semantic_input.setdefault(
            "intent", understanding.get("intent", "conversation")
        )
        semantic_input.setdefault("answer", reasoning_answer)
        semantic_input.setdefault("propositions", [reasoning_answer])

        language = self.send_and_wait(
            "language",
            "generate",
            {"semantic_input": semantic_input, "user_id": safe_user_id, "user_input": user_input},
        )
        if language["status"] != "success":
            return "I'm having trouble finding the words right now."
        response_text = self._content(language).get("sentence", "")

        output = self.send_and_wait(
            "output",
            "generate_output",
            {
                "text": response_text,
                "emotion": emotional_state.get("current_emotion", "neutral"),
                "intensity": emotional_state.get("intensity", 0.5),
                "user_input": user_input,
                "user_id": safe_user_id,
                "preserve_text": True,
            },
        )
        final_text = self._content(output).get("text", response_text)
        self._record_fallback_memory(safe_user_id, "assistant", final_text)
        return final_text

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
            lobe_health = self._probe_lobes_health()
            return {
                "status": "success",
                "content": {
                    "thalamus_healthy": self.running
                    and bool(lobe_health)
                    and all(entry.get("healthy") for entry in lobe_health.values()),
                    "running": self.running,
                    "lobes": lobe_health,
                },
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
