#!/usr/bin/env python3
"""Shared Representation — common semantic substrate for Mercy lobes.

LOCKED job:
- Own stable concept identity, canonical names/aliases, accepted semantic
  relationships, activation state, and bounded spreading activation.
- Hold transient referent instances and proposition/event structures supplied by
  other lobes so every subsystem can reference the same meaning by stable ID.
- Expose candidate concept IDs for ambiguous or multi-word surface forms.

HARD BOUNDARY:
Shared Representation stores, identifies, links, activates, retrieves, and
exposes representations supplied by other Mercy systems. It MUST NOT infer the
linguistic or cognitive meaning required to create those representations. It
must not parse grammar, determine semantic roles, resolve pronouns, choose word
senses, determine truth, reason, decide intent, generate language, or
independently promote current input into memory.

Existing Concept/Relationship persistence remains the durable substrate.
ReferentInstance and Proposition are transient/in-memory by default and are not
written to shared_representation.json.

Legacy resolve_terms/resolve_from_text behavior is retained for compatibility.
Old representation.py stays unwired (historical only).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from runtime_paths import runtime_dir

_PUNCT_RE = re.compile(r"[^\w\s\-']+", re.UNICODE)
_STOP = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "to", "of", "in", "on",
        "at", "for", "is", "are", "was", "were", "be", "been", "am",
        "i", "me", "my", "you", "your", "we", "our", "they", "them",
        "their", "it", "its", "this", "that", "with", "from", "as", "by",
        "if", "so", "do", "does", "did", "have", "has", "had", "not",
        "no", "yes", "just", "about", "into", "than", "then", "too",
        "very", "can", "could", "would", "should", "will", "shall", "may",
        "might", "must",
    }
)

_VALID_REL_TYPES = frozenset(
    {
        "is_a",
        "has_property",
        "causes",
        "similar_to",
        "opposite_of",
        "associated_with",
        "personal_assoc",
        "co_occurrence",  # legacy live resolve_terms producer
    }
)


@dataclass
class Concept:
    """Stable concept identity in the durable shared substrate."""

    concept_id: str
    canonical_name: str
    aliases: List[str] = field(default_factory=list)
    concept_type: str = "unknown"
    properties: Dict[str, Any] = field(default_factory=dict)
    activation: float = 0.0
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_public(self) -> Dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "id": self.concept_id,
            "canonical_name": self.canonical_name,
            "name": self.canonical_name,
            "aliases": list(self.aliases),
            "concept_type": self.concept_type,
            "properties": dict(self.properties),
            "activation": float(self.activation),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Relationship:
    """Structured durable semantic edge (not a free-form string)."""

    source_id: str
    target_id: str
    rel_type: str
    strength: float = 0.5
    scope: str = "global"  # global | user
    user_id: Optional[str] = None
    created_at: float = 0.0

    def to_public(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "source": self.source_id,
            "target": self.target_id,
            "rel_type": self.rel_type,
            "type": self.rel_type,
            "strength": float(self.strength),
            "confidence": float(self.strength),
            "scope": self.scope,
            "user_id": self.user_id,
            "created_at": self.created_at,
        }


@dataclass
class Provenance:
    """Where a transient representation came from; never a truth judgment."""

    producer_lobe: str
    source_type: str
    turn_id: Optional[str] = None
    clause_id: Optional[str] = None
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)

    def to_public(self) -> Dict[str, Any]:
        return {
            "producer_lobe": self.producer_lobe,
            "source_type": self.source_type,
            "turn_id": self.turn_id,
            "clause_id": self.clause_id,
            "confidence": float(self.confidence),
            "created_at": float(self.created_at),
        }

    @classmethod
    def from_value(cls, value: Any) -> "Provenance":
        if isinstance(value, Provenance):
            return value
        raw = value if isinstance(value, dict) else {}
        producer = str(raw.get("producer_lobe") or raw.get("source_lobe") or "unknown").strip()
        source_type = str(raw.get("source_type") or raw.get("epistemic_status") or "unspecified").strip()
        try:
            confidence = float(raw.get("confidence", 1.0))
        except (TypeError, ValueError):
            confidence = 1.0
        return cls(
            producer_lobe=producer or "unknown",
            source_type=source_type or "unspecified",
            turn_id=(str(raw.get("turn_id")) if raw.get("turn_id") is not None else None),
            clause_id=(
                str(raw.get("clause_id", raw.get("source_clause_idx")))
                if raw.get("clause_id", raw.get("source_clause_idx")) is not None
                else None
            ),
            confidence=max(0.0, min(1.0, confidence)),
            created_at=float(raw.get("created_at") or time.time()),
        )


@dataclass
class ReferentInstance:
    """A particular discourse/situational referent pointing to a Concept."""

    instance_id: str
    concept_id: str
    label: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    provenance: Provenance = field(
        default_factory=lambda: Provenance("unknown", "unspecified")
    )
    user_id: Optional[str] = None
    activation: float = 1.0
    created_at: float = field(default_factory=time.time)
    expires_after_turn: Optional[int] = None

    def to_public(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "id": self.instance_id,
            "concept_id": self.concept_id,
            "label": self.label,
            "properties": dict(self.properties),
            "provenance": self.provenance.to_public(),
            "user_id": self.user_id,
            "activation": float(self.activation),
            "created_at": float(self.created_at),
            "expires_after_turn": self.expires_after_turn,
            "storage_tier": "transient",
        }


@dataclass
class Proposition:
    """Transient n-ary meaning frame supplied by an owning cognitive lobe."""

    proposition_id: str
    predicate_id: str
    roles: Dict[str, str]
    qualifiers: Dict[str, Any] = field(default_factory=dict)
    provenance: Provenance = field(
        default_factory=lambda: Provenance("unknown", "unspecified")
    )
    user_id: Optional[str] = None
    activation: float = 1.0
    created_at: float = field(default_factory=time.time)
    expires_after_turn: Optional[int] = None

    def to_public(self) -> Dict[str, Any]:
        return {
            "proposition_id": self.proposition_id,
            "id": self.proposition_id,
            "predicate_id": self.predicate_id,
            "roles": dict(self.roles),
            "qualifiers": dict(self.qualifiers),
            "provenance": self.provenance.to_public(),
            "user_id": self.user_id,
            "activation": float(self.activation),
            "created_at": float(self.created_at),
            "expires_after_turn": self.expires_after_turn,
            "storage_tier": "transient",
        }


class SharedRepresentationSystem:
    """Common substrate: durable concepts/edges + transient shared meaning."""

    def __init__(
        self,
        thalamus: Any = None,
        store_path: Optional[str | Path] = None,
        *,
        activation_decay: float = 0.15,
        activation_threshold: float = 0.08,
        spread_strength: float = 0.65,
        max_spread_depth: int = 3,
        max_spread_nodes: int = 64,
        highly_active_threshold: float = 0.55,
    ) -> None:
        self.thalamus = thalamus
        self.running = True
        self._lock = threading.RLock()

        self.activation_decay = float(activation_decay)
        self.activation_threshold = float(activation_threshold)
        self.spread_strength = float(spread_strength)
        self.max_spread_depth = int(max_spread_depth)
        self.max_spread_nodes = int(max_spread_nodes)
        self.highly_active_threshold = float(highly_active_threshold)

        if store_path is None:
            self.store_path = Path(runtime_dir()) / "shared_representation.json"
        else:
            self.store_path = Path(store_path)

        self.concepts: Dict[str, Concept] = {}
        self._alias_index: Dict[str, str] = {}
        self._surface_index: Dict[str, List[str]] = {}
        self.global_relationships: List[Relationship] = []
        self.user_relationships: Dict[str, List[Relationship]] = {}
        self.instances: Dict[str, ReferentInstance] = {}
        self.propositions: Dict[str, Proposition] = {}

        self._load()

    @staticmethod
    def _normalize_surface(term: str) -> str:
        t = (term or "").strip().lower()
        t = _PUNCT_RE.sub("", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def _canonical_key(self, term: str) -> str:
        surface = self._normalize_surface(term)
        if not surface:
            return ""
        cid = self._alias_index.get(surface)
        if cid and cid in self.concepts:
            return self.concepts[cid].canonical_name
        return surface

    @staticmethod
    def _bounded_activation(value: Any, default: float = 1.0) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
        return max(0.0, min(1.0, number))

    def _new_concept_id(self) -> str:
        return f"c_{uuid.uuid4().hex[:12]}"

    def _new_instance_id(self) -> str:
        return f"i_{uuid.uuid4().hex[:12]}"

    def _new_proposition_id(self) -> str:
        return f"p_{uuid.uuid4().hex[:12]}"

    def _surface_add(self, surface: str, concept_id: str) -> None:
        surface = self._normalize_surface(surface)
        if not surface:
            return
        bucket = self._surface_index.setdefault(surface, [])
        if concept_id not in bucket:
            bucket.append(concept_id)

    def _index_concept(self, concept: Concept) -> None:
        self.concepts[concept.concept_id] = concept
        names = {concept.canonical_name}
        names.update(self._normalize_surface(a) for a in concept.aliases)
        for name in names:
            if not name:
                continue
            self._alias_index.setdefault(name, concept.concept_id)
            self._surface_add(name, concept.concept_id)

    def _load(self) -> None:
        path = self.store_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(data, dict):
            return
        with self._lock:
            self.concepts.clear()
            self._alias_index.clear()
            self._surface_index.clear()
            self.global_relationships.clear()
            self.user_relationships.clear()
            for raw in data.get("concepts") or []:
                if not isinstance(raw, dict):
                    continue
                cid = str(raw.get("concept_id") or "").strip()
                name = self._normalize_surface(str(raw.get("canonical_name") or ""))
                if not cid or not name:
                    continue
                concept = Concept(
                    concept_id=cid,
                    canonical_name=name,
                    aliases=[
                        self._normalize_surface(str(alias))
                        for alias in (raw.get("aliases") or [])
                        if self._normalize_surface(str(alias))
                    ],
                    concept_type=str(raw.get("concept_type") or "unknown"),
                    properties=dict(raw.get("properties") or {}),
                    activation=0.0,
                    created_at=float(raw.get("created_at") or 0.0),
                    updated_at=float(raw.get("updated_at") or 0.0),
                )
                self._index_concept(concept)
            for raw in data.get("global_relationships") or []:
                rel = self._rel_from_raw(raw, default_scope="global")
                if rel:
                    self.global_relationships.append(rel)
            user_map = data.get("user_relationships") or {}
            if isinstance(user_map, dict):
                for uid, edges in user_map.items():
                    bucket: List[Relationship] = []
                    for raw in edges or []:
                        rel = self._rel_from_raw(raw, default_scope="user", force_user=str(uid))
                        if rel:
                            bucket.append(rel)
                    if bucket:
                        self.user_relationships[str(uid)] = bucket

    @staticmethod
    def _rel_from_raw(raw: Any, *, default_scope: str = "global", force_user: Optional[str] = None) -> Optional[Relationship]:
        if not isinstance(raw, dict):
            return None
        src = str(raw.get("source_id") or raw.get("source") or "").strip()
        tgt = str(raw.get("target_id") or raw.get("target") or "").strip()
        rtype = str(raw.get("rel_type") or raw.get("type") or "").strip()
        if not src or not tgt or not rtype:
            return None
        try:
            strength = float(raw.get("strength", raw.get("confidence", 0.5)) or 0.5)
        except (TypeError, ValueError):
            strength = 0.5
        strength = max(0.0, min(1.0, strength))
        scope = str(raw.get("scope") or default_scope)
        uid = force_user if force_user is not None else raw.get("user_id")
        if scope == "user" and not uid:
            return None
        return Relationship(src, tgt, rtype, strength, scope, str(uid) if uid else None, float(raw.get("created_at") or 0.0))

    def _persist(self) -> None:
        path = self.store_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            payload = {
                "version": 1,
                "concepts": [
                    {
                        "concept_id": c.concept_id,
                        "canonical_name": c.canonical_name,
                        "aliases": list(c.aliases),
                        "concept_type": c.concept_type,
                        "properties": dict(c.properties),
                        "created_at": c.created_at,
                        "updated_at": c.updated_at,
                    }
                    for c in self.concepts.values()
                ],
                "global_relationships": [r.to_public() for r in self.global_relationships],
                "user_relationships": {uid: [r.to_public() for r in edges] for uid, edges in self.user_relationships.items()},
            }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)

    def resolve_concept(self, term: str, *, concept_type: str = "unknown", create: bool = True, properties: Optional[Dict[str, Any]] = None) -> Optional[Concept]:
        surface = self._normalize_surface(term)
        if not surface or surface in _STOP:
            return None
        with self._lock:
            cid = self._alias_index.get(surface)
            if cid and cid in self.concepts:
                return self.concepts[cid]
            if not create:
                return None
            now = time.time()
            concept = Concept(self._new_concept_id(), surface, [], concept_type or "unknown", dict(properties or {}), 0.0, now, now)
            self._index_concept(concept)
            self._persist()
            return concept

    def create_concept_sense(self, surface_form: str, *, concept_type: str = "unknown", properties: Optional[Dict[str, Any]] = None) -> Optional[Concept]:
        surface = self._normalize_surface(surface_form)
        if not surface:
            return None
        with self._lock:
            now = time.time()
            concept = Concept(self._new_concept_id(), surface, [], concept_type or "unknown", dict(properties or {}), 0.0, now, now)
            self._index_concept(concept)
            self._persist()
            return concept

    def get_concept(self, concept_id: str) -> Optional[Concept]:
        with self._lock:
            return self.concepts.get(concept_id)

    def get_candidate_concepts(self, surface_form: str) -> List[Concept]:
        surface = self._normalize_surface(surface_form)
        if not surface:
            return []
        with self._lock:
            return [self.concepts[cid] for cid in self._surface_index.get(surface, []) if cid in self.concepts]

    def lookup_surface(self, surface_form: str) -> List[Concept]:
        return self.get_candidate_concepts(surface_form)

    def add_alias(self, concept_id: str, alias: str) -> bool:
        surface = self._normalize_surface(alias)
        if not surface:
            return False
        with self._lock:
            concept = self.concepts.get(concept_id)
            if not concept:
                return False
            existing = self._alias_index.get(surface)
            if existing and existing != concept_id:
                return False
            if surface not in concept.aliases and surface != concept.canonical_name:
                concept.aliases.append(surface)
            self._alias_index[surface] = concept_id
            self._surface_add(surface, concept_id)
            concept.updated_at = time.time()
            self._persist()
            return True

    def add_candidate_alias(self, concept_id: str, alias: str) -> bool:
        surface = self._normalize_surface(alias)
        if not surface:
            return False
        with self._lock:
            concept = self.concepts.get(concept_id)
            if not concept:
                return False
            if surface not in concept.aliases and surface != concept.canonical_name:
                concept.aliases.append(surface)
            self._alias_index.setdefault(surface, concept_id)
            self._surface_add(surface, concept_id)
            concept.updated_at = time.time()
            self._persist()
            return True

    def add_relationship(self, source_id: str, target_id: str, rel_type: str, strength: float = 0.5, *, scope: str = "global", user_id: Optional[str] = None) -> Optional[Relationship]:
        rel_type = str(rel_type or "").strip()
        if rel_type not in _VALID_REL_TYPES and not rel_type:
            return None
        try:
            strength = max(0.0, min(1.0, float(strength)))
        except (TypeError, ValueError):
            strength = 0.5
        scope = "user" if scope == "user" else "global"
        uid = (user_id or "").strip() if scope == "user" else None
        if scope == "user" and not uid:
            return None
        with self._lock:
            if source_id not in self.concepts or target_id not in self.concepts:
                return None
            bucket = self.user_relationships.setdefault(uid, []) if scope == "user" else self.global_relationships
            for existing in bucket:
                if existing.source_id == source_id and existing.target_id == target_id and existing.rel_type == rel_type and existing.scope == scope and (existing.user_id or None) == uid:
                    existing.strength = strength
                    self._persist()
                    return existing
            rel = Relationship(source_id, target_id, rel_type, strength, scope, uid, time.time())
            bucket.append(rel)
            self._persist()
            return rel

    def get_relationships(self, concept_id: str, *, user_id: Optional[str] = None, include_personal: bool = True) -> List[Relationship]:
        with self._lock:
            out = [r for r in self.global_relationships if r.source_id == concept_id or r.target_id == concept_id]
            if include_personal and user_id:
                out.extend(r for r in self.user_relationships.get(str(user_id).strip(), []) if r.source_id == concept_id or r.target_id == concept_id)
            return list(out)

    @staticmethod
    def _normalize_user_id(user_id: Any) -> Optional[str]:
        if user_id is None:
            return None
        value = str(user_id).strip()
        return value or None

    def _reference_exists(self, reference_id: str) -> bool:
        return reference_id in self.concepts or reference_id in self.instances or reference_id in self.propositions

    def register_instance(self, concept_id: str, *, label: Optional[str] = None, properties: Optional[Dict[str, Any]] = None, provenance: Any = None, user_id: Optional[str] = None, activation: float = 1.0, expires_after_turn: Optional[int] = None, instance_id: Optional[str] = None) -> Optional[ReferentInstance]:
        with self._lock:
            if concept_id not in self.concepts:
                return None
            iid = str(instance_id or self._new_instance_id()).strip()
            if not iid or iid in self.instances or iid in self.propositions:
                return None
            item = ReferentInstance(iid, concept_id, str(label).strip() if label is not None else None, dict(properties or {}), Provenance.from_value(provenance), self._normalize_user_id(user_id), self._bounded_activation(activation), time.time(), int(expires_after_turn) if expires_after_turn is not None else None)
            self.instances[iid] = item
            return item

    def get_instance(self, instance_id: str, *, user_id: Optional[str] = None) -> Optional[ReferentInstance]:
        with self._lock:
            item = self.instances.get(instance_id)
            if not item:
                return None
            uid = self._normalize_user_id(user_id)
            if uid is not None and item.user_id not in {None, uid}:
                return None
            return item

    def register_proposition(self, predicate_id: str, roles: Dict[str, str], *, qualifiers: Optional[Dict[str, Any]] = None, provenance: Any = None, user_id: Optional[str] = None, activation: float = 1.0, expires_after_turn: Optional[int] = None, proposition_id: Optional[str] = None) -> Optional[Proposition]:
        if not isinstance(roles, dict):
            return None
        with self._lock:
            if predicate_id not in self.concepts:
                return None
            cleaned: Dict[str, str] = {}
            for role, ref in roles.items():
                r, rid = str(role or "").strip(), str(ref or "").strip()
                if not r or not rid or not self._reference_exists(rid):
                    return None
                cleaned[r] = rid
            pid = str(proposition_id or self._new_proposition_id()).strip()
            if not pid or pid in self.propositions or pid in self.instances:
                return None
            item = Proposition(pid, predicate_id, cleaned, dict(qualifiers or {}), Provenance.from_value(provenance), self._normalize_user_id(user_id), self._bounded_activation(activation), time.time(), int(expires_after_turn) if expires_after_turn is not None else None)
            self.propositions[pid] = item
            return item

    def get_proposition(self, proposition_id: str, *, user_id: Optional[str] = None) -> Optional[Proposition]:
        with self._lock:
            item = self.propositions.get(proposition_id)
            if not item:
                return None
            uid = self._normalize_user_id(user_id)
            if uid is not None and item.user_id not in {None, uid}:
                return None
            return item

    def get_active_propositions(self, *, user_id: Optional[str] = None, threshold: float = 0.08) -> List[Proposition]:
        uid = self._normalize_user_id(user_id)
        try:
            thr = float(threshold)
        except (TypeError, ValueError):
            thr = 0.08
        with self._lock:
            out = [p for p in self.propositions.values() if p.activation >= thr and (uid is None or p.user_id in {None, uid})]
            out.sort(key=lambda p: (-p.activation, p.created_at, p.proposition_id))
            return out

    def expire_turn(self, current_turn: int, *, user_id: Optional[str] = None) -> Dict[str, int]:
        turn = int(current_turn)
        uid = self._normalize_user_id(user_id)
        ri = rp = 0
        with self._lock:
            for iid, item in list(self.instances.items()):
                if uid is not None and item.user_id not in {None, uid}:
                    continue
                if item.expires_after_turn is not None and item.expires_after_turn <= turn:
                    del self.instances[iid]; ri += 1
            for pid, item in list(self.propositions.items()):
                if uid is not None and item.user_id not in {None, uid}:
                    continue
                if item.expires_after_turn is not None and item.expires_after_turn <= turn:
                    del self.propositions[pid]; rp += 1
        return {"instances": ri, "propositions": rp}

    def clear_transient(self, *, user_id: Optional[str] = None) -> Dict[str, int]:
        uid = self._normalize_user_id(user_id)
        with self._lock:
            if uid is None:
                counts = {"instances": len(self.instances), "propositions": len(self.propositions)}
                self.instances.clear(); self.propositions.clear(); return counts
            iids = [k for k, v in self.instances.items() if v.user_id == uid]
            pids = [k for k, v in self.propositions.items() if v.user_id == uid]
            for k in iids: del self.instances[k]
            for k in pids: del self.propositions[k]
            return {"instances": len(iids), "propositions": len(pids)}

    def proposition_to_grounded_structure(self, proposition_id: str, *, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        p = self.get_proposition(proposition_id, user_id=user_id)
        if not p:
            return None
        roles, q = dict(p.roles), dict(p.qualifiers)
        return {"proposition_id": p.proposition_id, "predicate": p.predicate_id, "predicate_id": p.predicate_id, "roles": roles, "qualifiers": q, "certainty": q.get("certainty", p.provenance.confidence), "provenance": p.provenance.to_public(), "subject": roles.get("subject", roles.get("agent")), "object": roles.get("object", roles.get("theme", roles.get("patient", roles.get("recipient"))))}

    def _edges_for_spread(self, user_id: Optional[str]) -> List[Relationship]:
        edges = list(self.global_relationships)
        if user_id:
            edges.extend(self.user_relationships.get(str(user_id).strip(), []))
        return edges

    def activate(self, concept_id: str, amount: float = 1.0, *, user_id: Optional[str] = None, spread: bool = True) -> Dict[str, float]:
        amount = self._bounded_activation(amount)
        with self._lock:
            if concept_id not in self.concepts:
                return {}
            activation_delta = {concept_id: amount}
            if spread:
                queue: List[Tuple[str, float, int]] = [(concept_id, amount, 0)]
                seen_depth = {concept_id: 0}
                visited: List[str] = []
                edges = sorted(self._edges_for_spread(user_id), key=lambda r: (r.source_id, r.target_id, r.rel_type, r.strength))
                while queue and len(visited) < self.max_spread_nodes:
                    cid, act, depth = queue.pop(0)
                    if cid not in visited: visited.append(cid)
                    if depth >= self.max_spread_depth: continue
                    for rel in edges:
                        neighbor = rel.target_id if rel.source_id == cid else rel.source_id if rel.target_id == cid else None
                        if not neighbor or neighbor not in self.concepts: continue
                        spread_amt = act * float(rel.strength) * self.spread_strength
                        if spread_amt < self.activation_threshold: continue
                        if spread_amt > activation_delta.get(neighbor, 0.0): activation_delta[neighbor] = spread_amt
                        prior = seen_depth.get(neighbor)
                        if prior is None or depth + 1 < prior:
                            seen_depth[neighbor] = depth + 1; queue.append((neighbor, spread_amt, depth + 1))
                        if len(activation_delta) >= self.max_spread_nodes: break
            for cid, delta in activation_delta.items():
                c = self.concepts[cid]; c.activation = min(1.0, max(c.activation, float(delta))); c.updated_at = time.time()
            return {cid: float(self.concepts[cid].activation) for cid in activation_delta if cid in self.concepts}

    def decay_activation(self, factor: Optional[float] = None) -> None:
        f = self.activation_decay if factor is None else float(factor); f = max(0.0, min(1.0, f))
        with self._lock:
            for c in self.concepts.values():
                c.activation = max(0.0, c.activation * (1.0 - f)); c.activation = 0.0 if c.activation < self.activation_threshold else c.activation
            for x in list(self.instances.values()) + list(self.propositions.values()):
                x.activation = max(0.0, x.activation * (1.0 - f)); x.activation = 0.0 if x.activation < self.activation_threshold else x.activation

    def reset_activation(self) -> None:
        with self._lock:
            for c in self.concepts.values(): c.activation = 0.0
            for x in list(self.instances.values()) + list(self.propositions.values()): x.activation = 0.0

    def get_active_concepts(self, *, threshold: Optional[float] = None) -> List[Concept]:
        thr = self.activation_threshold if threshold is None else float(threshold)
        with self._lock:
            active = [c for c in self.concepts.values() if c.activation >= thr]; active.sort(key=lambda c: (-c.activation, c.canonical_name, c.concept_id)); return list(active)

    def get_highly_active(self, *, threshold: Optional[float] = None) -> List[Dict[str, Any]]:
        thr = self.highly_active_threshold if threshold is None else float(threshold)
        return [{"id": c.concept_id, "concept_id": c.concept_id, "name": c.canonical_name, "canonical_name": c.canonical_name, "activation": float(c.activation), "concept_type": c.concept_type} for c in self.get_active_concepts(threshold=thr)]

    def resolve_terms(self, terms: Sequence[str], *, user_id: Optional[str] = None, activate: bool = True, activate_amount: float = 1.0) -> Dict[str, Any]:
        resolved: List[Dict[str, Any]] = []; ids: List[str] = []; seen: Set[str] = set()
        with self._lock:
            if activate:
                for c in self.concepts.values(): c.activation = 0.0
        for term in terms:
            c = self.resolve_concept(str(term), create=True)
            if not c or c.concept_id in seen: continue
            seen.add(c.concept_id); ids.append(c.concept_id); resolved.append(c.to_public())
        edges_added = 0
        if len(ids) >= 2:
            scope = "user" if user_id else "global"
            for i in range(len(ids)-1):
                a,b=ids[i],ids[i+1]
                if a==b: continue
                for src,tgt in ((a,b),(b,a)):
                    if self.add_relationship(src,tgt,"co_occurrence",0.35,scope=scope,user_id=user_id): edges_added += 1
        amap: Dict[str,float] = {}; edge_count=len(self._edges_for_spread(user_id))
        if activate and ids:
            for cid in ids:
                for k,v in self.activate(cid,activate_amount,user_id=user_id,spread=True).items(): amap[k]=max(amap.get(k,0.0),v)
        return {"status":"success","resolved":resolved,"concept_ids":ids,"activation":amap,"highly_active_concepts":self.get_highly_active(),"active_concepts":[{"id":c.concept_id,"name":c.canonical_name,"activation":float(c.activation)} for c in self.get_active_concepts()],"user_id":user_id,"relationship_edges":edge_count,"co_occurrence_edges_added":edges_added,"spread_had_edges":edge_count>0}

    def resolve_from_text(self, text: str, *, user_id: Optional[str] = None, extra_terms: Optional[Iterable[str]] = None, activate: bool = True) -> Dict[str, Any]:
        terms=[t for t in self._normalize_surface(text).split() if t and t not in _STOP and len(t)>1]
        if extra_terms:
            for t in extra_terms:
                s=self._normalize_surface(str(t))
                if s and s not in _STOP: terms.append(s)
        return self.resolve_terms(terms,user_id=user_id,activate=activate)

    def envelope(self, resolve_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        b=dict(resolve_result or {})
        return {"status":"success","resolved":b.get("resolved") or [],"concept_ids":list(b.get("concept_ids") or []),"highly_active_concepts":list(b.get("highly_active_concepts") or []),"active_concepts":list(b.get("active_concepts") or []),"activation":dict(b.get("activation") or {}),"user_id":b.get("user_id"),"relationship_edges":b.get("relationship_edges",0),"co_occurrence_edges_added":b.get("co_occurrence_edges_added",0),"spread_had_edges":bool(b.get("spread_had_edges")),"source":"shared_representation","timestamp":time.time()}

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type=message.get("type") or message.get("message_type") or ""; content=message.get("content") if isinstance(message.get("content"),dict) else {}
        if not content and isinstance(message,dict): content={k:v for k,v in message.items() if k not in {"type","message_type","source","message_id","content"}}
        if msg_type=="health": return {"status":"success","healthy":True,"concept_count":len(self.concepts),"global_relationship_count":len(self.global_relationships),"transient_instance_count":len(self.instances),"transient_proposition_count":len(self.propositions),"live_co_occurrence_producer":True,"store_path":str(self.store_path)}
        if msg_type in {"resolve","resolve_terms","resolve_from_text"}:
            uid=content.get("user_id")
            if msg_type=="resolve_from_text" or content.get("text"): result=self.resolve_from_text(str(content.get("text") or ""),user_id=uid,extra_terms=content.get("terms") or content.get("concepts"),activate=bool(content.get("activate",True)))
            else:
                terms=content.get("terms") or content.get("concepts") or []
                if content.get("term"): terms=list(terms)+[content.get("term")]
                result=self.resolve_terms(list(terms),user_id=uid,activate=bool(content.get("activate",True)))
            env=self.envelope(result); return {"status":"success","content":env,**env}
        if msg_type in {"get_candidate_concepts","lookup_surface","resolve_span"}:
            surface=content.get("surface") or content.get("term") or content.get("text")
            if surface is None and isinstance(content.get("tokens"),list): surface=" ".join(str(t) for t in content.get("tokens") or [])
            candidates=[c.to_public() for c in self.get_candidate_concepts(str(surface or ""))]; payload={"surface":self._normalize_surface(str(surface or "")),"candidate_concepts":candidates,"concept_ids":[c["concept_id"] for c in candidates]}; return {"status":"success","content":payload,**payload}
        if msg_type=="create_concept_sense":
            c=self.create_concept_sense(str(content.get("surface") or content.get("term") or ""),concept_type=str(content.get("concept_type") or "unknown"),properties=content.get("properties") if isinstance(content.get("properties"),dict) else None)
            if not c: return {"status":"error","message":"could not create concept sense"}
            pub=c.to_public(); return {"status":"success","content":pub,"concept":pub}
        if msg_type=="get_concept":
            cid=str(content.get("concept_id") or content.get("id") or ""); c=self.get_concept(cid)
            if not c and (content.get("name") or content.get("term")): c=self.resolve_concept(str(content.get("name") or content.get("term")),create=False)
            if not c: return {"status":"error","message":"concept not found"}
            pub=c.to_public(); return {"status":"success","content":pub,"concept":pub}
        if msg_type in {"add_alias","add_candidate_alias"}:
            ok=self.add_candidate_alias(str(content.get("concept_id") or content.get("id") or ""),str(content.get("alias") or "")) if msg_type=="add_candidate_alias" else self.add_alias(str(content.get("concept_id") or content.get("id") or ""),str(content.get("alias") or "")); return {"status":"success","content":{"added":True}} if ok else {"status":"error","message":"could not add alias"}
        if msg_type=="register_instance":
            x=self.register_instance(str(content.get("concept_id") or ""),label=content.get("label"),properties=content.get("properties") if isinstance(content.get("properties"),dict) else None,provenance=content.get("provenance"),user_id=content.get("user_id"),activation=content.get("activation",1.0),expires_after_turn=content.get("expires_after_turn"),instance_id=content.get("instance_id"));
            if not x:return {"status":"error","message":"could not register instance"}
            pub=x.to_public();return {"status":"success","content":pub,"instance":pub}
        if msg_type=="get_instance":
            x=self.get_instance(str(content.get("instance_id") or content.get("id") or ""),user_id=content.get("user_id"));
            if not x:return {"status":"error","message":"instance not found"}
            pub=x.to_public();return {"status":"success","content":pub,"instance":pub}
        if msg_type=="register_proposition":
            roles=content.get("roles");x=self.register_proposition(str(content.get("predicate_id") or ""),roles if isinstance(roles,dict) else {},qualifiers=content.get("qualifiers") if isinstance(content.get("qualifiers"),dict) else None,provenance=content.get("provenance"),user_id=content.get("user_id"),activation=content.get("activation",1.0),expires_after_turn=content.get("expires_after_turn"),proposition_id=content.get("proposition_id"));
            if not x:return {"status":"error","message":"could not register proposition"}
            pub=x.to_public();return {"status":"success","content":pub,"proposition":pub}
        if msg_type=="get_proposition":
            x=self.get_proposition(str(content.get("proposition_id") or content.get("id") or ""),user_id=content.get("user_id"));
            if not x:return {"status":"error","message":"proposition not found"}
            pub=x.to_public();return {"status":"success","content":pub,"proposition":pub}
        if msg_type=="get_active_propositions":
            items=[x.to_public() for x in self.get_active_propositions(user_id=content.get("user_id"),threshold=content.get("threshold",self.activation_threshold))];return {"status":"success","content":{"propositions":items},"propositions":items}
        if msg_type=="proposition_to_grounded_structure":
            g=self.proposition_to_grounded_structure(str(content.get("proposition_id") or content.get("id") or ""),user_id=content.get("user_id"));return {"status":"success","content":g,"grounded_structure":g} if g else {"status":"error","message":"proposition not found"}
        if msg_type=="expire_turn":
            if content.get("turn") is None and content.get("current_turn") is None:return {"status":"error","message":"current turn required"}
            e=self.expire_turn(int(content.get("current_turn",content.get("turn"))),user_id=content.get("user_id"));return {"status":"success","content":{"expired":e},"expired":e}
        if msg_type=="clear_transient":
            c=self.clear_transient(user_id=content.get("user_id"));return {"status":"success","content":{"cleared":c},"cleared":c}
        if msg_type=="add_relationship":
            r=self.add_relationship(str(content.get("source_id") or content.get("source") or ""),str(content.get("target_id") or content.get("target") or ""),str(content.get("rel_type") or content.get("type") or "associated_with"),float(content.get("strength",content.get("confidence",0.5)) or 0.5),scope=str(content.get("scope") or "global"),user_id=content.get("user_id"));
            if not r:return {"status":"error","message":"could not add relationship"}
            pub=r.to_public();return {"status":"success","content":pub,"relationship":pub}
        if msg_type=="get_relationships":
            rels=[r.to_public() for r in self.get_relationships(str(content.get("concept_id") or content.get("id") or ""),user_id=content.get("user_id"),include_personal=bool(content.get("include_personal",True)))];return {"status":"success","content":{"relationships":rels},"relationships":rels}
        if msg_type=="activate":
            amap=self.activate(str(content.get("concept_id") or content.get("id") or ""),float(content.get("amount",1.0) or 1.0),user_id=content.get("user_id"),spread=bool(content.get("spread",True)));return {"status":"success","content":{"activation":amap},"activation":amap,"highly_active_concepts":self.get_highly_active()}
        if msg_type in {"get_active","get_highly_active"}:
            thr=content.get("threshold")
            if msg_type=="get_highly_active":
                h=self.get_highly_active(threshold=float(thr) if thr is not None else None);return {"status":"success","content":{"highly_active_concepts":h},"highly_active_concepts":h}
            a=[{"id":c.concept_id,"name":c.canonical_name,"activation":float(c.activation)} for c in self.get_active_concepts(threshold=float(thr) if thr is not None else None)];return {"status":"success","content":{"active_concepts":a},"active_concepts":a}
        if msg_type=="decay":self.decay_activation(content.get("factor"));return {"status":"success","content":{"decayed":True}}
        if msg_type=="reset_activation":self.reset_activation();return {"status":"success","content":{"reset":True}}
        if msg_type=="get_status":
            status={"concept_count":len(self.concepts),"global_edge_count":len(self.global_relationships),"user_edge_users":len(self.user_relationships),"surface_form_count":len(self._surface_index),"transient_instance_count":len(self.instances),"transient_proposition_count":len(self.propositions),"store_path":str(self.store_path),"running":self.running};return {"status":"success","content":status,**status}
        return {"status":"error","message":f"Unknown message type: {msg_type}"}

    def shutdown(self) -> None:
        self.running=False
        try:self._persist()
        except Exception:pass


__all__=["Concept","Relationship","Provenance","ReferentInstance","Proposition","SharedRepresentationSystem"]
