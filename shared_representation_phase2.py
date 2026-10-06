#!/usr/bin/env python3
"""Phase 2 bridge for Mercy's Shared Representation migration.

This module deliberately wraps the existing live Reasoning and Language classes
instead of rewriting them all at once.

Ownership stays explicit:
- Reasoning supplies grounded meaning it already owns.
- Shared Representation assigns/reuses concept IDs and stores transient
  propositions supplied by Reasoning. It does not infer roles or truth.
- Language consumes those proposition IDs, resolves their shared references,
  and converts them into the existing grounded-structure compatibility shape
  before wording the answer.
- Existing grounded_structures remain as a fallback during migration.

The native SharedRepresentationSystem now owns the Phase 1/2 storage and
message APIs directly. This bridge only connects existing Reasoning/Language to
that contract; it does not duplicate Shared Representation behavior.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from direct_reasoning import (
    DirectMaximumSophisticationAdapter as LegacyDirectReasoningAdapter,
)
from language_generation import LanguageGenerator as LegacyLanguageGenerator
from shared_representation import SharedRepresentationSystem as LegacySharedRepresentationSystem


class Phase2SharedRepresentationSystem(LegacySharedRepresentationSystem):
    """Native SharedRepresentationSystem under the Phase 2 import name."""

    pass


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
        user_id: Optional[str] = None,
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
                    "user_id": user_id,
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

        payload = message.get("content") if isinstance(message.get("content"), dict) else {}
        direct_input = payload.get("input") if isinstance(payload.get("input"), dict) else {}
        user_id = direct_input.get("user_id")
        user_id = str(user_id).strip() if user_id is not None else None

        registered = self._register_grounded_structures(
            structures,
            turn_id=str(message.get("message_id")) if message.get("message_id") else None,
            user_id=user_id or None,
        )
        if registered:
            semantic_input["representation_proposition_ids"] = [
                str(item.get("proposition_id") or item.get("id"))
                for item in registered
                if item.get("proposition_id") or item.get("id")
            ]
            semantic_input["representation_propositions"] = registered
            semantic_input["representation_contract"] = "shared_representation_phase2"
            if user_id:
                semantic_input["representation_user_id"] = user_id
        return result


class SharedRepresentationLanguageGenerator(LegacyLanguageGenerator):
    """Consume Shared Representation proposition IDs before composing language."""

    def _send_shared(self, msg_type: str, content: Dict[str, Any]) -> Dict[str, Any]:
        if self.thalamus is None:
            return {}
        response = self.thalamus.send_message(
            "shared_representation",
            msg_type,
            content,
            source="language",
        )
        return response if isinstance(response, dict) else {}

    @staticmethod
    def _response_content(response: Dict[str, Any]) -> Dict[str, Any]:
        content = response.get("content")
        return content if isinstance(content, dict) else response

    def _name_for_reference(self, reference_id: Any, user_id: Optional[str]) -> Optional[str]:
        ref = str(reference_id or "").strip()
        if not ref:
            return None

        concept_response = self._send_shared("get_concept", {"concept_id": ref})
        if concept_response.get("status") == "success":
            concept = self._response_content(concept_response)
            name = concept.get("canonical_name") or concept.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()

        instance_response = self._send_shared(
            "get_instance",
            {"instance_id": ref, "user_id": user_id},
        )
        if instance_response.get("status") == "success":
            instance = self._response_content(instance_response)
            label = instance.get("label")
            if isinstance(label, str) and label.strip():
                return label.strip()
            concept_id = instance.get("concept_id")
            if concept_id:
                parent_response = self._send_shared(
                    "get_concept",
                    {"concept_id": str(concept_id)},
                )
                if parent_response.get("status") == "success":
                    parent = self._response_content(parent_response)
                    name = parent.get("canonical_name") or parent.get("name")
                    if isinstance(name, str) and name.strip():
                        return name.strip()

        return ref

    def _legacy_structure_from_proposition(
        self,
        proposition_id: Any,
        user_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        response = self._send_shared(
            "get_proposition",
            {"proposition_id": str(proposition_id), "user_id": user_id},
        )
        if response.get("status") != "success":
            return None
        proposition = self._response_content(response)

        predicate_id = proposition.get("predicate_id")
        predicate = self._name_for_reference(predicate_id, user_id)
        if not predicate:
            return None

        roles = proposition.get("roles")
        roles = roles if isinstance(roles, dict) else {}
        subject_ref = roles.get("subject") or roles.get("agent")
        object_ref = (
            roles.get("object")
            or roles.get("theme")
            or roles.get("patient")
            or roles.get("recipient")
            or roles.get("value")
        )
        subject = self._name_for_reference(subject_ref, user_id)
        obj = self._name_for_reference(object_ref, user_id)

        qualifiers = proposition.get("qualifiers")
        qualifiers = qualifiers if isinstance(qualifiers, dict) else {}
        provenance = proposition.get("provenance")
        provenance = provenance if isinstance(provenance, dict) else {}
        try:
            certainty = float(qualifiers.get("certainty", provenance.get("confidence", 1.0)))
        except (TypeError, ValueError):
            certainty = 1.0

        return {
            "subject": subject,
            "relation": predicate,
            "predicate": predicate,
            "value": obj,
            "object": obj,
            "certainty": certainty,
            "proposition_id": str(proposition.get("proposition_id") or proposition_id),
        }

    def _hydrate_shared_propositions(self, semantic_input: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(semantic_input, dict) or self.thalamus is None:
            return semantic_input
        proposition_ids = semantic_input.get("representation_proposition_ids")
        if not isinstance(proposition_ids, list) or not proposition_ids:
            return semantic_input

        user_id = semantic_input.get("representation_user_id")
        user_id = str(user_id).strip() if user_id is not None else None

        structures: List[Dict[str, Any]] = []
        for proposition_id in proposition_ids:
            structure = self._legacy_structure_from_proposition(proposition_id, user_id)
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
