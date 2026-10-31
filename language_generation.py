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

    MAX_REPLY_ATTEMPTS = 7
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
        # Greetings and goodbyes are Social Context's call (above), not Language's.
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

    def _user_facts(self, query: str, user_id: str) -> List[Dict[str, Any]]:
        body = self._ask("notus", "query_facts", {"query": query, "user_id": user_id, "limit": 10})
        return [f for f in body.get("facts") or [] if isinstance(f, dict)]

    @staticmethod
    def _entity_for(text: str) -> Dict[str, Any]:
        """Who/what a filed fact is about, as a meaning: "user" is him,
        "monday" is her, "user's brother" is his brother, a name is a name."""
        t = (text or "").strip()
        low = t.casefold()
        if low in ("user", "i", "me", ""):
            return {"ref": "addressee"}
        if low == "monday":
            return {"ref": "speaker"}
        if "'s " in t:
            owner, thing = t.split("'s ", 1)
            return {"noun": thing.strip().casefold(), "owner": LanguageGenerator._entity_for(owner)}
        if t[:1].isupper():
            return {"name": t}
        words = low.split()
        # As he said it: "a castle", "the sword", "rain" (no article: uncountable or many).
        if len(words) > 1 and words[0] in ("a", "an"):
            return {"noun": " ".join(words[1:]), "definite": False, "count": "one"}
        if len(words) > 1 and words[0] == "the":
            return {"noun": " ".join(words[1:]), "definite": True}
        return {"noun": low, "count": "mass"}

    @staticmethod
    def _owner_for(subject: str) -> Dict[str, Any]:
        sub = (subject or "").strip()
        if sub.casefold() in {"user", "i", "me", ""}:
            return {"ref": "addressee"}
        return {"name": sub}

    def _fact_meaning(self, fact: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Turn a stored fact (subject / predicate / object) into a meaning to say."""
        pred = str(fact.get("predicate") or "").strip()
        obj = str(fact.get("object") or "").strip()
        if not pred or not obj:
            return None
        owner = self._owner_for(str(fact.get("subject") or ""))
        record = {"subject": fact.get("subject"), "predicate": pred, "object": obj}
        value = {"name": obj} if obj[:1].isupper() else None
        complement = {"entity": value} if value else {"phrase": obj}
        negated = pred.startswith("not_")
        core = pred[4:] if negated else pred
        if core in ("is", "is_a") or core.startswith("v:"):
            # A fact memory filed from Language's reading of any sentence.
            subject = self._entity_for(str(fact.get("subject") or ""))
            if core == "is":
                meaning = {"subject": subject, "verb": "be", "complement": {"adjectives": [obj]}}
            elif core == "is_a":
                whose = str(fact.get("value") or "").strip()
                meaning = {"subject": subject, "verb": "be",
                           "complement": ({"entity": {"noun": obj, "owner": self._entity_for(whose)}} if whose
                                          else {"noun": obj, "definite": False})}
            else:
                verb, _, prep = core[2:].partition("@")
                target = self._entity_for(obj)
                meaning = {"subject": subject, "verb": verb}
                if prep:
                    meaning["modifiers"] = [{"prep": prep, "object": target}]
                else:
                    meaning["object"] = target
            if negated:
                meaning["negated"] = True
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
        meaning["_fact"] = record
        return meaning

    # Grammar forms she can speak in (sentence shapes, not reply types).
    _FORMS = ("state", "ask", "greet", "farewell", "quiet")
    FAREWELL_SENSE = "oewn-06642117-n"  # dictionary sense: "a farewell remark"
    _PIECE_KINDS = ("heard_noun", "heard_verb", "heard_adjective", "memory", "feeling", "not_knowing")

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
            if kind == "proper_noun":
                pieces["heard_noun"].append({"name": surface[:1].upper() + surface[1:]})
            elif kind == "noun":
                pieces["heard_noun"].append({"noun": lemma.casefold(), "count": "one"})
            elif kind == "verb":
                pieces["heard_verb"].append(lemma.casefold())
            elif kind == "adjective":
                pieces["heard_adjective"].append(lemma.casefold())
        for fact in self._user_facts(user_input, user_id)[:5]:
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
        return pieces

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
        form = builder._choose(plan, f"plan_form@{ctx}", list(self._FORMS))
        if form == "quiet":
            return {"_quiet": True}
        if form in ("greet", "farewell"):
            options = [you] + [p for p in pieces["heard_noun"] if p.get("name")]
            names = [f for f in self._user_facts("name", user_id) if f.get("predicate") == "name"]
            if names:
                options.append({"name": names[0]["object"]})
            target = builder._choose(plan, f"plan_{form}_who@{ctx}", ["you", "a_name"])
            named = [o for o in options if o.get("name")]
            return {"act": form, "addressee": rng.choice(named) if target == "a_name" and named else you}
        available = [k for k in self._PIECE_KINDS if pieces[k]]
        if not available:
            return None
        kind = builder._choose(plan, f"plan_piece@{ctx}", available)
        if kind == "memory":
            meaning = dict(rng.choice(pieces["memory"]))
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
                meaning = {"subject": subject, "verb": "be", "complement": {"adjectives": [pieces["feeling"][0]]}}
                if who == "me":
                    meaning["_purpose"] = "own_feeling"  # how she feels: something she knows
            else:  # heard_noun
                noun = rng.choice(pieces["heard_noun"])
                meaning = {"subject": subject, "verb": "be",
                           "complement": {"entity": noun} if noun.get("name")
                           else {"noun": noun["noun"], "definite": False}}
        meaning["act"] = "ask" if form == "ask" else "state"
        return meaning

    # What kind of reply Reasoning said would fit, and how Language narrows its
    # next try to fit it (it still chooses, and still learns from what's kept).
    _FEEDBACK = {
        "use_memory": ({"plan_form@": {"state"}, "plan_piece@": {"memory"}}, {}),
        "say_dont_know": ({"plan_form@": {"state"}, "plan_piece@": {"not_knowing"}}, {}),
        "say_own_feeling": ({"plan_form@": {"state"}, "plan_piece@": {"feeling"},
                             "plan_subject@": {"me"}}, {}),
        "other_fact_or_dont_know": ({"plan_form@": {"state"}, "plan_piece@": {"memory", "not_knowing"}}, {}),
        "answer_not_ask": ({}, {"plan_form@": {"ask"}}),
        "greet_back": ({"plan_form@": {"greet"}}, {}),
        "not_silence": ({}, {"plan_form@": {"quiet"}}),
        "respond_to_feeling": ({"plan_piece@": {"heard_adjective", "feeling"}}, {"plan_form@": {"quiet"}}),
        "about_him": ({"plan_subject@": {"you"}}, {"plan_form@": {"quiet"}}),
        "farewell_back": ({"plan_form@": {"farewell"}}, {}),
        "no_name": ({"plan_greet_who@": {"you"}, "plan_farewell_who@": {"you"}}, {}),
        "complete_it": ({"plan_object@": {"object"}}, {}),
        "not_greeting": ({}, {"plan_form@": {"greet"}}),
        "not_farewell": ({}, {"plan_form@": {"farewell"}}),
        "restate_or_ask": ({"plan_form@": {"state", "ask"},
                            "plan_piece@": {"memory", "heard_noun", "heard_verb", "heard_adjective"}}, {}),
        "about_what_he_said": ({"plan_piece@": {"memory", "heard_noun", "heard_verb", "heard_adjective"}}, {}),
    }

    def _take_feedback(self, builder: Any, wanted: str) -> None:
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
        pieces = self._pieces(semantic_input, user_id, user_input)
        ctx = self._context_key(semantic_input, pieces)
        feeling_words = [e.get("surface") for e in (understanding.get("affect") or {}).get("evidence") or []
                         if e.get("surface")]

        builder = self._builder("monday")
        base_explore = builder.explore_rate
        last_reason = ""
        builder.steer_only, builder.steer_avoid = {}, {}
        sent_back: set = set()
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
                    if meaning.get("_quiet"):
                        built = Built("", learner=builder.learner)
                    else:
                        meaning["_feeling_words"] = feeling_words
                        built = builder.build(meaning)
                    if (built.sentence or "(quiet)") not in sent_back:
                        break
                if meaning is None:
                    last_reason = "she had nothing to put together"
                    continue
                built.choices = plan.choices + built.choices
                review = self._ask("reasoning", "review_reply", {
                    "sentence": built.sentence, "problems": built.problems, "situation": situation,
                    "meaning": meaning, "user_input": user_input, "user_id": user_id,
                    "chosen_silence": bool(meaning.get("_quiet")),
                    "her_feeling": (pieces.get("feeling") or [None])[0],
                    "expected_move": situation if situation in ("greeting", "farewell") else None,
                })
                if not review:
                    last_reason = "reasoning did not review the reply"
                    self._trace("reply_done", silence="failed", situation=situation, reason=last_reason)
                    return {"sentence": "", "silence": "failed", "reason": last_reason, "situation": situation}
                ok = bool(review.get("ok"))
                last_reason = str(review.get("reason") or "")
                builder.feedback(built, ok, last_reason)
                if not ok:
                    sent_back.add(built.sentence or "(quiet)")
                    self._take_feedback(builder, str(review.get("wanted") or ""))
                self._trace("reply_attempt", ok=ok, sentence=built.sentence or "(stays quiet)",
                            reason=last_reason, context=ctx, attempt=attempt,
                            plan=[f"{p}={o}" for p, o, _ in plan.choices])
                if ok:
                    silence = "chosen" if meaning.get("_quiet") else None
                    self._trace("reply_done", silence=silence, situation=situation, attempts=attempt,
                                sentence=built.sentence, reason=last_reason)
                    return {"sentence": built.sentence, "silence": silence, "reason": last_reason,
                            "situation": situation, "attempts": attempt}
        finally:
            builder.explore_rate = base_explore
            builder.steer_only, builder.steer_avoid = {}, {}
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
            # Read a sentence without registering anything (used by Reasoning's review).
            return {'status': 'success', 'content': {'understanding': self.comprehension.analyze(str(payload.get('text') or ''))}}

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
