#!/usr/bin/env python3
"""
Language Lobe - Monday's understanding and speech.

Understanding: language_comprehension.py (offline dictionary).
Speaking: respond() composes a meaning from the pieces in front of her and
language_builder.py builds the sentence; Reasoning reviews it. Every choice is
learned; there are no preset replies. The old grammar engine and reply path
were moved to legacy/language_generation_legacy.py (Oct 30, 2026).
"""

import json
import os
import re
import random
import time
from typing import Dict, Any, List, Optional, Tuple
from thalamus import get_thalamus
from language_comprehension import LanguageComprehensionEngine

# FIX: optional deterministic seed for reproducible output
SEED = os.environ.get("LANG_SEED")
if SEED is not None:
    try:
        random.seed(int(SEED))
        print(f"Deterministic language mode enabled (seed={SEED})")
    except Exception:
        pass


class LanguageGenerator:
    """Builds sentences from meaning - Monday's voice"""
    
    def __init__(self, thalamus=None):
        self.running = True
        self.comprehension = LanguageComprehensionEngine()
        
        # Persistent connection to Thalamus (created once at startup, reused forever)
        # Direct reference to Thalamus (NO SOCKETS)
        self.thalamus = thalamus or get_thalamus()
        
        # Cache for emotional state (avoid repeated queries)
        self.current_emotional_state = None
        self.emotion_cache_time = 0
        # Sentence builder (meaning -> sentence, always learning); one per learner.
        self._builders: Dict[str, Any] = {}

    def _builder(self, learner: str = "monday"):
        from language_builder import SentenceBuilder

        learner = (learner or "monday").strip() or "monday"
        if learner not in self._builders:
            self._builders[learner] = SentenceBuilder(learner=learner)
        return self._builders[learner]

    def express(self, meaning: Any, learner: str = "monday") -> Dict[str, Any]:
        """Build a sentence from a meaning (one dict, or a list of facts).

        Not used by the live reply path yet. Returns the sentence plus the
        record of choices that feedback needs.
        """
        builder = self._builder(learner)
        if isinstance(meaning, list):
            built = builder.build_many([m for m in meaning if isinstance(m, dict)])
        else:
            built = builder.build(meaning if isinstance(meaning, dict) else {})
        return built.to_dict()

    def express_feedback(self, record: Dict[str, Any], good: bool, reason: str = "") -> Dict[str, Any]:
        """Learn from a judgment of a sentence that express() built."""
        from language_builder import Built

        built = Built.from_dict(record if isinstance(record, dict) else {})
        return self._builder(built.learner).feedback(built, bool(good), str(reason or ""))
    
    def _send_shared(self, msg_type: str, content: Dict[str, Any]) -> Dict[str, Any]:
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

    def _query_emotional_state(self) -> Dict[str, Any]:
        """Query current emotional state from Emotional Engine"""
        try:
            # Only query every 1 second to avoid overhead
            current_time = time.time()
            if self.current_emotional_state and (current_time - self.emotion_cache_time) < 1.0:
                return self.current_emotional_state
            
            result = self.thalamus.send_message(
                destination='emotion',
                msg_type='get_emotional_state',
                content={},
                source='language'
            )
            
            if result and result.get('status') == 'success':
                self.current_emotional_state = result.get('content', {})
                self.emotion_cache_time = current_time
                return self.current_emotional_state
            
            return {}
        except Exception as e:
            print(f"⚠️  Failed to query emotional state: {e}")
            return {}
    
    
    # ------------------------------------------------------------------
    # Reply: Language decides what Monday means and builds the sentence;
    # Reasoning reviews it and says why when it doesn't make sense; Language
    # redoes it. Silence is only ever her choice, and is reported as such.
    # ------------------------------------------------------------------

    MAX_REPLY_ATTEMPTS = 10
    GREETING_SENSE = "oewn-06645018-n"  # dictionary sense: "an expression of greeting"

    def generate(self, semantic_input: Dict[str, Any]) -> str:
        """Build Monday's reply for this turn."""
        result = self.respond(semantic_input if isinstance(semantic_input, dict) else {})
        return result["sentence"]

    def _ask(self, lobe: str, msg_type: str, content: Dict[str, Any]) -> Dict[str, Any]:
        if self.thalamus is None:
            return {}
        response = self.thalamus.send_message(lobe, msg_type, content, source="language")
        if not isinstance(response, dict) or response.get("status") != "success":
            return {}
        body = response.get("content")
        return body if isinstance(body, dict) else {}

    @staticmethod
    def _trace(kind: str, **data: Any) -> None:
        try:
            from trace_monitor import trace_event
            trace_event(kind, **data)
        except Exception:
            pass

    # ---- who he / she / it / they mean ------------------------------------
    def _resolve_references(self, reading: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        from language_references import PeopleBeliefs, resolve
        beliefs = self.__dict__.get("_people_beliefs")
        if beliefs is None:
            path = self.__dict__.get("people_beliefs_path")
            if path is None:
                try:
                    from runtime_paths import runtime_file
                    path = runtime_file("language_people.json")
                except Exception:
                    path = None
            beliefs = self.__dict__["_people_beliefs"] = PeopleBeliefs(path)
        people = payload.get("people") if isinstance(payload.get("people"), dict) else {}
        context = [str(line) for line in payload.get("context") or [] if str(line).strip()]
        return resolve(reading, context, {str(k): list(v or []) for k, v in people.items()},
                       self.comprehension.analyze, beliefs, str(payload.get("user_id") or "default"))

    _POSSESSIVE_PRONOUNS = {"his", "her", "its", "their"}

    def _resolved_text(self, text: str, user_id: str) -> str:
        """His line with he/she/it/they replaced by who they mean, where Language
        is sure ("what is her dog's name?" -> "what is Ariana's dog's name?")."""
        reading = self.comprehension.analyze(text)
        if not any(str(t.get("surface") or "").casefold() in
                   {"he", "him", "his", "she", "her", "it", "its", "they", "them", "their"}
                   for t in reading.get("tokens") or []):
            return text
        context = self._ask("notus", "reading_context", {"text": text, "user_id": user_id})
        if not isinstance(context.get("context"), list):
            return text
        reading = self._resolve_references(reading, {**context, "user_id": user_id})
        words = [str(t.get("surface") or "") for t in reading.get("tokens") or []]
        as_written = self.comprehension.tokenize(text)
        if len(as_written) == len(words):
            words = list(as_written)  # keep his spelling ("Texas", not "texas")
        for ref in reading.get("references") or []:
            idx = ref.get("index")
            if not ref.get("sure") or not ref.get("label") or not isinstance(idx, int) or idx >= len(words):
                continue  # ("it rains": a placeholder "it" means nothing; it stays "it")
            label = str(ref.get("label") or "")  # in his own words ("my brother")
            nxt = words[idx + 1].casefold() if idx + 1 < len(words) else ""
            name = str((ref.get("refers_to") or {}).get("name") or "")
            if name and ref.get("pronoun") in self._POSSESSIVE_PRONOUNS and nxt in ("name", "names"):
                # "what is his name?" after "my dog is named Rex": Rex is the name; it
                # asks about the one with that name, his dog.
                named = [f for f in self._user_facts(name, user_id) if str(f.get("object") or "") == name
                         and str(f.get("subject") or "") == "user" and str(f.get("predicate") or "").isalpha()]
                if named:
                    label = "my " + str(named[-1]["predicate"]).replace("_", " ")
            words[idx] = label + ("'s" if ref.get("pronoun") in self._POSSESSIVE_PRONOUNS else "")
        out = " ".join(w for w in words if w)
        return re.sub(r"\s+([?.!,])", r"\1", out)

    # ---- on the team: hear social context's read of each moment -----------
    def on_joined(self, name: str) -> None:
        listen = getattr(self.thalamus, "listen", None)
        if callable(listen):
            listen(name, "social_read")

    def _hear_social(self, read: Dict[str, Any]) -> Dict[str, Any]:
        self.__dict__.setdefault("_social_reads", {})[str(read.get("user_id") or "default")] = dict(read)
        return {"status": "success", "content": {"heard": True}}

    def _social_for(self, user_id: str, user_input: str) -> Dict[str, Any]:
        read = (self.__dict__.get("_social_reads") or {}).get(user_id) or {}
        return read if str(read.get("said") or "").strip() == user_input.strip() else {}

    # His words for the two of them, turned to her side.
    _TURN = {"i": {"ref": "addressee"}, "me": {"ref": "addressee"}, "myself": {"ref": "addressee"},
             "you": {"ref": "speaker"},
             # "we" said by him is him and her: said back, still both of them.
             "we": {"group": [{"ref": "addressee"}, {"ref": "speaker"}], "count": "many"},
             "us": {"group": [{"ref": "addressee"}, {"ref": "speaker"}], "count": "many"},
             "he": {"pronoun": "he"}, "him": {"pronoun": "he"}, "she": {"pronoun": "she"},
             "her": {"pronoun": "she"}, "it": {"pronoun": "it"}, "they": {"pronoun": "they"},
             "them": {"pronoun": "they"}}
    _OWNER = {"my": {"ref": "addressee"}, "our": {"group": [{"ref": "addressee"}, {"ref": "speaker"}],
                                                    "count": "many"}, "your": {"ref": "speaker"},
              "his": {"pronoun": "he"}, "her": {"pronoun": "she"}, "their": {"pronoun": "they"},
              "its": {"pronoun": "it"}}

    def _mention_entity(self, mention: Dict[str, Any], tokens: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Who or what a mention in his sentence is, as she'd say it."""
        if not isinstance(mention, dict):
            return None
        if mention.get("refers_to"):
            ref = mention["refers_to"]
            if ref.get("name") or ref.get("names"):
                name = ref.get("name") or " and ".join(ref["names"])
                return {"name": name, "count": "many"} if ref.get("names") else {"name": name}
        start, end = mention.get("start"), mention.get("end")
        inside = [t for t in tokens if isinstance(start, int) and isinstance(end, int)
                  and start <= int(t.get("index", -1)) < end and t.get("kind") != "temporal"]
        if any(str(t.get("surface") or "").casefold() == "and" for t in inside) \
                and not all(t.get("kind") in ("proper_noun", "conjunction") for t in inside):
            # "me and you", "my sister and I": each of them, together.
            groups, group = [], []
            for t in inside:
                if str(t.get("surface") or "").casefold() == "and":
                    groups.append(group)
                    group = []
                else:
                    group.append(t)
            groups.append(group)
            members = []
            for g in groups:
                if not g:
                    continue
                one = self._mention_entity({"start": g[0].get("index"), "end": int(g[-1].get("index", 0)) + 1,
                                            "pronoun": len(g) == 1 and g[0].get("kind") == "pronoun",
                                            "surface": " ".join(str(t.get("surface") or "") for t in g)}, tokens)
                if not one:
                    return None
                members.append(one)
            return {"group": members, "count": "many"} if len(members) > 1 else (members[0] if members else None)
        if mention.get("pronoun"):
            word = str((mention.get("properties") or {}).get("pronoun") or mention.get("surface") or "").casefold()
            return dict(self._TURN.get(word) or {}) or None
        names = [t for t in inside if t.get("kind") == "proper_noun"]
        if names:
            words = [str(t.get("surface") or "") for t in names]
            name = " and ".join(w[:1].upper() + w[1:] for w in words)
            return {"name": name, "count": "many"} if len(words) > 1 else {"name": name}
        prep_at = next((n for n, t in enumerate(inside) if n and t.get("kind") == "preposition"), None)
        rest = []
        if prep_at is not None and not any(t.get("kind") == "verb" for t in inside[prep_at:]):
            # "the dog in the yard": the dog, where it is said after it.
            inside, rest = inside[:prep_at], inside[prep_at:]
        nouns = [t for t in inside if t.get("kind") == "noun"]
        if not nouns:
            return None
        head = nouns[-1]
        surface, lemma = str(head.get("surface") or ""), str(head.get("lemma") or "")
        entity: Dict[str, Any] = {"noun": lemma.casefold()}
        adjectives = [str(t.get("lemma") or "").casefold() for t in inside if t.get("kind") == "adjective"]
        if adjectives:
            entity["adjectives"] = adjectives
        first = str(inside[0].get("surface") or "").casefold() if inside else ""
        if first in self._OWNER:
            entity["owner"] = dict(self._OWNER[first])
        elif inside and inside[0].get("kind") == "possessive":
            owner = str(inside[0].get("lemma") or "")
            entity["owner"] = {"name": owner[:1].upper() + owner[1:]}
        elif first == "the":
            entity["definite"] = True
        many = surface.casefold() != lemma.casefold() and surface.casefold().endswith("s")
        entity["count"] = "many" if many else ("one" if first in ("a", "an") or entity.get("owner")
                                               or entity.get("definite") else "mass")
        if first in ("a", "an"):
            entity["definite"] = False
        if len(rest) > 1:
            where = self._mention_entity({"start": rest[1].get("index"), "end": int(rest[-1].get("index", 0)) + 1,
                                          "surface": " ".join(str(t.get("surface") or "") for t in rest[1:])}, tokens)
            if where:
                entity["modifiers"] = [{"prep": str(rest[0].get("surface") or "").casefold(), "object": where}]
        after_head = inside[inside.index(head) + 1:]
        if after_head and after_head[0].get("kind") == "preposition" and any(t.get("kind") == "verb" for t in after_head):
            # "a lot to work on", "someone to talk to": what it's for stays with it.
            entity["tail"] = " ".join(str(t.get("surface") or "") for t in after_head)
        # How many, as he said it: "7 dogs", "2 more dogs", "one dog".
        from reasoning_engine import number_in
        at = next((n for n, t in enumerate(inside) if t is not head and (
            t.get("kind") == "number" or (t.get("kind") == "noun"
                                          and number_in(str(t.get("surface") or "")) is not None))), None)
        if at is not None:
            words = [str(t.get("surface") or "") for t in inside[at:inside.index(head)]]
            entity["number"] = " ".join(words)
            entity.pop("adjectives", None) if set(entity.get("adjectives") or []) <= set(words) else None
            entity["count"] = "one" if number_in(words[0]) == 1 else "many"
        return entity

    def _statement_meaning(self, reading: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """His sentence as a whole meaning, from her side: who, did what, to
        what, when, whether not, and how sure. Language reads it; nothing here
        is a sentence shape."""
        if not reading or reading.get("speech_act") not in ("declarative", "statement", None):
            return None
        clauses = reading.get("clauses") or []
        if not clauses:
            return None
        clause = clauses[0]
        roles = clause.get("roles") or {}
        tokens = [t for t in reading.get("tokens") or [] if isinstance(t, dict)]
        mentions = {m.get("mention_id"): m for m in reading.get("mentions") or [] if isinstance(m, dict)}
        copular = bool(clause.get("copular"))
        subject_id = (roles.get("theme") or roles.get("agent")) if copular else (
            roles.get("agent") or roles.get("experiencer") or roles.get("theme"))
        subject = self._mention_entity(mentions.get(subject_id), tokens)
        if not subject:
            return None
        meaning: Dict[str, Any] = {"subject": subject, "act": "state", "_purpose": "say_back"}
        complement = reading.get("predicative_complement") or clause.get("predicative_complement") or {}
        if copular:
            # "we will stay home", "she seems happy": the linking verb he used stays.
            linking = str(clause.get("predicate_surface") or "").casefold()
            linking_verb = any(str(t.get("surface") or "").casefold() == linking and t.get("kind") == "verb"
                               for t in tokens)
            # ("I am so happy": "happy" is what he is, not a linking verb.)
            meaning["verb"] = linking if linking and linking != "be" and linking.isalpha() and linking_verb \
                and linking != str(complement.get("lemma") or "").casefold() else "be"
            if complement.get("kind") == "adjective" and complement.get("lemma"):
                meaning["complement"] = {"adjectives": [str(complement["lemma"]).casefold()]}
            else:
                target = self._mention_entity(mentions.get(complement.get("mention_id") or roles.get("attribute")), tokens)
                if not target:
                    return None
                meaning["complement"] = {"entity": target} if target.get("name") or target.get("owner") else \
                    {"noun": target["noun"], "definite": False, "adjectives": target.get("adjectives") or []}
        else:
            verb = str(clause.get("predicate_surface") or "").casefold()
            if not verb or verb in ("be",):
                return None
            meaning["verb"] = verb
            verb_token = next((t for t in tokens if t.get("kind") == "verb" and t.get("phrase")
                               and str(t.get("lemma") or "").casefold() == verb), None) or next(
                (t for t in tokens if t.get("kind") == "verb" and t.get("phrase")
                 and (verb in str(t["phrase"]).split()[1:] or any(
                     str(u.get("lemma") or "").casefold() == verb and str(u.get("surface") or "").casefold()
                     in str(t["phrase"]).split()[1:] for u in tokens))), None)  # "got married": get married
            particle = ""
            inside: set = set()
            if verb_token:
                verb = str(verb_token.get("lemma") or verb).casefold()
                if not meaning.get("verb") or str(verb_token["phrase"]).split()[0] == verb:
                    meaning["verb"] = verb
            if verb_token and str(verb_token["phrase"]).split()[0] == verb:
                # "gave up", "work on", "kicked the bucket": the phrase is the action.
                meaning["verb"] = str(verb_token["phrase"])
                words = str(verb_token["phrase"]).split()
                particle = words[-1] if len(words) == 2 else ""
                start = int(verb_token.get("index", -99))
                inside = {mid for mid, m in mentions.items()
                          if isinstance(m.get("start"), int) and start < m["start"] < start + len(words)}
                roles = {r: mid for r, mid in roles.items() if mid not in inside}
            other = next((roles[r] for r in ("theme", "patient") if roles.get(r) and roles[r] != subject_id), None)
            if other:
                target = self._mention_entity(mentions.get(other), tokens)
                if target:
                    meaning["object"] = target
            mods = []
            for role, mention_id in roles.items():
                if role.startswith("prep_"):
                    target = self._mention_entity(mentions.get(mention_id), tokens)
                    if target and particle and role[5:] == particle and "object" not in meaning:
                        meaning["object"] = target  # "work on cars": cars is what's worked on
                    elif target:
                        mods.append({"prep": role[5:], "object": target})
            if mods:
                meaning["modifiers"] = mods
        if (clause.get("qualifiers") or {}).get("polarity") == "negative":
            meaning["negated"] = True
        if meaning.get("verb") and meaning["verb"] != "be":
            meaning["_word_chosen"] = True  # his own verb, as he said it
        if reading.get("tense") in ("past", "future"):
            meaning["tense"] = reading["tense"]
            heard_verb = next((str(t.get("surface") or "") for t in tokens if t.get("kind") == "verb"
                               and str(t.get("lemma") or "").casefold() == meaning.get("verb")), "")
            if reading["tense"] == "past" and heard_verb and heard_verb != meaning.get("verb"):
                meaning["past_form"] = heard_verb  # "worked", as he said it
        if reading.get("modal"):
            meaning["modal"] = reading["modal"]
        how = [str(t.get("surface") or "") for t in tokens if t.get("read_as") == "how, after the action"]
        if how:
            meaning["how"] = " ".join(how)  # "you didn't sleep well"
        when = str((clause.get("qualifiers") or {}).get("event_time_text") or "").strip()
        if when:
            meaning["when"] = self._from_her_side(when)  # "last time", "this morning"
        sure = (reading.get("certainty") or {}).get("sure")
        if isinstance(sure, (int, float)) and sure < 0.9:
            meaning["hedge"] = "maybe" if sure < 0.6 else "probably"
        return meaning

    def _meaning_from_words(self, words: str) -> Optional[Dict[str, Any]]:
        """Words social context believes fit ("you're welcome", "it's okay")
        turned into a meaning she can say: Language reads them like any words."""
        reading = self.comprehension.analyze(words)
        tokens = [t for t in reading.get("tokens") or [] if t.get("kind") != "punctuation"]
        if not tokens:
            return None
        who = {"you": {"ref": "addressee"}, "i": {"ref": "speaker"}, "me": {"ref": "speaker"},
               "it": {"pronoun": "it"}, "we": {"pronoun": "we"}, "they": {"pronoun": "they"}}
        subject = who.get(str(tokens[0].get("lemma") or "").casefold())
        complement = reading.get("predicative_complement") or {}
        if subject and complement.get("kind") == "adjective" and complement.get("lemma"):
            return {"subject": subject, "verb": "be", "act": "state", "_purpose": "social_reply",
                    "complement": {"adjectives": [str(complement["lemma"]).casefold()]}}
        # Not a sentence she can build ("no problem", "me too"): she says it the
        # way she was taught it, as a whole.
        return {"act": "phrase", "words": words, "_purpose": "social_reply"}

    def _tell_emotion(self, failed: bool, used_memory: bool, social_move: bool = False) -> None:
        """Whether she managed to say something is part of how she feels."""
        tell = getattr(self.thalamus, "tell", None)
        if callable(tell):
            try:
                tell("emotion", "reply_outcome", {"failed": failed, "used_memory": used_memory,
                                                  "social_move": social_move}, "language")
            except Exception:
                pass

    @staticmethod
    def _fact_key(meaning: Dict[str, Any]) -> Tuple[str, str, str]:
        fact = meaning.get("_fact") if isinstance(meaning.get("_fact"), dict) else {}
        return (str(fact.get("subject")), str(fact.get("predicate")), str(fact.get("object")))

    @classmethod
    def _his_words(cls, pieces: Any, out: Optional[set] = None) -> set:
        """(part of speech, word) for every word in what he said and what she
        remembers him saying."""
        out = out if out is not None else set()
        if isinstance(pieces, dict):
            for key, value in pieces.items():
                if key == "noun" and isinstance(value, str):
                    out.add(("n", value.casefold()))
                elif key == "verb" and isinstance(value, str):
                    out.add(("v", value.casefold()))
                elif key == "adjectives" and isinstance(value, list):
                    out.update(("a", str(a).casefold()) for a in value if isinstance(a, str))
                elif key in ("heard_verb",) and isinstance(value, list):
                    out.update(("v", str(v).casefold()) for v in value if isinstance(v, str))
                elif key in ("heard_adjective",) and isinstance(value, list):
                    out.update(("a", str(a).casefold()) for a in value if isinstance(a, str))
                elif not str(key).startswith("_") and isinstance(value, (dict, list)):
                    cls._his_words(value, out)
        elif isinstance(pieces, list):
            for item in pieces:
                cls._his_words(item, out)
        return out

    def _situation(self, semantic_input: Dict[str, Any]) -> str:
        understanding = semantic_input.get("language_understanding") or {}
        user_id = str(understanding.get("user_id") or semantic_input.get("user_id") or "default")
        heard = self._social_for(user_id, str(semantic_input.get("user_input") or understanding.get("raw_text") or ""))
        social = semantic_input.get("social_context") or {}
        expects = heard.get("expects") or social.get("expects")
        if expects == "greeting":
            return "greeting"
        if expects == "goodbye":
            return "farewell"
        if heard.get("expected_reply") or social.get("expected_reply"):
            return "social_reply"
        # Greetings and goodbyes are Social Context's call (above). When it has
        # no read, what his words mean still counts: the dictionary files "good
        # night" as an expression of farewell, "good morning" as a greeting.
        said = re.sub(r"[^a-z' ]", "", str(semantic_input.get("user_input") or "").casefold()).strip()
        if said and len(said.split()) <= 3 and not heard.get("expects") and not social.get("expects"):
            try:
                from lexicon.oewn_offline import get_wordnet
                senses = list(get_wordnet().synsets(said, pos="n"))[:1]
            except Exception:
                senses = []
            for x in senses:
                above = {str(h.id) for h in x.hypernyms()} | {str(x.id)}
                if self._GREETING_FAMILY & above:
                    return "greeting"
                if self._FAREWELL_FAMILY & above:
                    return "farewell"
        social_now = social.get("last_cue") if social.get("is_social_turn") else None
        if understanding.get("speech_act") == "question" or str(semantic_input.get("user_input", "")).strip().endswith("?"):
            return "question"
        # He is the one feeling it ("I", "me"); "my" is about something of his ("my favorite color").
        about_self = any(
            str(t.get("lemma") or t.get("surface") or "").casefold() in {"i", "me", "myself"}
            for t in understanding.get("tokens") or []
        )
        # A feeling counts as shared only when Language reads it as about him (I / me),
        # even if Social Context flags an emotional share.
        if about_self and (social_now == "emotional_share" or (understanding.get("affect") or {}).get("present")):
            return "emotional_share"
        return "statement"

    def _facts_for_this(self, text: str, user_id: str) -> List[Dict[str, Any]]:
        """What memory brings up, the ones that share the most of his words
        first ("do I like tea?" -> the tea fact before the cats one), newest
        first among equals ("where did I go?" -> the latest trip)."""
        facts = self._user_facts(text, user_id)
        reading = self.comprehension.analyze(text)
        his = {str(t.get("lemma") or "").casefold() for t in reading.get("tokens") or []
               if t.get("kind") in ("noun", "proper_noun", "verb", "adjective", "possessive")}
        # Who he's asking about: "am I tired?" -> him; "is Kate tired?" -> Kate.
        who = ""
        for t in reading.get("tokens") or []:
            if t.get("kind") == "pronoun" and str(t.get("lemma")).casefold() in ("i", "me", "my"):
                who = "user"
                break
            if t.get("kind") == "proper_noun":
                who = str(t.get("surface") or "").casefold()
                break
        def shared(fact: Dict[str, Any]) -> int:
            words = set(re.findall(r"[a-z]+", " ".join(str(fact.get(k) or "") for k in
                                                       ("subject", "predicate", "object")).casefold()))
            words |= {w[:-1] for w in words if w.endswith("s")}
            predicate = str(fact.get("predicate") or "")
            if "v:" in predicate:
                # "drove" counts as going: the dictionary's more general verbs.
                from direct_notus import DirectNotusProcess
                words |= set(DirectNotusProcess._verb_kinds(predicate.split("v:", 1)[1].split("@", 1)[0]))
            subject = str(fact.get("subject") or "").casefold()
            about_them = 2 if who and subject == who else (1 if who and subject.startswith(who + "'s") else 0)
            # "what is my dog named?" asks for a name: a fact that is one comes first.
            name = 2 if his & {"name", "named", "call", "called"} and str(fact.get("object") or "")[:1].isupper() else 0
            return len(his & words) + about_them + name
        return sorted(facts, key=lambda f: (shared(f), int(f.get("id") or 0)), reverse=True)

    def _user_facts(self, query: str, user_id: str) -> List[Dict[str, Any]]:
        body = self._ask("notus", "query_facts", {"query": query, "user_id": user_id, "limit": 10})
        return [f for f in body.get("facts") or [] if isinstance(f, dict)]

    @staticmethod
    def _entity_for(text: str) -> Dict[str, Any]:
        """Who/what a filed fact is about, as a meaning: "user" is him,
        "monday" is her, "user's brother" is his brother, a name is a name."""
        t = (text or "").strip()
        low = t.casefold()
        if " and " in t and not all(m.strip()[:1].isupper() for m in t.split(" and ")):
            # "user's sister and user": both of them ("you and your sister").
            return {"group": [LanguageGenerator._entity_for(m) for m in t.split(" and ") if m.strip()],
                    "count": "many"}
        if low in ("user", "i", "me", ""):
            return {"ref": "addressee"}
        if low == "monday":
            return {"ref": "speaker"}
        if "'s " in t:
            owner, thing = t.split("'s ", 1)
            return {"noun": thing.strip().casefold(), "owner": LanguageGenerator._entity_for(owner)}
        if t[:1].isupper():
            # "Ariana and Cleo" are two: they take "are".
            return {"name": t, "count": "many"} if " and " in t else {"name": t}
        words = low.split()
        # As he said it: "a castle", "the sword", "rain" (no article: uncountable or many).
        if len(words) > 1 and words[0] in ("a", "an"):
            return {"noun": " ".join(words[1:]), "definite": False, "count": "one"}
        if len(words) > 1 and words[0] == "the":
            noun, count = LanguageGenerator._number_of(" ".join(words[1:]))
            return {"noun": noun, "definite": True, "count": count}
        from reasoning_engine import number_in
        if len(words) > 1 and number_in(words[0]) is not None:
            # "7 dogs", "2 more dogs": how many, then what.
            noun, _ = LanguageGenerator._number_of(words[-1])
            return {"noun": noun, "number": " ".join(words[:-1]),
                    "count": "one" if number_in(words[0]) == 1 else "many"}
        noun, count = LanguageGenerator._number_of(low)
        return {"noun": noun, "count": "many" if count == "many" else "mass"}

    @staticmethod
    def _from_her_side(words: str) -> str:
        """His words said back by her: what he said about himself is about
        "you", what he said about her is about "I" ("when I was a kid" ->
        "when you were a kid")."""
        out: List[str] = []
        said = words.split()
        for i, word in enumerate(said):
            low = word.casefold()
            before = said[i - 1].casefold() if i else ""
            if low in ("i", "me"):
                out.append("you")
            elif low == "you":
                nxt = said[i + 1].casefold() if i + 1 < len(said) else ""
                out.append("I" if nxt and nxt not in ("and", "or") and i + 1 < len(said) else "me")
            elif low in ("my", "mine", "myself"):
                out.append({"my": "your", "mine": "yours", "myself": "yourself"}[low])
            elif low in ("your", "yours", "yourself"):
                out.append({"your": "my", "yours": "mine", "yourself": "myself"}[low])
            elif low in ("am", "was") and before == "i":
                out.append({"am": "are", "was": "were"}[low])
            elif low in ("are", "were") and before == "you":
                out.append({"are": "am", "were": "was"}[low])
            else:
                out.append(word)
        return " ".join(out)

    @staticmethod
    def _number_of(phrase: str) -> Tuple[str, str]:
        """("kid", "many") for "kids": the dictionary's base word is shorter, so
        he meant more than one. The last word of the phrase decides."""
        words = phrase.split()
        if not words:
            return phrase, "one"
        last = words[-1]
        try:
            from lexicon.oewn_offline import lemma_and_pos_candidates
            bases = {str(c.get("lemma")) for c in lemma_and_pos_candidates(last) if c.get("pos") == "n"
                     and str(c.get("lemma")) == str(c.get("lemma")).lower()}  # not CAT the scan
        except Exception:
            bases = set()
        if last in bases:
            bases = set()  # the word is a base word itself ("news", "glasses")
        base = next((b for b in bases if b != last), None)
        if base and last.endswith("s"):
            return " ".join(words[:-1] + [base]), "many"
        return phrase, "one"

    @staticmethod
    def _owner_for(subject: str) -> Dict[str, Any]:
        sub = (subject or "").strip()
        if sub.casefold() in {"user", "i", "me", ""}:
            return {"ref": "addressee"}
        return {"name": sub}

    @staticmethod
    def _said_today(fact: Dict[str, Any]) -> bool:
        import datetime as _dt
        when = str(fact.get("created_at") or "")
        try:
            said = _dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            return False
        now = _dt.datetime.now(said.tzinfo) if said.tzinfo else _dt.datetime.now()
        return said.date() == now.date()

    @staticmethod
    def _how_it_was_said(meaning: Dict[str, Any], fact: Dict[str, Any]) -> None:
        """Keep a fact's tense, its "can", and how sure he was: "I went" stays
        past, "I can swim" keeps can, "maybe Lily is sick" keeps maybe."""
        if fact.get("tense") in ("past", "future"):
            meaning["tense"] = fact["tense"]
        value = str(fact.get("value") or "")
        if value.startswith("said:") and fact.get("tense") == "past":
            meaning["past_form"] = value[5:]  # "worked", as he said it
        if fact.get("modal"):
            meaning["modal"] = str(fact["modal"])
        sure = fact.get("sure")
        if isinstance(sure, (int, float)) and sure < 0.9:
            meaning["hedge"] = "maybe" if sure < 0.6 else "probably"
        when = str(fact.get("when_said") or "").strip()
        if when and when.split()[0].casefold() in ("when", "after", "before", "while", "since", "until", "once"):
            # "when I was a kid": true whenever it's said, in her words ("when you were a kid").
            meaning["when"] = LanguageGenerator._from_her_side(when)
        elif when and LanguageGenerator._said_today(fact):
            # "yesterday" is only still true the day he said it.
            meaning["when"] = when
        because = str(fact.get("because") or "").strip()
        if because:
            meaning["_because_text"] = because  # turned into a meaning by Language when used

    def _fact_meaning(self, fact: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Turn a stored fact (subject / predicate / object) into a meaning to say."""
        pred = str(fact.get("predicate") or "").strip()
        obj = str(fact.get("object") or "").strip()
        if not pred or not obj:
            return None
        owner = self._owner_for(str(fact.get("subject") or ""))
        record = {"subject": fact.get("subject"), "predicate": pred, "object": obj, "value": fact.get("value"),
                  "tense": fact.get("tense"), "modal": fact.get("modal"), "sure": fact.get("sure"),
                  "because": fact.get("because"), "when_said": fact.get("when_said"),
                  "created_at": fact.get("created_at")}
        value = {"name": obj} if obj[:1].isupper() else None
        complement = {"entity": value} if value else {"phrase": obj}
        negated = pred.startswith("not_")
        core = pred[4:] if negated else pred
        if core in ("is", "is_a") or core.startswith("v:"):
            # A fact memory filed from Language's reading of any sentence.
            subject = self._entity_for(str(fact.get("subject") or ""))
            if core == "is":
                meaning = {"subject": subject, "verb": "be", "complement": {"adjectives": [obj]}}
                value = str(fact.get("value") or "")
                if value.startswith("than:"):
                    meaning["complement"]["than"] = self._entity_for(value[5:])  # "older than you"
            elif core == "is_a":
                whose = str(fact.get("value") or "").strip()
                meaning = {"subject": subject, "verb": "be",
                           "complement": ({"entity": {"noun": obj, "owner": self._entity_for(whose)}} if whose
                                          else {"noun": obj, "definite": False})}
            else:
                verb, _, prep = core[2:].partition("@")
                meaning = {"subject": subject, "verb": verb}
                if obj != "(nothing)":  # "I can swim": the action alone
                    target = self._entity_for(obj)
                    if prep:
                        meaning["modifiers"] = [{"prep": prep, "object": target}]
                    else:
                        meaning["object"] = target
            if negated:
                meaning["negated"] = True
            if meaning.get("verb") and meaning["verb"] != "be":
                meaning["_word_chosen"] = True  # his own verb, not a dictionary stand-in ("hold" for "have")
            self._how_it_was_said(meaning, fact)
            meaning["_fact"] = record
            return meaning
        if pred == "name":
            meaning = {"subject": {"noun": "name", "owner": owner}, "verb": "be", "complement": complement}
        elif pred.endswith("_name"):
            thing = pred[:-5].replace("_", " ").strip() or "thing"
            meaning = {"subject": {"noun": "name", "owner": {"noun": thing, "owner": owner}},
                       "verb": "be", "complement": complement}
        elif pred.startswith(("favorite_", "favourite_")):
            thing = pred.split("_", 1)[1].replace("_", " ")
            meaning = {"subject": {"noun": thing, "adjectives": ["favorite"], "owner": owner},
                       "verb": "be", "complement": complement}
        elif pred == "lives_in":
            meaning = {"subject": owner, "verb": "live",
                       "modifiers": [{"prep": "in", "object": value or {"noun": obj, "count": "mass"}}]}
        elif pred.startswith("work_"):
            prep = pred[5:] or "as"
            target = value or ({"noun": obj, "count": "one"} if prep == "as" else {"noun": obj, "count": "mass"})
            meaning = {"subject": owner, "verb": "work", "modifiers": [{"prep": prep, "object": target}]}
        else:
            meaning = {"subject": {"noun": pred.replace("_", " "), "owner": owner},
                       "verb": "be", "complement": complement}
        self._how_it_was_said(meaning, fact)
        meaning["_fact"] = record
        return meaning

    # Grammar forms she can speak in (sentence shapes, not reply types).
    # Whether to say anything at all is not Language's decision (Matthew,
    # Oct 31): Language only turns what she means into words. The part that
    # decides whether she replies isn't built yet, so for now she always tries.
    _FORMS = ("state", "ask", "greet", "farewell")
    FAREWELL_SENSE = "oewn-06642117-n"  # dictionary sense: "a farewell remark"
    # The dictionary's groupings: greetings ("hello", "good morning") and
    # farewells ("goodbye", "good night") are filed under these two.
    _GREETING_FAMILY = {"oewn-06642524-n", "oewn-06645018-n"}
    _FAREWELL_FAMILY = {"oewn-06641899-n", "oewn-06642117-n"}
    _PIECE_KINDS = ("heard_noun", "heard_verb", "heard_adjective", "memory", "feeling", "not_knowing",
                    "expected_reply", "what_he_said", "understood", "what_he_means")

    # Pronouns he uses for other people and things, turned to her point of view.
    # ("I", "me", "you" are the two of them and come in as subject choices already.)
    _HIS_PRONOUNS = {
        "he": {"pronoun": "he"}, "him": {"pronoun": "he"},
        "she": {"pronoun": "she"}, "her": {"pronoun": "she"},
        "it": {"pronoun": "it"},
        "they": {"pronoun": "they"}, "them": {"pronoun": "they"},
        "we": {"ref": "addressee"}, "us": {"ref": "addressee"},
    }

    def _pieces(self, semantic_input: Dict[str, Any], user_id: str, user_input: str) -> Dict[str, List[Any]]:
        """What she has in front of her this turn. Nothing here decides what to say."""
        understanding = semantic_input.get("language_understanding") or {}
        pieces: Dict[str, List[Any]] = {k: [] for k in self._PIECE_KINDS}
        for token in understanding.get("tokens") or []:
            kind = token.get("kind")
            lemma = str(token.get("lemma") or "").strip()
            surface = str(token.get("surface") or "").strip()
            if not lemma or lemma.casefold() in {"be", "do", "have"}:
                continue
            if kind == "pronoun" and lemma.casefold() in self._HIS_PRONOUNS:
                # Someone he spoke of, seen from her side: his "we" is "you" to her.
                entity = self._HIS_PRONOUNS[lemma.casefold()]
                if entity not in pieces["heard_noun"]:
                    pieces["heard_noun"].append(dict(entity))
            elif kind == "proper_noun":
                pieces["heard_noun"].append({"name": surface[:1].upper() + surface[1:]})
            elif kind == "noun":
                # Keep it the way he said it: "music" (no a/the) stays "music",
                # "dogs" stays many, "a dog" one.
                index = int(token.get("index", -1))
                before = next((t for t in understanding.get("tokens") or []
                               if int(t.get("index", -2)) == index - 1), {})
                plural = surface.casefold() != lemma.casefold() and surface.casefold().endswith("s")
                bare = before.get("kind") not in ("determiner", "possessive", "number") \
                    and str(before.get("kind")) != "adjective"
                count = "many" if plural else ("mass" if bare else "one")
                pieces["heard_noun"].append({"noun": lemma.casefold(), "count": count})
            elif kind == "verb":
                pieces["heard_verb"].append(lemma.casefold())
            elif kind == "adjective":
                pieces["heard_adjective"].append(lemma.casefold())
        for fact in self._facts_for_this(user_input, user_id)[:5]:
            meaning = self._fact_meaning(fact)
            if meaning:
                pieces["memory"].append(meaning)
        feeling = str(semantic_input.get("emotion") or "").strip().lower()
        if feeling and feeling not in {"neutral", "unknown"}:
            pieces["feeling"].append(feeling)
        for evidence in (understanding.get("affect") or {}).get("evidence") or []:
            # A word Language read as his feeling ("tired") is something she can
            # say back as a feeling, even when it also reads as a verb.
            word = str(evidence.get("lemma") or evidence.get("surface") or "").strip().casefold()
            if word and word not in pieces["heard_adjective"]:
                pieces["heard_adjective"].append(word)
        if understanding.get("speech_act") == "question":
            # Asked something, she can always say she doesn't know it.
            pieces["not_knowing"].append(True)
        to_do = understanding.get("asks_her_to_do") or self.comprehension.analyze(user_input).get("asks_her_to_do")
        if to_do and not to_do.get("what"):
            # "Can you help me?" with nothing said about what: she asks what he needs.
            pieces["what_he_means"].append({"ask_about": "object", "subject": {"ref": "addressee"},
                                             "verb": "need", "_word_chosen": True,
                                             "_purpose": "ask_what_he_needs"})
        elif to_do:
            # "Could you remind me to call Sam?": she says back what he asks of her
            # ("You want me to remind you to call Sam."). Whether she does it is
            # Executive Control's to decide, not Language's.
            asked = " ".join(w for w in [to_do["do"], "you", self._from_her_side(to_do["what"])] if w)
            pieces["what_he_said"].append({"subject": {"ref": "addressee"}, "verb": "want", "_word_chosen": True,
                                           "object": {"ref": "speaker"}, "how": "to " + asked,
                                           "_purpose": "say_back_request", "act": "state"})
        self._didnt_get = None
        pieces["understood"] = self._understood_pieces(user_id, user_input,
                                                       understanding.get("speech_act") == "question")
        if self._didnt_get:
            # Reasoning couldn't make sense of it: she can ask what he means.
            pieces["what_he_means"].append({"ask_about": "object", "subject": {"ref": "addressee"},
                                             "verb": "mean", "_word_chosen": True,
                                             "_purpose": "ask_what_he_means"})
        return pieces

    def _understood_pieces(self, user_id: str, text: str, question: bool) -> List[Dict[str, Any]]:
        """What Reasoning worked out, as meanings she can say: for a question,
        its guesses that answer it ("maybe because you drank coffee"); for
        anything else, what it just worked out and what he corrected. A guess
        is said as one: "probably" or "maybe", by how sure it is."""
        out: List[Dict[str, Any]] = []
        if question:
            body = self._ask("reasoning", "work_out", {"question": text, "user_id": user_id})
            guesses = body.get("answers") or []
        else:
            body = self._ask("reasoning", "get_understanding", {"user_id": user_id})
            if str(body.get("said") or "").strip() and str(body.get("said")).strip() != text.strip():
                return out  # it's about something else he said
            self._didnt_get = body.get("didnt_get")
            guesses = body.get("conclusions") or []
            for wrong in body.get("corrected") or []:
                # He said her guess was wrong: what he means is the other way round.
                turned = dict(wrong)
                predicate = str(turned.get("predicate") or "")
                turned["predicate"] = predicate[4:] if predicate.startswith("not_") else "not_" + predicate
                turned["sure"] = 1.0
                meaning = self._fact_meaning(turned)
                if meaning:
                    meaning["_purpose"] = "take_correction"
                    meaning["_fact"] = dict(meaning.get("_fact") or {}, held_by="he corrected her")
                    out.append(meaning)
        for guess in guesses[:3]:
            if not isinstance(guess, dict):
                continue
            explains = guess.get("explains")
            if isinstance(explains, dict) and guess.get("first_cause"):
                # Why something is: the thing he told her, with the first cause.
                meaning = self._fact_meaning(dict(explains, because=str(guess["first_cause"]),
                                                  sure=guess.get("sure")))
            elif str(guess.get("predicate") or "") == "then":
                continue  # an if-rule she worked out: not something to say on its own
            else:
                meaning = self._fact_meaning(dict(guess, held_by="concluded"))
            if meaning:
                meaning.setdefault("hedge", "maybe" if float(guess.get("sure") or 0) < 0.6 else "probably")
                meaning["_fact"] = dict(meaning.get("_fact") or {}, held_by="concluded",
                                        reasoned=str(guess.get("because") or ""))
                out.append(meaning)
        return out

    @staticmethod
    def _context_key(semantic_input: Dict[str, Any], pieces: Dict[str, List[Any]]) -> str:
        """The circumstances her choices are learned under (what she perceives, not a rule)."""
        understanding = semantic_input.get("language_understanding") or {}
        social = semantic_input.get("social_context") or {}
        cue = social.get("last_cue") if social.get("is_social_turn") else "none"
        act = understanding.get("speech_act") or "unknown"
        mem = "memory" if pieces.get("memory") else "no_memory"
        return f"{act}.{cue or 'none'}.{mem}"

    def _compose(self, builder: Any, plan: Any, ctx: str, pieces: Dict[str, List[Any]],
                 user_id: str) -> Optional[Dict[str, Any]]:
        """Put pieces together into a meaning. Every choice is learned; none is preset."""
        rng = builder.rng
        you = {"ref": "addressee"}
        me = {"ref": "speaker"}
        # Greeting or saying goodbye is something she does back when he does it;
        # otherwise the forms are telling and asking.
        forms = [f for f in self._FORMS if f not in ("greet", "farewell")
                 or (f == "greet" and self.__dict__.get("_situation_now") == "greeting")
                 or (f == "farewell" and self.__dict__.get("_situation_now") == "farewell")]
        form = builder._choose(plan, f"plan_form@{ctx}", forms)
        if form in ("greet", "farewell"):
            options = [you] + [p for p in pieces["heard_noun"] if p.get("name")]
            names = [f for f in self._user_facts("name", user_id) if f.get("predicate") == "name"]
            if names:
                options.append({"name": names[0]["object"]})
            target = builder._choose(plan, f"plan_{form}_who@{ctx}", ["you", "a_name"])
            named = [o for o in options if o.get("name")]
            his = re.sub(r"[^a-z' ]", "", str(self.__dict__.get("_heard_now") or "").casefold()).strip()
            # His own greeting or goodbye ("good night") can be said back as he said it.
            return {"act": form, "addressee": rng.choice(named) if target == "a_name" and named else you,
                    "his_words": [his] if his and len(his.split()) <= 3 else []}
        available = [k for k in self._PIECE_KINDS if pieces[k]]
        if not available:
            return None
        kind = builder._choose(plan, f"plan_piece@{ctx}", available)
        if kind == "memory":
            # Answering, she uses what fits best (newest first); otherwise any.
            # One Reasoning sent back this turn isn't tried again.
            skip = self.__dict__.get("_sent_back_facts") or set()
            fresh = [m for m in pieces["memory"] if self._fact_key(m) not in skip] or pieces["memory"]
            # A question asks one thing; "tell me about..." asks for all she knows.
            may_say_several = not ctx.startswith("question") or bool(self.__dict__.get("_asked_about"))
            if not ctx.startswith("question") and not self.__dict__.get("_asked_about"):
                # Told something, she adds what she knows that goes with it, not
                # everything (and not her guesses: those come from Reasoning's piece).
                fresh = [m for m in fresh if not str((m.get("_fact") or {}).get("held_by") or "").startswith("concluded")
                         and not m.get("hedge")][:2] or fresh[:1]
            if may_say_several and len(fresh) > 1 \
                    and builder._choose(plan, f"plan_how_much@{ctx}.memory", ["one", "several"]) == "several":
                # More than one thing she knows about it, said together.
                chosen = [dict(m) for m in fresh[:6]]
                for m in chosen:
                    self._add_reason(m)
                meaning = {"several": chosen, "_fact": chosen[0].get("_fact"),
                           "_facts": [m.get("_fact") for m in chosen if m.get("_fact")]}
            else:
                meaning = dict(fresh[0] if ctx.startswith("question") else rng.choice(fresh))
                self._add_reason(meaning)
        elif kind == "understood":
            # What Reasoning worked out: the surest first when answering.
            skip = self.__dict__.get("_sent_back_facts") or set()
            fresh = [m for m in pieces["understood"] if self._fact_key(m) not in skip] or pieces["understood"]
            meaning = dict(fresh[0] if ctx.startswith("question") else rng.choice(fresh))
            self._add_reason(meaning)
        elif kind == "what_he_said":
            said = pieces["what_he_said"]
            if len(said) > 1 and builder._choose(plan, f"plan_how_much@{ctx}.what_he_said", ["one", "several"]) == "several":
                # Everything he said in his long sentence, from her side.
                meaning = {"several": [dict(m) for m in said]}
            else:
                meaning = dict(rng.choice(said))
        elif kind == "expected_reply":
            meaning = dict(pieces["expected_reply"][0])
            if meaning.get("act") == "phrase":
                return meaning  # said as taught, never turned into a question
        elif kind == "what_he_means":
            return dict(pieces["what_he_means"][0], act="ask")
        elif kind == "not_knowing":
            meaning = {"subject": me, "verb": "know", "negated": True, "_purpose": "admit_unknown"}
        else:
            subjects = {"me": me, "you": you}
            if pieces["heard_noun"]:
                subjects["heard"] = rng.choice(pieces["heard_noun"])
            who = builder._choose(plan, f"plan_subject@{ctx}.{kind}", list(subjects))
            subject = subjects[who]
            if kind == "heard_verb":
                meaning = {"subject": subject, "verb": rng.choice(pieces["heard_verb"])}
                if pieces["heard_noun"] and builder._choose(plan, f"plan_object@{ctx}", ["object", "none"]) == "object":
                    meaning["object"] = rng.choice(pieces["heard_noun"])
            elif kind == "heard_adjective":
                meaning = {"subject": subject, "verb": "be",
                           "complement": {"adjectives": [rng.choice(pieces["heard_adjective"])]}}
            elif kind == "feeling":
                # Her feeling is hers: it is only ever said about her.
                meaning = {"subject": me, "verb": "be", "complement": {"adjectives": [pieces["feeling"][0]]},
                           "_purpose": "own_feeling"}
            else:  # heard_noun: a thing or a name, never a pronoun ("Are you a they?")
                things = [n for n in pieces["heard_noun"] if n.get("noun") or n.get("name")]
                if not things:
                    return None
                noun = rng.choice(things)
                meaning = {"subject": subject, "verb": "be",
                           "complement": {"entity": noun} if noun.get("name")
                           else {"noun": noun["noun"], "definite": False}}
        meaning["act"] = "ask" if form == "ask" else "state"
        for part in meaning.get("several") or []:
            part["act"] = meaning["act"]
        return meaning

    def _use_his_ways(self, builder: Any, user_input: str) -> None:
        """The shapes she has read, used in her own sentences: how he puts a
        "not" ("didn't" or "did not") is counted from what he says, and once he
        clearly has a way, she says it his way too."""
        try:
            shapes = self.comprehension._structure().shapes
        except Exception:
            return
        low = user_input.casefold()
        if re.search(r"n't\b|\bwon't\b|\bcan't\b", low):
            shapes.note_style("negation_style", "contracted")
        elif re.search(r"\b(not|cannot)\b", low):
            shapes.note_style("negation_style", "full")
        way = shapes.his_way("negation_style")
        if way:
            builder.steer_only["negation_style"] = {way}

    def _tell_pattern_how_built(self, reading: Dict[str, Any], user_id: str) -> None:
        """Send Pattern Recognition how his sentence was built (the shape of
        each statement in it: "N V N", "N be A"), so it can find the shapes he
        uses and how they follow each other."""
        tell = getattr(self.thalamus, "tell", None)
        if not callable(tell):
            return
        try:
            from language_structure import ShapeMemory
            parts = [self.comprehension.analyze(p) for p in reading.get("parts") or []] or [reading]
            shapes = [ShapeMemory.shape(r.get("tokens") or []) for r in parts]
            shapes = [x for x in shapes if x]
            if shapes:
                tell("pattern", "observe", {"items": [f"sentence shape: {x}" for x in shapes],
                                                        "user_id": user_id, "from": "language"}, "language")
        except Exception as error:
            print(f"⚠️  Language: couldn't tell Pattern Recognition how his sentence was built ({error})")

    def _add_reason(self, meaning: Dict[str, Any]) -> None:
        if meaning.get("_because_text"):
            # "...because your dog died": his reason, read and turned to her side.
            reason = self._statement_meaning(self.comprehension.analyze(meaning["_because_text"]))
            if reason:
                meaning["because"] = reason

    # What kind of reply Reasoning said would fit, and how Language narrows its
    # next try to fit it (it still chooses, and still learns from what's kept).
    _FEEDBACK = {
        "use_memory": ({"plan_form@": {"state"}, "plan_piece@": {"memory", "understood"}}, {}),
        "say_dont_know": ({"plan_form@": {"state"}, "plan_piece@": {"not_knowing"}}, {}),
        "say_expected": ({"plan_form@": {"state"}, "plan_piece@": {"expected_reply"}}, {}),
        "say_own_feeling": ({"plan_form@": {"state"}, "plan_piece@": {"feeling"},
                             "plan_subject@": {"me"}}, {}),
        "other_fact_or_dont_know": ({"plan_form@": {"state"}, "plan_piece@": {"memory", "understood", "not_knowing"}}, {}),
        "answer_not_ask": ({}, {"plan_form@": {"ask"}}),
        "state_not_ask": ({"plan_form@": {"state"}}, {}),
        "not_about_herself": ({}, {"plan_subject@": {"me"}, "plan_piece@": {"what_he_said"}}),
        "greet_back": ({"plan_form@": {"greet"}}, {}),
        "respond_to_feeling": ({"plan_piece@": {"what_he_said", "heard_adjective", "feeling"},
                                "plan_how_much@": {"several"}}, {}),
        "about_him": ({"plan_subject@": {"you"}}, {}),
        "farewell_back": ({"plan_form@": {"farewell"}}, {}),
        "no_name": ({"plan_greet_who@": {"you"}, "plan_farewell_who@": {"you"}}, {}),
        "complete_it": ({"plan_object@": {"object"}}, {}),
        "not_greeting": ({}, {"plan_form@": {"greet"}}),
        "not_farewell": ({}, {"plan_form@": {"farewell"}}),
        "restate_or_ask": ({"plan_form@": {"state", "ask"},
                            "plan_piece@": {"what_he_said", "memory", "understood", "heard_noun", "heard_verb",
                                            "heard_adjective"}}, {}),
        "about_what_he_said": ({"plan_piece@": {"what_he_said", "memory", "heard_noun", "heard_verb",
                                                "heard_adjective"}}, {}),
        "misheard": ({"plan_piece@": {"what_he_means"}}, {}),
    }

    def _take_feedback(self, builder: Any, wanted: str) -> None:
        if wanted in ("about_what_he_said", "restate_or_ask", "respond_to_feeling") \
                and not (self.__dict__.get("_said_back_several_failed") if wanted == "respond_to_feeling"
                         else self.__dict__.get("_said_back_failed")):
            # Sent back for not keeping to what he said: say what he said, from her
            # side (unless that was what got sent back).
            builder.steer_only["plan_piece@"] = {"what_he_said"}
            builder.steer_only["plan_form@"] = {"state"}
            if wanted == "respond_to_feeling":
                builder.steer_only["plan_how_much@"] = {"several"}
            return
        if wanted.startswith("plain_word:"):
            _, pos, word = (wanted.split(":", 2) + ["", ""])[:3]
            if pos and word:
                builder.steer_only[f"word_{pos}_{word}"] = {word}
            return
        only, avoid = self._FEEDBACK.get(wanted, ({}, {}))
        for prefix, values in only.items():
            builder.steer_only[prefix] = set(values)
        for prefix, values in avoid.items():
            builder.steer_avoid.setdefault(prefix, set()).update(values)

    def respond(self, semantic_input: Dict[str, Any]) -> Dict[str, Any]:
        """Compose from the pieces, build, have Reasoning review, learn, redo. Always reports why."""
        from language_builder import Built

        understanding = semantic_input.get("language_understanding") or {}
        user_id = str(understanding.get("user_id") or semantic_input.get("user_id") or "default")
        user_input = str(semantic_input.get("user_input") or understanding.get("raw_text") or "")
        situation = self._situation(semantic_input)
        self._situation_now = situation
        self._heard_now = user_input
        resolved_input = self._resolved_text(user_input, user_id) if user_input else user_input
        asks_her = understanding.get("asks_her") or self.comprehension.analyze(resolved_input or "").get("asks_her")
        if asks_her and asks_her.get("about") and not asks_her.get("say"):
            # "Tell me about my brother" asks what she knows about him: answered
            # like that question, from what she knows.
            about = str(asks_her["about"]).strip()
            resolved_input = (about + "?") if about.split()[0].casefold() in ("why", "how", "what", "where", "who", "when") \
                else f"what do you know about {about}?"
            situation = "question"
            understanding = dict(understanding, speech_act="question")
            semantic_input = dict(semantic_input, language_understanding=understanding)
        # What social context believes this moment calls for, in words ("you're welcome").
        social_now = self._social_for(user_id, user_input) or semantic_input.get("social_context") or {}
        expected_reply = str(social_now.get("expected_reply") or "").strip()
        if asks_her and asks_her.get("say"):
            # "Say hello", "repeat after me: ...": what he asked her to say, as he gave it.
            expected_reply = str(asks_her["say"])
            situation = "social_reply"
        if resolved_input != user_input:
            self._trace("references_resolved", heard=user_input, means=resolved_input)
        if understanding.get("unknown_words") or [u for u in understanding.get("unresolved_references") or []]:
            # She couldn't make sense of some of it: Emotion feels that.
            tell = getattr(self.thalamus, "tell", None)
            if callable(tell):
                try:
                    tell("emotion", "didnt_understand", {"text": user_input}, "language")
                except Exception:
                    pass
        pieces = self._pieces(semantic_input, user_id, resolved_input)
        # What he said, as a whole meaning, from Language's own reading of it
        # (each part of a two-part sentence on its own).
        his = self.comprehension.analyze(resolved_input or "")
        taught = self.comprehension.learn_taught_word(his)
        if taught:
            self._trace("word_taught", word=taught["word"], means=taught["means"],
                        senses=len(taught.get("senses") or []))
            his = self.comprehension.analyze(resolved_input or "")
        self._tell_pattern_how_built(his, user_id)
        said_parts = [self._statement_meaning(self.comprehension.analyze(part)) for part in his.get("parts") or []] \
            if his.get("parts") else [self._statement_meaning(his)]
        attached = set()
        for link in his.get("links") or []:
            # A statement that says when, why, on what condition or despite what
            # another is true goes with that one ("we will stay home if it rains").
            a, b = link.get("from"), link.get("to")
            if link.get("kind") in ("when", "why", "on_condition", "unless", "despite") and isinstance(a, int) \
                    and isinstance(b, int) and a < len(said_parts) and b < len(said_parts) \
                    and said_parts[a] and said_parts[b]:
                if link.get("kind") == "why":
                    said_parts[a]["because"] = said_parts[b]
                else:
                    said_parts[a]["linked"] = {"word": link.get("word"), "meaning": said_parts[b]}
                attached.add(b)
        for n, said in enumerate(said_parts):
            if said and n not in attached:
                pieces["what_he_said"].append(said)
        if expected_reply:
            said = self._meaning_from_words(expected_reply)
            if said:
                pieces["expected_reply"].append(said)
        ctx = self._context_key(semantic_input, pieces)
        feeling_words = [e.get("surface") for e in (understanding.get("affect") or {}).get("evidence") or []
                         if e.get("surface")]

        builder = self._builder("monday")
        base_explore = builder.explore_rate
        last_reason = ""
        builder.steer_only, builder.steer_avoid = {}, {}
        self._sent_back_facts = set()
        # His words stay his words: saying back what he said (or what he told
        # her before), she keeps the words he used instead of a dictionary
        # synonym that may mean something else ("hold" for "have").
        for pos, word in self._his_words(pieces):
            builder.steer_only[f"word_{pos}_{word}"] = {word}
        whole = re.sub(r"[^a-z' ]", "", user_input.casefold()).strip()
        if whole:
            # "good night" back for his "good night".
            builder.steer_only.setdefault("greeting_word", set()).update({whole, whole.replace(" ", "_")})
            builder.steer_only.setdefault("farewell_word", set()).update({whole, whole.replace(" ", "_")})
        for token in his.get("tokens") or []:
            # "hello" back for his "hello", "bye" for "bye": his greeting word, if it is one.
            word = str(token.get("surface") or "").casefold()
            if word.isalpha():
                builder.steer_only.setdefault("greeting_word", set()).add(word)
                builder.steer_only.setdefault("farewell_word", set()).add(word)
        self._asked_about = bool(asks_her and asks_her.get("about") and not asks_her.get("say"))
        if asks_her and asks_her.get("about") and not asks_her.get("say") and len(pieces.get("memory") or []) > 1:
            # "Tell me about my brother" asks for what she knows about him, all of it.
            builder.steer_only["plan_how_much@"] = {"several"}
            builder.steer_only["plan_form@"] = {"state"}
            builder.steer_only["plan_piece@"] = {"memory"}
        self._use_his_ways(builder, user_input)
        if any(p.get("_purpose") == "say_back_request" for p in pieces.get("what_he_said") or []):
            # He asked her to do something: she shows she got what he asks.
            builder.steer_only["plan_piece@"] = {"what_he_said"}
            builder.steer_only["plan_form@"] = {"state"}
        if any(p.get("_purpose") == "ask_what_he_needs" for p in pieces.get("what_he_means") or []):
            # He asked her to do something without saying what: what he needs comes first.
            builder.steer_only["plan_piece@"] = {"what_he_means"}
            builder.steer_only["plan_form@"] = {"ask"}
        sent_back: set = set()
        self._said_back_failed = self._said_back_several_failed = False
        try:
            for attempt in range(1, self.MAX_REPLY_ATTEMPTS + 1):
                builder.explore_rate = min(1.0, base_explore + 0.15 * (attempt - 1))
                # Don't say the same thing that was just sent back.
                for _ in range(6):
                    plan = Built("", learner=builder.learner)
                    meaning = self._compose(builder, plan, ctx, pieces, user_id)
                    if meaning is None:
                        built = None
                        break
                    meaning["_feeling_words"] = feeling_words
                    built = builder.build(meaning)
                    if built.sentence not in sent_back:
                        break
                if meaning is None:
                    last_reason = "she had nothing to put together"
                    continue
                built.choices = plan.choices + built.choices
                review = self._ask("reasoning", "review_reply", {
                    "sentence": built.sentence, "problems": built.problems, "situation": situation,
                    "meaning": meaning, "user_input": user_input, "user_id": user_id,
                    "resolved_input": resolved_input,
                    "her_feeling": (pieces.get("feeling") or [None])[0],
                    "expected_move": situation if situation in ("greeting", "farewell") else None,
                    "expected_reply": expected_reply or None,
                })
                if not review:
                    last_reason = "reasoning did not review the reply"
                    self._trace("reply_done", silence="failed", situation=situation, reason=last_reason)
                    return {"sentence": "", "silence": "failed", "reason": last_reason, "situation": situation}
                ok = bool(review.get("ok"))
                last_reason = str(review.get("reason") or "")
                builder.feedback(built, ok, last_reason)
                if not ok:
                    sent_back.add(built.sentence)
                    if meaning.get("_purpose") == "say_back" and meaning.get("act") == "state":
                        self._said_back_failed = True
                    if meaning.get("act") == "state" and any(
                            p.get("_purpose") == "say_back" for p in meaning.get("several") or []):
                        self._said_back_failed = self._said_back_several_failed = True
                    if meaning.get("_fact"):
                        self.__dict__.setdefault("_sent_back_facts", set()).add(self._fact_key(meaning))
                    self._take_feedback(builder, str(review.get("wanted") or ""))
                self._trace("reply_attempt", ok=ok, sentence=built.sentence,
                            reason=last_reason, context=ctx, attempt=attempt,
                            plan=[f"{p}={o}" for p, o, _ in plan.choices])
                if ok:
                    silence = None
                    self._tell_emotion(failed=False, used_memory=bool(meaning.get("_fact")) and situation == "question")
                    self._trace("reply_done", silence=silence, situation=situation, attempts=attempt,
                                sentence=built.sentence, reason=last_reason)
                    return {"sentence": built.sentence, "silence": silence, "reason": last_reason,
                            "situation": situation, "attempts": attempt}
        finally:
            builder.explore_rate = base_explore
            builder.steer_only, builder.steer_avoid = {}, {}
        self._tell_emotion(failed=True, used_memory=False,
                           social_move=situation in ("greeting", "farewell", "social_reply"))
        self._trace("reply_done", silence="failed", situation=situation, reason=last_reason,
                    attempts=self.MAX_REPLY_ATTEMPTS)
        return {"sentence": "", "silence": "failed", "reason": last_reason, "situation": situation,
                "attempts": self.MAX_REPLY_ATTEMPTS}


    
    def _register_with_thalamus(self):
        """Register with Thalamus - DIRECT FUNCTION CALL (NO SOCKETS)"""
        try:
            result = self.thalamus.register_lobe('language', self)
            if result.get('status') == 'success':
                print("✅ Language registered with Thalamus (direct function calls)")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register with Thalamus: {e}")
            return False

    def _send_to_thalamus(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send message to Thalamus - DIRECT FUNCTION CALL (helper for Language Generator)"""
        try:
            msg_type = message.get('type')
            if msg_type == 'route_message':
                destination = message.get('destination')
                route_msg_type = message.get('msg_type')
                content = message.get('content', {})
                return self.thalamus.send_message(destination, route_msg_type, content, source='language')
            elif msg_type == 'broadcast_message':
                destinations = message.get('destinations', [])
                broadcast_msg_type = message.get('msg_type')
                broadcast_content = message.get('content', {})
                return self.thalamus.broadcast_message(destinations, broadcast_msg_type, broadcast_content, source='language')
            else:
                return self.thalamus.handle_request(message)
        except Exception:
            return None
    
    def _send_to_output(self, sentence: str, user_input: str = None):
        """Send generated sentence to Output through Thalamus - DIRECT FUNCTION CALL"""
        if not sentence or not isinstance(sentence, str) or not sentence.strip():
            # Nothing real to say — do not substitute a stock line; skip Output.
            return
        
        # Direct function call - NO SOCKETS
        # Pass user_input so Output can store the full conversation to Notus
        self.thalamus.send_message('output', 'text_response', {
            'text': sentence,
            'user_input': user_input  # Pass user_input for memory storage
        }, source='language')
    
    def start(self):
        """Start language generation - register with Thalamus (NO SOCKETS)"""
        print(f"💬 Language Generation: Registering with Thalamus...")
        print(f"   Grammar-based semantic-to-sentence construction")
        print(f"   Communication: Direct function calls (NO SOCKETS)")
        
        # Register with Thalamus
        if not self._register_with_thalamus():
            print("❌ Failed to register with Thalamus")
            return
        
        # Keep running (Thalamus calls us directly, no listening loop needed)
        while self.running:
            time.sleep(0.1)
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming message - DIRECT FUNCTION CALL"""
        msg_type = message.get('type')
        payload = message.get('content', message)

        if msg_type == 'social_read':
            return self._hear_social(payload if isinstance(payload, dict) else {})
        if msg_type == 'comprehend':
            text = payload.get('text') or payload.get('user_input') or ''
            user_id = str(payload.get('user_id') or 'default')
            turn_id = payload.get('turn_id') or message.get('message_id')
            result = self.comprehend(
                str(text),
                user_id=user_id,
                turn_id=str(turn_id) if turn_id else None,
            )
            return {'status': 'success', 'content': result, **result}

        if msg_type == 'express':
            learner = str(payload.get('learner') or 'monday')
            result = self.express(payload.get('meaning'), learner=learner)
            return {'status': 'success', 'content': result}

        if msg_type == 'express_feedback':
            result = self.express_feedback(
                payload.get('record') or {}, payload.get('good', False), payload.get('reason', '')
            )
            return {'status': 'success', 'content': result}

        if msg_type == 'analyze':
            # Read a sentence without registering anything. Whoever asks may supply
            # context (recent lines, what's known about names); with it, Language
            # works out who he/she/it/they mean, or marks them uncertain.
            reading = self.comprehension.analyze(str(payload.get('text') or ''))
            if isinstance(payload.get('context'), list):
                reading = self._resolve_references(reading, payload)
            return {'status': 'success', 'content': {'understanding': reading}}

        if msg_type == 'read_again':
            # Reasoning says the reading of what he said didn't make sense and
            # which words fit better how. Read it again that way; from now on
            # that sentence reads the new way (for the reply too), and anyone
            # who filed the old reading hears about it.
            text = str(payload.get('text') or '')
            hints = [h for h in payload.get('problems') or [] if isinstance(h, dict)]
            reading = self.comprehension.analyze(text, hints=hints)
            if isinstance(payload.get('context'), list):
                reading = self._resolve_references(reading, payload)
            try:
                import copy
                self.comprehension.__dict__.setdefault('_readings', {})[text.strip()] = copy.deepcopy(reading)
                kept = self.__dict__.setdefault('_read_again', {})
                kept[text.strip()] = copy.deepcopy(reading)
                while len(kept) > 50:
                    kept.pop(next(iter(kept)))
            except Exception:
                pass
            if self.thalamus is not None and hasattr(self.thalamus, 'announce'):
                try:
                    self.thalamus.announce('read_again', {'text': text, 'understanding': reading,
                                                          'because': hints}, source='language')
                except Exception as error:
                    print(f"⚠️  Language: couldn't tell the others it read '{text}' again ({error})")
            return {'status': 'success', 'content': {'understanding': reading}}

        if msg_type in {'generate', 'generate_grounded'}:
            semantic_input = payload.get('semantic_input', payload)
            semantic_input = dict(semantic_input) if isinstance(semantic_input, dict) else {}
            # Language hears what was said itself; it does not depend on another
            # lobe forwarding it.
            heard = str(payload.get('user_input') or semantic_input.get('user_input') or '')
            if heard:
                semantic_input['user_input'] = heard
            if payload.get('user_id'):
                semantic_input.setdefault('user_id', str(payload['user_id']))
            understanding = semantic_input.get('language_understanding')
            again = (self.__dict__.get('_read_again') or {}).get(heard.strip()) if heard else None
            if again:
                # Reasoning had it read again: reply to what he meant.
                import copy
                understanding = copy.deepcopy(again)
                understanding['user_id'] = semantic_input.get('user_id', 'default')
                semantic_input['language_understanding'] = understanding
            if heard and not (isinstance(understanding, dict) and understanding.get('tokens')):
                understanding = self.comprehension.analyze(heard)
                understanding['user_id'] = semantic_input.get('user_id', 'default')
                semantic_input['language_understanding'] = understanding
            result = self.respond(semantic_input)
            sentence = result['sentence']
            
            # Only send to Output if reasoning explicitly says this is the main response
            is_main_response = payload.get('is_main_response', False)
            if is_main_response:
                # Pass user_input so Output can store the full conversation
                user_input = payload.get('user_input', '')
                self._send_to_output(sentence, user_input)
            
            return {'status': 'success', 'response': sentence, 'sentence': sentence, 'sent_to_output': is_main_response,
                    'silence': result.get('silence'), 'reason': result.get('reason'), 'situation': result.get('situation')}
        elif msg_type == 'health':
            return {'status': 'success', 'healthy': True, 'pid': os.getpid()}
        else:
            return {'status': 'error', 'message': 'Unknown message type'}

    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        # No sockets to close

if __name__ == "__main__":
    generator = LanguageGenerator()
    try:
        generator.start()
    except KeyboardInterrupt:
        print("\n🛑 Language generation shutting down...")
        generator.shutdown()
