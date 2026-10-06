#!/usr/bin/env python3
"""One-shot Phase 5 source migration. The workflow deletes this file after applying it."""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


# ---------------------------------------------------------------------------
# Conversation: move the Phase 4 Language/SR context bridge into the native lobe.
# ---------------------------------------------------------------------------
conversation = read("conversation.py")
conversation_helper = '''    @staticmethod
    def _linguistic_context(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Carry Language-owned structure into Conversation without reinterpreting it."""
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        perception = payload.get("perception") if isinstance(payload.get("perception"), dict) else {}
        if not perception and isinstance(context.get("perception"), dict):
            perception = context.get("perception") or {}

        language_understanding = payload.get("language_understanding")
        if not isinstance(language_understanding, dict):
            language_understanding = perception.get("language_understanding")
        if not isinstance(language_understanding, dict):
            language_understanding = context.get("language_understanding")

        def _ids(name: str) -> List[str]:
            value = payload.get(name)
            if not isinstance(value, list):
                value = perception.get(name)
            if not isinstance(value, list):
                value = context.get(name)
            return [str(item) for item in (value or []) if item]

        return {
            "language_understanding": (
                language_understanding if isinstance(language_understanding, dict) else None
            ),
            "proposition_ids": _ids("proposition_ids"),
            "referent_ids": _ids("referent_ids"),
            "concept_ids": _ids("concept_ids"),
        }

'''
conversation = replace_once(
    conversation,
    "    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:\n",
    conversation_helper + "    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:\n",
    "conversation helper insertion",
)
conversation_return_old = '''            return {
                'status': 'success',
                'content': {
                    'understanding': understanding,
                    'intent': understanding.get('intent'),
                    'confidence': understanding.get('confidence'),
                    'sentiment': understanding.get('sentiment'),
                    'entities': understanding.get('entities', []),
                    'slots': understanding.get('slots', {}),
                    'ask_kind': understanding.get('ask_kind'),
                }  # Thalamus will transform this
            }
'''
conversation_return_new = '''            routed = self._linguistic_context(payload)
            if isinstance(routed.get("language_understanding"), dict):
                # Conversation owns dialogue intent/context. Language owns the
                # linguistic interpretation below; preserve it verbatim.
                understanding["language_understanding"] = routed["language_understanding"]
                understanding["representation_proposition_ids"] = routed["proposition_ids"]
                understanding["representation_referent_ids"] = routed["referent_ids"]
                understanding["representation_concept_ids"] = routed["concept_ids"]
                understanding["linguistic_context_source"] = "language_via_shared_representation"

            content = {
                'understanding': understanding,
                'intent': understanding.get('intent'),
                'confidence': understanding.get('confidence'),
                'sentiment': understanding.get('sentiment'),
                'entities': understanding.get('entities', []),
                'slots': understanding.get('slots', {}),
                'ask_kind': understanding.get('ask_kind'),
            }
            if isinstance(routed.get("language_understanding"), dict):
                content["language_understanding"] = routed["language_understanding"]
                content["proposition_ids"] = routed["proposition_ids"]
                content["referent_ids"] = routed["referent_ids"]
                content["concept_ids"] = routed["concept_ids"]
            return {'status': 'success', 'content': content}
'''
conversation = replace_once(
    conversation, conversation_return_old, conversation_return_new, "conversation native routing"
)
write("conversation.py", conversation)


# ---------------------------------------------------------------------------
# Reasoning: absorb Phase 2 SR publication + Phase 4 evidence/finalization.
# ---------------------------------------------------------------------------
reasoning = read("direct_reasoning.py")
reasoning = replace_once(
    reasoning,
    '_POISON_MARKERS = ("How it felt:", "What it meant:")\n',
    '_POISON_MARKERS = ("How it felt:", "What it meant:")\n_MERCY_ROLES = {"monday", "assistant", "abin", "mercy"}\n',
    "reasoning role constant",
)
reasoning_helpers = '''    @staticmethod
    def _response_content(response: Dict[str, Any]) -> Dict[str, Any]:
        content = response.get("content") if isinstance(response, dict) else None
        return content if isinstance(content, dict) else (response if isinstance(response, dict) else {})

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

    def _prepare_memory_context(self, direct_input: Dict[str, Any]) -> Dict[str, Any]:
        """Reasoning owns evidence preparation; Thalamus only routes Notus output."""
        raw = direct_input.get("memory_context")
        context = dict(raw) if isinstance(raw, dict) else {}
        memories = [
            dict(item)
            for item in (context.get("memories") or [])
            if isinstance(item, dict)
        ]

        working_set = context.get("working_set")
        if isinstance(working_set, dict):
            for turn in working_set.get("turns") or []:
                if isinstance(turn, dict):
                    memories.append(dict(turn))

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
                current = str(direct_input.get("user_input") or "").strip().casefold()
                for memory in body.get("memories") or []:
                    if not isinstance(memory, dict):
                        continue
                    role = str(memory.get("role") or "").strip().lower()
                    if role not in _MERCY_ROLES:
                        continue
                    content = str(memory.get("content") or "").strip()
                    if not content or content.casefold() == current:
                        continue
                    item = dict(memory)
                    item["role"] = "monday"
                    memories.append(item)

        context["memories"] = self._dedupe_memories(memories)
        return context

    @staticmethod
    def _route_expression_context(
        semantic_input: Dict[str, Any], direct_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Attach already-owned context to Reasoning's semantic handoff."""
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
            out["representation_concept_ids"] = list(representation.get("concept_ids") or [])
            out["representation_referent_ids"] = list(representation.get("referent_ids") or [])
            out["input_representation_proposition_ids"] = list(
                representation.get("proposition_ids") or []
            )
            if isinstance(representation.get("language_understanding"), dict):
                out["language_understanding"] = representation["language_understanding"]

        out["native_semantics_finalized"] = True
        out["semantic_owner"] = "reasoning"
        return out

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
        body = self._response_content(response)
        ids = body.get("concept_ids") or []
        return str(ids[0]) if isinstance(ids, list) and ids else None

    def _register_grounded_structures(
        self,
        structures: Any,
        *,
        turn_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Publish Reasoning-owned meaning to SR; SR stores but does not infer it."""
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
                subject_id = self._resolve_shared_concept(structure.get("subject"))
                object_id = self._resolve_shared_concept(
                    structure.get("object", structure.get("value"))
                )
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
            qualifiers = (
                dict(structure.get("qualifiers") or {})
                if isinstance(structure.get("qualifiers"), dict)
                else {}
            )
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
            body = self._response_content(response)
            if body.get("proposition_id") or body.get("id"):
                registered.append(dict(body))
        return registered

'''
reasoning = replace_once(
    reasoning,
    "    @staticmethod\n    def _clean_memories(memories: Any, user_input: str) -> List[Dict[str, Any]]:\n",
    reasoning_helpers + "    @staticmethod\n    def _clean_memories(memories: Any, user_input: str) -> List[Dict[str, Any]]:\n",
    "reasoning native helper insertion",
)
reasoning = replace_once(
    reasoning,
    '''        if not isinstance(direct_input, dict):
            direct_input = {}
        user_input = direct_input.get("user_input", "")
''',
    '''        if not isinstance(direct_input, dict):
            direct_input = {}
        direct_input = dict(direct_input)
        direct_input["memory_context"] = self._prepare_memory_context(direct_input)
        user_input = direct_input.get("user_input", "")
''',
    "reasoning evidence ownership",
)
reasoning = reasoning.replace(
    "        # Legacy composition can turn an evidence-free question into a word bag;\n        # that is not a conclusion. Let Thalamus use its emergency fallback.\n",
    "        # Legacy composition can turn an evidence-free question into a word bag;\n        # that is not a conclusion. Leave the semantic handoff empty.\n",
)
reasoning = replace_once(
    reasoning,
    '''        if isinstance(representation_result, dict) and representation_result.get("status") == "success":
            semantic_input["representation_concept_ids"] = list(
                representation_result.get("concept_ids") or []
            )
            semantic_input["representation_highly_active"] = list(
                representation_result.get("highly_active_concepts") or []
            )[:12]
''',
    '''        if isinstance(representation_result, dict) and representation_result.get("status") == "success":
            semantic_input["representation_concept_ids"] = list(
                representation_result.get("concept_ids") or []
            )
            semantic_input["representation_referent_ids"] = list(
                representation_result.get("referent_ids") or []
            )
            semantic_input["input_representation_proposition_ids"] = list(
                representation_result.get("proposition_ids") or []
            )
            semantic_input["representation_highly_active"] = list(
                representation_result.get("highly_active_concepts") or []
            )[:12]
            if isinstance(representation_result.get("language_understanding"), dict):
                semantic_input["language_understanding"] = representation_result[
                    "language_understanding"
                ]
''',
    "reasoning representation IDs",
)
reasoning_return_old = '''        return {
            "status": "success",
            "content": {
                "thinking": thinking,
                "semantic_input": semantic_input,
                "composed_response": thinking.get("composed_response"),
            },
        }
'''
reasoning_return_new = '''        semantic_input = self._route_expression_context(semantic_input, direct_input)
        structures = semantic_input.get("grounded_structures")
        if isinstance(structures, list) and structures:
            user_id = str(direct_input.get("user_id") or "default")
            registered = self._register_grounded_structures(
                structures,
                turn_id=str(message.get("message_id")) if message.get("message_id") else None,
                user_id=user_id,
            )
            if registered:
                semantic_input["representation_proposition_ids"] = [
                    str(item.get("proposition_id") or item.get("id"))
                    for item in registered
                    if item.get("proposition_id") or item.get("id")
                ]
                semantic_input["representation_propositions"] = registered
                semantic_input["representation_contract"] = "shared_representation_native"
                semantic_input["representation_user_id"] = user_id

        return {
            "status": "success",
            "content": {
                "thinking": thinking,
                "semantic_input": semantic_input,
                "composed_response": thinking.get("composed_response"),
                "native_semantics_finalized": True,
            },
            "native_semantics_finalized": True,
        }
'''
reasoning = replace_once(reasoning, reasoning_return_old, reasoning_return_new, "reasoning native finalization")
write("direct_reasoning.py", reasoning)


# ---------------------------------------------------------------------------
# Language: absorb comprehension/SR hydration and stop doing Reasoning's job.
# ---------------------------------------------------------------------------
language = read("language_generation.py")
language = replace_once(
    language,
    "from thalamus import get_thalamus\n",
    "from thalamus import get_thalamus\nfrom language_comprehension import LanguageComprehensionEngine\n",
    "language comprehension import",
)
language = replace_once(
    language,
    "        self.grammar = GrammarEngine()\n",
    "        self.grammar = GrammarEngine()\n        self.comprehension = LanguageComprehensionEngine()\n",
    "language comprehension engine",
)
language_helpers = '''    def _send_shared(self, msg_type: str, content: Dict[str, Any]) -> Dict[str, Any]:
        if self.thalamus is None:
            return {}
        response = self.thalamus.send_message(
            "shared_representation", msg_type, content, source="language"
        )
        return response if isinstance(response, dict) else {}

    @staticmethod
    def _response_content(response: Dict[str, Any]) -> Dict[str, Any]:
        content = response.get("content") if isinstance(response, dict) else None
        return content if isinstance(content, dict) else (response if isinstance(response, dict) else {})

    def _candidate_concepts(self, surface: str) -> List[Dict[str, Any]]:
        response = self._send_shared("lookup_surface", {"surface": surface})
        if response.get("status") != "success":
            return []
        candidates = self._response_content(response).get("candidate_concepts") or []
        return [dict(item) for item in candidates if isinstance(item, dict)]

    def _resolve_or_create_concept(
        self, surface: str, *, allow_create: bool
    ) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        candidates = self._candidate_concepts(surface)
        if len(candidates) == 1:
            cid = candidates[0].get("concept_id") or candidates[0].get("id")
            return (str(cid) if cid else None), candidates
        if len(candidates) > 1:
            return None, candidates
        if not allow_create:
            return None, []
        response = self._send_shared(
            "resolve_terms", {"terms": [surface], "activate": False}
        )
        if response.get("status") != "success":
            return None, []
        body = self._response_content(response)
        ids = list(body.get("concept_ids") or [])
        resolved = [
            dict(item)
            for item in (body.get("resolved") or [])
            if isinstance(item, dict)
        ]
        return (str(ids[0]) if ids else None), resolved

    def comprehend(
        self,
        text: str,
        *,
        user_id: str = "default",
        turn_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Language interprets text; SR only assigns IDs and stores supplied meaning."""
        understanding = self.comprehension.analyze(text)
        mentions = [
            dict(item)
            for item in understanding.get("mentions") or []
            if isinstance(item, dict)
        ]
        clauses = [
            dict(item)
            for item in understanding.get("clauses") or []
            if isinstance(item, dict)
        ]
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
            selected, candidates = self._resolve_or_create_concept(
                surface, allow_create=True
            )
            mention["candidate_concepts"] = candidates
            mention["candidate_concept_ids"] = [
                str(item.get("concept_id") or item.get("id"))
                for item in candidates
                if item.get("concept_id") or item.get("id")
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
            instance_response = self._send_shared(
                "register_instance",
                {
                    "concept_id": selected,
                    "label": mention.get("surface"),
                    "properties": {
                        "mention_id": mention_id,
                        "linguistic_kind": mention.get("kind"),
                        "quantity": mention.get("quantity"),
                        "pronoun": bool(mention.get("pronoun")),
                    },
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
                    continue
            mention["instance_id"] = None

        for clause in clauses:
            predicate_surface = str(clause.get("predicate_surface") or "").strip()
            predicate_known = bool(clause.get("predicate_known"))
            if predicate_surface:
                predicate_id, predicate_candidates = self._resolve_or_create_concept(
                    predicate_surface, allow_create=predicate_known
                )
            else:
                predicate_id, predicate_candidates = None, []
            clause["predicate_candidate_concepts"] = predicate_candidates
            clause["predicate_candidate_concept_ids"] = [
                str(item.get("concept_id") or item.get("id"))
                for item in predicate_candidates
                if item.get("concept_id") or item.get("id")
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
                        "confidence": float(
                            clause.get("confidence")
                            or understanding.get("confidence")
                            or 0.0
                        ),
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
                    continue
            clause["proposition_id"] = None

        understanding["mentions"] = mentions
        understanding["clauses"] = clauses
        understanding["unresolved_ambiguities"] = unresolved_ambiguities
        understanding["concept_ids"] = concept_ids
        understanding["referent_ids"] = referent_ids
        understanding["proposition_ids"] = proposition_ids
        understanding["representation_contract"] = "shared_representation_native"
        understanding["user_id"] = user_id
        return {
            "language_understanding": understanding,
            "resolved_concepts": list(resolved_concepts.values()),
            "concept_ids": concept_ids,
            "referent_ids": referent_ids,
            "proposition_ids": proposition_ids,
        }

    def _name_for_reference(
        self, reference_id: Any, user_id: Optional[str]
    ) -> Optional[str]:
        ref = str(reference_id or "").strip()
        if not ref:
            return None
        response = self._send_shared("get_concept", {"concept_id": ref})
        if response.get("status") == "success":
            concept = self._response_content(response)
            name = concept.get("canonical_name") or concept.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        response = self._send_shared(
            "get_instance", {"instance_id": ref, "user_id": user_id}
        )
        if response.get("status") == "success":
            instance = self._response_content(response)
            label = instance.get("label")
            if isinstance(label, str) and label.strip():
                return label.strip()
            concept_id = instance.get("concept_id")
            if concept_id:
                parent = self._send_shared("get_concept", {"concept_id": str(concept_id)})
                if parent.get("status") == "success":
                    body = self._response_content(parent)
                    name = body.get("canonical_name") or body.get("name")
                    if isinstance(name, str) and name.strip():
                        return name.strip()
        return ref

    def _structure_from_proposition(
        self, proposition_id: Any, user_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        response = self._send_shared(
            "get_proposition",
            {"proposition_id": str(proposition_id), "user_id": user_id},
        )
        if response.get("status") != "success":
            return None
        proposition = self._response_content(response)
        predicate = self._name_for_reference(proposition.get("predicate_id"), user_id)
        if not predicate:
            return None
        roles = proposition.get("roles") if isinstance(proposition.get("roles"), dict) else {}
        subject_ref = (
            roles.get("subject")
            or roles.get("agent")
            or roles.get("experiencer")
            or roles.get("theme")
        )
        object_ref = (
            roles.get("object")
            or roles.get("theme")
            or roles.get("patient")
            or roles.get("recipient")
            or roles.get("value")
        )
        subject = self._name_for_reference(subject_ref, user_id)
        obj = self._name_for_reference(object_ref, user_id)
        qualifiers = proposition.get("qualifiers") if isinstance(proposition.get("qualifiers"), dict) else {}
        provenance = proposition.get("provenance") if isinstance(proposition.get("provenance"), dict) else {}
        try:
            certainty = float(
                qualifiers.get("certainty", provenance.get("confidence", 1.0))
            )
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

    def _hydrate_shared_propositions(
        self, semantic_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not isinstance(semantic_input, dict) or self.thalamus is None:
            return semantic_input
        proposition_ids = semantic_input.get("representation_proposition_ids")
        if not isinstance(proposition_ids, list) or not proposition_ids:
            return semantic_input
        user_id = semantic_input.get("representation_user_id")
        user_id = str(user_id).strip() if user_id is not None else None
        structures: List[Dict[str, Any]] = []
        for proposition_id in proposition_ids:
            structure = self._structure_from_proposition(proposition_id, user_id)
            if isinstance(structure, dict):
                structures.append(structure)
        if structures:
            semantic_input = dict(semantic_input)
            semantic_input["grounded_structures"] = structures
            semantic_input["propositions"] = structures
            semantic_input["representation_hydrated"] = True
        return semantic_input

'''
language = replace_once(
    language,
    "    def _query_emotional_state(self) -> Dict[str, Any]:\n",
    language_helpers + "    def _query_emotional_state(self) -> Dict[str, Any]:\n",
    "language native SR/comprehension insertion",
)
# Language may normalize already-supplied structures but may not mine memory or judge evidence.
salvage_start = language.index("    def _salvage_grounded_answer(self, semantic_input: Dict[str, Any]) -> Dict[str, Any]:")
salvage_end = language.index("\n\n    def _apply_emotion_wording", salvage_start)
language_salvage = '''    def _salvage_grounded_answer(self, semantic_input: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize already-supplied semantic structures; never select memory evidence."""
        existing = semantic_input.get("grounded_structures")
        if isinstance(existing, list) and existing:
            return semantic_input
        propositions = semantic_input.get("propositions")
        if isinstance(propositions, list):
            structures = [item for item in propositions if isinstance(item, dict)]
            if structures:
                semantic_input = dict(semantic_input)
                semantic_input["grounded_structures"] = structures
                semantic_input["answer"] = ""
        return semantic_input
'''
language = language[:salvage_start] + language_salvage + language[salvage_end:]
language = replace_once(
    language,
    '''        # CRITICAL FIX: Check if this is a novelty question
''',
    '''        semantic_input = self._hydrate_shared_propositions(dict(semantic_input))

        # CRITICAL FIX: Check if this is a novelty question
''',
    "language proposition hydration",
)
language_process_old = '''        if msg_type in {'generate', 'generate_grounded'}:
            semantic_input = payload.get('semantic_input', payload)
'''
language_process_new = '''        if msg_type == 'comprehend':
            text = payload.get('text') or payload.get('user_input') or ''
            user_id = str(payload.get('user_id') or 'default')
            turn_id = payload.get('turn_id') or message.get('message_id')
            result = self.comprehend(
                str(text),
                user_id=user_id,
                turn_id=str(turn_id) if turn_id else None,
            )
            return {'status': 'success', 'content': result, **result}

        if msg_type in {'generate', 'generate_grounded'}:
            semantic_input = payload.get('semantic_input', payload)
'''
language = replace_once(language, language_process_old, language_process_new, "language comprehend route")
write("language_generation.py", language)


# ---------------------------------------------------------------------------
# Shared Representation: IDs/storage/activation only. No raw parser, no pattern discovery.
# ---------------------------------------------------------------------------
shared = read("shared_representation.py")
resolve_pattern = re.compile(
    r"    def resolve_terms\(self, terms: Sequence\[str\].*?\n    def envelope\(",
    re.S,
)
match = resolve_pattern.search(shared)
if not match:
    raise RuntimeError("shared representation resolve_terms block not found")
new_resolve = '''    def resolve_terms(self, terms: Sequence[str], *, user_id: Optional[str] = None, activate: bool = True, activate_amount: float = 1.0) -> Dict[str, Any]:
        """Assign/reuse IDs and optionally activate them; never infer relationships."""
        resolved: List[Dict[str, Any]] = []
        ids: List[str] = []
        seen: Set[str] = set()
        with self._lock:
            if activate:
                for concept in self.concepts.values():
                    concept.activation = 0.0
        for term in terms:
            concept = self.resolve_concept(str(term), create=True)
            if not concept or concept.concept_id in seen:
                continue
            seen.add(concept.concept_id)
            ids.append(concept.concept_id)
            resolved.append(concept.to_public())
        activation: Dict[str, float] = {}
        edge_count = len(self._edges_for_spread(user_id))
        if activate and ids:
            for concept_id in ids:
                for key, value in self.activate(
                    concept_id,
                    activate_amount,
                    user_id=user_id,
                    spread=True,
                ).items():
                    activation[key] = max(activation.get(key, 0.0), value)
        return {
            "status": "success",
            "resolved": resolved,
            "concept_ids": ids,
            "activation": activation,
            "highly_active_concepts": self.get_highly_active(),
            "active_concepts": [
                {"id": c.concept_id, "name": c.canonical_name, "activation": float(c.activation)}
                for c in self.get_active_concepts()
            ],
            "user_id": user_id,
            "relationship_edges": edge_count,
            "co_occurrence_edges_added": 0,
            "spread_had_edges": edge_count > 0,
        }

    def envelope('''
shared = shared[:match.start()] + new_resolve + shared[match.end():]
old_route = '''        if msg_type in {"resolve","resolve_terms","resolve_from_text"}:
            uid=content.get("user_id")
            if msg_type=="resolve_from_text" or content.get("text"): result=self.resolve_from_text(str(content.get("text") or ""),user_id=uid,extra_terms=content.get("terms") or content.get("concepts"),activate=bool(content.get("activate",True)))
            else:
                terms=content.get("terms") or content.get("concepts") or []
                if content.get("term"): terms=list(terms)+[content.get("term")]
                result=self.resolve_terms(list(terms),user_id=uid,activate=bool(content.get("activate",True)))
            env=self.envelope(result); return {"status":"success","content":env,**env}
'''
new_route = '''        if msg_type=="resolve_from_text":
            return {"status":"error","message":"raw text interpretation belongs to language","content":{}}
        if msg_type in {"resolve","resolve_terms"}:
            uid=content.get("user_id")
            if content.get("text"):
                return {"status":"error","message":"shared_representation accepts supplied terms/IDs, not raw text","content":{}}
            terms=content.get("terms") or content.get("concepts") or []
            if content.get("term"): terms=list(terms)+[content.get("term")]
            result=self.resolve_terms(list(terms),user_id=uid,activate=bool(content.get("activate",True)))
            env=self.envelope(result); return {"status":"success","content":env,**env}
'''
shared = replace_once(shared, old_route, new_route, "shared representation raw text boundary")
write("shared_representation.py", shared)


# ---------------------------------------------------------------------------
# Thalamus: remove migration-phase metadata; keep only routing diagnostics.
# ---------------------------------------------------------------------------
thalamus = read("thalamus.py")
thalamus = thalamus.replace('"phase3_language_comprehension": False,', '"language_comprehension_available": False,')
thalamus = thalamus.replace('"phase4_language_first": True,', '"language_first": True,')
thalamus = thalamus.replace('"legacy_raw_text_parser_used": False,', '"raw_text_parser_used": False,')
thalamus = thalamus.replace('"phase3_language_comprehension": isinstance(understanding, dict),', '"language_comprehension_available": isinstance(understanding, dict),')
if "phase3_" in thalamus or "phase4_" in thalamus:
    raise RuntimeError("phase-specific runtime metadata still present in thalamus.py")
write("thalamus.py", thalamus)


# ---------------------------------------------------------------------------
# Production imports: native modules only.
# ---------------------------------------------------------------------------
run_abin = read("run_abin.py")
old_imports = '''from autonomous_speech import AutonomousSpeechSystem
from phase4_conversation import Phase4ConversationSystem as ConversationSystem
from phase4_reasoning import Phase4ReasoningAdapter as DirectMaximumSophisticationAdapter
from shared_representation_phase2 import (
    LanguageGenerator,
    SharedRepresentationSystem,
)
'''
new_imports = '''from autonomous_speech import AutonomousSpeechSystem
from conversation import ConversationSystem
from direct_reasoning import DirectMaximumSophisticationAdapter
from language_generation import LanguageGenerator
from shared_representation import SharedRepresentationSystem
'''
run_abin = replace_once(run_abin, old_imports, new_imports, "run_abin native imports")
run_abin = replace_once(
    run_abin,
    "from phase4_thalamus import Phase4Thalamus as Thalamus\n",
    "from thalamus import Thalamus\n",
    "run_abin native thalamus",
)
if "phase4_" in run_abin or "shared_representation_phase2" in run_abin:
    raise RuntimeError("production still imports migration bridges")
write("run_abin.py", run_abin)


# ---------------------------------------------------------------------------
# Native tests replace phase-scaffold tests instead of hiding them from CI.
# ---------------------------------------------------------------------------
phase2_test = read("test_shared_representation_phase2.py")
phase2_test = phase2_test.replace(
    '''from shared_representation_phase2 import (
    Phase2SharedRepresentationSystem,
    SharedRepresentationLanguageGenerator,
    SharedRepresentationReasoningAdapter,
)
''',
    '''from shared_representation import SharedRepresentationSystem
from language_generation import LanguageGenerator
from direct_reasoning import DirectReasoningAdapter
''',
)
phase2_test = phase2_test.replace("Phase2SharedRepresentationSystem", "SharedRepresentationSystem")
phase2_test = phase2_test.replace("SharedRepresentationLanguageGenerator", "LanguageGenerator")
phase2_test = phase2_test.replace("SharedRepresentationReasoningAdapter", "DirectReasoningAdapter")
phase2_test = phase2_test.replace("test_phase2_", "test_native_")
write("test_shared_representation_native.py", phase2_test)
(ROOT / "test_shared_representation_phase2.py").unlink()

language_test = read("test_language_phase3.py")
language_test = re.sub(
    r"from phase3_thalamus import Phase3Thalamus as Thalamus\nfrom shared_representation_phase2 import \(\n    Phase2SharedRepresentationSystem,\n    SharedRepresentationLanguageGenerator,\n\)\n",
    "from thalamus import Thalamus\nfrom shared_representation import SharedRepresentationSystem\nfrom language_generation import LanguageGenerator\n",
    language_test,
    count=1,
)
language_test = language_test.replace("Phase2SharedRepresentationSystem", "SharedRepresentationSystem")
language_test = language_test.replace("SharedRepresentationLanguageGenerator", "LanguageGenerator")
language_test = language_test.replace("test_phase3_", "test_native_")
legacy_test_pattern = re.compile(
    r"def test_native_legacy_thalamus_resolution_path_delegates_to_language\(tmp_path\):.*?(?=\n\ndef test_native_real_thalamus_live_representation_path_uses_language)",
    re.S,
)
replacement_test = '''def test_shared_representation_rejects_raw_text_interpretation(tmp_path):
    shared, _, router = _systems(tmp_path)
    response = router.send_message(
        "shared_representation",
        "resolve_from_text",
        {"text": "Steve gave the dog a ball yesterday.", "user_id": "u1"},
        source="thalamus",
    )
    assert response["status"] == "error"
    assert "belongs to language" in response["message"]

'''
language_test, count = legacy_test_pattern.subn(replacement_test, language_test, count=1)
if count != 1:
    raise RuntimeError("obsolete language bridge test was not replaced")
language_test = language_test.replace('result["phase3_language_comprehension"] is True', 'result["language_comprehension_available"] is True')
language_test = language_test.replace('result["legacy_raw_text_parser_used"] is False', 'result["raw_text_parser_used"] is False')
write("test_language_native.py", language_test)
(ROOT / "test_language_phase3.py").unlink()

native_routing_test = '''from __future__ import annotations

import inspect
from pathlib import Path

from conversation import ConversationSystem
from direct_reasoning import DirectReasoningAdapter
from language_generation import LanguageGenerator
from shared_representation import SharedRepresentationSystem
from thalamus import Thalamus


class NoRawTextSharedRepresentation(SharedRepresentationSystem):
    def process_message(self, message):
        if message.get("type") == "resolve_from_text":
            raise AssertionError("Thalamus must never ask SR to interpret raw text")
        return super().process_message(message)


def _stack(tmp_path):
    thalamus = Thalamus()
    shared = NoRawTextSharedRepresentation(
        thalamus=thalamus, store_path=tmp_path / "shared.json"
    )
    language = LanguageGenerator(thalamus=thalamus)
    conversation = ConversationSystem(thalamus=thalamus)
    assert thalamus.register_lobe("shared_representation", shared)["status"] == "success"
    assert thalamus.register_lobe("language", language)["status"] == "success"
    assert thalamus.register_lobe("conversation", conversation)["status"] == "success"
    return thalamus, shared, language, conversation


def test_thalamus_is_native_router_not_wrapper():
    assert Thalamus.__module__ == "thalamus"
    assert Thalamus.__bases__ == (object,)


def test_language_first_then_sr_ids(tmp_path):
    thalamus, shared, _, _ = _stack(tmp_path)
    perception = {"modality": "text"}
    result = thalamus._resolve_representation_live(
        "Steve gave the dog a ball yesterday.",
        perception_payload=perception,
        user_id="u1",
    )
    assert result["status"] == "success"
    assert result["language_first"] is True
    assert result["raw_text_parser_used"] is False
    assert result["language_comprehension_available"] is True
    assert result["proposition_ids"]
    assert any(
        route.get("to") == "language" and route.get("type") == "comprehend"
        for route in thalamus.message_routes
    )
    assert not any(
        route.get("to") == "shared_representation"
        and route.get("type") == "resolve_from_text"
        for route in thalamus.message_routes
    )
    proposition = shared.get_proposition(result["proposition_ids"][0], user_id="u1")
    assert proposition is not None
    assert proposition.provenance.producer_lobe == "language"


def test_conversation_natively_receives_language_structure(tmp_path):
    thalamus, _, _, conversation = _stack(tmp_path)
    perception = {"modality": "text"}
    representation = thalamus._resolve_representation_live(
        "Steve gave the dog a ball yesterday.",
        perception_payload=perception,
        user_id="u1",
    )
    response = conversation.process_message(
        {
            "type": "understand",
            "source": "thalamus",
            "content": {
                "user_input": "Steve gave the dog a ball yesterday.",
                "user_id": "u1",
                "perception": perception,
                "language_understanding": representation["language_understanding"],
                "concept_ids": representation["concept_ids"],
                "referent_ids": representation["referent_ids"],
                "proposition_ids": representation["proposition_ids"],
            },
        }
    )
    understanding = response["content"]["understanding"]
    assert understanding["language_understanding"] == representation["language_understanding"]
    assert understanding["representation_proposition_ids"] == representation["proposition_ids"]
    assert understanding["linguistic_context_source"] == "language_via_shared_representation"


def test_reasoning_native_finalizes_semantics_and_publishes_to_sr(tmp_path):
    class QuietReasoner:
        def __init__(self, thalamus=None):
            self.thalamus = thalamus
            self.facts = {}
            self._direct_core = True
        def think_about(self, input_data):
            return {"composed_response": None, "theories": []}
        def shutdown(self):
            return None

    thalamus, _, _, _ = _stack(tmp_path)
    reasoning = DirectReasoningAdapter(thalamus=thalamus, reasoner_factory=QuietReasoner)
    thalamus.register_lobe("reasoning", reasoning)
    result = reasoning.process_message(
        {
            "type": "think",
            "message_id": "native-reasoning",
            "content": {
                "input": {
                    "user_input": "What is my favorite color?",
                    "user_id": "u1",
                    "understanding": {"intent": "question", "confidence": 0.95},
                    "memory_context": {
                        "memories": [{"role": "fact", "content": "Your favorite color is teal."}],
                        "facts": [],
                    },
                    "emotion_result": {"current_emotion": "neutral", "intensity": 0.4},
                    "representation_result": {
                        "status": "success",
                        "concept_ids": ["c_input"],
                        "referent_ids": ["i_input"],
                        "proposition_ids": ["p_input"],
                        "language_understanding": {"contract": "language_understanding_v1"},
                    },
                }
            },
        }
    )
    semantic = result["content"]["semantic_input"]
    assert semantic["native_semantics_finalized"] is True
    assert semantic["semantic_owner"] == "reasoning"
    assert semantic["representation_referent_ids"] == ["i_input"]
    assert semantic["input_representation_proposition_ids"] == ["p_input"]
    assert semantic["representation_proposition_ids"]


def test_language_does_not_select_memory_evidence():
    source = inspect.getsource(LanguageGenerator._salvage_grounded_answer)
    for forbidden in (
        "structures_from_grounded_memories",
        "answer_from_grounded_memories",
        "prose_answer_to_structures",
    ):
        assert forbidden not in source


def test_shared_representation_does_not_parse_text_or_discover_cooccurrence(tmp_path):
    shared = SharedRepresentationSystem(store_path=tmp_path / "shared.json")
    denied = shared.process_message(
        {"type": "resolve_from_text", "content": {"text": "dog chases cat"}}
    )
    assert denied["status"] == "error"
    resolved = shared.resolve_terms(["dog", "cat"], user_id="u1", activate=False)
    assert resolved["co_occurrence_edges_added"] == 0
    assert shared.get_relationships(resolved["concept_ids"][0], user_id="u1") == []


def test_thalamus_has_no_semantic_repair_or_auto_learning():
    source = inspect.getsource(Thalamus)
    for forbidden in (
        "from direct_response import",
        "relevance_score(",
        "answer_from_grounded_memories(",
        "prose_answer_to_structures(",
        "structures_from_grounded_memories(",
        "_attribute_asked(",
        "_fact_covers_attribute(",
        "response_provider.render(",
        "_auto_adapt_from_interaction(",
        "_learned_guidance_for_message(",
        "phase3_",
        "phase4_",
    ):
        assert forbidden not in source


def test_production_uses_only_native_cognitive_classes():
    import run_abin
    from run_abin import ConversationSystem as ProductionConversation
    from run_abin import DirectMaximumSophisticationAdapter as ProductionReasoning
    from run_abin import LanguageGenerator as ProductionLanguage
    from run_abin import SharedRepresentationSystem as ProductionShared
    from run_abin import Thalamus as ProductionThalamus

    assert ProductionThalamus is Thalamus
    assert ProductionConversation is ConversationSystem
    assert ProductionReasoning is DirectReasoningAdapter
    assert ProductionLanguage is LanguageGenerator
    assert ProductionShared is SharedRepresentationSystem
    source = inspect.getsource(run_abin)
    assert "phase3_thalamus" not in source
    assert "phase4_" not in source
    assert "shared_representation_phase2" not in source


def test_migration_bridge_modules_are_gone():
    root = Path(__file__).resolve().parent
    for name in (
        "phase3_thalamus.py",
        "phase4_thalamus.py",
        "phase4_conversation.py",
        "phase4_reasoning.py",
        "shared_representation_phase2.py",
    ):
        assert not (root / name).exists(), name
'''
write("test_native_routing.py", native_routing_test)
(ROOT / "test_phase4_routing.py").unlink()


# ---------------------------------------------------------------------------
# CI checks the native architecture and no longer compiles deleted bridges.
# ---------------------------------------------------------------------------
workflow = read(".github/workflows/direct-core.yml")
workflow = replace_once(
    workflow,
    "          python -m py_compile run_abin.py thalamus.py phase3_thalamus.py phase4_thalamus.py phase4_conversation.py phase4_reasoning.py direct_reasoning.py language_comprehension.py shared_representation.py shared_representation_phase2.py notus.py notus_memory.py live_notus_memory_check.py\n",
    "          python -m py_compile run_abin.py thalamus.py conversation.py direct_reasoning.py language_generation.py language_comprehension.py shared_representation.py notus.py notus_memory.py live_notus_memory_check.py\n",
    "native py_compile list",
)
workflow = replace_once(
    workflow,
    "      - name: Run Shared Representation and Phase 3-4 ownership tests\n        run: python -m pytest -q test_shared_representation_semantics.py test_shared_representation_phase2.py test_language_phase3.py test_phase4_routing.py\n",
    "      - name: Run native cognitive ownership tests\n        run: python -m pytest -q test_shared_representation_semantics.py test_shared_representation_native.py test_language_native.py test_native_routing.py\n",
    "native test list",
)
write(".github/workflows/direct-core.yml", workflow)


# Remove migration bridge modules. Historical proof text files are left untouched.
for obsolete in (
    "phase3_thalamus.py",
    "phase4_thalamus.py",
    "phase4_conversation.py",
    "phase4_reasoning.py",
    "shared_representation_phase2.py",
):
    path = ROOT / obsolete
    if not path.exists():
        raise RuntimeError(f"expected migration bridge missing before removal: {obsolete}")
    path.unlink()

# Remove this one-shot migration mechanism from the final tree.
(ROOT / ".github/workflows/phase5-migrate.yml").unlink()
Path(__file__).unlink()

print("Phase 5 native migration applied")
