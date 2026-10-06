#!/usr/bin/env python3
"""Phase 2/3 bridge for Mercy's Shared Representation migration.

Phase 2 connected Reasoning → Shared Representation → Language expression.
Phase 3 adds the missing input-side Language comprehension path without
rewriting Thalamus yet.

Ownership stays explicit:
- Language determines lexical/syntactic/semantic language structure.
- Shared Representation assigns/reuses IDs and stores supplied transient
  referents/propositions. It does not infer roles or truth.
- Conversation still owns conversational intent/discourse policy.
- Reasoning still owns conclusions.
- Existing grounded_structures remain as an output compatibility fallback.

Temporary Phase 3 routing shim:
Thalamus still calls SharedRepresentation.resolve_from_text on the legacy live
path. This bridge intercepts that one legacy call and delegates the raw text to
Language.comprehend. Phase 4 can remove the shim when Thalamus routes Perception
→ Language directly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from direct_reasoning import (
    DirectMaximumSophisticationAdapter as LegacyDirectReasoningAdapter,
)
from language_comprehension import LanguageComprehensionEngine
from language_generation import LanguageGenerator as LegacyLanguageGenerator
from shared_representation import SharedRepresentationSystem as LegacySharedRepresentationSystem


class Phase2SharedRepresentationSystem(LegacySharedRepresentationSystem):
    """Native Shared Representation plus temporary Phase 3 routing shim."""

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = str(message.get("type") or message.get("message_type") or "")
        source = str(message.get("source") or "")
        content = message.get("content") if isinstance(message.get("content"), dict) else {}

        # TEMPORARY MIGRATION SHIM ONLY. Shared Representation does not parse
        # text; it delegates the legacy Thalamus raw-text call to Language.
        if (
            msg_type == "resolve_from_text"
            and source == "thalamus"
            and self.thalamus is not None
            and isinstance(content.get("text"), str)
        ):
            response = self.thalamus.send_message(
                "language",
                "comprehend",
                {
                    "text": content.get("text") or "",
                    "user_id": content.get("user_id") or "default",
                    "turn_id": message.get("message_id"),
                },
                source="shared_representation_phase3_bridge",
            )
            if isinstance(response, dict) and response.get("status") == "success":
                body = response.get("content")
                body = body if isinstance(body, dict) else response
                understanding = body.get("language_understanding")
                concept_ids = list(body.get("concept_ids") or [])
                resolved = list(body.get("resolved_concepts") or [])
                user_id = content.get("user_id") or "default"

                activation: Dict[str, float] = {}
                for concept_id in concept_ids:
                    for cid, value in self.activate(
                        str(concept_id),
                        1.0,
                        user_id=str(user_id),
                        spread=True,
                    ).items():
                        activation[cid] = max(activation.get(cid, 0.0), float(value))

                envelope = self.envelope(
                    {
                        "resolved": resolved,
                        "concept_ids": concept_ids,
                        "activation": activation,
                        "highly_active_concepts": self.get_highly_active(),
                        "active_concepts": [
                            {
                                "id": c.concept_id,
                                "name": c.canonical_name,
                                "activation": float(c.activation),
                            }
                            for c in self.get_active_concepts()
                        ],
                        "user_id": user_id,
                        "relationship_edges": len(self._edges_for_spread(str(user_id))),
                        "co_occurrence_edges_added": 0,
                        "spread_had_edges": bool(self._edges_for_spread(str(user_id))),
                    }
                )
                envelope.update(
                    {
                        "language_understanding": understanding,
                        "referent_ids": list(body.get("referent_ids") or []),
                        "proposition_ids": list(body.get("proposition_ids") or []),
                        "phase3_language_comprehension": True,
                        "legacy_raw_text_parser_used": False,
                    }
                )
                return {"status": "success", "content": envelope, **envelope}

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
    """Language expression plus Phase 3 linguistic comprehension."""

    def __init__(self, thalamus=None):
        super().__init__(thalamus=thalamus)
        self.comprehension = LanguageComprehensionEngine()

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

    def _candidate_concepts(self, surface: str) -> List[Dict[str, Any]]:
        response = self._send_shared("lookup_surface", {"surface": surface})
        if response.get("status") != "success":
            return []
        body = self._response_content(response)
        candidates = body.get("candidate_concepts") or []
        return [dict(c) for c in candidates if isinstance(c, dict)]

    def _resolve_or_create_concept(
        self,
        surface: str,
        *,
        allow_create: bool,
    ) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        candidates = self._candidate_concepts(surface)
        if len(candidates) == 1:
            cid = candidates[0].get("concept_id") or candidates[0].get("id")
            return (str(cid) if cid else None), candidates
        if len(candidates) > 1:
            # Ambiguity belongs in the result. Language must not silently pick.
            return None, candidates
        if not allow_create:
            return None, []

        response = self._send_shared(
            "resolve_terms",
            {"terms": [surface], "activate": False},
        )
        if response.get("status") != "success":
            return None, []
        body = self._response_content(response)
        ids = list(body.get("concept_ids") or [])
        resolved = [dict(c) for c in (body.get("resolved") or []) if isinstance(c, dict)]
        return (str(ids[0]) if ids else None), resolved

    def comprehend(
        self,
        text: str,
        *,
        user_id: str = "default",
        turn_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Understand language, then register supplied meaning in Shared Representation."""
        understanding = self.comprehension.analyze(text)
        mentions = [dict(m) for m in understanding.get("mentions") or [] if isinstance(m, dict)]
        clauses = [dict(c) for c in understanding.get("clauses") or [] if isinstance(c, dict)]

        resolved_concepts: Dict[str, Dict[str, Any]] = {}
        concept_ids: List[str] = []
        referent_ids: List[str] = []
        proposition_ids: List[str] = []
        mention_refs: Dict[str, str] = {}
        unresolved_ambiguities: List[Dict[str, Any]] = []

        for mention in mentions:
            mention_id = str(mention.get("mention_id") or "")
            surface = str(mention.get("concept_surface") or "").strip()
            if not mention_id or not surface:
                mention["selected_concept_id"] = None
                mention["instance_id"] = None
                continue

            selected, candidates = self._resolve_or_create_concept(surface, allow_create=True)
            mention["candidate_concepts"] = candidates
            mention["candidate_concept_ids"] = [
                str(c.get("concept_id") or c.get("id"))
                for c in candidates
                if c.get("concept_id") or c.get("id")
            ]
            mention["selected_concept_id"] = selected
            if len(candidates) > 1 and selected is None:
                unresolved_ambiguities.append(
                    {
                        "mention_id": mention_id,
                        "surface": surface,
                        "candidate_concept_ids": list(mention["candidate_concept_ids"]),
                    }
                )
                mention["instance_id"] = None
                continue
            if not selected:
                mention["instance_id"] = None
                continue

            if selected not in concept_ids:
                concept_ids.append(selected)
            for candidate in candidates:
                cid = candidate.get("concept_id") or candidate.get("id")
                if cid and str(cid) == selected:
                    resolved_concepts[selected] = candidate
                    break

            properties = {
                "mention_id": mention_id,
                "linguistic_kind": mention.get("kind"),
                "quantity": mention.get("quantity"),
                "pronoun": bool(mention.get("pronoun")),
            }
            instance_response = self._send_shared(
                "register_instance",
                {
                    "concept_id": selected,
                    "label": mention.get("surface"),
                    "properties": properties,
                    "user_id": user_id,
                    "provenance": {
                        "producer_lobe": "language",
                        "source_type": "user_utterance_linguistic_interpretation",
                        "turn_id": turn_id,
                        "confidence": float(understanding.get("confidence") or 0.0),
                    },
                },
            )
            if instance_response.get("status") == "success":
                body = self._response_content(instance_response)
                instance_id = body.get("instance_id") or body.get("id")
                if instance_id:
                    instance_id = str(instance_id)
                    mention["instance_id"] = instance_id
                    mention_refs[mention_id] = instance_id
                    referent_ids.append(instance_id)
                else:
                    mention["instance_id"] = None
            else:
                mention["instance_id"] = None

        for clause in clauses:
            predicate_surface = str(clause.get("predicate_surface") or "").strip()
            predicate_known = bool(clause.get("predicate_known"))
            predicate_id, predicate_candidates = self._resolve_or_create_concept(
                predicate_surface,
                allow_create=predicate_known,
            ) if predicate_surface else (None, [])
            clause["predicate_candidate_concepts"] = predicate_candidates
            clause["predicate_candidate_concept_ids"] = [
                str(c.get("concept_id") or c.get("id"))
                for c in predicate_candidates
                if c.get("concept_id") or c.get("id")
            ]
            clause["predicate_id"] = predicate_id
            if predicate_id and predicate_id not in concept_ids:
                concept_ids.append(predicate_id)
            for candidate in predicate_candidates:
                cid = candidate.get("concept_id") or candidate.get("id")
                if cid and str(cid) == predicate_id:
                    resolved_concepts[predicate_id] = candidate
                    break

            role_mentions = clause.get("roles") if isinstance(clause.get("roles"), dict) else {}
            shared_roles: Dict[str, str] = {}
            unresolved_roles: List[str] = []
            for role, mention_id in role_mentions.items():
                ref = mention_refs.get(str(mention_id))
                if ref:
                    shared_roles[str(role)] = ref
                else:
                    unresolved_roles.append(str(role))
            clause["shared_roles"] = shared_roles
            clause["unresolved_roles"] = unresolved_roles

            if not predicate_id or unresolved_roles or not shared_roles:
                clause["proposition_id"] = None
                continue

            qualifiers = dict(clause.get("qualifiers") or {})
            qualifiers.setdefault("linguistic_voice", clause.get("voice"))
            proposition_response = self._send_shared(
                "register_proposition",
                {
                    "predicate_id": predicate_id,
                    "roles": shared_roles,
                    "qualifiers": qualifiers,
                    "user_id": user_id,
                    "provenance": {
                        "producer_lobe": "language",
                        "source_type": "user_utterance_linguistic_interpretation",
                        "turn_id": turn_id,
                        "clause_id": clause.get("clause_id"),
                        "confidence": float(clause.get("confidence") or understanding.get("confidence") or 0.0),
                    },
                },
            )
            if proposition_response.get("status") == "success":
                body = self._response_content(proposition_response)
                proposition_id = body.get("proposition_id") or body.get("id")
                if proposition_id:
                    proposition_id = str(proposition_id)
                    clause["proposition_id"] = proposition_id
                    proposition_ids.append(proposition_id)
                else:
                    clause["proposition_id"] = None
            else:
                clause["proposition_id"] = None

        understanding["mentions"] = mentions
        understanding["clauses"] = clauses
        understanding["unresolved_ambiguities"] = unresolved_ambiguities
        understanding["concept_ids"] = concept_ids
        understanding["referent_ids"] = referent_ids
        understanding["proposition_ids"] = proposition_ids
        understanding["representation_contract"] = "shared_representation_phase3"
        understanding["user_id"] = user_id

        return {
            "language_understanding": understanding,
            "resolved_concepts": list(resolved_concepts.values()),
            "concept_ids": concept_ids,
            "referent_ids": referent_ids,
            "proposition_ids": proposition_ids,
        }

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
        subject_ref = roles.get("subject") or roles.get("agent") or roles.get("experiencer") or roles.get("theme")
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

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if message.get("type") == "comprehend":
            payload = message.get("content") if isinstance(message.get("content"), dict) else {}
            text = payload.get("text") or payload.get("user_input") or ""
            user_id = str(payload.get("user_id") or "default")
            turn_id = payload.get("turn_id") or message.get("message_id")
            result = self.comprehend(str(text), user_id=user_id, turn_id=str(turn_id) if turn_id else None)
            return {"status": "success", "content": result, **result}
        return super().process_message(message)


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
