#!/usr/bin/env python3
"""Phase 4 Reasoning adapter for Mercy.

HARD OWNERSHIP RULE:
Reasoning owns inference, evidence selection, answer relevance, grounded semantic
structures, and the semantic handoff to Language. Thalamus may route this result,
but must not reinterpret, salvage, rank, or rewrite its meaning.

This adapter sits on top of the Phase 2 Shared Representation reasoning bridge.
It prepares Reasoning's own memory evidence (including own-speech context), keeps
Language/SR IDs available, and marks the returned semantic envelope finalized for
Phase 4 routing.
"""

from __future__ import annotations

from typing import Any, Dict, List

from shared_representation_phase2 import SharedRepresentationReasoningAdapter


_MONDAY_ROLES = {"monday", "assistant", "abin"}


class Phase4ReasoningAdapter(SharedRepresentationReasoningAdapter):
    """Reasoning owns semantic finalization; Thalamus only routes the result."""

    @staticmethod
    def _response_content(response: Dict[str, Any]) -> Dict[str, Any]:
        content = response.get("content")
        return content if isinstance(content, dict) else response

    @staticmethod
    def _dedupe_memories(memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        out: List[Dict[str, Any]] = []
        for memory in memories:
            if not isinstance(memory, dict):
                continue
            content = str(memory.get("content") or memory.get("text") or "").strip()
            role = str(memory.get("role") or "").strip().lower()
            key = (role, content.casefold())
            if not content or key in seen:
                continue
            seen.add(key)
            out.append(dict(memory))
        return out

    def _prepare_memory_context(
        self,
        direct_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Prepare evidence inside Reasoning, not inside Thalamus."""
        raw = direct_input.get("memory_context")
        context = dict(raw) if isinstance(raw, dict) else {}
        memories = [
            dict(item)
            for item in (context.get("memories") or [])
            if isinstance(item, dict)
        ]

        # Working-set turns are memory evidence. Reasoning decides whether they
        # are useful; Thalamus should not promote them into semantic structures.
        working_set = context.get("working_set")
        if isinstance(working_set, dict):
            for turn in working_set.get("turns") or []:
                if isinstance(turn, dict):
                    memories.append(dict(turn))

        # Conversation owns the dialogue act. Once it says this is an own-speech
        # question, Reasoning may request recent Monday speech as evidence.
        understanding = direct_input.get("understanding")
        understanding = understanding if isinstance(understanding, dict) else {}
        if understanding.get("intent") == "monday_speech_ask" and self.thalamus is not None:
            try:
                recent = self.thalamus.send_message(
                    "notus",
                    "get_recent",
                    {
                        "user_id": str(direct_input.get("user_id") or "default"),
                        "limit": 25,
                    },
                    source="reasoning",
                )
            except Exception:
                recent = {"status": "error"}
            if isinstance(recent, dict) and recent.get("status") == "success":
                body = self._response_content(recent)
                current_text = str(direct_input.get("user_input") or "").strip().casefold()
                for memory in body.get("memories") or []:
                    if not isinstance(memory, dict):
                        continue
                    role = str(memory.get("role") or "").strip().lower()
                    if role not in _MONDAY_ROLES:
                        continue
                    content = str(memory.get("content") or "").strip()
                    if not content or content.casefold() == current_text:
                        continue
                    item = dict(memory)
                    item["role"] = "monday"
                    memories.append(item)

        context["memories"] = self._dedupe_memories(memories)
        return context

    @staticmethod
    def _route_expression_context(
        semantic_input: Dict[str, Any],
        direct_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Attach already-owned context for Language without interpreting it."""
        out = dict(semantic_input)
        out["user_input"] = str(direct_input.get("user_input") or "")

        social = direct_input.get("social_context")
        if isinstance(social, dict) and social:
            out["social_context"] = dict(social)

        emotion = direct_input.get("emotion_result")
        emotion = emotion if isinstance(emotion, dict) else {}
        if emotion.get("emotional_tone") is not None:
            out.setdefault("emotional_tone", emotion.get("emotional_tone"))
        if emotion.get("intensity") is not None:
            out.setdefault("emotional_intensity", emotion.get("intensity"))
        if emotion.get("current_emotion") or emotion.get("emotion"):
            out.setdefault(
                "emotion",
                emotion.get("current_emotion", emotion.get("emotion", "neutral")),
            )

        representation = direct_input.get("representation_result")
        representation = representation if isinstance(representation, dict) else {}
        if representation.get("status") == "success":
            out["representation_concept_ids"] = list(
                representation.get("concept_ids") or []
            )
            out["representation_referent_ids"] = list(
                representation.get("referent_ids") or []
            )
            # Input propositions created by Language are distinct from any new
            # Reasoning propositions registered after this method returns.
            out["input_representation_proposition_ids"] = list(
                representation.get("proposition_ids") or []
            )
            if isinstance(representation.get("language_understanding"), dict):
                out["language_understanding"] = representation.get(
                    "language_understanding"
                )

        out["phase4_semantics_finalized"] = True
        out["semantic_owner"] = "reasoning"
        return out

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if message.get("type") != "think":
            return super().process_message(message)

        payload = message.get("content") if isinstance(message.get("content"), dict) else {}
        direct_input = payload.get("input") if isinstance(payload.get("input"), dict) else {}
        prepared_input = dict(direct_input)
        prepared_input["memory_context"] = self._prepare_memory_context(prepared_input)

        prepared_message = dict(message)
        prepared_payload = dict(payload)
        prepared_payload["input"] = prepared_input
        prepared_message["content"] = prepared_payload

        # DirectReasoningAdapter performs relevance/evidence/pattern/empathic
        # semantic selection. SharedRepresentationReasoningAdapter then registers
        # any grounded structures as Reasoning-owned propositions.
        result = super().process_message(prepared_message)
        if not isinstance(result, dict) or result.get("status") != "success":
            return result

        content = result.get("content")
        if not isinstance(content, dict):
            return result
        semantic_input = content.get("semantic_input")
        if not isinstance(semantic_input, dict):
            semantic_input = {}

        # Keep the exact evidence list available to Language's grounded salvage,
        # but Reasoning—not Thalamus—decides what counts as evidence.
        prepared_context = prepared_input.get("memory_context")
        if isinstance(prepared_context, dict):
            semantic_input.setdefault(
                "memory_context",
                [
                    dict(item)
                    for item in (prepared_context.get("memories") or [])
                    if isinstance(item, dict)
                ],
            )

        semantic_input = self._route_expression_context(semantic_input, prepared_input)
        content["semantic_input"] = semantic_input
        content["phase4_semantics_finalized"] = True
        result["phase4_semantics_finalized"] = True
        return result


DirectMaximumSophisticationAdapter = Phase4ReasoningAdapter

__all__ = ["Phase4ReasoningAdapter", "DirectMaximumSophisticationAdapter"]
