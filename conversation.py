#!/usr/bin/env python3
"""
Conversation System for Monday / Mercy

Dialogue state across turns — topic, shifts, follow-ups, corrections,
answers to her questions, open threads, and cross-turn referents.

Owns: dialogue continuity from Language meaning packets.
Does not: regex turn classification, cue-word dialogue_move lists,
keyword slots/entities/sentiment, write final prose, invent facts,
or ground answers in memory.

FAIL notes (owned):
- b3d6ec6: frozenset cue lists (_TOPIC_SHIFT_DISCOURSE / _CORRECTION_PREDICATES /
  _AFFECT_PREDICATES). Matty caught it.
- b8ef040: _AFFECT_DEF_MARKERS definition substrings + correction = leading "no"
  + garbage topics ("is aluminum", "me more"). Matty caught it again.
FAIL history continued: bd4d5fb stamped PASS on angry/furious NOT affect +
wrong topics (anxiety/matthew) + awful terror false-positive + dirty Step4 tree.
Fourth redo: OEWN derivation/attribute affect (surface-scoped), about-first
topic_head, clean Step4 tree. Prior fake-correction FAILs: b8ef040 leading
"no"; bd4d5fb/_is_correction always False (honest gap, still not real repair);
any cue-word / frozenset discourse "correction" lists;
5e7003c any-different-lemma replace (Matty: aluminum→round / red→fast /
steel→loose counted). Real correction = same topic + polarity retract of
SAME complement OR OEWN same-kind competing complement replace — not
"No." theater and not any different word.

Language owns word/sentence meaning. Conversation places that meaning
in the exchange. Emotion owns affect. Reasoning owns truth/grounding.
"""

from __future__ import annotations

import os
import random
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from thalamus import get_thalamus
from lexicon.oewn_offline import complements_compete
from direct_response import (
    is_closing_social_turn,
    honest_curiosity_question,
    is_mild_social_turn,
    looks_like_teaching_turn,
)


# Step 3 REDO: Conversation does NOT classify dialogue_move via English cue
# frozensets (anyway/instead/meant/feel/talk/…). Dialogue state comes from
# Language packet structure: speech_act / clause_type, roles, mentions,
# contrast, affect, unresolved deictics. Closed-class token *kinds* from the
# packet are used only to reject junk topic anchors — not to name moves.
_CLOSED_TOKEN_KINDS = frozenset(
    {
        "determiner",
        "preposition",
        "pronoun",
        "auxiliary",
        "modal",
        "negation",
        "punctuation",
        "wh",
        "number",
        "temporal",
    }
)


@dataclass
class ConversationState:
    """Multi-turn dialogue state (Conversation-owned continuity)."""

    history: deque = field(default_factory=lambda: deque(maxlen=50))
    current_topic: Optional[str] = None
    previous_topic: Optional[str] = None
    user_name: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    turn_index: int = 0
    open_questions: List[Dict[str, Any]] = field(default_factory=list)
    unfinished_threads: List[Dict[str, Any]] = field(default_factory=list)
    referent_stack: deque = field(default_factory=lambda: deque(maxlen=40))
    pending_mercy_questions: List[Dict[str, Any]] = field(default_factory=list)
    last_dialogue_move: Optional[str] = None
    last_resolved_referents: List[Dict[str, Any]] = field(default_factory=list)
    # Assertable propositions keyed by topic for cross-turn replace-compare.
    # last_assertion is the most recent store (deictic inherit / FYI).
    assertions_by_topic: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_assertion: Optional[Dict[str, Any]] = None


class ConversationSystem:
    """Dialogue-state manager driven by Language meaning packets."""

    def __init__(self, thalamus=None):
        self.running = True
        self.state = ConversationState()
        self.thalamus = thalamus or get_thalamus()
        self.novelty_lobe = None

    # ------------------------------------------------------------------
    # Language packet access
    # ------------------------------------------------------------------

    def _packet_from_context(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(context, dict):
            return None
        for key in ("language_understanding",):
            value = context.get(key)
            if isinstance(value, dict) and value.get("contract") == "language_understanding_v1":
                return value
            if isinstance(value, dict) and (
                "speech_act" in value or "clauses" in value or "tokens" in value
            ):
                return value
        perception = context.get("perception")
        if isinstance(perception, dict):
            value = perception.get("language_understanding")
            if isinstance(value, dict):
                return value
        return None

    def _request_language_packet(self, user_input: str) -> Optional[Dict[str, Any]]:
        """Ask Language via Thalamus — Conversation does not run OEWN itself."""
        if self.thalamus is None or not user_input:
            return None
        try:
            if not self.thalamus._has_lobe("language"):
                return None
            response = self.thalamus.send_and_wait(
                "language",
                "comprehend",
                {"text": user_input, "user_input": user_input},
            )
            if response.get("status") != "success":
                return None
            body = response.get("content") if isinstance(response.get("content"), dict) else {}
            understanding = body.get("language_understanding")
            if isinstance(understanding, dict):
                return understanding
            if isinstance(body, dict) and (
                "speech_act" in body or "clauses" in body or "tokens" in body
            ):
                return body
        except Exception:
            return None
        return None

    # ------------------------------------------------------------------
    # Meaning → dialogue features (Language packet structure only)
    # ------------------------------------------------------------------

    @staticmethod
    def _token_surfaces(packet: Dict[str, Any]) -> List[str]:
        tokens = packet.get("tokens") or []
        surfaces: List[str] = []
        for tok in tokens:
            if not isinstance(tok, dict):
                continue
            surface = str(tok.get("surface") or "").strip().lower()
            if surface:
                surfaces.append(surface)
        return surfaces

    @staticmethod
    def _token_entries(packet: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [t for t in (packet.get("tokens") or []) if isinstance(t, dict)]

    @staticmethod
    def _primary_clause(packet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        clauses = packet.get("clauses") or []
        for clause in clauses:
            if isinstance(clause, dict) and clause.get("predicate_surface"):
                return clause
        return None

    def _closed_surface(self, packet: Dict[str, Any], surface: str) -> bool:
        """True when Language tagged this surface as closed-class (not a topic)."""
        low = str(surface or "").strip().lower()
        if not low:
            return True
        for tok in self._token_entries(packet):
            if str(tok.get("surface") or "").strip().lower() != low:
                continue
            if tok.get("kind") in _CLOSED_TOKEN_KINDS:
                return True
        # Multiword: junk if every alpha part is closed-class in the packet
        parts = [p for p in low.split() if p.isalpha()]
        if not parts:
            return True
        kind_by_surf = {
            str(t.get("surface") or "").lower(): t.get("kind")
            for t in self._token_entries(packet)
        }
        if parts and all(kind_by_surf.get(p) in _CLOSED_TOKEN_KINDS for p in parts):
            return True
        return False

    def _junk_topic(self, packet: Dict[str, Any], concept: str) -> bool:
        """Reject closed-class / deictic / unresolved scraps as topic anchors."""
        low = " ".join(str(concept or "").lower().split())
        if not low:
            return True
        if self._closed_surface(packet, low):
            return True
        # WH shells from Language kind=wh
        parts = low.split()
        if parts:
            for tok in self._token_entries(packet):
                if str(tok.get("surface") or "").lower() == parts[0] and tok.get("kind") == "wh":
                    return True
        return False

    def _topic_from_packet(self, packet: Dict[str, Any]) -> Optional[str]:
        """Topic = Language topic_head (content NP head) — never predicate glue."""
        # Language owns head extraction (theme/patient/about). Trust topic_head first.
        head = packet.get("topic_head")
        if isinstance(head, str) and head.strip():
            cleaned = head.strip().lower()
            if not self._junk_topic(packet, cleaned):
                return cleaned
        clause = self._primary_clause(packet)
        if clause and isinstance(clause.get("topic_head"), str) and clause.get("topic_head").strip():
            cleaned = str(clause.get("topic_head")).strip().lower()
            if not self._junk_topic(packet, cleaned):
                return cleaned

        mentions = [m for m in (packet.get("mentions") or []) if isinstance(m, dict)]
        mention_by_id = {m.get("mention_id"): m for m in mentions if m.get("mention_id")}
        roles = {}
        if clause:
            roles = clause.get("roles") if isinstance(clause.get("roles"), dict) else {}

        def _head_of(mention: Dict[str, Any]) -> Optional[str]:
            if mention.get("pronoun") or mention.get("unresolved_reference"):
                return None
            props = mention.get("properties") if isinstance(mention.get("properties"), dict) else {}
            for key in ("head_lemma", "head"):
                val = props.get(key)
                if isinstance(val, str) and val.isalpha() and not self._junk_topic(packet, val):
                    return val.lower()
            surface = mention.get("concept_surface") or mention.get("surface")
            if not surface:
                return None
            parts = [p for p in str(surface).lower().split() if p.isalpha()]
            if not parts:
                return None
            # Prefer last content token as NP head ("aluminum gasket" → gasket)
            for part in reversed(parts):
                if not self._junk_topic(packet, part):
                    return part
            return None

        # Unresolved deictic theme ("It's copper") → inherit prior assertion / dialogue topic.
        # Never treat predicative attribute/complement as the topic.
        theme_mid = roles.get("theme") or roles.get("experiencer") or roles.get("patient")
        theme_m = mention_by_id.get(theme_mid) if theme_mid else None
        if theme_m and (
            theme_m.get("unresolved_reference")
            or (theme_m.get("pronoun") and not theme_m.get("concept_surface"))
        ):
            if self.state.last_assertion and self.state.last_assertion.get("topic_head"):
                return str(self.state.last_assertion["topic_head"]).strip().lower()
            if self.state.current_topic:
                return str(self.state.current_topic).strip().lower()

        if clause:
            # about-NP first (same rule as Language.topic_head). Never "attribute".
            for role in ("about", "theme", "patient", "topic"):
                mid = roles.get(role)
                mention = mention_by_id.get(mid) if mid else None
                if not mention:
                    continue
                if role != "about" and mention.get("kind") == "proper_noun":
                    continue
                head = _head_of(mention)
                if head:
                    return head
        attr_mid = roles.get("attribute")
        for mention in mentions:
            if attr_mid and mention.get("mention_id") == attr_mid:
                continue  # complement is not topic
            head = _head_of(mention)
            if head:
                return head
        # Never fall back to predicate_surface — that produced "hold"/"fail"/"is aluminum".
        return None

    def _social_move_from_packet(self, packet: Dict[str, Any]) -> Optional[str]:
        """social_open / social_close from OEWN sense defs in the Language packet."""
        tokens = self._token_entries(packet)
        if not tokens:
            return None
        greeting_hit = False
        farewell_hit = False
        content_tokens = 0
        for tok in tokens:
            kind = tok.get("kind")
            if kind in _CLOSED_TOKEN_KINDS:
                continue
            content_tokens += 1
            for sense in tok.get("senses") or []:
                if not isinstance(sense, dict):
                    continue
                definition = str(sense.get("definition") or "").lower()
                if "expression of greeting" in definition:
                    greeting_hit = True
                if "farewell" in definition:
                    farewell_hit = True
        if farewell_hit and not greeting_hit:
            return "social_close"
        if greeting_hit:
            return "social_open"
        clauses = packet.get("clauses") or []
        if not clauses and content_tokens <= 3 and float(packet.get("confidence") or 0.0) <= 0.35:
            return "social_fragment"
        return None

    def _assertion_from_packet(self, packet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Pull Language assertion frame (topic + predicative complement)."""
        if not isinstance(packet, dict):
            return None
        raw = packet.get("assertion")
        if isinstance(raw, dict) and raw.get("assertable"):
            return dict(raw)
        # Fallback: rebuild from clause predicative_complement if top-level missing.
        clause = self._primary_clause(packet)
        if not clause:
            return None
        comp = clause.get("predicative_complement") or packet.get("predicative_complement")
        if not isinstance(comp, dict):
            return None
        lemma = str(comp.get("lemma") or comp.get("surface") or "").strip().lower()
        if not lemma:
            return None
        contrast = packet.get("contrast") if isinstance(packet.get("contrast"), dict) else {}
        theme_mid = None
        roles = clause.get("roles") if isinstance(clause.get("roles"), dict) else {}
        theme_mid = roles.get("theme") or roles.get("experiencer") or roles.get("patient")
        theme_m = None
        for m in packet.get("mentions") or []:
            if isinstance(m, dict) and m.get("mention_id") == theme_mid:
                theme_m = m
                break
        theme_unresolved = bool(theme_m and theme_m.get("unresolved_reference"))
        theme_is_deictic = bool(
            theme_m
            and (theme_m.get("pronoun") or theme_m.get("unresolved_reference"))
        )
        theme_concept = None
        if theme_m:
            theme_concept = theme_m.get("concept_surface")
            if not theme_concept and not theme_m.get("unresolved_reference"):
                theme_concept = theme_m.get("surface")
            if isinstance(theme_concept, str):
                theme_concept = theme_concept.strip().lower() or None
        return {
            "topic_head": packet.get("topic_head") or clause.get("topic_head"),
            "theme_mention_id": theme_mid,
            "theme_is_deictic": theme_is_deictic,
            "theme_unresolved": theme_unresolved,
            "theme_concept": theme_concept,
            "predicate_lemma": str(clause.get("predicate_surface") or "").lower() or None,
            "complement": {
                "kind": comp.get("kind"),
                "surface": comp.get("surface"),
                "lemma": lemma,
                "mention_id": comp.get("mention_id"),
                "senses": list(comp.get("senses") or []),
                "compete_keys": list(comp.get("compete_keys") or []),
            },
            "polarity": (
                "negative" if contrast.get("contrastive_negation") else "positive"
            ),
            "copular": bool(clause.get("copular")),
            "assertable": True,
        }

    @staticmethod
    def _complement_key(assertion: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(assertion, dict):
            return None
        comp = assertion.get("complement")
        if not isinstance(comp, dict):
            return None
        key = str(comp.get("lemma") or comp.get("surface") or "").strip().lower()
        return key or None

    def _assertion_topic_key(
        self,
        assertion: Optional[Dict[str, Any]],
        *,
        prior: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Topic identity for replace-compare.

        Content topic_head wins. Unresolved deictic theme (it/that) inherits
        prior assertion topic / referent_stack topic. Bound pronouns use
        theme_concept (user/mercy) so 'I am hungry'→'I am not hungry' can match.
        """
        if not isinstance(assertion, dict):
            return None
        head = assertion.get("topic_head")
        if isinstance(head, str) and head.strip():
            return head.strip().lower()
        if assertion.get("theme_unresolved") or (
            assertion.get("theme_is_deictic") and not assertion.get("theme_concept")
        ):
            if isinstance(prior, dict):
                phead = prior.get("topic_head")
                if isinstance(phead, str) and phead.strip():
                    return phead.strip().lower()
            stack = list(self.state.referent_stack)
            for rec in reversed(stack):
                t = rec.get("topic") or rec.get("concept_surface")
                if isinstance(t, str) and t.strip():
                    low = t.strip().lower()
                    # Prefer NP heads already used as topics, not attributes.
                    if low:
                        return low
            return None
        concept = assertion.get("theme_concept")
        if isinstance(concept, str) and concept.strip():
            return concept.strip().lower()
        return None

    def _prior_assertion_for(self, topic_key: Optional[str]) -> Optional[Dict[str, Any]]:
        """Prior assertable frame for this topic (not merely the chronologically last turn)."""
        if topic_key:
            hit = self.state.assertions_by_topic.get(topic_key.casefold())
            if isinstance(hit, dict) and hit.get("assertable"):
                return hit
        # Deictic with no topic yet: fall back to most recent assertion.
        if isinstance(self.state.last_assertion, dict) and self.state.last_assertion.get("assertable"):
            return self.state.last_assertion
        return None

    def _is_correction(self, packet: Dict[str, Any]) -> bool:
        """Correction = replace prior asserted content across turns.

        REQUIRED: same topic (or anaphor to it) AND either:
          1) polarity retract of the SAME complement, OR
          2) new complement that OEWN marks as a competing value of the SAME
             kind of claim (complements_compete) — e.g. aluminum↔copper,
             awful↔fine, loose↔tight. NOT aluminum↔round, red↔fast, steel↔loose.

        FORBIDDEN shortcuts (owned FAILs): leading 'no' alone; cue words;
        frozenset discourse lists; any-different-lemma replace (5e7003c /
        Matty); stamping PASS on 'No, X' without replace structure.
        """
        current = self._assertion_from_packet(packet)
        if not isinstance(current, dict) or not current.get("assertable"):
            return False
        # Resolve current topic (anaphor may inherit from last_assertion / stack).
        curr_topic = self._assertion_topic_key(current, prior=self.state.last_assertion)
        if not curr_topic and current.get("theme_unresolved"):
            curr_topic = self._assertion_topic_key(current, prior=self.state.last_assertion)
        prior = self._prior_assertion_for(curr_topic)
        if not isinstance(prior, dict) or not prior.get("assertable"):
            return False
        # Re-resolve with the matched prior (anaphor → that topic).
        curr_topic = self._assertion_topic_key(current, prior=prior)
        prev_topic = self._assertion_topic_key(prior)
        if not prev_topic or not curr_topic:
            return False
        if prev_topic.casefold() != curr_topic.casefold():
            return False
        prev_comp = self._complement_key(prior)
        curr_comp = self._complement_key(current)
        if not prev_comp or not curr_comp:
            return False
        prev_pol = str(prior.get("polarity") or "positive")
        curr_pol = str(current.get("polarity") or "positive")
        # Same complement + clause polarity retract (not fronted "No,") → correction.
        if prev_comp == curr_comp:
            if prev_pol == "positive" and curr_pol == "negative":
                return True
            return False
        # Different lemma: only if OEWN same-kind competing values.
        prev_frame = prior.get("complement") if isinstance(prior.get("complement"), dict) else {}
        curr_frame = current.get("complement") if isinstance(current.get("complement"), dict) else {}
        return bool(complements_compete(prev_frame, curr_frame))

    def _store_assertion_from_packet(
        self,
        packet: Dict[str, Any],
        *,
        speech_act: str,
        resolved_topic: Optional[str] = None,
    ) -> None:
        """Remember assertable proposition for later replace-compare."""
        if speech_act == "question":
            return
        assertion = self._assertion_from_packet(packet)
        if not assertion:
            return
        # Only inherit dialogue/prior topic for unresolved deictic themes ("It's copper").
        # Bound subjects (I/you) and content topics use their own identity — do NOT
        # paste the previous dialogue topic onto a new unrelated assertion
        # ("I am not hungry" must not become topic=gasket).
        deictic_inherit = bool(
            assertion.get("theme_unresolved")
            or (
                assertion.get("theme_is_deictic")
                and not assertion.get("theme_concept")
            )
        )
        if deictic_inherit:
            topic = resolved_topic or self._assertion_topic_key(
                assertion, prior=self.state.last_assertion
            )
        else:
            topic = self._assertion_topic_key(assertion, prior=None)
        if not topic:
            return  # no comparable topic identity — do not store a half frame
        stored = dict(assertion)
        stored["topic_head"] = topic
        stored["assertable"] = True
        self.state.last_assertion = stored
        self.state.assertions_by_topic[topic.casefold()] = stored

    def _is_affect_share(self, packet: Dict[str, Any]) -> bool:
        """Affect from Language OEWN affect signal — not a 'feel/feeling' list."""
        affect = packet.get("affect") if isinstance(packet.get("affect"), dict) else {}
        return bool(affect.get("present"))

    def _detect_deictic_hooks(
        self, packet: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Cross-turn hooks from Language unresolved refs / pronoun / proform / demonstrative."""
        hooks: List[Dict[str, Any]] = []
        seen = set()

        for item in packet.get("unresolved_references") or []:
            if not isinstance(item, dict):
                continue
            surface = str(item.get("surface") or "").strip().lower()
            if not surface:
                continue
            key = ("surface", surface)
            if key in seen:
                continue
            seen.add(key)
            hooks.append(
                {
                    "kind": "deictic",
                    "surface": surface,
                    "mention_id": item.get("mention_id"),
                    "source": "language_unresolved_reference",
                }
            )

        for mention in packet.get("mentions") or []:
            if not isinstance(mention, dict):
                continue
            kind = str(mention.get("kind") or "")
            is_deictic = bool(
                mention.get("pronoun")
                or mention.get("unresolved_reference")
                or kind in {"pronoun", "demonstrative", "proform"}
                or (mention.get("properties") or {}).get("deictic")
            )
            if not is_deictic:
                continue
            # Bound deictics (I/you/me → user/mercy) are not cross-turn hooks
            if mention.get("concept_surface") and not mention.get("unresolved_reference"):
                continue
            surface = str(mention.get("surface") or "").strip().lower()
            key = ("surface", surface)
            if key in seen:
                continue
            seen.add(key)
            hooks.append(
                {
                    "kind": "deictic" if kind != "proform" else "proform",
                    "surface": surface,
                    "mention_id": mention.get("mention_id"),
                    "source": "language_mention",
                }
            )
        return hooks

    def _resolve_referents(
        self, hooks: Sequence[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Bind Language deictics/proforms to prior-turn content on the referent stack."""
        resolved: List[Dict[str, Any]] = []
        stack = list(self.state.referent_stack)
        if not stack:
            for hook in hooks:
                resolved.append(
                    {
                        **hook,
                        "resolved": False,
                        "target": None,
                        "reason": "empty_referent_stack",
                    }
                )
            return resolved

        for hook in hooks:
            # Most recent content referent — grammar already marked the hook as deictic/proform.
            target = stack[-1]
            resolved.append(
                {
                    "kind": hook.get("kind"),
                    "surface": hook.get("surface"),
                    "source": hook.get("source"),
                    "resolved": True,
                    "target": {
                        "surface": target.get("surface"),
                        "concept_surface": target.get("concept_surface"),
                        "mention_id": target.get("mention_id"),
                        "referent_id": target.get("referent_id"),
                        "turn_index": target.get("turn_index"),
                        "role": target.get("role"),
                        "topic": target.get("topic"),
                    },
                    "reason": "dialogue_referent_stack",
                }
            )
        return resolved

    def _push_referents_from_packet(
        self,
        packet: Dict[str, Any],
        *,
        turn_index: int,
        topic: Optional[str],
        representation_referent_ids: Optional[Sequence[str]] = None,
    ) -> None:
        mentions = [m for m in (packet.get("mentions") or []) if isinstance(m, dict)]
        clause = self._primary_clause(packet)
        roles = (clause or {}).get("roles") if isinstance((clause or {}).get("roles"), dict) else {}
        id_to_role = {mid: role for role, mid in roles.items() if mid}
        ref_ids = [str(x) for x in (representation_referent_ids or []) if x]

        for idx, mention in enumerate(mentions):
            if mention.get("pronoun") or mention.get("unresolved_reference"):
                continue
            surface = str(mention.get("surface") or "").strip()
            concept = str(mention.get("concept_surface") or surface).strip()
            if not surface:
                continue
            if self._junk_topic(packet, surface) or self._junk_topic(packet, concept):
                continue
            record = {
                "surface": surface,
                "concept_surface": concept,
                "mention_id": mention.get("mention_id"),
                "referent_id": ref_ids[idx] if idx < len(ref_ids) else None,
                "turn_index": turn_index,
                "role": id_to_role.get(mention.get("mention_id")),
                "topic": topic,
            }
            self.state.referent_stack.append(record)

    def _topic_shifted(
        self,
        packet: Dict[str, Any],
        new_topic: Optional[str],
        previous_topic: Optional[str],
    ) -> bool:
        """Topic shift = content NP/topic from packet differs from prior turn topic.

        No discourse cue list (anyway/instead/…). First topic set is not a shift.
        """
        if not new_topic or not previous_topic:
            return False
        return new_topic.casefold() != previous_topic.casefold()

    def _answers_mercy_question(self, packet: Dict[str, Any], speech_act: str) -> bool:
        if not self.state.pending_mercy_questions:
            return False
        if speech_act == "question":
            return False
        if self._is_correction(packet):
            return False
        social = self._social_move_from_packet(packet)
        if social in {"social_open", "social_close"}:
            return False
        return speech_act in {"declarative", "imperative"} or bool(
            self._primary_clause(packet)
        )

    def _dialogue_move(
        self,
        packet: Dict[str, Any],
        *,
        speech_act: str,
        topic_shifted: bool,
        is_correction: bool,
        is_answer: bool,
        social_move: Optional[str],
        deictic_hooks: Sequence[Dict[str, Any]],
    ) -> str:
        # Priority from structure: social → answer/correction → speech_act →
        # affect (Language OEWN) → topic change → deictic follow-up → assertion.
        if social_move == "social_close":
            return "social_close"
        if social_move == "social_open":
            return "social_open"
        if is_answer:
            return "answer"
        if is_correction:
            return "correction"
        if speech_act == "question":
            return "question"
        if speech_act == "imperative":
            if deictic_hooks:
                return "referent_followup"
            return "request"
        if self._is_affect_share(packet):
            return "affect_share"
        if topic_shifted:
            return "topic_shift"
        if deictic_hooks:
            return "referent_followup"
        if social_move == "social_fragment":
            return "social_fragment"
        if speech_act == "declarative" or self._primary_clause(packet):
            return "assertion"
        return "unparsed"

    @staticmethod
    def _intent_compatibility(dialogue_move: str) -> str:
        """Thin compatibility label for Reasoning — derived from dialogue_move only."""
        mapping = {
            "question": "question",
            "request": "request",
            "correction": "statement",
            "answer": "statement",
            "topic_shift": "topic_shift",
            "assertion": "statement",
            "affect_share": "emotional_share",
            "social_open": "greeting",
            "social_close": "goodbye",
            "social_fragment": "conversation",
            "referent_followup": "request",
            "unparsed": "conversation",
        }
        return mapping.get(dialogue_move, "conversation")

    def _entities_from_packet(self, packet: Dict[str, Any]) -> List[str]:
        """Mentions from Language — not Conversation capital-letter regex."""
        entities: List[str] = []
        for mention in packet.get("mentions") or []:
            if not isinstance(mention, dict):
                continue
            if mention.get("pronoun") or mention.get("unresolved_reference"):
                continue
            surface = str(mention.get("concept_surface") or mention.get("surface") or "").strip()
            if not surface or self._junk_topic(packet, surface):
                continue
            if surface not in entities:
                entities.append(surface)
        return entities

    def _mark_mercy_question_answered(self) -> Optional[Dict[str, Any]]:
        if not self.state.pending_mercy_questions:
            return None
        answered = self.state.pending_mercy_questions.pop(0)
        answered = dict(answered)
        answered["answered"] = True
        answered["answered_at_turn"] = self.state.turn_index
        # Mirror into open_questions
        for item in self.state.open_questions:
            if (
                item.get("speaker") == "mercy"
                and item.get("thread_id") == answered.get("thread_id")
                and not item.get("answered")
            ):
                item["answered"] = True
                item["answered_at_turn"] = self.state.turn_index
                break
        return answered

    def note_mercy_question(self, text: str, *, topic: Optional[str] = None) -> None:
        """Record a question Mercy asked so later user turns can answer it."""
        text = (text or "").strip()
        if not text:
            return
        thread_id = f"mercy_q_{self.state.turn_index}_{len(self.state.pending_mercy_questions)}"
        record = {
            "thread_id": thread_id,
            "kind": "question",
            "text": text,
            "speaker": "mercy",
            "turn_index": self.state.turn_index,
            "topic": topic or self.state.current_topic,
            "answered": False,
        }
        self.state.pending_mercy_questions.append(record)
        self.state.open_questions.append(dict(record))
        self.state.unfinished_threads.append(
            {
                "thread_id": thread_id,
                "kind": "mercy_question",
                "text": text,
                "status": "open",
            }
        )

    # ------------------------------------------------------------------
    # Public understand API
    # ------------------------------------------------------------------

    def understand(self, user_input: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Build dialogue state for this turn from Language meaning packets."""
        if context is None:
            context = {}
        if not isinstance(context, dict):
            context = {}

        text = (user_input or "").strip()
        self.state.turn_index += 1
        turn_index = self.state.turn_index

        self.state.history.append(
            {
                "user": text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "turn_index": turn_index,
            }
        )

        packet = self._packet_from_context(context)
        packet_source = "context"
        if packet is None:
            packet = self._request_language_packet(text)
            packet_source = "language_via_thalamus" if packet is not None else "missing"

        representation_referent_ids = context.get("referent_ids") or context.get(
            "representation_referent_ids"
        )
        if not isinstance(representation_referent_ids, list):
            perception = context.get("perception") if isinstance(context.get("perception"), dict) else {}
            representation_referent_ids = perception.get("referent_ids") or []

        previous_topic = self.state.current_topic
        if not isinstance(packet, dict):
            understanding = {
                "intent": "conversation",
                "confidence": 0.0,
                "entities": [],
                "slots": {},
                "ask_kind": None,
                "topic": previous_topic,
                "previous_topic": previous_topic,
                "topic_shifted": False,
                "sentiment": None,
                "context_length": len(self.state.history),
                "curiosity_question": None,
                "dialogue_move": "unparsed",
                "dialogue_source": "no_language_packet",
                "language_packet_source": packet_source,
                "open_questions": list(self.state.open_questions),
                "unfinished_threads": list(self.state.unfinished_threads),
                "resolved_referents": [],
                "pending_mercy_questions": list(self.state.pending_mercy_questions),
                "language_understanding": None,
            }
            self.state.last_dialogue_move = "unparsed"
            return understanding

        speech_act = str(packet.get("speech_act") or "none")
        topic = self._topic_from_packet(packet)
        topic_shifted = self._topic_shifted(packet, topic, previous_topic)
        if topic:
            self.state.previous_topic = previous_topic
            self.state.current_topic = topic
        elif topic_shifted and topic:
            self.state.current_topic = topic

        social_move = self._social_move_from_packet(packet)
        # Correction compares Language assertion frame to last_assertion / anaphor.
        # Must run BEFORE storing this turn's assertion.
        is_correction = self._is_correction(packet)
        is_answer = self._answers_mercy_question(packet, speech_act)
        deictic_hooks = self._detect_deictic_hooks(packet)
        resolved_referents = self._resolve_referents(deictic_hooks) if deictic_hooks else []

        dialogue_move = self._dialogue_move(
            packet,
            speech_act=speech_act,
            topic_shifted=topic_shifted,
            is_correction=is_correction,
            is_answer=is_answer,
            social_move=social_move,
            deictic_hooks=deictic_hooks,
        )

        answered_mercy = None
        if is_answer:
            answered_mercy = self._mark_mercy_question_answered()

        # Open user questions / unfinished threads
        if dialogue_move == "question":
            thread_id = f"user_q_{turn_index}"
            record = {
                "thread_id": thread_id,
                "kind": "question",
                "text": text,
                "speaker": "user",
                "turn_index": turn_index,
                "topic": topic or self.state.current_topic,
                "answered": False,
            }
            self.state.open_questions.append(record)
            self.state.unfinished_threads.append(
                {
                    "thread_id": thread_id,
                    "kind": "user_question",
                    "text": text,
                    "status": "open",
                }
            )
        if dialogue_move == "topic_shift":
            self.state.unfinished_threads.append(
                {
                    "thread_id": f"topic_{turn_index}",
                    "kind": "topic_shift",
                    "text": text,
                    "from_topic": previous_topic,
                    "to_topic": topic or self.state.current_topic,
                    "status": "open",
                }
            )
        if dialogue_move == "correction":
            self.state.unfinished_threads.append(
                {
                    "thread_id": f"correction_{turn_index}",
                    "kind": "correction",
                    "text": text,
                    "status": "open",
                    "resolved_referents": resolved_referents,
                }
            )

        # Push this turn's contentful mentions AFTER resolving deictics against prior stack
        self._push_referents_from_packet(
            packet,
            turn_index=turn_index,
            topic=topic or self.state.current_topic,
            representation_referent_ids=representation_referent_ids,
        )

        # If follow-up resolved a referent and topic empty, inherit target topic/surface
        inherited_topic = None
        if resolved_referents:
            for item in resolved_referents:
                target = item.get("target") if item.get("resolved") else None
                if isinstance(target, dict):
                    inherited_topic = target.get("topic") or target.get("concept_surface")
                    if inherited_topic:
                        break
            if inherited_topic and not topic:
                topic = str(inherited_topic).lower()
                if not self.state.current_topic:
                    self.state.current_topic = topic

        # Store this turn's assertable proposition (resolved topic) for next-turn replace.
        store_topic = topic or self.state.current_topic
        if is_correction and not store_topic:
            # Prefer topic matched for the correction replace.
            cur_a = self._assertion_from_packet(packet)
            store_topic = self._assertion_topic_key(
                cur_a, prior=self.state.last_assertion
            ) if cur_a else None
        # Prior frame for this topic (before overwrite) — not merely chronological last.
        prior_for_note = None
        if store_topic:
            prior_for_note = self._prior_assertion_for(store_topic)
        if prior_for_note is None and self.state.last_assertion:
            prior_for_note = dict(self.state.last_assertion)
        else:
            prior_for_note = dict(prior_for_note) if prior_for_note else None
        self._store_assertion_from_packet(
            packet, speech_act=speech_act, resolved_topic=store_topic
        )
        # Enrich open correction thread with replace structure (not cue words).
        if dialogue_move == "correction" and self.state.unfinished_threads:
            for thread in reversed(self.state.unfinished_threads):
                if thread.get("kind") == "correction" and thread.get("thread_id", "").startswith(
                    f"correction_{turn_index}"
                ):
                    thread["replaced"] = {
                        "topic": store_topic
                        or (prior_for_note or {}).get("topic_head"),
                        "from_complement": self._complement_key(prior_for_note),
                        "to_complement": self._complement_key(self.state.last_assertion),
                        "from_polarity": (prior_for_note or {}).get("polarity"),
                        "to_polarity": (self.state.last_assertion or {}).get("polarity"),
                    }
                    break

        intent = self._intent_compatibility(dialogue_move)
        try:
            confidence = float(packet.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        # Dialogue-structure confidence floor when move is clear from speech_act
        if dialogue_move in {"question", "request", "topic_shift", "correction", "social_open", "social_close"}:
            confidence = max(confidence, 0.7)
        if resolved_referents and any(r.get("resolved") for r in resolved_referents):
            confidence = max(confidence, 0.75)

        entities = self._entities_from_packet(packet)
        # Prefer resolved referent targets as entities for follow-ups
        for item in resolved_referents:
            if not item.get("resolved"):
                continue
            target = item.get("target") or {}
            surface = target.get("concept_surface") or target.get("surface")
            if surface and surface not in entities:
                entities.insert(0, surface)

        self.state.last_dialogue_move = dialogue_move
        self.state.last_resolved_referents = list(resolved_referents)

        understanding = {
            # Compatibility for Reasoning — derived from dialogue_move, not regex.
            "intent": intent,
            "confidence": min(confidence, 1.0),
            "entities": entities,
            "slots": {},  # Conversation no longer owns slot extraction
            "ask_kind": dialogue_move,
            "topic": topic or self.state.current_topic,
            "previous_topic": previous_topic,
            "topic_shifted": topic_shifted or dialogue_move == "topic_shift",
            "sentiment": None,  # Emotion owns affect; Conversation does not
            "context_length": len(self.state.history),
            "curiosity_question": None,
            # Dialogue-native fields (Step 3)
            "dialogue_move": dialogue_move,
            "dialogue_source": "language_packet",
            "language_packet_source": packet_source,
            "speech_act": speech_act,
            "open_questions": [dict(x) for x in self.state.open_questions if not x.get("answered")][-12:],
            "unfinished_threads": [dict(x) for x in self.state.unfinished_threads][-12:],
            "resolved_referents": resolved_referents,
            "pending_mercy_questions": [dict(x) for x in self.state.pending_mercy_questions],
            "answered_mercy_question": answered_mercy,
            "deictic_hooks": list(deictic_hooks),
            "is_correction": is_correction,
            "last_assertion": dict(self.state.last_assertion)
            if isinstance(self.state.last_assertion, dict)
            else None,
            "language_understanding": packet,
        }
        return understanding

    def _register_with_thalamus(self):
        """Register with Thalamus - DIRECT FUNCTION CALL (NO SOCKETS)"""
        try:
            result = self.thalamus.register_lobe("conversation", self)
            if result.get("status") == "success":
                print("✅ Conversation registered with Thalamus (direct function calls)")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register with Thalamus: {e}")
            return False

    def _push_intent_to_reasoning(self, user_input: str, understanding: Dict[str, Any]):
        """Push dialogue-move hints to Reasoning (compat intent derived from packets)."""
        intent = understanding.get("intent", "conversation")
        confidence = understanding.get("confidence", 0.5)
        dialogue_move = understanding.get("dialogue_move", "unparsed")

        strategy_mapping = {
            "greeting": "social_greeting",
            "question": "information_gathering",
            "emotional_share": "empathic_listen",
            "topic_shift": "topic_reorient",
            "request": "help_seeking",
            "statement": "expression_analysis",
            "goodbye": "social_closing",
            "conversation": "engagement",
        }
        suggested_strategy = strategy_mapping.get(intent, "engagement")
        if dialogue_move == "correction":
            suggested_strategy = "correction_ack"
        elif dialogue_move == "answer":
            suggested_strategy = "answer_integration"
        elif dialogue_move == "referent_followup":
            suggested_strategy = "referent_continue"

        try:
            self.thalamus.send_message(
                destination="reasoning",
                msg_type="intent_hints",
                content={
                    "user_input": user_input,
                    "intent": intent,
                    "dialogue_move": dialogue_move,
                    "confidence": confidence,
                    "suggested_strategy": suggested_strategy,
                    "entities": understanding.get("entities", []),
                    "topic": understanding.get("topic"),
                    "resolved_referents": understanding.get("resolved_referents") or [],
                    "open_questions": understanding.get("open_questions") or [],
                },
                source="conversation",
            )
        except Exception as e:
            print(f"⚠️  Failed to push intent to Reasoning: {e}")

    def start(self):
        """Start conversation - register with Thalamus (NO SOCKETS)"""
        print("💬 Conversation Lobe: Registering with Thalamus...")
        print("   Dialogue state from Language packets (no regex intent brain)")
        print("   Communication: Direct function calls (NO SOCKETS)")

        if not self._register_with_thalamus():
            print("❌ Failed to register with Thalamus")
            return

        while self.running:
            time.sleep(0.1)

    @staticmethod
    def _linguistic_context(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Carry Language-owned structure into Conversation without reinterpreting it."""
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        perception = (
            payload.get("perception") if isinstance(payload.get("perception"), dict) else {}
        )
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

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming message"""
        msg_type = message.get("type")
        payload = message.get("content", message)

        if msg_type == "health":
            return {"status": "success", "healthy": True, "pid": os.getpid()}

        if msg_type == "understand":
            user_input = payload.get("user_input", "")
            context = payload.get("context", {})
            if not isinstance(context, dict):
                context = {}
            context = dict(context)

            perception = payload.get("perception")
            if isinstance(perception, dict):
                context["perception"] = perception
            attention = payload.get("attention")
            if isinstance(attention, dict):
                context["attention"] = attention

            routed = self._linguistic_context(payload)
            if isinstance(routed.get("language_understanding"), dict):
                context["language_understanding"] = routed["language_understanding"]
            for key in ("proposition_ids", "referent_ids", "concept_ids"):
                if routed.get(key):
                    context[key] = list(routed[key])

            understanding = self.understand(user_input, context)

            # Fold perception observables (not sentiment ownership).
            perc = (
                context.get("perception")
                if isinstance(context.get("perception"), dict)
                else {}
            )
            if perc:
                understanding["perception_words"] = list(perc.get("words") or [])
                concepts = perc.get("concepts")
                if isinstance(concepts, dict):
                    understanding["perception_concepts"] = list(concepts.get("words") or [])
                else:
                    understanding["perception_concepts"] = list(concepts or [])
                understanding["perception_modality"] = perc.get("modality") or "text"
                understanding["perception_novelty_flags"] = list(
                    perc.get("novelty_flags") or []
                )
                try:
                    understanding["novelty_score"] = float(perc.get("novelty_score") or 0.0)
                except (TypeError, ValueError):
                    understanding["novelty_score"] = 0.0
                understanding["novelty_is_novel"] = bool(perc.get("novelty_is_novel"))
                if isinstance(perc.get("novelty"), dict):
                    understanding["novelty"] = dict(perc.get("novelty") or {})

            attn = (
                context.get("attention")
                if isinstance(context.get("attention"), dict)
                else {}
            )
            if attn:
                understanding["attention_focus"] = attn.get("focus")
                understanding["attention_focus_text"] = attn.get("focus_text")
                understanding["attention_focus_score"] = attn.get("focus_score")
                ranked = attn.get("ranked") or []
                understanding["attention_ranked"] = [
                    {
                        "id": r.get("id"),
                        "score": r.get("score"),
                        "text": r.get("text"),
                        "source": r.get("source"),
                    }
                    for r in ranked[:8]
                    if isinstance(r, dict)
                ]

            if isinstance(routed.get("language_understanding"), dict):
                understanding["representation_proposition_ids"] = routed["proposition_ids"]
                understanding["representation_referent_ids"] = routed["referent_ids"]
                understanding["representation_concept_ids"] = routed["concept_ids"]
                understanding["linguistic_context_source"] = "language_via_shared_representation"

            # If Language produced a curiosity question via later path, allow noting it
            content = {
                "understanding": understanding,
                "intent": understanding.get("intent"),
                "confidence": understanding.get("confidence"),
                "dialogue_move": understanding.get("dialogue_move"),
                "topic": understanding.get("topic"),
                "topic_shifted": understanding.get("topic_shifted"),
                "entities": understanding.get("entities", []),
                "slots": understanding.get("slots", {}),
                "ask_kind": understanding.get("ask_kind"),
                "resolved_referents": understanding.get("resolved_referents") or [],
                "open_questions": understanding.get("open_questions") or [],
                "sentiment": None,
            }
            if isinstance(understanding.get("language_understanding"), dict):
                content["language_understanding"] = understanding["language_understanding"]
            if isinstance(routed.get("language_understanding"), dict):
                content["proposition_ids"] = routed["proposition_ids"]
                content["referent_ids"] = routed["referent_ids"]
                content["concept_ids"] = routed["concept_ids"]
            return {"status": "success", "content": content}

        if msg_type == "note_mercy_question":
            text = payload.get("text") or payload.get("question") or ""
            topic = payload.get("topic")
            self.note_mercy_question(text, topic=topic)
            return {
                "status": "success",
                "content": {
                    "pending_mercy_questions": list(self.state.pending_mercy_questions)
                },
            }

        if msg_type == "check_unprompted_speech":
            return {
                "status": "error",
                "message": "check_unprompted_speech removed; speech lobe is decision-only",
                "has_speech": False,
            }

        if msg_type == "get_history":
            return {
                "status": "success",
                "history": list(self.state.history),
                "current_topic": self.state.current_topic,
                "open_questions": list(self.state.open_questions),
                "unfinished_threads": list(self.state.unfinished_threads),
                "referent_stack": list(self.state.referent_stack),
                "pending_mercy_questions": list(self.state.pending_mercy_questions),
            }

        return {"status": "error", "message": f"Unknown message type: {msg_type}"}

    def maybe_curiosity_follow_up(
        self,
        user_input: str,
        emotional_context: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None,
        *,
        force: bool = False,
    ) -> Optional[str]:
        """Maybe one honest follow-up when affect is hot, unresolved, or novel.

        Uses dialogue_move from Language-driven understanding. Does not invent
        questions from Novelty.
        """
        emotional_context = emotional_context if isinstance(emotional_context, dict) else {}
        understanding = understanding if isinstance(understanding, dict) else {}
        intent = understanding.get("intent")
        dialogue_move = understanding.get("dialogue_move")

        if (
            is_mild_social_turn(user_input, intent)
            or is_closing_social_turn(user_input, intent)
            or intent == "goodbye"
            or dialogue_move in {"social_open", "social_close", "social_fragment"}
        ) and not force:
            return None
        if looks_like_teaching_turn(user_input) and not force:
            return None
        if dialogue_move in {"assertion", "answer", "correction"} and looks_like_teaching_turn(
            user_input
        ):
            return None

        try:
            intensity = float(emotional_context.get("intensity", 0.0) or 0.0)
        except (TypeError, ValueError):
            intensity = 0.0
        try:
            novelty_score = float(understanding.get("novelty_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            novelty_score = 0.0
        unresolved = emotional_context.get("unresolved_appraisals") or []
        if not isinstance(unresolved, list):
            unresolved = []
        max_sev = 0.0
        if unresolved:
            try:
                max_sev = max(
                    float(u.get("severity", 0.0) or 0.0)
                    for u in unresolved
                    if isinstance(u, dict)
                )
            except Exception:
                max_sev = 0.55

        elevated_novelty = novelty_score >= 0.55
        eligible = (
            bool(force)
            or bool(unresolved)
            or intensity >= 0.70
            or elevated_novelty
        )
        if not eligible:
            return None

        if not force:
            if unresolved and (intensity >= 0.50 or max_sev >= 0.55):
                if random.random() >= 0.88:
                    return None
            elif elevated_novelty and novelty_score >= 0.70:
                if random.random() >= 0.70:
                    return None
            elif elevated_novelty:
                if random.random() >= 0.45:
                    return None
            elif intensity >= 0.70:
                if random.random() >= 0.55:
                    return None
            else:
                return None

        try:
            question = honest_curiosity_question(user_input, emotional_context)
        except Exception:
            return None
        if question:
            self.note_mercy_question(question, topic=understanding.get("topic"))
        return question

    def shutdown(self):
        """Graceful shutdown"""
        self.running = False


if __name__ == "__main__":
    system = ConversationSystem()
    try:
        system.start()
    except KeyboardInterrupt:
        print("\n🛑 Conversation system shutting down...")
        system.shutdown()
