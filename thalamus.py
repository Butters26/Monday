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
import json
from pathlib import Path
import re
import threading
import uuid
from typing import Any, Dict, Iterable, Optional, Set

from direct_response import DeterministicResponseProvider, ResponseProvider
from learning.experience_envelope import ExperienceEnvelope
from learning.learning_contract import (
    contract_rejection,
    normalize_learning_result,
    resolve_lobe_contract,
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
_NO_GUIDANCE_OR_ADAPT_TYPES = {"health", "learn_from_experience", "sync_notus_pending", "notus_sync_status"}
_GENERIC_EXPERIENCE_PROFILES = {
    "conversation": {"policy": "reply_guidance", "confidence_scale": 0.95, "confidence_cap": 0.9},
    "reasoning": {"policy": "inference_preferences", "confidence_scale": 0.9, "confidence_cap": 0.88},
    "emotion": {"policy": "emotion_response_guidance", "confidence_scale": 0.75, "confidence_cap": 0.8},
    "output": {"policy": "delivery_tone", "confidence_scale": 0.8, "confidence_cap": 0.82},
    "pattern": {"policy": "pattern_rules", "confidence_scale": 0.9, "confidence_cap": 0.88},
    "language": {"policy": "generation_guidance", "confidence_scale": 0.9, "confidence_cap": 0.88},
    "attention": {"policy": "behavior_rules", "confidence_scale": 0.7, "confidence_cap": 0.78},
    "meta_cognition": {"policy": "behavior_rules", "confidence_scale": 0.88, "confidence_cap": 0.86},
    "executive_control": {"policy": "behavior_rules", "confidence_scale": 0.83, "confidence_cap": 0.84},
    "social_context": {"policy": "behavior_rules", "confidence_scale": 0.8, "confidence_cap": 0.83},
    "sensory_integration": {"policy": "behavior_rules", "confidence_scale": 0.72, "confidence_cap": 0.8},
    "motor_action": {"policy": "behavior_rules", "confidence_scale": 0.72, "confidence_cap": 0.8},
    "novelty": {"policy": "behavior_rules", "confidence_scale": 0.78, "confidence_cap": 0.83},
    "perception": {"policy": "behavior_rules", "confidence_scale": 0.8, "confidence_cap": 0.84},
}
_LESSON_CAPABILITY_MAP = {
    "skill": {"rules", "procedures"},
    "correction": {"rules", "exceptions"},
    "feedback": {"feedback", "rules"},
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
        self._pending_notus_writes: Dict[str, deque] = {}
        self._synced_notus_write_ids: Dict[str, Set[str]] = {}
        self._notus_sync_lock = threading.RLock()
        self._lobe_contracts: Dict[str, Dict[str, Any]] = {}

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
            self._lobe_contracts[name] = resolve_lobe_contract(name, lobe)
        if name != "notus" and not hasattr(lobe, "_lobe_learning_store"):
            setattr(
                lobe,
                "_lobe_learning_store",
                LobeLearningStore(name, runtime_directory=self.learning_runtime_directory),
            )
        if name != "notus":
            setattr(lobe, "_learning_contract", dict(self._lobe_contracts[name]))
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
    def _normalise_notus_write(payload: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        normalised = dict(payload) if isinstance(payload, dict) else {}
        normalised["user_id"] = (
            user_id.strip() if isinstance(user_id, str) and user_id.strip() else "default"
        )
        existing_id = normalised.get("_thalamus_write_id")
        if not isinstance(existing_id, str) or not existing_id.strip():
            normalised["_thalamus_write_id"] = str(uuid.uuid4())
        return normalised

    def _mark_notus_write_synced(self, payload: Dict[str, Any]) -> None:
        user_id = payload.get("user_id", "default")
        write_id = payload.get("_thalamus_write_id")
        if not isinstance(write_id, str) or not write_id.strip():
            return
        safe_user = user_id.strip() if isinstance(user_id, str) and user_id.strip() else "default"
        with self._notus_sync_lock:
            bucket = self._synced_notus_write_ids.setdefault(safe_user, set())
            bucket.add(write_id)

    def _enqueue_notus_write(self, payload: Dict[str, Any]) -> None:
        write = self._normalise_notus_write(payload, payload.get("user_id", "default"))
        safe_user = write["user_id"]
        write_id = write["_thalamus_write_id"]
        with self._notus_sync_lock:
            synced = self._synced_notus_write_ids.setdefault(safe_user, set())
            if write_id in synced:
                return
            queue = self._pending_notus_writes.setdefault(safe_user, deque(maxlen=500))
            if any(item.get("_thalamus_write_id") == write_id for item in queue):
                return
            queue.append(write)

    def _sync_pending_notus_writes(self, user_id: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        safe_limit = max(1, min(int(limit), 500))
        attempted = 0
        synced = 0
        failed = 0
        with self._notus_sync_lock:
            users = [user_id] if isinstance(user_id, str) and user_id.strip() else list(self._pending_notus_writes.keys())
        for queued_user in users:
            safe_user = queued_user.strip() if isinstance(queued_user, str) and queued_user.strip() else "default"
            while attempted < safe_limit:
                with self._notus_sync_lock:
                    queue = self._pending_notus_writes.get(safe_user)
                    item = queue[0] if queue else None
                if item is None:
                    break
                attempted += 1
                result = self.send_and_wait("notus", "store", item, source="thalamus:notus_sync")
                if result.get("status") == "success":
                    with self._notus_sync_lock:
                        queue = self._pending_notus_writes.get(safe_user)
                        if queue and queue and queue[0].get("_thalamus_write_id") == item.get("_thalamus_write_id"):
                            queue.popleft()
                            if not queue:
                                self._pending_notus_writes.pop(safe_user, None)
                    self._mark_notus_write_synced(item)
                    synced += 1
                    continue
                failed += 1
                break
        pending = 0
        with self._notus_sync_lock:
            pending = sum(len(queue) for queue in self._pending_notus_writes.values())
        return {
            "attempted": attempted,
            "synced": synced,
            "failed": failed,
            "pending": pending,
        }

    def _learning_targets(self) -> list[str]:
        with self.lobe_handlers_lock:
            items = list(self.lobe_handlers.items())
        targets = []
        for name, _handler in items:
            if name == "notus":
                continue
            contract = self._lobe_contracts.get(name, {})
            if bool(contract.get("learning_enabled", True)):
                targets.append(name)
        return targets

    def _lobe_contract(self, name: str) -> Dict[str, Any]:
        contract = self._lobe_contracts.get(name, {})
        if isinstance(contract, dict):
            return contract
        return {}

    @staticmethod
    def _safe_confidence(value: Any, default: float = 0.7) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
        return max(0.0, min(1.0, number))

    def _generic_experience_learning(
        self, destination: str, payload: Dict[str, Any], source: str
    ) -> Dict[str, Any]:
        envelope = payload.get("envelope", payload) if isinstance(payload, dict) else {}
        envelope = envelope if isinstance(envelope, dict) else {}
        raw_experience = envelope.get("raw_experience", "")
        raw_experience = raw_experience.strip() if isinstance(raw_experience, str) else ""
        examples = envelope.get("examples", [])
        examples = examples if isinstance(examples, list) else []
        counterexamples = envelope.get("counterexamples", [])
        counterexamples = counterexamples if isinstance(counterexamples, list) else []
        user_id = envelope.get("user_id", "default")
        if not isinstance(user_id, str) or not user_id.strip():
            user_id = "default"

        signal = raw_experience
        if not signal:
            for sample in examples:
                if isinstance(sample, str) and sample.strip():
                    signal = sample.strip()
                    break
        if not signal:
            return {
                "status": "success",
                "content": {
                    "delivered": True,
                    "interpreted": False,
                    "update_proposed": False,
                    "update_accepted": False,
                    "behavior_affected": False,
                    "validation_passed": False,
                    "message": "No usable learning signal",
                    "changes": {},
                },
            }

        event_type = envelope.get("event_type", "experience")
        if not isinstance(event_type, str) or not event_type.strip():
            event_type = "experience"
        lesson_type = self._classify_lesson_type(f"{event_type} {signal}", envelope)
        contract = self._lobe_contract(destination)
        allowed_record_types = contract.get("allowed_record_types", {"fact", "rule"})
        allowed_record_types = (
            allowed_record_types if isinstance(allowed_record_types, set) else set(allowed_record_types)
        )
        desired_type = "rule" if lesson_type in {"skill", "feedback", "correction"} else "fact"
        if desired_type not in allowed_record_types:
            return {
                "status": "success",
                "content": {
                    "delivered": True,
                    "interpreted": False,
                    "proposed": False,
                    "saved": False,
                    "retrieved": False,
                    "applied": False,
                    "behavior_changed": False,
                    "validated": True,
                    "message": f"{destination} contract rejects {desired_type} record",
                    "changes": {"lesson_type": lesson_type},
                },
            }

        profile = _GENERIC_EXPERIENCE_PROFILES.get(
            destination,
            {"policy": "general_adaptation", "confidence_scale": 0.8, "confidence_cap": 0.82},
        )
        policy_surface = self._surface_for_destination(
            destination, preferred=str(profile.get("policy", ""))
        )
        base_confidence = self._safe_confidence(envelope.get("confidence"), 0.7)
        confidence = min(
            float(profile.get("confidence_cap", 0.82)),
            max(0.35, base_confidence * float(profile.get("confidence_scale", 0.8))),
        )
        fact = (
            f"[{destination}:{profile.get('policy', 'general_adaptation')}] "
            f"{self._behavior_from_lesson(signal[:280], lesson_type)}"
        )
        key = (
            f"experience:{lesson_type}:{event_type}:"
            f"{str(profile.get('policy', 'general_adaptation')).replace(' ', '_')}"
        )
        learned = self._handle_lobe_learning(
            destination,
            "learn",
            {
                "user_id": user_id,
                "key": key,
                "fact": fact,
                "confidence": confidence,
                "source": f"{source}:experience:{destination}",
                "record": {
                    "type": desired_type,
                    "subject": policy_surface,
                    "surface": policy_surface,
                    "relation": lesson_type,
                    "value": signal[:280],
                    "scope": destination,
                    "confidence": confidence,
                    "source": "explicit_user_teaching",
                    "examples": [item for item in examples if isinstance(item, str)][:5],
                    "exceptions": [item for item in counterexamples if isinstance(item, str)][:5],
                    "status": "provisional",
                },
            },
            source=f"{source}:experience",
        )
        if learned.get("status") != "success":
            return {
                "status": "error",
                "message": learned.get("message", "learning failed"),
                "content": {
                    "delivered": True,
                    "interpreted": True,
                    "proposed": True,
                    "saved": False,
                    "retrieved": False,
                    "applied": False,
                    "behavior_changed": False,
                    "validated": False,
                    "changes": {"key": key, "policy": profile.get("policy")},
                },
            }

        if counterexamples:
            self._handle_lobe_learning(
                destination,
                "contradict_learning",
                {
                    "user_id": user_id,
                    "key": key,
                    "penalty": 0.06,
                    "correction_fact": f"[{destination}:{profile.get('policy', 'general_adaptation')}] Refine behavior with counterexamples.",
                    "correction_evidence": [
                        f"before:[{destination}:{profile.get('policy', 'general_adaptation')}] {self._behavior_from_lesson(signal[:280], lesson_type)}",
                        f"after:[{destination}:{profile.get('policy', 'general_adaptation')}] Refine behavior with counterexamples.",
                        "validated:experience_counterexample",
                    ],
                },
                source=f"{source}:experience_counterexample",
            )
        recalled = self._handle_lobe_learning(
            destination,
            "recall",
            {"user_id": user_id, "query": signal, "limit": 1, "include_disputed": True},
            source=f"{source}:experience_validation",
        )
        retrieved = recalled.get("status") == "success" and bool(
            self._content(recalled).get("memories", [])
        )
        behavior_changed = bool(envelope.get("behavior_delta_observed", False))
        validated = bool(retrieved and behavior_changed)

        return {
            "status": "success",
            "content": {
                "delivered": True,
                "interpreted": True,
                "proposed": True,
                "saved": True,
                "retrieved": retrieved,
                "applied": retrieved,
                "behavior_changed": behavior_changed,
                "validated": validated,
                "confidence": confidence,
                "evidence": [signal, *[item for item in examples if isinstance(item, str)]][:4],
                "changes": {
                    "key": key,
                    "policy": profile.get("policy"),
                    "lesson_type": lesson_type,
                    "counterexamples_seen": len(counterexamples),
                },
            },
        }

    def _record_learning_event_in_notus(self, envelope: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._normalise_notus_write(
            {
                "role": "note",
                "user_id": envelope.get("user_id", "default"),
                "memory_type": "learning_event",
                "content": json.dumps(
                    {
                        "event_id": envelope.get("event_id"),
                        "correlation_id": envelope.get("correlation_id"),
                        "event_type": envelope.get("event_type"),
                        "raw_experience": envelope.get("raw_experience"),
                        "examples": envelope.get("examples", []),
                        "counterexamples": envelope.get("counterexamples", []),
                        "timestamp": envelope.get("timestamp"),
                    },
                    sort_keys=True,
                ),
                "_thalamus_write_id": f"learning_event:{envelope.get('event_id', str(uuid.uuid4()))}",
            },
            envelope.get("user_id", "default"),
        )
        result = self.send_and_wait("notus", "store", payload, source="thalamus:learning_event")
        if result.get("status") == "success":
            self._mark_notus_write_synced(payload)
            return {"status": "success", "queued": False}
        self._enqueue_notus_write(payload)
        return {"status": "error", "queued": True, "message": result.get("message")}

    def process_learning_event(self, payload: Dict[str, Any], source: str = "thalamus") -> Dict[str, Any]:
        envelope = ExperienceEnvelope.from_payload(payload, source=source)
        validation_error = envelope.validate()
        if validation_error:
            return {
                "status": "error",
                "message": validation_error,
                "content": {"delivered": 0, "interpreted": 0, "accepted": 0, "results": []},
            }
        envelope_dict = envelope.to_dict()
        memory_result = self._record_learning_event_in_notus(envelope_dict)
        learning_signal = str(envelope_dict.get("raw_experience", "")).strip()
        event_type = str(envelope_dict.get("event_type", "experience")).strip() or "experience"
        lesson_type = self._classify_lesson_type(f"{event_type} {learning_signal}", envelope_dict)
        derived_record = (
            envelope_dict.get("record")
            if isinstance(envelope_dict.get("record"), dict)
            else self._record_from_lesson(learning_signal or event_type, lesson_type, envelope_dict)
        )
        targets = self._learning_targets_for_record(lesson_type, derived_record)
        results = []
        if not targets:
            return {
                "status": "error",
                "content": {
                    "envelope": envelope_dict,
                    "targets": [],
                    "results": [],
                    "delivery_status": {
                        "delivered": 0,
                        "interpreted": 0,
                        "proposed": 0,
                        "saved": 0,
                        "retrieved": 0,
                        "applied": 0,
                        "behavior_changed": 0,
                        "validated": 0,
                        "update_proposed": 0,
                        "accepted": 0,
                        "behavior_affected": 0,
                        "validation_passed": 0,
                    },
                    "routing_condition": "no_capability_match",
                    "notus_event_record": memory_result,
                    "partial_failures": [],
                },
            }
        for destination in targets:
            response = self.send_and_wait(
                destination,
                "learn_from_experience",
                {"envelope": envelope_dict},
                source=f"{source}:learning",
            )
            results.append(normalize_learning_result(destination, envelope.event_id, response))
        delivered = sum(1 for item in results if item.get("delivered"))
        interpreted = sum(1 for item in results if item.get("interpreted"))
        accepted = sum(1 for item in results if item.get("saved"))
        retrieved = sum(1 for item in results if item.get("retrieved"))
        applied = sum(1 for item in results if item.get("applied"))
        behavior_affected = sum(1 for item in results if item.get("behavior_changed"))
        validation_passed = sum(1 for item in results if item.get("validated"))
        partial_failures = [
            {"lobe": item.get("lobe"), "message": item.get("message")}
            for item in results
            if not item.get("saved")
        ]
        status = "success" if accepted > 0 else "partial" if delivered > 0 else "error"
        return {
            "status": status,
            "content": {
                "envelope": envelope_dict,
                "targets": targets,
                "results": results,
                "delivery_status": {
                    "delivered": delivered,
                    "interpreted": interpreted,
                    "proposed": sum(1 for item in results if item.get("proposed")),
                    "saved": accepted,
                    "retrieved": retrieved,
                    "applied": applied,
                    "behavior_changed": behavior_affected,
                    "validated": validation_passed,
                    # Backward-compatible aliases
                    "update_proposed": sum(1 for item in results if item.get("proposed")),
                    "accepted": accepted,
                    "behavior_affected": behavior_affected,
                    "validation_passed": validation_passed,
                },
                "notus_event_record": memory_result,
                "partial_failures": partial_failures,
            },
        }

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
        if (
            destination == "notus"
            or msg_type in _LEARNING_ROUTE_TYPES
            or msg_type in _NO_GUIDANCE_OR_ADAPT_TYPES
        ):
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

    def _classify_lesson_type(self, lesson_text: str, payload: Optional[Dict[str, Any]] = None) -> str:
        data = payload if isinstance(payload, dict) else {}
        explicit = data.get("lesson_type")
        if isinstance(explicit, str):
            label = explicit.strip().lower()
            if label in {"skill", "feedback", "correction"}:
                return label

        record = data.get("record") if isinstance(data.get("record"), dict) else {}
        record_type = str(record.get("type", data.get("record_type", ""))).strip().lower()
        if record_type == "exception":
            return "correction"
        if record_type in {"procedure", "rule"}:
            return "skill"

        analysis_text = " ".join(
            item
            for item in (
                lesson_text,
                str(data.get("subject", "")),
                str(data.get("relation", "")),
                str(data.get("feedback", "")),
                str(record.get("subject", "")),
                str(record.get("relation", "")),
            )
            if isinstance(item, str) and item.strip()
        ).lower()
        tokens = {token for token in re.findall(r"[a-z0-9]{3,}", analysis_text)}
        if not analysis_text.strip():
            return "skill"
        semantic_input = data.get("semantic_input", {})
        semantic_input = semantic_input if isinstance(semantic_input, dict) else {}
        semantic_text = " ".join(
            str(semantic_input.get(key, ""))
            for key in ("answer", "conclusion", "query", "text")
            if isinstance(semantic_input.get(key), str) and semantic_input.get(key).strip()
        ).lower()
        combined_text = f"{analysis_text} {semantic_text}".strip()
        if not combined_text:
            return "skill"

        def _vector(text: str, dims: int = 256) -> list[float]:
            vector = [0.0] * dims
            padded = f"  {text}  "
            for index in range(len(padded) - 2):
                gram = padded[index:index + 3]
                bucket = hash(gram) % dims
                vector[bucket] += 1.0
            for token in re.findall(r"[a-z0-9]{2,}", text):
                bucket = hash(f"tok:{token}") % dims
                vector[bucket] += 2.0
            magnitude = sum(value * value for value in vector) ** 0.5
            if magnitude == 0.0:
                return [0.0] * dims
            return [value / magnitude for value in vector]

        def _cosine(left: list[float], right: list[float]) -> float:
            if not left or not right or len(left) != len(right):
                return 0.0
            return sum(x * y for x, y in zip(left, right))

        label_prototypes = {
            "feedback": (
                "improve tone style wording respectful calm polite constructive response behavior",
                {"feedback", "tone", "style", "delivery", "polite", "respectful", "calm", "kind"},
            ),
            "correction": (
                "fix contradiction replace incorrect disputed deprecated exception conflict correction",
                {"correct", "correction", "replace", "deprecated", "disputed", "conflict", "exception"},
            ),
            "skill": (
                "new procedure rule method pattern reasoning language generation inference capability",
                {"procedure", "rule", "pattern", "reasoning", "language", "generation", "inference"},
            ),
        }
        combined_vector = _vector(combined_text)
        scores: Dict[str, float] = {}
        for label, (prototype_text, cue_tokens) in label_prototypes.items():
            semantic_score = _cosine(combined_vector, _vector(prototype_text))
            cue_score = (
                float(len(tokens.intersection(cue_tokens))) / float(len(cue_tokens))
                if cue_tokens
                else 0.0
            )
            scores[label] = (0.75 * semantic_score) + (0.25 * cue_score)
        return max(scores.items(), key=lambda item: item[1])[0]

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

    def _record_from_lesson(self, lesson_text: str, lesson_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        record_type = payload.get("record_type")
        if not isinstance(record_type, str) or not record_type.strip():
            record_type = "rule" if lesson_type in {"skill", "feedback", "correction"} else "fact"
        scope = payload.get("scope", "general")
        if not isinstance(scope, str) or not scope.strip():
            scope = "general"
        return {
            "type": record_type.strip().lower(),
            "subject": payload.get("subject", lesson_type),
            "relation": payload.get("relation", "guidance"),
            "value": lesson_text,
            "scope": scope.strip().lower(),
            "confidence": self._safe_confidence(payload.get("confidence"), 0.75),
            "source": payload.get("source", "explicit_user_teaching"),
            "examples": payload.get("examples", []),
            "exceptions": payload.get("exceptions", []),
            "status": "provisional",
        }

    def _surface_for_destination(
        self, destination: str, preferred: Optional[str] = None
    ) -> str:
        preferred_value = (
            preferred.strip().lower()
            if isinstance(preferred, str) and preferred.strip()
            else ""
        )
        contract = self._lobe_contract(destination)
        mutable_surfaces = contract.get("mutable_surfaces", set())
        mutable_surfaces = (
            mutable_surfaces if isinstance(mutable_surfaces, set) else set(mutable_surfaces)
        )
        available = sorted(
            item.strip().lower()
            for item in mutable_surfaces
            if isinstance(item, str) and item.strip()
        )
        if preferred_value and preferred_value in available:
            return preferred_value
        if available:
            return available[0]
        return preferred_value or "behavior_rules"

    def _experience_contract_rejection(
        self, destination: str, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        envelope = payload.get("envelope", payload) if isinstance(payload, dict) else {}
        envelope = envelope if isinstance(envelope, dict) else {}
        signal = envelope.get("raw_experience", "")
        signal = signal.strip() if isinstance(signal, str) else ""
        event_type = envelope.get("event_type", "experience")
        if not isinstance(event_type, str) or not event_type.strip():
            event_type = "experience"
        lesson_type = self._classify_lesson_type(f"{event_type} {signal}", envelope)
        profile = _GENERIC_EXPERIENCE_PROFILES.get(destination, {"policy": "behavior_rules"})
        policy = str(profile.get("policy", "behavior_rules"))
        surface = self._surface_for_destination(destination, preferred=policy)
        record = {
            "type": "rule" if lesson_type in {"skill", "feedback", "correction"} else "fact",
            "subject": policy,
            "surface": surface,
            "status": envelope.get("status", "provisional"),
            "evidence": envelope.get("evidence", []),
        }
        return contract_rejection(
            self._lobe_contract(destination),
            "learn",
            {
                "record": record,
                "record_type": record["type"],
                "surface": surface,
                "status": record["status"],
                "evidence": record["evidence"],
            },
        )

    @staticmethod
    def _required_capabilities_for_record(record: Dict[str, Any], lesson_type: str) -> set[str]:
        capability = _LESSON_CAPABILITY_MAP.get(lesson_type, {"rules"})
        record_type = str(record.get("type", "fact")).strip().lower()
        if record_type == "fact":
            capability = {"facts"}
        elif record_type == "procedure":
            capability = {"procedures"}
        elif record_type == "exception":
            capability = {"exceptions", "rules"}
        elif record_type == "example":
            capability = {"facts", "rules"}
        elif record_type == "rule":
            capability = {"rules"}
        return set(capability)

    def _learning_targets_for_record(self, lesson_type: str, record: Dict[str, Any]) -> list[str]:
        with self.lobe_handlers_lock:
            registered = list(self.lobe_handlers.keys())
        candidates = [name for name in registered if name not in {"notus"}]
        if not candidates:
            return []
        required_capabilities = self._required_capabilities_for_record(record, lesson_type)
        record_type = str(record.get("type", "fact")).strip().lower()
        matched: list[str] = []
        for lobe in candidates:
            contract = self._lobe_contract(lobe)
            if not bool(contract.get("learning_enabled", True)):
                continue
            capabilities = contract.get("capabilities", set())
            capabilities = capabilities if isinstance(capabilities, set) else set(capabilities)
            if required_capabilities and not capabilities.intersection(required_capabilities):
                continue
            allowed_record_types = contract.get("allowed_record_types", {"fact", "rule"})
            allowed_record_types = (
                allowed_record_types
                if isinstance(allowed_record_types, set)
                else set(allowed_record_types)
            )
            if record_type not in allowed_record_types:
                continue
            matched.append(lobe)
        return matched

    def teach_monday(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        lesson = payload.get("lesson", payload.get("text", payload.get("content", "")))
        if not isinstance(lesson, str) or not lesson.strip():
            return {"status": "error", "message": "teach_monday requires lesson text"}
        lesson_text = lesson.strip()
        user_id = payload.get("user_id", "default")
        if not isinstance(user_id, str) or not user_id.strip():
            user_id = "default"
        lesson_type = self._classify_lesson_type(lesson_text, payload)
        record = payload.get("record") if isinstance(payload.get("record"), dict) else None
        if record is None:
            record = self._record_from_lesson(lesson_text, lesson_type, payload)
        skill_name = self._skill_name_from_lesson(lesson_text, lesson_type)
        behavior = self._behavior_from_lesson(lesson_text, lesson_type)
        targets = self._learning_targets_for_record(lesson_type, record)
        taught = []
        failed = []
        for destination in targets:
            contract = self._lobe_contract(destination)
            required_evidence = contract.get("required_evidence", set())
            required_evidence = (
                required_evidence if isinstance(required_evidence, set) else set(required_evidence)
            )
            preferred_surface = str(
                _GENERIC_EXPERIENCE_PROFILES.get(destination, {}).get("policy", "")
            )
            destination_record = dict(record)
            destination_record.setdefault(
                "surface",
                self._surface_for_destination(
                    destination,
                    preferred=preferred_surface or str(destination_record.get("subject", "")),
                ),
            )
            destination_record.setdefault("scope", destination)
            current_subject = str(destination_record.get("subject", "")).strip().lower()
            if current_subject in {
                "",
                "skill",
                "feedback",
                "correction",
                "fact",
                "rule",
                "procedure",
                "example",
                "exception",
            }:
                destination_record["subject"] = destination_record.get("surface")
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
                    "record": {**destination_record, "status": "provisional"},
                    "required_evidence": sorted(required_evidence),
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

    def learning_contracts(self) -> Dict[str, Any]:
        with self.lobe_handlers_lock:
            names = [name for name in self.lobe_handlers.keys() if name != "notus"]
        contracts = {name: dict(self._lobe_contract(name)) for name in names}
        for contract in contracts.values():
            for key in (
                "capabilities",
                "allowed_record_types",
                "required_evidence",
                "mutable_surfaces",
                "fixed_surfaces",
                "rejection_conditions",
            ):
                value = contract.get(key)
                if isinstance(value, set):
                    contract[key] = sorted(value)
        return {"status": "success", "content": {"contracts": contracts}, "contracts": contracts}

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
        contract = self._lobe_contract(destination)
        payload_for_contract = dict(payload)
        if msg_type in {"learn", "teach_skill"}:
            record = payload_for_contract.get("record", {})
            record = dict(record) if isinstance(record, dict) else {}
            if not isinstance(record.get("surface"), str) or not record.get("surface", "").strip():
                surface = self._surface_for_destination(
                    destination, preferred=str(record.get("subject", ""))
                )
                record["surface"] = surface
            else:
                surface = str(record.get("surface"))
            if not isinstance(record.get("subject"), str) or not record.get("subject", "").strip():
                record["subject"] = str(record.get("surface", "")).strip().lower()
            payload_for_contract["record"] = record
            payload_for_contract.setdefault("surface", str(record.get("surface", surface)))
        rejection = contract_rejection(contract, msg_type, payload_for_contract)
        if rejection is not None:
            return {
                "status": "error",
                "message": rejection.get("message", "Rejected by lobe contract"),
                "content": {
                    "destination": destination,
                    "action": "contract_rejected",
                    "condition": rejection.get("condition"),
                    **(
                        {"missing_evidence": rejection.get("missing_evidence")}
                        if rejection.get("missing_evidence")
                        else {}
                    ),
                },
            }

        user_id = payload.get("user_id", "default")
        memory_type = self._learning_memory_type(destination)

        if msg_type in {"learn", "teach_skill"}:
            payload_to_store = dict(payload_for_contract)
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
        if (
            destination == "notus"
            or msg_type in _LEARNING_ROUTE_TYPES
            or msg_type in _NO_GUIDANCE_OR_ADAPT_TYPES
        ):
            return
        user_id = self._normalised_user_id(content)
        behavior_key = f"behavior:{msg_type}"
        if response.get("status") == "success":
            surface = self._surface_for_destination(destination)
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
                    "record": {"type": "rule", "subject": surface, "surface": surface},
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
                "correction_fact": (
                    f"For message type '{msg_type}', avoid failing behavior and prefer safe recovery."
                ),
                "correction_evidence": [
                    f"before:For message type '{msg_type}', keep behavior that returns status success with stable content.",
                    f"after:For message type '{msg_type}', avoid failing behavior and prefer safe recovery.",
                    "validated:auto_adapt",
                ],
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
                "record": {"type": "rule", "subject": self._surface_for_destination(destination), "surface": self._surface_for_destination(destination)},
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
        if msg_type == "learn_from_experience" and not bool(
            getattr(lobe, "supports_experience_learning", False)
        ):
            rejection = self._experience_contract_rejection(destination, content)
            if rejection is not None:
                return {
                    "status": "error",
                    "message": rejection.get("message", "Rejected by lobe contract"),
                    "content": {
                        "delivered": True,
                        "interpreted": False,
                        "proposed": False,
                        "saved": False,
                        "retrieved": False,
                        "applied": False,
                        "behavior_changed": False,
                        "validated": False,
                        "action": "contract_rejected",
                        "condition": rejection.get("condition"),
                        **(
                            {"missing_evidence": rejection.get("missing_evidence")}
                            if rejection.get("missing_evidence")
                            else {}
                        ),
                    },
                }
            response = self._generic_experience_learning(destination, content, source)
            self.lobe_status[destination] = "online" if response.get("status") != "error" else "error"
            self.message_routes.append(
                {
                    "from": source,
                    "to": destination,
                    "type": msg_type,
                    "status": response.get("status", "error"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return response
        if msg_type == "learn_from_experience":
            rejection = self._experience_contract_rejection(destination, content)
            if rejection is not None:
                return {
                    "status": "error",
                    "message": rejection.get("message", "Rejected by lobe contract"),
                    "content": {
                        "action": "contract_rejected",
                        "condition": rejection.get("condition"),
                        **(
                            {"missing_evidence": rejection.get("missing_evidence")}
                            if rejection.get("missing_evidence")
                            else {}
                        ),
                    },
                }

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
        self._sync_pending_notus_writes(user_id=safe_user_id, limit=25)

        conversation = self.send_and_wait(
            "conversation", "understand", {"user_input": user_input, "user_id": safe_user_id}
        )
        if conversation["status"] != "success":
            return "I'm having trouble understanding right now."
        understanding = self._content(conversation).get("understanding", {})

        memory_payload = self._normalise_notus_write(
            {
                "role": "user",
                "content": user_input,
                "user_id": safe_user_id,
                "memory_type": "conversation",
            },
            safe_user_id,
        )
        memory = {"status": "error"}
        for _ in range(2):
            memory = self.send_and_wait(
                "notus",
                "store",
                memory_payload,
            )
            if memory.get("status") == "success":
                self._mark_notus_write_synced(memory_payload)
                break
        if memory.get("status") != "success":
            self._enqueue_notus_write(memory_payload)

        memory_context = {"status": "error", "content": {}}
        for _ in range(2):
            memory_context = self.send_and_wait(
                "notus",
                "query",
                {"query": user_input, "user_id": safe_user_id, "limit": 15},
            )
            if memory_context.get("status") == "success":
                self._sync_pending_notus_writes(user_id=safe_user_id, limit=50)
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
        if msg_type == "learn_from_experience":
            return self.process_learning_event(payload if isinstance(payload, dict) else {}, source="learn_from_experience")
        if msg_type == "learning_overview":
            return self.learning_overview(payload if isinstance(payload, dict) else {})
        if msg_type == "learning_contracts":
            return self.learning_contracts()
        if msg_type == "sync_notus_pending":
            content = payload if isinstance(payload, dict) else {}
            return {
                "status": "success",
                "content": self._sync_pending_notus_writes(
                    user_id=content.get("user_id"),
                    limit=content.get("limit", 100),
                ),
            }
        if msg_type == "notus_sync_status":
            with self._notus_sync_lock:
                pending = {
                    user: len(queue) for user, queue in self._pending_notus_writes.items() if queue
                }
            return {"status": "success", "content": {"pending": pending, "total_pending": sum(pending.values())}}
        if msg_type == "health":
            lobe_health = self._probe_lobes_health()
            if lobe_health.get("notus", {}).get("healthy"):
                self._sync_pending_notus_writes(limit=100)
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
