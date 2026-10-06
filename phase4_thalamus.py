#!/usr/bin/env python3
"""Phase 4 routing bridge for Mercy's Thalamus.

HARD ROUTING RULE:
Thalamus routes information; it does not determine linguistic or semantic meaning.
Raw user language goes to Language comprehension first. Shared Representation is
then addressed only with already-resolved IDs/structures for storage, activation,
and retrieval. Reasoning owns evidence/relevance/inference/semantic finalization;
Language owns linguistic comprehension and expression; Conversation owns dialogue
acts/discourse; MetaCognition owns epistemic intervention.

Phase 4 removes the old live-path semantic glue from Thalamus. Phase 5 can fold
these migration adapters into the native classes and remove the bridge files.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from phase3_thalamus import Phase3Thalamus


class Phase4Thalamus(Phase3Thalamus):
    """Route cognitive envelopes without deciding their meaning."""

    @staticmethod
    def _response_content(response: Dict[str, Any]) -> Dict[str, Any]:
        content = response.get("content")
        return content if isinstance(content, dict) else response

    @classmethod
    def _route_reasoning_semantics(cls, response: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Reasoning's envelope without judging or rewriting meaning.

        Phase 4 Reasoning returns ``semantic_input``. Legacy/injected Reasoning
        implementations may still return ``answer``, ``conclusion`` and
        ``propositions`` directly in their content envelope. Carry those fields
        into the canonical semantic envelope unchanged so Language can consume
        them. This is schema/routing compatibility only: no relevance scoring,
        fallback generation, parsing, precedence selection, or fact salvage.
        """
        body = cls._response_content(response)
        semantic = body.get("semantic_input")
        semantic = dict(semantic) if isinstance(semantic, dict) else {}

        for key in ("answer", "conclusion", "propositions"):
            if key in semantic:
                continue
            value = body.get(key)
            if value is None:
                value = response.get(key)
            if value is not None:
                semantic[key] = value

        semantic.setdefault("semantic_owner", "reasoning")
        return semantic

    def _empty_representation(self, user_id: str) -> Dict[str, Any]:
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
            "phase3_language_comprehension": False,
            "phase4_language_first": True,
            "legacy_raw_text_parser_used": False,
            "user_id": user_id,
            "source": "shared_representation",
        }

    def _activate_representation_ids(
        self,
        concept_ids: List[str],
        *,
        user_id: str,
    ) -> Dict[str, Any]:
        """Route activation by stable IDs only; never reinterpret text here."""
        activation: Dict[str, float] = {}
        highly_active: List[Dict[str, Any]] = []

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
            body = self._response_content(response)
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
                highly_active = [dict(item) for item in candidates if isinstance(item, dict)]

        active_concepts: List[Dict[str, Any]] = []
        active_response = self.send_and_wait(
            "shared_representation",
            "get_active",
            {"user_id": user_id},
            source="thalamus",
        )
        if active_response.get("status") == "success":
            body = self._response_content(active_response)
            active = body.get("active_concepts") or active_response.get("active_concepts") or []
            if isinstance(active, list):
                active_concepts = [dict(item) for item in active if isinstance(item, dict)]

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
        """Language → Shared Representation IDs → downstream routing envelope."""
        empty = self._empty_representation(user_id)
        with self.lobe_handlers_lock:
            has_language = "language" in self.lobe_handlers
            has_shared = "shared_representation" in self.lobe_handlers

        # No semantic fallback through Shared Representation. If Language is not
        # available, Thalamus reports absence rather than interpreting raw text.
        if not has_language or not has_shared:
            self.last_representation = None
            return empty

        try:
            language_response = self.send_and_wait(
                "language",
                "comprehend",
                {
                    "text": user_input or "",
                    "user_id": user_id,
                },
                source="thalamus",
            )
        except Exception:
            self.last_representation = None
            return empty

        if language_response.get("status") != "success":
            self.last_representation = None
            return empty

        body = self._response_content(language_response)
        understanding = body.get("language_understanding")
        concept_ids = [str(item) for item in (body.get("concept_ids") or []) if item]
        referent_ids = [str(item) for item in (body.get("referent_ids") or []) if item]
        proposition_ids = [str(item) for item in (body.get("proposition_ids") or []) if item]
        resolved = [
            dict(item)
            for item in (body.get("resolved_concepts") or body.get("resolved") or [])
            if isinstance(item, dict)
        ]

        activation_state = self._activate_representation_ids(
            concept_ids,
            user_id=user_id,
        )

        env: Dict[str, Any] = {
            "status": "success",
            "resolved": resolved,
            "concept_ids": concept_ids,
            "referent_ids": referent_ids,
            "proposition_ids": proposition_ids,
            "highly_active_concepts": activation_state["highly_active_concepts"],
            "active_concepts": activation_state["active_concepts"],
            "activation": activation_state["activation"],
            "language_understanding": understanding if isinstance(understanding, dict) else None,
            "phase3_language_comprehension": isinstance(understanding, dict),
            "phase4_language_first": True,
            "legacy_raw_text_parser_used": False,
            "user_id": user_id,
            "source": "shared_representation",
        }

        self.last_representation = dict(env)
        if isinstance(perception_payload, dict):
            # Routing metadata only. Perception did not derive these semantics.
            perception_payload["concept_ids"] = list(concept_ids)
            perception_payload["resolved_concepts"] = list(resolved)
            perception_payload["language_understanding"] = env["language_understanding"]
            perception_payload["referent_ids"] = list(referent_ids)
            perception_payload["proposition_ids"] = list(proposition_ids)
            perception_payload["representation_source"] = "language_via_shared_representation"

        return env

    def _maybe_attach_curiosity_follow_up(
        self,
        reply: str,
        user_input: str = "",
        emotional_state: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Route curiosity decision to Conversation; Thalamus does not invent it."""
        if not isinstance(reply, str) or not reply.strip():
            return reply
        if self._executive_should_inhibit("curiosity_follow_up"):
            self._force_curiosity_follow_up = False
            return reply

        emotional_state = emotional_state if isinstance(emotional_state, dict) else {}
        understanding = understanding if isinstance(understanding, dict) else {}
        force = bool(getattr(self, "_force_curiosity_follow_up", False))
        now = time.time()
        if not force and (
            now - float(getattr(self, "_last_curiosity_time", 0.0) or 0.0)
        ) < float(getattr(self, "_curiosity_cooldown_sec", 25.0)):
            return reply

        with self.lobe_handlers_lock:
            conversation = self.lobe_handlers.get("conversation")
        decide = getattr(conversation, "maybe_curiosity_follow_up", None) if conversation else None
        if not callable(decide):
            return reply
        try:
            question = decide(
                user_input,
                emotional_state,
                understanding,
                force=force,
            )
        except Exception:
            question = None
        if not isinstance(question, str) or not question.strip():
            return reply

        question = question.strip()
        if question in reply:
            return reply
        self._last_curiosity_time = now
        if force:
            self._force_curiosity_follow_up = False
        return f"{reply.rstrip()}\n\n{question}"

    def process_user_input(
        self,
        user_input: str,
        user_id: str = "default",
        perception_payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Orchestrate one prompted turn without semantic decision-making."""
        if not isinstance(user_input, str) or not user_input.strip():
            return ""

        # Perception owns sensory normalization. Thalamus only routes its envelope.
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
                    return ""
                perception_payload = self._content(perception)
                normalized = (
                    perception_payload.get("text")
                    or perception_payload.get("normalized_text")
                    or user_input
                )
                if isinstance(normalized, str) and normalized.strip():
                    user_input = normalized.strip()
        else:
            perception_payload = dict(perception_payload)

        # SensoryIntegration owns fusion; Thalamus routes the envelope through it.
        with self.lobe_handlers_lock:
            has_si = "sensory_integration" in self.lobe_handlers
        if has_si and isinstance(perception_payload, dict) and perception_payload:
            already_si = (
                (perception_payload.get("raw_meta") or {}).get("source")
                == "sensory_integration"
            )
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
                except Exception:
                    pass

        # Novelty owns novelty assessment; Thalamus only carries the result.
        with self.lobe_handlers_lock:
            has_novelty = "novelty" in self.lobe_handlers
        if has_novelty:
            try:
                fresh = self.send_and_wait(
                    "novelty", "take_fresh_assessment", {}, source="thalamus"
                )
                fresh_body = (
                    self._content(fresh) if fresh.get("status") == "success" else {}
                )
                reuse = bool(fresh.get("fresh") or fresh_body.get("stimulus"))
                if reuse and str(fresh_body.get("stimulus") or "") == user_input[:240]:
                    novelty_payload = fresh_body
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
                    novelty_payload = (
                        self._content(nov_resp)
                        if nov_resp.get("status") == "success"
                        else {}
                    )
                if isinstance(novelty_payload, dict) and novelty_payload:
                    perception_payload = dict(perception_payload or {})
                    try:
                        perception_payload["novelty_score"] = float(
                            novelty_payload.get("novelty_score") or 0.0
                        )
                    except (TypeError, ValueError):
                        perception_payload["novelty_score"] = 0.0
                    perception_payload["novelty_is_novel"] = bool(
                        novelty_payload.get("is_novel")
                    )
                    perception_payload["novelty_flags"] = list(
                        novelty_payload.get("novelty_flags")
                        or perception_payload.get("novelty_flags")
                        or []
                    )
                    perception_payload["novelty"] = {
                        "score": perception_payload["novelty_score"],
                        "is_novel": perception_payload["novelty_is_novel"],
                        "novel_tokens": list(novelty_payload.get("novel_tokens") or []),
                        "familiar_overlap": novelty_payload.get("familiar_overlap"),
                        "nearest_similarity": novelty_payload.get("nearest_similarity"),
                    }
            except Exception:
                pass

        attention_payload: Dict[str, Any] = self._attend_live_signals(
            user_input, perception_payload, user_id=user_id
        )
        representation_result: Dict[str, Any] = self._resolve_representation_live(
            user_input, perception_payload, user_id=user_id
        )

        # Presence/pacing notifications are routing, not semantic interpretation.
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
        try:
            self._speech_notify_user_turn(user_id=user_id)
        except Exception:
            pass

        pre_turn_intensity = 0.5
        preloaded_aside = None
        try:
            with self.lobe_handlers_lock:
                has_emotion = "emotion" in self.lobe_handlers
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
                            now = time.time()
                            cooled = (
                                now
                                - float(
                                    getattr(self, "_last_spoken_aside_time", 0.0)
                                    or 0.0
                                )
                            ) >= float(
                                getattr(self, "_spoken_aside_cooldown_sec", 45.0)
                            )
                            if cooled:
                                preloaded_aside = self._mint_speak_worthy_from_inner_life()
            elif has_autonomous:
                preloaded_aside = self._pop_speak_worthy_candidate()
        except Exception:
            preloaded_aside = None

        # Conversation receives Language/SR context explicitly. Conversation owns
        # dialogue act, intent, topic continuity, and discourse resolution.
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
                "referent_ids": list(representation_result.get("referent_ids") or []),
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

        # Memory owns storage/retrieval. Thalamus no longer reformats facts,
        # promotes working-set rows, detects own-speech semantics, or filters
        # evidence. The complete context is routed to Reasoning as returned.
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
            fallback_memories = self.notus_fallback.memories_for(user_id, limit=15)
            memory_context = {
                "status": "success",
                "content": {
                    "memories": fallback_memories,
                    "semantic": fallback_memories,
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
        if not (emotional_state.get("unresolved_appraisals") or []):
            try:
                state = self.send_and_wait("emotion", "get_state", {})
                if state.get("status") == "success":
                    body = self._content(state)
                    unresolved = (
                        state.get("unresolved_appraisals")
                        or body.get("unresolved_appraisals")
                        or []
                    )
                    if unresolved:
                        emotional_state = dict(emotional_state)
                        emotional_state["unresolved_appraisals"] = unresolved
            except Exception:
                pass

        pattern_result = self._run_pattern_live(
            user_input,
            perception_payload=perception_payload,
            attention_payload=attention_payload,
            understanding=understanding,
            emotional_state=emotional_state,
            user_id=user_id,
        )

        # Reasoning receives all routed evidence/context and returns the finalized
        # semantic envelope. Thalamus does not rank, salvage, parse, or rewrite it.
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
                },
            },
        )
        if reasoning.get("status") != "success":
            return ""
        semantic_input = self._route_reasoning_semantics(reasoning)

        # Phase 4's production Reasoning adapter marks this. Do not replace a
        # missing marker with Thalamus-side semantic repair.
        if not semantic_input.get("phase4_semantics_finalized"):
            semantic_input = dict(semantic_input)
            semantic_input["phase4_semantics_finalized"] = False
            semantic_input["semantic_owner"] = semantic_input.get(
                "semantic_owner", "reasoning"
            )

        grounded = semantic_input.get("grounded_structures")
        self.last_grounded_structures = (
            [dict(item) for item in grounded if isinstance(item, dict)]
            if isinstance(grounded, list)
            else None
        )

        # MetaCognition may intervene epistemically; Thalamus merely routes the
        # finalized semantic envelope through that owner and forwards its result.
        memories_for_meta = (
            list(ctx.get("memories") or []) if isinstance(ctx, dict) else []
        )
        reasoning_answer = semantic_input.get("answer")
        semantic_input = self._meta_cognition_watch_reasoning(
            user_input,
            semantic_input,
            reasoning_answer,
            memories_for_meta,
        )
        grounded = semantic_input.get("grounded_structures")
        self.last_grounded_structures = (
            [dict(item) for item in grounded if isinstance(item, dict)]
            if isinstance(grounded, list)
            else None
        )

        language = self.send_and_wait(
            "language",
            "generate",
            {"semantic_input": semantic_input},
        )
        if language.get("status") != "success":
            return ""
        response_text = self._content(language).get("sentence", "")
        if isinstance(response_text, str):
            response_text = self._meta_cognition_watch_language(
                response_text, semantic_input
            )
        self.last_language_sentence = (
            response_text if isinstance(response_text, str) else None
        )

        # Delivery orchestration remains in Thalamus; wording/meaning does not.
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
            user_id=user_id,
        )
        final_text = self._maybe_attach_curiosity_follow_up(
            final_text,
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
                "uncertainty_flagged": bool(
                    isinstance(self.last_meta_cognition, dict)
                    and (self.last_meta_cognition.get("signals") or {}).get(
                        "flag_uncertainty"
                    )
                ),
            },
        )
        output_body = self._content(output)
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
        self._motor_deliver_to_output(user_id=user_id)
        try:
            output_intensity = float(
                (envelope.get("intensity") if isinstance(envelope, dict) else None)
                or emotional_state.get("intensity", 0.5)
                or 0.5
            )
        except (TypeError, ValueError):
            output_intensity = 0.5
        self._voice_speak_for_output(
            (envelope.get("text") if isinstance(envelope, dict) else None)
            or output_body.get("text", final_text)
            or "",
            user_id=user_id,
            emotion=str(
                (envelope.get("emotion") if isinstance(envelope, dict) else None)
                or emotional_state.get("current_emotion")
                or emotional_state.get("emotion")
                or "neutral"
            ),
            intensity=output_intensity,
            voice_prosody=(
                (envelope.get("voice_prosody") if isinstance(envelope, dict) else None)
                or emotional_state.get("voice_prosody")
                or {}
            ),
        )
        self._meta_awareness_release(user_id=user_id, reason="turn_complete")
        if isinstance(self.last_meta_awareness, dict) and isinstance(
            self.last_output_envelope, dict
        ):
            self.last_output_envelope["meta_awareness"] = dict(
                self.last_meta_awareness
            )
        if isinstance(self.last_output_envelope, dict):
            envelope = self.last_output_envelope
        reply = envelope.get("text") or output_body.get("text", final_text)

        # Persist exact delivered speech. This is routing to Memory, not semantic
        # reinterpretation of the response.
        if isinstance(reply, str) and reply.strip():
            try:
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
            except Exception as exc:
                spoken = {"status": "error", "message": str(exc)}
            if not isinstance(spoken, dict) or spoken.get("status") != "success":
                self.notus_fallback.enqueue(
                    user_id=user_id,
                    role="monday",
                    content=reply.strip(),
                    memory_type="conversation",
                    extra={"tag": "Spoken", "importance": 6.5, "mode": "memory"},
                )
            else:
                self._flush_notus_fallback_best_effort(user_id)
        return reply

    def process_user_input(self, user_input: str, user_id: str = "default") -> str:
        """Run the legacy orchestration with Phase 4 semantic ownership enforced.

        The legacy coordinator still contains migration-era semantic repair code.
        Phase 4 does not permit that code to make semantic decisions. Instead,
        Reasoning returns a finalized semantic envelope and this router temporarily
        disables the legacy repair helpers while the inherited orchestration routes
        that envelope through MetaCognition, Language, Output, and the other lobes.
        """
        import thalamus as legacy_module

        forbidden = {
            "relevance_score": legacy_module.relevance_score,
            "answer_from_grounded_memories": legacy_module.answer_from_grounded_memories,
            "structures_from_grounded_memories": legacy_module.structures_from_grounded_memories,
            "prose_answer_to_structures": legacy_module.prose_answer_to_structures,
            "_attribute_asked": legacy_module._attribute_asked,
            "_fact_covers_attribute": legacy_module._fact_covers_attribute,
        }

        # Neutralize only Thalamus's migration-era semantic choices. Reasoning and
        # Language import/own their corresponding helpers independently.
        legacy_module.relevance_score = lambda _query, _candidate: 1.0
        legacy_module._attribute_asked = lambda _query: None
        legacy_module._fact_covers_attribute = lambda _candidate, _attribute: True
        legacy_module.answer_from_grounded_memories = lambda _query, _memories: None
        legacy_module.structures_from_grounded_memories = lambda _query, _memories: []
        legacy_module.prose_answer_to_structures = lambda _answer: []
        try:
            return super().process_user_input(user_input, user_id=user_id)
        finally:
            for name, value in forbidden.items():
                setattr(legacy_module, name, value)


Thalamus = Phase4Thalamus

__all__ = ["Phase4Thalamus", "Thalamus"]
