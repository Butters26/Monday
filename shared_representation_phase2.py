#!/usr/bin/env python3
"""Phase 2 bridge for Mercy's Shared Representation migration.

This module deliberately wraps the existing live Reasoning, Language, and
SharedRepresentation classes instead of rewriting them all at once.

Ownership stays explicit:
- Reasoning supplies grounded meaning it already owns.
- Shared Representation assigns/reuses concept IDs and stores transient
  propositions supplied by Reasoning. It does not infer roles or truth.
- Language consumes those proposition IDs and asks Shared Representation for a
  compatibility view before wording the answer.
- Existing grounded_structures remain as a fallback during migration.

Once all producers/consumers speak the new proposition contract natively, this
bridge can be removed without changing the underlying cognitive boundaries.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from direct_reasoning import (
    DirectMaximumSophisticationAdapter as LegacyDirectReasoningAdapter,
)
from language_generation import LanguageGenerator as LegacyLanguageGenerator
from shared_representation import SharedRepresentationSystem as LegacySharedRepresentationSystem


class Phase2SharedRepresentationSystem(LegacySharedRepresentationSystem):
    """Expose Phase 1 transient representation APIs through the lobe contract."""

    @staticmethod
    def _payload(message: Dict[str, Any]) -> Dict[str, Any]:
        content = message.get("content")
        if isinstance(content, dict):
            return content
        return {
            key: value
            for key, value in message.items()
            if key not in {"type", "message_type", "source", "message_id", "content"}
        }

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = str(message.get("type") or message.get("message_type") or "")
        content = self._payload(message)

        if msg_type == "get_candidate_concepts":
            surface = str(content.get("surface") or content.get("term") or "")
            matches = [concept.to_public() for concept in self.get_candidate_concepts(surface)]
            return {
                "status": "success",
                "content": {"surface": surface, "candidates": matches},
                "candidates": matches,
            }

        if msg_type == "lookup_surface":
            surface = str(content.get("surface") or content.get("term") or "")
            matches = self.lookup_surface(surface)
            return {
                "status": "success",
                "content": {"surface": surface, "candidates": matches},
                "candidates": matches,
            }

        if msg_type == "register_instance":
            instance = self.register_instance(
                str(content.get("concept_id") or ""),
                label=content.get("label"),
                properties=content.get("properties") if isinstance(content.get("properties"), dict) else None,
                provenance=content.get("provenance"),
                activation=content.get("activation", 1.0),
                expires_after_turn=content.get("expires_after_turn"),
            )
            if instance is None:
                return {"status": "error", "message": "could not register instance", "content": {}}
            public = instance.to_public()
            return {"status": "success", "content": public, "instance": public}

        if msg_type == "get_instance":
            instance = self.get_instance(str(content.get("instance_id") or content.get("id") or ""))
            if instance is None:
                return {"status": "error", "message": "instance not found", "content": {}}
            public = instance.to_public()
            return {"status": "success", "content": public, "instance": public}

        if msg_type == "register_proposition":
            roles = content.get("roles")
            proposition = self.register_proposition(
                str(content.get("predicate_id") or ""),
                roles if isinstance(roles, dict) else {},
                qualifiers=content.get("qualifiers") if isinstance(content.get("qualifiers"), dict) else None,
                provenance=content.get("provenance"),
                activation=content.get("activation", 1.0),
                expires_after_turn=content.get("expires_after_turn"),
            )
            if proposition is None:
                return {"status": "error", "message": "could not register proposition", "content": {}}
            public = proposition.to_public()
            return {"status": "success", "content": public, "proposition": public}

        if msg_type == "get_proposition":
            proposition = self.get_proposition(
                str(content.get("proposition_id") or content.get("id") or "")
            )
            if proposition is None:
                return {"status": "error", "message": "proposition not found", "content": {}}
            public = proposition.to_public()
            return {"status": "success", "content": public, "proposition": public}

        if msg_type == "get_active_propositions":
            try:
                threshold = float(content.get("threshold", 0.08))
            except (TypeError, ValueError):
                threshold = 0.08
            propositions = [p.to_public() for p in self.get_active_propositions(threshold)]
            return {
                "status": "success",
                "content": {"propositions": propositions},
                "propositions": propositions,
            }

        if msg_type == "expire_turn":
            expired = self.expire_turn(content.get("turn_id"))
            return {"status": "success", "content": expired, **expired}

        if msg_type == "proposition_to_grounded_structure":
            proposition_id = str(content.get("proposition_id") or content.get("id") or "")
            structure = self.proposition_to_grounded_structure(proposition_id)
            if structure is None:
                return {"status": "error", "message": "proposition not found", "content": {}}
            return {
                "status": "success",
                "content": {"grounded_structure": structure},
                "grounded_structure": structure,
            }

        return super().process_message(message)


class SharedRepresentationReasoningAdapter(LegacyDirectReasoningAdapter):
    """Publish Reasoning-owned grounded structures into Shared Representation."""

    @staticmethod
    def _surface(value: Any) -> Optional[str]:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            return text or None
        return None

    def _resolve_shared_concept(self, value: Any) -> Optional[str]:
        surface = self._surface(value)
        if not surface or self.thalamus is None:
            return None
        response = self.thalamus.send_message(
            "shared_representation",
            "resolve_terms",
            {"terms": [surface], "activate": False},
            source="reasoning",
        )
        if not isinstance(response, dict) or response.get("status") != "success":
            return None
        content = response.get("content")
        content = content if isinstance(content, dict) else response
        ids = content.get("concept_ids") or []
        return str(ids[0]) if isinstance(ids, list) and ids else None

    def _register_grounded_structures(
        self,
        structures: Any,
        *,
        turn_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not isinstance(structures, list) or self.thalamus is None:
            return []

        registered: List[Dict[str, Any]] = []
        for structure in structures:
            if not isinstance(structure, dict):
                continue

            predicate_surface = self._surface(
                structure.get("predicate") or structure.get("relation")
            )
            if not predicate_surface:
                continue
            predicate_id = self._resolve_shared_concept(predicate_surface)
            if not predicate_id:
                continue

            roles: Dict[str, str] = {}
            supplied_roles = structure.get("roles")
            if isinstance(supplied_roles, dict):
                for role, target in supplied_roles.items():
                    role_name = str(role or "").strip()
                    target_id = self._resolve_shared_concept(target)
                    if role_name and target_id:
                        roles[role_name] = target_id
            else:
                subject = structure.get("subject")
                obj = structure.get("object", structure.get("value"))
                subject_id = self._resolve_shared_concept(subject)
                object_id = self._resolve_shared_concept(obj)
                if subject_id:
                    roles["subject"] = subject_id
                if object_id:
                    roles["object"] = object_id

            if not roles:
                continue

            try:
                certainty = max(0.0, min(1.0, float(structure.get("certainty", 1.0))))
            except (TypeError, ValueError):
                certainty = 1.0
            qualifiers = dict(structure.get("qualifiers") or {}) if isinstance(
                structure.get("qualifiers"), dict
            ) else {}
            qualifiers.setdefault("certainty", certainty)

            response = self.thalamus.send_message(
                "shared_representation",
                "register_proposition",
                {
                    "predicate_id": predicate_id,
                    "roles": roles,
                    "qualifiers": qualifiers,
                    "provenance": {
                        "producer_lobe": "reasoning",
                        "source_type": "reasoning_grounded_structure",
                        "turn_id": turn_id,
                        "confidence": certainty,
                    },
                },
                source="reasoning",
            )
            if not isinstance(response, dict) or response.get("status") != "success":
                continue
            content = response.get("content")
            content = content if isinstance(content, dict) else response
            proposition_id = content.get("proposition_id") or content.get("id")
            if proposition_id:
                registered.append(dict(content))

        return registered

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        result = super().process_message(message)
        if message.get("type") != "think" or not isinstance(result, dict):
            return result
        if result.get("status") != "success":
            return result

        content = result.get("content")
        if not isinstance(content, dict):
            return result
        semantic_input = content.get("semantic_input")
        if not isinstance(semantic_input, dict):
            return result
        structures = semantic_input.get("grounded_structures")
        if not isinstance(structures, list) or not structures:
            return result

        registered = self._register_grounded_structures(
            structures,
            turn_id=str(message.get("message_id")) if message.get("message_id") else None,
        )
        if registered:
            semantic_input["representation_proposition_ids"] = [
                str(item.get("proposition_id") or item.get("id"))
                for item in registered
                if item.get("proposition_id") or item.get("id")
            ]
            semantic_input["representation_propositions"] = registered
            semantic_input["representation_contract"] = "shared_representation_phase2"
        return result


class SharedRepresentationLanguageGenerator(LegacyLanguageGenerator):
    """Consume SR proposition IDs before composing language."""

    def _hydrate_shared_propositions(self, semantic_input: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(semantic_input, dict) or self.thalamus is None:
            return semantic_input
        proposition_ids = semantic_input.get("representation_proposition_ids")
        if not isinstance(proposition_ids, list) or not proposition_ids:
            return semantic_input

        structures: List[Dict[str, Any]] = []
        for proposition_id in proposition_ids:
            response = self.thalamus.send_message(
                "shared_representation",
                "proposition_to_grounded_structure",
                {"proposition_id": str(proposition_id)},
                source="language",
            )
            if not isinstance(response, dict) or response.get("status") != "success":
                continue
            content = response.get("content")
            content = content if isinstance(content, dict) else response
            structure = content.get("grounded_structure")
            if isinstance(structure, dict):
                structures.append(structure)

        # Shared Representation becomes the live source when IDs resolve.
        # Existing grounded_structures remain untouched as a fallback if it does not.
        if structures:
            semantic_input = dict(semantic_input)
            semantic_input["grounded_structures"] = structures
            semantic_input["propositions"] = structures
            semantic_input["representation_hydrated"] = True
        return semantic_input

    def generate(self, semantic_input: Dict[str, Any]) -> str:
        semantic_input = self._hydrate_shared_propositions(
            dict(semantic_input) if isinstance(semantic_input, dict) else semantic_input
        )
        return super().generate(semantic_input)


# Keep run_abin's existing import names stable during the migration.
DirectMaximumSophisticationAdapter = SharedRepresentationReasoningAdapter
LanguageGenerator = SharedRepresentationLanguageGenerator
SharedRepresentationSystem = Phase2SharedRepresentationSystem


__all__ = [
    "Phase2SharedRepresentationSystem",
    "SharedRepresentationReasoningAdapter",
    "SharedRepresentationLanguageGenerator",
    "DirectMaximumSophisticationAdapter",
    "LanguageGenerator",
    "SharedRepresentationSystem",
]
