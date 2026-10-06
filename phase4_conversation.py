#!/usr/bin/env python3
"""Phase 4 Conversation routing adapter.

Conversation still owns dialogue acts, intent, topic continuity, and discourse
context. Language owns linguistic interpretation. This adapter makes the
Language/Shared Representation result available to Conversation without moving
those responsibilities into Thalamus or re-parsing the sentence here.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from conversation import ConversationSystem as LegacyConversationSystem


class Phase4ConversationSystem(LegacyConversationSystem):
    """Conversation with routed Language/SR context attached to its result."""

    @staticmethod
    def _linguistic_context(payload: Dict[str, Any]) -> Dict[str, Any]:
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        perception = payload.get("perception") if isinstance(payload.get("perception"), dict) else {}
        if not perception and isinstance(context.get("perception"), dict):
            perception = context.get("perception") or {}

        language_understanding: Optional[Dict[str, Any]] = None
        direct = payload.get("language_understanding")
        if isinstance(direct, dict):
            language_understanding = direct
        elif isinstance(perception.get("language_understanding"), dict):
            language_understanding = perception.get("language_understanding")
        elif isinstance(context.get("language_understanding"), dict):
            language_understanding = context.get("language_understanding")

        proposition_ids = payload.get("proposition_ids")
        if not isinstance(proposition_ids, list):
            proposition_ids = perception.get("proposition_ids")
        if not isinstance(proposition_ids, list):
            proposition_ids = context.get("proposition_ids")

        referent_ids = payload.get("referent_ids")
        if not isinstance(referent_ids, list):
            referent_ids = perception.get("referent_ids")
        if not isinstance(referent_ids, list):
            referent_ids = context.get("referent_ids")

        concept_ids = payload.get("concept_ids")
        if not isinstance(concept_ids, list):
            concept_ids = perception.get("concept_ids")
        if not isinstance(concept_ids, list):
            concept_ids = context.get("concept_ids")

        return {
            "language_understanding": language_understanding,
            "proposition_ids": list(proposition_ids or []),
            "referent_ids": list(referent_ids or []),
            "concept_ids": list(concept_ids or []),
        }

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        result = super().process_message(message)
        if message.get("type") != "understand" or not isinstance(result, dict):
            return result
        if result.get("status") != "success":
            return result

        payload = message.get("content") if isinstance(message.get("content"), dict) else {}
        routed = self._linguistic_context(payload)
        if not isinstance(routed.get("language_understanding"), dict):
            return result

        content = result.get("content")
        if not isinstance(content, dict):
            content = {}
            result["content"] = content
        understanding = content.get("understanding")
        if not isinstance(understanding, dict):
            understanding = {}
            content["understanding"] = understanding

        # Conversation may use this context for discourse decisions, but does
        # not rewrite or reinterpret Language's linguistic structure here.
        understanding["language_understanding"] = routed["language_understanding"]
        understanding["representation_proposition_ids"] = routed["proposition_ids"]
        understanding["representation_referent_ids"] = routed["referent_ids"]
        understanding["representation_concept_ids"] = routed["concept_ids"]
        understanding["linguistic_context_source"] = "language_via_shared_representation"

        content["language_understanding"] = routed["language_understanding"]
        content["proposition_ids"] = routed["proposition_ids"]
        content["referent_ids"] = routed["referent_ids"]
        content["concept_ids"] = routed["concept_ids"]
        return result


ConversationSystem = Phase4ConversationSystem

__all__ = ["Phase4ConversationSystem", "ConversationSystem"]
