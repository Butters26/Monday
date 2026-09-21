#!/usr/bin/env python3
"""Shared Representation — common semantic substrate for Monday lobes.

Owns stable concept identity, canonical names/aliases, structured relationships,
activation state, and bounded spreading activation. Does NOT own Pattern
discovery, Reasoning conclusions, Attention focus, Emotion, Notus memory,
Language wording, MetaCognition/MetaAwareness, Executive, or Learning.

Persistence: own JSON under runtime_dir()/shared_representation.json — NOT Notus.
Old representation.py stays unwired (historical only).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from runtime_paths import runtime_dir

_PUNCT_RE = re.compile(r"[^\w\s\-']+", re.UNICODE)
_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "am",
        "i",
        "me",
        "my",
        "you",
        "your",
        "we",
        "our",
        "they",
        "them",
        "their",
        "it",
        "its",
        "this",
        "that",
        "with",
        "from",
        "as",
        "by",
        "if",
        "so",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "not",
        "no",
        "yes",
        "just",
        "about",
        "into",
        "than",
        "then",
        "too",
        "very",
        "can",
        "could",
        "would",
        "should",
        "will",
        "shall",
        "may",
        "might",
        "must",
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
    }
)


@dataclass
class Concept:
    """Stable concept identity in the shared substrate."""

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
    """Structured semantic edge (not a free-form string)."""

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


class SharedRepresentationSystem:
    """Common semantic substrate: identity, relationships, bounded activation."""

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
        # surface form (lowercase) → concept_id
        self._alias_index: Dict[str, str] = {}
        self.global_relationships: List[Relationship] = []
        # user_id → list of personal Relationship
        self.user_relationships: Dict[str, List[Relationship]] = {}

        self._load()

    # --- identity / canonicalization ---------------------------------------

    @staticmethod
    def _normalize_surface(term: str) -> str:
        t = (term or "").strip().lower()
        t = _PUNCT_RE.sub("", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    @staticmethod
    def _plural_fold(term: str) -> str:
        """Deliberate English plural fold — NOT fuzzy merge."""
        if len(term) <= 2:
            return term
        if term.endswith("ies") and len(term) > 4:
            return term[:-3] + "y"
        if term.endswith("ses") or term.endswith("xes") or term.endswith("zes"):
            return term[:-2]
        if term.endswith("ches") or term.endswith("shes"):
            return term[:-2]
        if term.endswith("s") and not term.endswith("ss"):
            return term[:-1]
        return term

    def _canonical_key(self, term: str) -> str:
        surface = self._normalize_surface(term)
        if not surface:
            return ""
        folded = self._plural_fold(surface)
        # Prefer existing alias hit for either form.
        if surface in self._alias_index:
            cid = self._alias_index[surface]
            return self.concepts[cid].canonical_name if cid in self.concepts else folded
        if folded in self._alias_index:
            cid = self._alias_index[folded]
            return self.concepts[cid].canonical_name if cid in self.concepts else folded
        return folded

    def _new_concept_id(self) -> str:
        return f"c_{uuid.uuid4().hex[:12]}"

    def _index_concept(self, concept: Concept) -> None:
        self.concepts[concept.concept_id] = concept
        names = {concept.canonical_name}
        names.update(self._normalize_surface(a) for a in concept.aliases)
        names.add(self._plural_fold(concept.canonical_name))
        for n in names:
            if n:
                self._alias_index[n] = concept.concept_id

    # --- persistence -------------------------------------------------------

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
                        self._normalize_surface(a)
                        for a in (raw.get("aliases") or [])
                        if self._normalize_surface(str(a))
                    ],
                    concept_type=str(raw.get("concept_type") or "unknown"),
                    properties=dict(raw.get("properties") or {}),
                    activation=0.0,  # ephemeral — never restore as durable
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
                        rel = self._rel_from_raw(
                            raw, default_scope="user", force_user=str(uid)
                        )
                        if rel:
                            bucket.append(rel)
                    if bucket:
                        self.user_relationships[str(uid)] = bucket

    @staticmethod
    def _rel_from_raw(
        raw: Any,
        *,
        default_scope: str = "global",
        force_user: Optional[str] = None,
    ) -> Optional[Relationship]:
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
        return Relationship(
            source_id=src,
            target_id=tgt,
            rel_type=rtype,
            strength=strength,
            scope=scope,
            user_id=str(uid) if uid else None,
            created_at=float(raw.get("created_at") or 0.0),
        )

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
                "global_relationships": [
                    r.to_public() for r in self.global_relationships
                ],
                "user_relationships": {
                    uid: [r.to_public() for r in edges]
                    for uid, edges in self.user_relationships.items()
                },
            }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)

    # --- core API ----------------------------------------------------------

    def resolve_concept(
        self,
        term: str,
        *,
        concept_type: str = "unknown",
        create: bool = True,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Optional[Concept]:
        """Resolve surface term to stable Concept (create if never-seen)."""
        surface = self._normalize_surface(term)
        if not surface or surface in _STOP:
            return None
        with self._lock:
            # Exact alias / plural fold lookup
            for key in (surface, self._plural_fold(surface)):
                cid = self._alias_index.get(key)
                if cid and cid in self.concepts:
                    concept = self.concepts[cid]
                    # Register plural/surface as alias if missing
                    if surface not in concept.aliases and surface != concept.canonical_name:
                        concept.aliases.append(surface)
                        self._alias_index[surface] = cid
                        concept.updated_at = time.time()
                        self._persist()
                    return concept
            if not create:
                return None
            now = time.time()
            canonical = self._plural_fold(surface)
            concept = Concept(
                concept_id=self._new_concept_id(),
                canonical_name=canonical,
                aliases=[] if surface == canonical else [surface],
                concept_type=concept_type or "unknown",
                properties=dict(properties or {}),
                activation=0.0,
                created_at=now,
                updated_at=now,
            )
            self._index_concept(concept)
            self._persist()
            return concept

    def get_concept(self, concept_id: str) -> Optional[Concept]:
        with self._lock:
            return self.concepts.get(concept_id)

    def add_alias(self, concept_id: str, alias: str) -> bool:
        surface = self._normalize_surface(alias)
        if not surface:
            return False
        with self._lock:
            concept = self.concepts.get(concept_id)
            if not concept:
                return False
            # Refuse dangerous takeover of another concept's name
            existing = self._alias_index.get(surface)
            if existing and existing != concept_id:
                return False
            if surface not in concept.aliases and surface != concept.canonical_name:
                concept.aliases.append(surface)
            self._alias_index[surface] = concept_id
            concept.updated_at = time.time()
            self._persist()
            return True

    def add_relationship(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        strength: float = 0.5,
        *,
        scope: str = "global",
        user_id: Optional[str] = None,
    ) -> Optional[Relationship]:
        rel_type = str(rel_type or "").strip()
        if rel_type not in _VALID_REL_TYPES:
            # Allow documented types; still accept unknown as associated_with
            if not rel_type:
                return None
        try:
            strength = max(0.0, min(1.0, float(strength)))
        except (TypeError, ValueError):
            strength = 0.5
        scope = "user" if scope == "user" else "global"
        if scope == "user":
            uid = (user_id or "").strip()
            if not uid:
                return None
        else:
            uid = None
        with self._lock:
            if source_id not in self.concepts or target_id not in self.concepts:
                return None
            # Upsert same (source,target,type,scope,user)
            bucket = (
                self.user_relationships.setdefault(uid, [])
                if scope == "user"
                else self.global_relationships
            )
            for existing in bucket:
                if (
                    existing.source_id == source_id
                    and existing.target_id == target_id
                    and existing.rel_type == rel_type
                    and existing.scope == scope
                    and (existing.user_id or None) == uid
                ):
                    existing.strength = strength
                    self._persist()
                    return existing
            rel = Relationship(
                source_id=source_id,
                target_id=target_id,
                rel_type=rel_type,
                strength=strength,
                scope=scope,
                user_id=uid,
                created_at=time.time(),
            )
            bucket.append(rel)
            self._persist()
            return rel

    def get_relationships(
        self,
        concept_id: str,
        *,
        user_id: Optional[str] = None,
        include_personal: bool = True,
    ) -> List[Relationship]:
        """Return global edges (+ optional personal for user_id only)."""
        with self._lock:
            out: List[Relationship] = []
            for rel in self.global_relationships:
                if rel.source_id == concept_id or rel.target_id == concept_id:
                    out.append(rel)
            if include_personal and user_id:
                uid = str(user_id).strip()
                for rel in self.user_relationships.get(uid, []):
                    if rel.source_id == concept_id or rel.target_id == concept_id:
                        out.append(rel)
            return list(out)

    def _edges_for_spread(
        self, user_id: Optional[str]
    ) -> List[Relationship]:
        edges = list(self.global_relationships)
        if user_id:
            edges.extend(self.user_relationships.get(str(user_id).strip(), []))
        return edges

    def activate(
        self,
        concept_id: str,
        amount: float = 1.0,
        *,
        user_id: Optional[str] = None,
        spread: bool = True,
    ) -> Dict[str, float]:
        """Activate a concept; optionally bounded-spread. Returns activation map."""
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            amount = 1.0
        amount = max(0.0, min(1.0, amount))
        with self._lock:
            if concept_id not in self.concepts:
                return {}
            # Reset ephemeral activations for a clean spread from seeds? No —
            # additive within turn; caller may reset_activation first.
            visited_order: List[str] = []
            activation_delta: Dict[str, float] = {concept_id: amount}
            if spread:
                # BFS: (concept_id, incoming_activation, depth)
                queue: List[Tuple[str, float, int]] = [(concept_id, amount, 0)]
                seen_at_depth: Dict[str, int] = {concept_id: 0}
                edges = self._edges_for_spread(user_id)
                # Deterministic edge order
                edges_sorted = sorted(
                    edges,
                    key=lambda r: (r.source_id, r.target_id, r.rel_type, r.strength),
                )
                while queue and len(visited_order) < self.max_spread_nodes:
                    cid, act, depth = queue.pop(0)
                    if cid not in visited_order:
                        visited_order.append(cid)
                    if depth >= self.max_spread_depth:
                        continue
                    for rel in edges_sorted:
                        if rel.source_id == cid:
                            neighbor = rel.target_id
                        elif rel.target_id == cid:
                            neighbor = rel.source_id
                        else:
                            continue
                        if neighbor not in self.concepts:
                            continue
                        spread_amt = act * float(rel.strength) * self.spread_strength
                        if spread_amt < self.activation_threshold:
                            continue
                        prev = activation_delta.get(neighbor, 0.0)
                        # Keep max contribution (deterministic, no runaway sum)
                        if spread_amt > prev:
                            activation_delta[neighbor] = spread_amt
                        prior_depth = seen_at_depth.get(neighbor)
                        if prior_depth is None or depth + 1 < prior_depth:
                            seen_at_depth[neighbor] = depth + 1
                            queue.append((neighbor, spread_amt, depth + 1))
                        if len(activation_delta) >= self.max_spread_nodes:
                            break

            for cid, delta in activation_delta.items():
                concept = self.concepts[cid]
                concept.activation = min(1.0, max(concept.activation, float(delta)))
                concept.updated_at = time.time()

            return {
                cid: float(self.concepts[cid].activation)
                for cid in activation_delta
                if cid in self.concepts
            }

    def decay_activation(self, factor: Optional[float] = None) -> None:
        f = self.activation_decay if factor is None else float(factor)
        f = max(0.0, min(1.0, f))
        with self._lock:
            for concept in self.concepts.values():
                concept.activation = max(0.0, concept.activation * (1.0 - f))
                if concept.activation < self.activation_threshold:
                    concept.activation = 0.0

    def reset_activation(self) -> None:
        with self._lock:
            for concept in self.concepts.values():
                concept.activation = 0.0

    def get_active_concepts(
        self, *, threshold: Optional[float] = None
    ) -> List[Concept]:
        thr = self.activation_threshold if threshold is None else float(threshold)
        with self._lock:
            active = [c for c in self.concepts.values() if c.activation >= thr]
            active.sort(key=lambda c: (-c.activation, c.canonical_name, c.concept_id))
            return list(active)

    def get_highly_active(
        self, *, threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        thr = (
            self.highly_active_threshold
            if threshold is None
            else float(threshold)
        )
        return [
            {
                "id": c.concept_id,
                "concept_id": c.concept_id,
                "name": c.canonical_name,
                "canonical_name": c.canonical_name,
                "activation": float(c.activation),
                "concept_type": c.concept_type,
            }
            for c in self.get_active_concepts(threshold=thr)
        ]

    def resolve_terms(
        self,
        terms: Sequence[str],
        *,
        user_id: Optional[str] = None,
        activate: bool = True,
        activate_amount: float = 1.0,
    ) -> Dict[str, Any]:
        """Resolve many surface terms; optionally activate+spread."""
        resolved: List[Dict[str, Any]] = []
        ids: List[str] = []
        seen: Set[str] = set()
        with self._lock:
            # Reset turn activation so live path is deterministic per turn
            if activate:
                for c in self.concepts.values():
                    c.activation = 0.0
        for term in terms:
            concept = self.resolve_concept(str(term), create=True)
            if not concept:
                continue
            if concept.concept_id in seen:
                continue
            seen.add(concept.concept_id)
            ids.append(concept.concept_id)
            resolved.append(concept.to_public())
        activation_map: Dict[str, float] = {}
        if activate and ids:
            # Seed all, then one coordinated spread pass from each seed
            for cid in ids:
                part = self.activate(
                    cid, activate_amount, user_id=user_id, spread=True
                )
                for k, v in part.items():
                    activation_map[k] = max(activation_map.get(k, 0.0), v)
        highly = self.get_highly_active()
        return {
            "status": "success",
            "resolved": resolved,
            "concept_ids": ids,
            "activation": activation_map,
            "highly_active_concepts": highly,
            "active_concepts": [
                {
                    "id": c.concept_id,
                    "name": c.canonical_name,
                    "activation": float(c.activation),
                }
                for c in self.get_active_concepts()
            ],
            "user_id": user_id,
        }

    def resolve_from_text(
        self,
        text: str,
        *,
        user_id: Optional[str] = None,
        extra_terms: Optional[Iterable[str]] = None,
        activate: bool = True,
    ) -> Dict[str, Any]:
        tokens = self._normalize_surface(text).split()
        terms: List[str] = []
        for tok in tokens:
            if tok and tok not in _STOP and len(tok) > 1:
                terms.append(tok)
        if extra_terms:
            for t in extra_terms:
                s = self._normalize_surface(str(t))
                if s and s not in _STOP:
                    terms.append(s)
        return self.resolve_terms(terms, user_id=user_id, activate=activate)

    def envelope(
        self, resolve_result: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Common concept envelope for Thalamus handoff."""
        body = dict(resolve_result or {})
        return {
            "status": "success",
            "resolved": body.get("resolved") or [],
            "concept_ids": list(body.get("concept_ids") or []),
            "highly_active_concepts": list(body.get("highly_active_concepts") or []),
            "active_concepts": list(body.get("active_concepts") or []),
            "activation": dict(body.get("activation") or {}),
            "user_id": body.get("user_id"),
            "source": "shared_representation",
            "timestamp": time.time(),
        }

    # --- messaging ---------------------------------------------------------

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type") or message.get("message_type") or ""
        content = message.get("content") if isinstance(message.get("content"), dict) else {}
        # Allow flat payloads (Thalamus sometimes passes content as the body)
        if not content and isinstance(message, dict):
            content = {
                k: v
                for k, v in message.items()
                if k not in {"type", "message_type", "source", "message_id", "content"}
            }

        if msg_type == "health":
            return {
                "status": "success",
                "healthy": True,
                "concept_count": len(self.concepts),
                "store_path": str(self.store_path),
            }

        if msg_type in {"resolve", "resolve_terms", "resolve_from_text"}:
            user_id = content.get("user_id")
            if msg_type == "resolve_from_text" or content.get("text"):
                result = self.resolve_from_text(
                    str(content.get("text") or ""),
                    user_id=user_id,
                    extra_terms=content.get("terms") or content.get("concepts"),
                    activate=bool(content.get("activate", True)),
                )
            else:
                terms = content.get("terms") or content.get("concepts") or []
                if content.get("term"):
                    terms = list(terms) + [content.get("term")]
                result = self.resolve_terms(
                    list(terms),
                    user_id=user_id,
                    activate=bool(content.get("activate", True)),
                )
            env = self.envelope(result)
            return {"status": "success", "content": env, **env}

        if msg_type == "get_concept":
            cid = str(content.get("concept_id") or content.get("id") or "")
            concept = self.get_concept(cid)
            if not concept:
                name = content.get("name") or content.get("term")
                if name:
                    concept = self.resolve_concept(str(name), create=False)
            if not concept:
                return {"status": "error", "message": "concept not found"}
            pub = concept.to_public()
            return {"status": "success", "content": pub, "concept": pub}

        if msg_type == "add_relationship":
            rel = self.add_relationship(
                str(content.get("source_id") or content.get("source") or ""),
                str(content.get("target_id") or content.get("target") or ""),
                str(content.get("rel_type") or content.get("type") or "associated_with"),
                float(content.get("strength", content.get("confidence", 0.5)) or 0.5),
                scope=str(content.get("scope") or "global"),
                user_id=content.get("user_id"),
            )
            if not rel:
                return {"status": "error", "message": "could not add relationship"}
            pub = rel.to_public()
            return {"status": "success", "content": pub, "relationship": pub}

        if msg_type == "get_relationships":
            cid = str(content.get("concept_id") or content.get("id") or "")
            rels = [
                r.to_public()
                for r in self.get_relationships(
                    cid,
                    user_id=content.get("user_id"),
                    include_personal=bool(content.get("include_personal", True)),
                )
            ]
            return {
                "status": "success",
                "content": {"relationships": rels},
                "relationships": rels,
            }

        if msg_type == "activate":
            cid = str(content.get("concept_id") or content.get("id") or "")
            amap = self.activate(
                cid,
                float(content.get("amount", 1.0) or 1.0),
                user_id=content.get("user_id"),
                spread=bool(content.get("spread", True)),
            )
            return {
                "status": "success",
                "content": {"activation": amap},
                "activation": amap,
                "highly_active_concepts": self.get_highly_active(),
            }

        if msg_type in {"get_active", "get_highly_active"}:
            thr = content.get("threshold")
            if msg_type == "get_highly_active":
                highly = self.get_highly_active(
                    threshold=float(thr) if thr is not None else None
                )
                return {
                    "status": "success",
                    "content": {"highly_active_concepts": highly},
                    "highly_active_concepts": highly,
                }
            active = [
                {
                    "id": c.concept_id,
                    "name": c.canonical_name,
                    "activation": float(c.activation),
                }
                for c in self.get_active_concepts(
                    threshold=float(thr) if thr is not None else None
                )
            ]
            return {
                "status": "success",
                "content": {"active_concepts": active},
                "active_concepts": active,
            }

        if msg_type == "decay":
            self.decay_activation(content.get("factor"))
            return {"status": "success", "content": {"decayed": True}}

        if msg_type == "reset_activation":
            self.reset_activation()
            return {"status": "success", "content": {"reset": True}}

        if msg_type == "get_status":
            with self._lock:
                status = {
                    "concept_count": len(self.concepts),
                    "global_edge_count": len(self.global_relationships),
                    "user_edge_users": len(self.user_relationships),
                    "store_path": str(self.store_path),
                    "running": self.running,
                }
            return {"status": "success", "content": status, **status}

        return {"status": "error", "message": f"Unknown message type: {msg_type}"}

    def shutdown(self) -> None:
        self.running = False
        try:
            self._persist()
        except Exception:
            pass


__all__ = ["Concept", "Relationship", "SharedRepresentationSystem"]
