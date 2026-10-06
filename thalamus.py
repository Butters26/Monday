#!/usr/bin/env python3
"""Mercy Thalamus: routing and turn coordination only.

HARD OWNERSHIP RULE:
Thalamus may route envelopes, sequence lobe calls, record route diagnostics,
and handle transport/failure boundaries. It must not determine meaning, select
facts, judge answer relevance, infer truth, parse prose into semantics, generate
fallback answers, or take over work owned by another lobe.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import threading
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional

from notus_outage_fallback import NotusOutageFallback


class Thalamus:
    """Synchronous router/coordinator for Mercy's direct-call lobe graph."""

    def __init__(self) -> None:
        self.running = True
        self.lobe_handlers: Dict[str, Any] = {}
        self.lobe_handlers_lock = threading.RLock()
        self.lobe_status: Dict[str, str] = {}
        self.message_routes: deque = deque(maxlen=200)

        self.last_output_envelope: Optional[Dict[str, Any]] = None
        self.last_grounded_structures: Optional[List[Dict[str, Any]]] = None
        self.last_language_sentence: Optional[str] = None
        self.last_meta_cognition: Optional[Dict[str, Any]] = None
        self.last_executive: Optional[Dict[str, Any]] = None
        self.last_social_context: Optional[Dict[str, Any]] = None
        self.last_motor_action: Optional[Dict[str, Any]] = None
        self.last_voice_envelope: Optional[Dict[str, Any]] = None
        self.last_meta_awareness: Optional[Dict[str, Any]] = None
        self.last_speech_decision: Optional[Dict[str, Any]] = None
        self.last_representation: Optional[Dict[str, Any]] = None
        self._last_pre_output_final_text: Optional[str] = None
        self._last_curiosity_time = 0.0
        self._curiosity_cooldown_sec = 25.0
        self._force_curiosity_follow_up = False

        self.notus_fallback = NotusOutageFallback()

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
        return {
            "status": "success",
            "content": {"registered": name},
            "registered": name,
        }

    def _has_lobe(self, name: str) -> bool:
        with self.lobe_handlers_lock:
            return name in self.lobe_handlers

    def send_message(
        self,
        destination: str,
        msg_type: str,
        content: Optional[Dict[str, Any]] = None,
        source: str = "thalamus",
    ) -> Dict[str, Any]:
        """Route one envelope unchanged except for transport metadata."""
        if content is None:
            content = {}
        if not isinstance(content, dict):
            return {"status": "error", "message": "Message content must be a dictionary", "content": {}}

        with self.lobe_handlers_lock:
            lobe = self.lobe_handlers.get(destination)
        if lobe is None:
            self.lobe_status[destination] = "offline"
            return {
                "status": "error",
                "message": f"Unknown destination: {destination}",
                "content": {},
            }

        envelope = {
            "type": msg_type,
            "content": dict(content),
            "source": source,
            "message_id": str(uuid.uuid4()),
        }
        try:
            handler = getattr(lobe, "process_message", None) or getattr(
                lobe, "process_message_safe", None
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
            response = {
                "status": "error",
                "message": f"{destination}: {exc}",
                "content": {},
            }

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

    def send_and_wait(
        self,
        destination: str,
        msg_type: str,
        content: Optional[Dict[str, Any]] = None,
        source: str = "thalamus",
    ) -> Dict[str, Any]:
        return self.send_message(destination, msg_type, content or {}, source)

    def broadcast_message(
        self,
        destinations: Iterable[str],
        msg_type: str,
        content: Optional[Dict[str, Any]] = None,
        source: str = "thalamus",
    ) -> Dict[str, Dict[str, Any]]:
        return {
            destination: self.send_message(destination, msg_type, content or {}, source)
            for destination in destinations
        }

    @staticmethod
    def _content(response: Dict[str, Any]) -> Dict[str, Any]:
        content = response.get("content", {}) if isinstance(response, dict) else {}
        return content if isinstance(content, dict) else {}

    @classmethod
    def _route_reasoning_semantics(cls, response: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Reasoning's envelope without judging its meaning."""
        body = cls._content(response)
        semantic = body.get("semantic_input")
        semantic = dict(semantic) if isinstance(semantic, dict) else {}
        for key in ("answer", "conclusion", "propositions"):
            if key in semantic:
                continue
            value = body.get(key)
            if value is None and isinstance(response, dict):
                value = response.get(key)
            if value is not None:
                semantic[key] = value
        semantic.setdefault("semantic_owner", "reasoning")
        return semantic

    @staticmethod
    def _empty_representation(user_id: str) -> Dict[str, Any]:
        return {
            "status": "absent",
            "resolved": [],
            "concept_ids": [],
            "referent_ids": [],
            "proposition_ids": [],
            "highly_active_concepts": [],
            "active_concepts": [],
            "activation": {},
            "language_understanding": None,
            "language_comprehension_available": False,
            "language_first": True,
            "raw_text_parser_used": False,
            "user_id": user_id,
            "source": "shared_representation",
        }

    def _activate_representation_ids(
        self, concept_ids: List[str], *, user_id: str
    ) -> Dict[str, Any]:
        activation: Dict[str, float] = {}
        highly_active: List[Dict[str, Any]] = []

        if not self._has_lobe("shared_representation"):
            return {
                "activation": activation,
                "highly_active_concepts": highly_active,
                "active_concepts": [],
            }

        for concept_id in concept_ids:
            response = self.send_and_wait(
                "shared_representation",
                "activate",
                {
                    "concept_id": concept_id,
                    "amount": 1.0,
                    "spread": True,
                    "user_id": user_id,
                },
                source="thalamus",
            )
            if response.get("status") != "success":
                continue
            body = self._content(response)
            current = body.get("activation") or response.get("activation") or {}
            if isinstance(current, dict):
                for key, value in current.items():
                    try:
                        score = float(value)
                    except (TypeError, ValueError):
                        continue
                    activation[str(key)] = max(activation.get(str(key), 0.0), score)
            candidates = (
                body.get("highly_active_concepts")
                or response.get("highly_active_concepts")
                or []
            )
            if isinstance(candidates, list):
                highly_active = [
                    dict(item) for item in candidates if isinstance(item, dict)
                ]

        active_concepts: List[Dict[str, Any]] = []
        active_response = self.send_and_wait(
            "shared_representation",
            "get_active",
            {"user_id": user_id},
            source="thalamus",
        )
        if active_response.get("status") == "success":
            body = self._content(active_response)
            active = (
                body.get("active_concepts")
                or active_response.get("active_concepts")
                or []
            )
            if isinstance(active, list):
                active_concepts = [
                    dict(item) for item in active if isinstance(item, dict)
                ]

        return {
            "activation": activation,
            "highly_active_concepts": highly_active,
            "active_concepts": active_concepts,
        }

    def _resolve_representation_live(
        self,
        user_input: str,
        perception_payload: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        """Route raw language to Language, then route Language-owned IDs to SR."""
        empty = self._empty_representation(user_id)
        if not self._has_lobe("language") or not self._has_lobe(
            "shared_representation"
        ):
            self.last_representation = None
            return empty

        response = self.send_and_wait(
            "language",
            "comprehend",
            {"text": user_input or "", "user_id": user_id},
            source="thalamus",
        )
        if response.get("status") != "success":
            self.last_representation = None
            return empty

        body = self._content(response)
        understanding = body.get("language_understanding")
        concept_ids = [str(item) for item in (body.get("concept_ids") or []) if item]
        referent_ids = [
            str(item) for item in (body.get("referent_ids") or []) if item
        ]
        proposition_ids = [
            str(item) for item in (body.get("proposition_ids") or []) if item
        ]
        resolved = [
            dict(item)
            for item in (
                body.get("resolved_concepts") or body.get("resolved") or []
            )
            if isinstance(item, dict)
        ]
        active = self._activate_representation_ids(concept_ids, user_id=user_id)
        env = {
            "status": "success",
            "resolved": resolved,
            "concept_ids": concept_ids,
            "referent_ids": referent_ids,
            "proposition_ids": proposition_ids,
            "highly_active_concepts": active["highly_active_concepts"],
            "active_concepts": active["active_concepts"],
            "activation": active["activation"],
            "language_understanding": (
                understanding if isinstance(understanding, dict) else None
            ),
            "language_comprehension_available": isinstance(understanding, dict),
            "language_first": True,
            "raw_text_parser_used": False,
            "user_id": user_id,
            "source": "shared_representation",
        }
        self.last_representation = dict(env)

        if isinstance(perception_payload, dict):
            perception_payload["concept_ids"] = list(concept_ids)
            perception_payload["resolved_concepts"] = list(resolved)
            perception_payload["language_understanding"] = env[
                "language_understanding"
            ]
            perception_payload["referent_ids"] = list(referent_ids)
            perception_payload["proposition_ids"] = list(proposition_ids)
            perception_payload[
                "representation_source"
            ] = "language_via_shared_representation"
        return env

    def _attend_live_signals(
        self,
        user_input: str,
        perception_payload: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        if not self._has_lobe("attention"):
            return {}
        signals: List[Dict[str, Any]] = [
            {
                "id": "user_input",
                "text": user_input,
                "source": "user",
                "modality": "text",
                "user_id": user_id,
            }
        ]
        if isinstance(perception_payload, dict):
            for item in perception_payload.get("attention_signals") or []:
                if isinstance(item, dict):
                    signals.append(dict(item))
        response = self.send_and_wait(
            "attention",
            "evaluate",
            {"signals": signals, "user_id": user_id},
            source="thalamus",
        )
        if response.get("status") != "success":
            return {}
        payload = self._content(response)
        if payload.get("focus"):
            self.send_and_wait("attention", "route_focus", {}, source="thalamus")
        return payload

    def _executive_set_goal_from_turn(
        self, user_input: str, understanding: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        if not self._has_lobe("executive_control"):
            return None
        response = self.send_and_wait(
            "executive_control",
            "set_goal_from_turn",
            {"user_input": user_input, "understanding": understanding},
        )
        if response.get("status") != "success":
            return None
        body = self._content(response)
        self.last_executive = dict(body)
        self.send_and_wait(
            "executive_control", "steer_attention", {}, source="thalamus"
        )
        return self.last_executive

    def _executive_should_inhibit(self, action: str) -> bool:
        if not self._has_lobe("executive_control"):
            return False
        response = self.send_and_wait(
            "executive_control",
            "should_inhibit",
            {"action": action},
            source="thalamus",
        )
        if response.get("status") != "success":
            return False
        body = self._content(response)
        return bool(body.get("inhibited", response.get("inhibited")))

    def _social_observe_turn(
        self,
        user_input: str,
        understanding: Dict[str, Any],
        user_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        if not self._has_lobe("social_context"):
            return None
        response = self.send_and_wait(
            "social_context",
            "observe_turn",
            {
                "user_input": user_input,
                "understanding": understanding,
                "user_id": user_id,
            },
            source="thalamus",
        )
        if response.get("status") != "success":
            return None
        body = self._content(response)
        if body:
            self.last_social_context = dict(body)
            return self.last_social_context
        return None

    def _motor_plan_from_turn(
        self,
        user_input: str,
        understanding: Dict[str, Any],
        user_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        if not self._has_lobe("motor_action"):
            self.last_motor_action = None
            return None
        response = self.send_and_wait(
            "motor_action",
            "plan_from_turn",
            {
                "user_input": user_input,
                "understanding": understanding,
                "user_id": user_id,
                "goal": (
                    self.last_executive.get("goal")
                    if isinstance(self.last_executive, dict)
                    else None
                ),
            },
            source="thalamus",
        )
        if response.get("status") != "success":
            self.last_motor_action = None
            return None
        body = self._content(response)
        action = body.get("action")
        if isinstance(action, dict):
            self.last_motor_action = dict(action)
        return body

    def _motor_deliver_to_output(
        self, user_id: str = "default"
    ) -> Optional[Dict[str, Any]]:
        if not self._has_lobe("motor_action"):
            return None
        response = self.send_and_wait(
            "motor_action",
            "execute_next",
            {"user_id": user_id},
            source="thalamus",
        )
        if response.get("status") != "success":
            return None
        body = self._content(response)
        action = body.get("action")
        if isinstance(action, dict):
            self.last_motor_action = dict(action)
            if isinstance(self.last_output_envelope, dict):
                self.last_output_envelope["motor_action"] = dict(action)
            return dict(action)
        return None

    def _meta_awareness_observe_turn(
        self,
        user_input: str,
        understanding: Dict[str, Any],
        user_id: str = "default",
        novelty_score: float = 0.0,
    ) -> Optional[Dict[str, Any]]:
        if not self._has_lobe("meta_awareness"):
            self.last_meta_awareness = None
            return None
        response = self.send_and_wait(
            "meta_awareness",
            "observe_turn",
            {
                "user_input": user_input,
                "understanding": understanding,
                "user_id": user_id,
                "novelty_score": novelty_score,
            },
            source="thalamus",
        )
        if response.get("status") != "success":
            return None
        body = self._content(response)
        if body:
            self.last_meta_awareness = dict(body)
            return self.last_meta_awareness
        return None

    def _meta_awareness_release(
        self, user_id: str = "default", reason: str = "turn_complete"
    ) -> Optional[Dict[str, Any]]:
        if not self._has_lobe("meta_awareness"):
            return None
        response = self.send_and_wait(
            "meta_awareness",
            "release_to_wandering",
            {"reason": reason, "user_id": user_id},
            source="thalamus",
        )
        if response.get("status") != "success":
            return None
        return self._content(response)

    def _refresh_attention_payload_post_executive(
        self, prior: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        payload = dict(prior) if isinstance(prior, dict) else {}
        if not self._has_lobe("attention"):
            return payload
        routed = self.send_and_wait(
            "attention", "route_focus", {}, source="thalamus"
        )
        if routed.get("status") == "success":
            body = self._content(routed)
            candidate = body.get("payload")
            if isinstance(candidate, dict):
                payload.update(candidate)
        ranked = self.send_and_wait("attention", "rank", {}, source="thalamus")
        if ranked.get("status") == "success":
            body = self._content(ranked)
            values = body.get("ranked", ranked.get("ranked"))
            if isinstance(values, list):
                payload["ranked"] = values
        return payload

    def _run_pattern_live(
        self,
        user_input: str,
        perception_payload: Optional[Dict[str, Any]] = None,
        attention_payload: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None,
        emotional_state: Optional[Dict[str, Any]] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        if not self._has_lobe("pattern"):
            return {}
        perception_payload = (
            perception_payload if isinstance(perception_payload, dict) else {}
        )
        observation = {
            "statement": user_input,
            "items": list(perception_payload.get("words") or []),
            "words": list(perception_payload.get("words") or []),
            "perception": perception_payload,
            "attention": (
                attention_payload if isinstance(attention_payload, dict) else {}
            ),
            "understanding": (
                understanding if isinstance(understanding, dict) else {}
            ),
            "emotion": (
                emotional_state if isinstance(emotional_state, dict) else {}
            ),
            "user_id": user_id,
        }
        observed = self.send_and_wait(
            "pattern", "observe", observation, source="thalamus"
        )
        if observed.get("status") != "success":
            return {"status": "error", "significant_patterns": {}}
        significant = self.send_and_wait(
            "pattern", "get_significant", {"user_id": user_id}, source="thalamus"
        )
        body = self._content(significant) if significant.get("status") == "success" else {}
        values = body.get("significant_patterns") or significant.get(
            "significant_patterns"
        ) or {}
        return {
            "status": "success",
            "significant_patterns": values if isinstance(values, dict) else {},
            "observed_patterns": self._content(observed).get("patterns")
            or observed.get("patterns")
            or {},
        }

    def _meta_cognition_watch_reasoning(
        self,
        user_input: str,
        semantic_input: Dict[str, Any],
        reasoning_answer: Any,
        memories: Any,
    ) -> Dict[str, Any]:
        if not self._has_lobe("meta_cognition"):
            return semantic_input
        response = self.send_and_wait(
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
        if response.get("status") != "success":
            return semantic_input
        body = self._content(response)
        verdict = body.get("verdict") or response.get("verdict")
        if isinstance(verdict, dict):
            self.last_meta_cognition = dict(verdict)
        applied = body.get("semantic_input") or response.get("semantic_input")
        return applied if isinstance(applied, dict) else semantic_input

    def _meta_cognition_watch_language(
        self, sentence: str, semantic_input: Dict[str, Any]
    ) -> str:
        if not self._has_lobe("meta_cognition"):
            return sentence
        response = self.send_and_wait(
            "meta_cognition",
            "monitor_language",
            {
                "sentence": sentence,
                "semantic_input": semantic_input,
                "prior_verdict": self.last_meta_cognition,
            },
        )
        if response.get("status") != "success":
            return sentence
        body = self._content(response)
        verdict = body.get("verdict") or response.get("verdict")
        if isinstance(verdict, dict):
            self.last_meta_cognition = dict(verdict)
            corrected = verdict.get("corrected_sentence")
            if isinstance(corrected, str):
                return corrected
        return sentence

    def _speech_notify_user_turn(self, user_id: str = "default") -> None:
        if self._has_lobe("speech"):
            self.send_message(
                "speech", "user_spoke", {"user_id": user_id}, source="thalamus"
            )

    def _voice_speak_for_output(
        self,
        text: str,
        *,
        user_id: str = "default",
        emotion: str = "neutral",
        intensity: float = 0.5,
        voice_prosody: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self._has_lobe("voice") or not isinstance(text, str) or not text.strip():
            self.last_voice_envelope = None
            return None
        response = self.send_and_wait(
            "voice",
            "speak_for_output",
            {
                "text": text,
                "user_id": user_id,
                "emotion": emotion,
                "intensity": intensity,
                "voice_prosody": voice_prosody or {},
            },
            source="thalamus",
        )
        if response.get("status") != "success":
            self.last_voice_envelope = None
            return None
        body = self._content(response)
        voice = body.get("voice") or response.get("voice")
        if isinstance(voice, dict):
            self.last_voice_envelope = dict(voice)
            if isinstance(self.last_output_envelope, dict):
                self.last_output_envelope["voice"] = dict(voice)
            return dict(voice)
        return None

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

    def retry_unsaved_notus_records(
        self, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        def _store(record: Dict[str, Any]) -> bool:
            payload = {
                "role": record.get("role", "user"),
                "content": record.get("content", ""),
                "user_id": record.get("user_id", "default"),
                "memory_type": record.get("memory_type", "conversation"),
            }
            for key in ("tag", "importance", "mode"):
                if key in record:
                    payload[key] = record[key]
            event_id = record.get("event_id") or record.get("dedupe_key")
            if event_id:
                payload["event_id"] = event_id
            response = self.send_and_wait("notus", "store", payload)
            return response.get("status") == "success"

        return self.notus_fallback.flush(_store, user_id=user_id)

    def _merge_notus_fallback_into_context(
        self, memory_context: Dict[str, Any], user_id: str, limit: int = 15
    ) -> Dict[str, Any]:
        if self.notus_fallback.pending_count(user_id) <= 0:
            return memory_context
        body = dict(self._content(memory_context))
        memories = list(body.get("memories") or [])
        merged = self.notus_fallback.merge_pending_into(
            user_id, memories, limit=limit
        )
        body["memories"] = merged
        if isinstance(body.get("semantic"), list):
            body["semantic"] = merged
        body["fallback_pending"] = True
        return {"status": "success", "content": body}

    def _flush_notus_fallback_best_effort(self, user_id: str) -> None:
        try:
            if self.notus_fallback.pending_count(user_id):
                self.retry_unsaved_notus_records(user_id=user_id)
        except Exception:
            pass

    def process_user_input(
        self,
        user_input: str,
        user_id: str = "default",
        perception_payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Sequence lobe-owned work without interpreting or repairing its meaning."""
        if not isinstance(user_input, str) or not user_input.strip():
            return ""

        if perception_payload is None:
            perception_payload = {}
            if self._has_lobe("perception"):
                response = self.send_and_wait(
                    "perception",
                    "perceive_text",
                    {"text": user_input, "user_id": user_id},
                )
                if response.get("status") != "success":
                    return ""
                perception_payload = self._content(response)
                normalized = (
                    perception_payload.get("text")
                    or perception_payload.get("normalized_text")
                )
                if isinstance(normalized, str) and normalized.strip():
                    user_input = normalized.strip()
        else:
            perception_payload = dict(perception_payload)

        if (
            self._has_lobe("sensory_integration")
            and isinstance(perception_payload, dict)
            and perception_payload
            and (perception_payload.get("raw_meta") or {}).get("source")
            != "sensory_integration"
        ):
            response = self.send_and_wait(
                "sensory_integration",
                "absorb",
                {
                    "envelope": perception_payload,
                    "user_id": user_id,
                    "route_attention": False,
                },
                source="thalamus",
            )
            if response.get("status") == "success":
                body = self._content(response)
                if body:
                    perception_payload = body

        if self._has_lobe("novelty"):
            response = self.send_and_wait(
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
            if response.get("status") == "success":
                novelty = self._content(response)
                perception_payload = dict(perception_payload)
                if "novelty_score" in novelty:
                    perception_payload["novelty_score"] = novelty.get(
                        "novelty_score"
                    )
                if "is_novel" in novelty:
                    perception_payload["novelty_is_novel"] = novelty.get(
                        "is_novel"
                    )
                if "novelty_flags" in novelty:
                    perception_payload["novelty_flags"] = list(
                        novelty.get("novelty_flags") or []
                    )

        attention_payload = self._attend_live_signals(
            user_input, perception_payload, user_id=user_id
        )
        representation_result = self._resolve_representation_live(
            user_input, perception_payload, user_id=user_id
        )

        if self._has_lobe("autonomous"):
            self.send_message(
                "autonomous",
                "user_active",
                {"user_id": user_id, "text": user_input},
                source="thalamus",
            )
        self._speech_notify_user_turn(user_id=user_id)

        conversation = self.send_and_wait(
            "conversation",
            "understand",
            {
                "user_input": user_input,
                "user_id": user_id,
                "perception": perception_payload,
                "attention": attention_payload,
                "language_understanding": representation_result.get(
                    "language_understanding"
                ),
                "concept_ids": list(representation_result.get("concept_ids") or []),
                "referent_ids": list(
                    representation_result.get("referent_ids") or []
                ),
                "proposition_ids": list(
                    representation_result.get("proposition_ids") or []
                ),
                "context": {
                    "perception": perception_payload,
                    "attention": attention_payload,
                    "language_understanding": representation_result.get(
                        "language_understanding"
                    ),
                    "concept_ids": list(
                        representation_result.get("concept_ids") or []
                    ),
                    "referent_ids": list(
                        representation_result.get("referent_ids") or []
                    ),
                    "proposition_ids": list(
                        representation_result.get("proposition_ids") or []
                    ),
                },
            },
        )
        if conversation.get("status") != "success":
            return ""
        understanding = self._content(conversation).get("understanding", {})
        understanding = understanding if isinstance(understanding, dict) else {}

        self._executive_set_goal_from_turn(user_input, understanding)
        social_context = self._social_observe_turn(
            user_input, understanding, user_id=user_id
        )
        self._motor_plan_from_turn(user_input, understanding, user_id=user_id)
        try:
            novelty_score = float(perception_payload.get("novelty_score") or 0.0)
        except (TypeError, ValueError):
            novelty_score = 0.0
        self._meta_awareness_observe_turn(
            user_input,
            understanding,
            user_id=user_id,
            novelty_score=novelty_score,
        )
        attention_payload = self._refresh_attention_payload_post_executive(
            attention_payload
        )

        stored = self.send_and_wait(
            "notus",
            "store",
            {"role": "user", "content": user_input, "user_id": user_id},
        )
        if stored.get("status") != "success":
            self.notus_fallback.enqueue(
                user_id=user_id,
                role="user",
                content=user_input,
                memory_type="conversation",
            )
        else:
            self._flush_notus_fallback_best_effort(user_id)

        memory_context = self.send_and_wait(
            "notus",
            "query_context",
            {"query": user_input, "user_id": user_id, "limit": 15},
        )
        if memory_context.get("status") != "success":
            memory_context = self.send_and_wait(
                "notus",
                "query",
                {"query": user_input, "user_id": user_id, "limit": 15},
            )
        if memory_context.get("status") != "success":
            fallback = self.notus_fallback.memories_for(user_id, limit=15)
            memory_context = {
                "status": "success",
                "content": {
                    "memories": fallback,
                    "semantic": fallback,
                    "facts": [],
                    "episodic": [],
                    "memory_source": "notus_outage_fallback",
                },
            }
        else:
            memory_context = self._merge_notus_fallback_into_context(
                memory_context, user_id, limit=15
            )
            self._flush_notus_fallback_best_effort(user_id)
        ctx = self._content(memory_context)

        emotion = self.send_and_wait(
            "emotion", "process_input", {"user_input": user_input}
        )
        if emotion.get("status") != "success":
            return ""
        emotional_state = self._content(emotion)

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
                    "representation_result": representation_result,
                    "social_context": (
                        social_context
                        if isinstance(social_context, dict)
                        else self.last_social_context
                    ),
                }
            },
        )
        if reasoning.get("status") != "success":
            return ""
        semantic_input = self._route_reasoning_semantics(reasoning)

        grounded = semantic_input.get("grounded_structures")
        self.last_grounded_structures = (
            [dict(item) for item in grounded if isinstance(item, dict)]
            if isinstance(grounded, list)
            else None
        )

        semantic_input = self._meta_cognition_watch_reasoning(
            user_input,
            semantic_input,
            semantic_input.get("answer"),
            list(ctx.get("memories") or []) if isinstance(ctx, dict) else [],
        )

        language = self.send_and_wait(
            "language", "generate", {"semantic_input": semantic_input}
        )
        if language.get("status") != "success":
            return ""
        response_text = self._content(language).get("sentence", "")
        if not isinstance(response_text, str):
            response_text = ""
        response_text = self._meta_cognition_watch_language(
            response_text, semantic_input
        )
        self.last_language_sentence = response_text

        final_text = self._maybe_attach_curiosity_follow_up(
            response_text,
            user_input=user_input,
            emotional_state=emotional_state,
            understanding=understanding,
        )
        self._last_pre_output_final_text = final_text

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
            },
        )
        if output.get("status") != "success":
            return ""
        output_body = self._content(output)
        envelope = output_body.get("envelope") or output.get("envelope")
        if not isinstance(envelope, dict):
            envelope = {
                "text": output_body.get("text", final_text),
                "expression": output_body.get("expression") or {},
                "delivery": output_body.get("delivery") or {},
                "emotional_tone": output_body.get("emotional_tone"),
                "voice_prosody": output_body.get("voice_prosody") or {},
                "emotion": emotional_state.get(
                    "current_emotion", emotional_state.get("emotion", "neutral")
                ),
                "intensity": emotional_state.get("intensity", 0.5),
            }
        self.last_output_envelope = envelope

        self._motor_deliver_to_output(user_id=user_id)
        try:
            output_intensity = float(envelope.get("intensity") or 0.5)
        except (TypeError, ValueError):
            output_intensity = 0.5
        self._voice_speak_for_output(
            str(envelope.get("text") or output_body.get("text") or final_text or ""),
            user_id=user_id,
            emotion=str(
                envelope.get("emotion")
                or emotional_state.get("current_emotion")
                or emotional_state.get("emotion")
                or "neutral"
            ),
            intensity=output_intensity,
            voice_prosody=envelope.get("voice_prosody") or {},
        )
        self._meta_awareness_release(user_id=user_id, reason="turn_complete")

        if isinstance(self.last_meta_awareness, dict) and isinstance(
            self.last_output_envelope, dict
        ):
            self.last_output_envelope["meta_awareness"] = dict(
                self.last_meta_awareness
            )

        reply = (
            self.last_output_envelope.get("text")
            if isinstance(self.last_output_envelope, dict)
            else None
        ) or output_body.get("text") or final_text
        reply = reply if isinstance(reply, str) else ""

        if reply.strip():
            spoken = self.send_and_wait(
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
            if spoken.get("status") != "success":
                self.notus_fallback.enqueue(
                    user_id=user_id,
                    role="monday",
                    content=reply.strip(),
                    memory_type="conversation",
                    extra={
                        "tag": "Spoken",
                        "importance": 6.5,
                        "mode": "memory",
                    },
                )
            else:
                self._flush_notus_fallback_best_effort(user_id)
        return reply

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
        modality = (modality or "text").strip().lower()
        if modality in {"text", "chat", "language"}:
            if not isinstance(text, str) or not text.strip():
                return {"status": "error", "message": "text modality requires text="}
            if continue_conversation:
                return self.process_user_input(text, user_id=user_id)
            return self.send_and_wait(
                "perception",
                "perceive_text",
                {"text": text, "user_id": user_id},
            )

        if not self._has_lobe("sensory_integration"):
            return {
                "status": "error",
                "message": "sensory_integration lobe not registered",
            }

        item: Dict[str, Any] = {"modality": modality}
        if path:
            item["path"] = path
        if audio_bytes is not None:
            item["audio_bytes"] = audio_bytes
        if image_bytes is not None:
            item["image_bytes"] = image_bytes
        inputs = [item]
        for extra in extra_inputs or []:
            if extra is not None:
                inputs.append(extra)
        response = self.send_and_wait(
            "sensory_integration",
            "ingest",
            {
                "inputs": inputs,
                "user_id": user_id,
                "route_attention": not continue_conversation,
                "primary_modality": modality,
            },
            source="thalamus",
        )
        if response.get("status") != "success" or not continue_conversation:
            return response
        stream = self._content(response)
        routed_text = stream.get("text") or stream.get("normalized_text")
        if not isinstance(routed_text, str) or not routed_text.strip():
            return ""
        return self.process_user_input(
            routed_text.strip(), user_id=user_id, perception_payload=stream
        )

    def handle_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        payload = message.get("content", message)
        payload = payload if isinstance(payload, dict) else {}
        if msg_type == "process_input":
            response = self.process_user_input(
                str(payload.get("user_input") or ""),
                user_id=str(payload.get("user_id") or "default"),
            )
            return {
                "status": "success",
                "content": {"response": response},
                "response": response,
            }
        if msg_type == "health":
            return {
                "status": "success",
                "content": {
                    "thalamus_healthy": True,
                    "lobes": self.lobe_status.copy(),
                },
            }
        if msg_type == "pop_spoken_aside" and self._has_lobe("autonomous"):
            with self.lobe_handlers_lock:
                autonomous = self.lobe_handlers.get("autonomous")
            pop = getattr(autonomous, "pop_spoken_aside", None)
            aside = pop() if callable(pop) else None
            return {
                "status": "success",
                "content": {"aside": aside, "thought": aside},
                "aside": aside,
                "thought": aside,
            }
        return {
            "status": "error",
            "message": f"Unknown type: {msg_type}",
            "content": {},
        }

    def start(self) -> "Thalamus":
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


__all__ = ["Thalamus", "get_thalamus"]
