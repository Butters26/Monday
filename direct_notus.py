"""PostgreSQL and pgvector-backed memory service for Monday's direct core."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import uuid
from typing import Any, Dict, Iterator, List, Optional, Sequence

import psycopg2
from psycopg2.pool import ThreadedConnectionPool

from thalamus import get_thalamus

_TRANSCRIPT_PREFIX = re.compile(r"^\s*(?:user|abin)\s*:", re.IGNORECASE)
_WORDS = re.compile(r"\b[\w'-]+\b")
_FAVORITE_FACT = re.compile(
    r"\bmy\s+(?P<subject>favorite\s+[a-z][a-z ]{0,40}?)\s+is\s+"
    r"(?P<object>[a-z0-9][a-z0-9 -]{0,80}?)(?:[.!?]|$)", re.IGNORECASE
)
_DIMENSIONS = 384


class DirectNotusProcess:
    """Typed, user-scoped memory with hybrid full-text and vector retrieval."""

    def __init__(self, dsn: Optional[str] = None, thalamus: Any = None) -> None:
        self.running = True
        self.thalamus = thalamus or get_thalamus()
        self.dsn = dsn or os.environ.get(
            "MONDAY_NOTUS_DSN", "dbname=notus_memory host=localhost"
        )
        self._pool = ThreadedConnectionPool(1, 8, self.dsn)
        self._lock = threading.RLock()
        self.memory_ready = threading.Event()
        self._apply_schema()
        self.memory_ready.set()

    @contextmanager
    def _cursor(self) -> Iterator[Any]:
        connection = self._pool.getconn()
        try:
            with connection:
                with connection.cursor() as cursor:
                    yield cursor
        finally:
            self._pool.putconn(connection)

    @staticmethod
    def _is_safe_memory(role: Any, content: Any) -> bool:
        return (
            isinstance(role, str)
            and role in {"user", "assistant", "fact", "note", "system"}
            and isinstance(content, str)
            and bool(content.strip())
            and not _TRANSCRIPT_PREFIX.match(content)
        )

    @staticmethod
    def _vector(text: str) -> str:
        """Stable local fallback vector; replaceable with a model-backed encoder."""
        values = [0.0] * _DIMENSIONS
        for word in _WORDS.findall(text.lower()):
            slot = int.from_bytes(hashlib.blake2b(word.encode(), digest_size=4).digest(), "big") % _DIMENSIONS
            values[slot] += 1.0
        magnitude = sum(value * value for value in values) ** 0.5
        if magnitude:
            values = [value / magnitude for value in values]
        return "[" + ",".join(f"{value:.8f}" for value in values) + "]"

    def _apply_schema(self) -> None:
        schema = Path(__file__).with_name("postgresql_schema.sql").read_text(encoding="utf-8")
        with self._cursor() as cursor:
            cursor.execute(schema)
            cursor.execute(
                """INSERT INTO notus_schema_migrations (version)
                   VALUES ('2026-08-13-postgres-turns')
                   ON CONFLICT (version) DO NOTHING"""
            )
            cursor.execute(
                """SELECT id, user_id, content, created_at, scope
                   FROM memories
                   WHERE role = 'user' AND legacy_turn_id IS NULL AND deleted_at IS NULL"""
            )
            for memory_id, user_id, content, created_at, scope in cursor.fetchall():
                scope = scope or "general"
                conversation_id = self._conversation_id(user_id or "default", scope, None)
                turn_id = str(uuid.uuid4())
                cursor.execute(
                    """INSERT INTO conversations (id, user_id, scope)
                       VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING""",
                    (conversation_id, user_id or "default", scope),
                )
                cursor.execute(
                    """INSERT INTO conversation_turns
                       (id, idempotency_key, conversation_id, user_id, scope, user_text,
                        turn_state, extraction_status, created_at, metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, 'legacy_user_only', 'complete', %s, %s::jsonb)
                       ON CONFLICT (idempotency_key) DO NOTHING""",
                    (turn_id, f"legacy-memory:{memory_id}", conversation_id, user_id or "default",
                     scope, content, created_at, json.dumps({"legacy_memory_id": str(memory_id)})),
                )
                cursor.execute("UPDATE memories SET legacy_turn_id = %s WHERE id = %s", (turn_id, memory_id))

    def start(self) -> "DirectNotusProcess":
        if not self.running:
            raise RuntimeError("Cannot restart a closed Notus service")
        self.thalamus.register_lobe("notus", self)
        return self

    def _extract_concepts(self, text: str) -> List[str]:
        return sorted({word.lower() for word in _WORDS.findall(text) if len(word) > 3})[:20]

    def _learn_fact(self, cursor: Any, content: str, user_id: str, memory_id: str) -> None:
        match = _FAVORITE_FACT.search(content)
        if not match:
            return
        subject = " ".join(match.group("subject").lower().split())
        object_value = match.group("object").strip(" .!?")
        cursor.execute(
            """INSERT INTO facts
               (id, user_id, subject, predicate, object, confidence, source_memory_id, source)
               VALUES (%s, %s, %s, 'is', %s, 0.95, %s, 'conversation')
               ON CONFLICT (user_id, scope, subject, predicate, object) DO UPDATE
               SET reinforcement_count = facts.reinforcement_count + 1,
                   last_reinforced_at = now(), confidence = GREATEST(facts.confidence, EXCLUDED.confidence)""",
            (str(uuid.uuid4()), user_id, subject, object_value, memory_id),
        )

    @staticmethod
    def _conversation_id(user_id: str, scope: str, supplied_id: Optional[str]) -> str:
        if supplied_id:
            return supplied_id
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"monday:{user_id}:{scope}"))

    def _store_turn(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        user_id = payload.get("user_id", "default")
        scope = payload.get("scope", "general")
        user_text = payload.get("user_text")
        assistant_text = payload.get("assistant_text")
        idempotency_key = payload.get("idempotency_key")
        if (
            not isinstance(user_id, str) or not user_id
            or not isinstance(scope, str) or not scope
            or not self._is_safe_memory("user", user_text)
            or not isinstance(assistant_text, str) or not assistant_text.strip()
            or not isinstance(idempotency_key, str) or not idempotency_key
        ):
            return {"status": "error", "message": "A complete, scoped turn and idempotency key are required", "content": {}}
        conversation_id = self._conversation_id(user_id, scope, payload.get("conversation_id"))
        turn_id = payload.get("turn_id") or str(uuid.uuid4())
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            return {"status": "error", "message": "Turn metadata must be an object", "content": {}}
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT id, user_text, assistant_text FROM conversation_turns WHERE idempotency_key = %s",
                (idempotency_key,),
            )
            existing = cursor.fetchone()
            if existing:
                if existing[1] == user_text and existing[2] == assistant_text:
                    return {"status": "success", "content": {"stored": True, "duplicate": True, "turn_id": str(existing[0]), "extraction_status": "complete"}}
                return {"status": "error", "message": "Idempotency key conflicts with a different turn", "content": {}}
            cursor.execute(
                """INSERT INTO conversations (id, user_id, scope)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET updated_at = now()""",
                (conversation_id, user_id, scope),
            )
            cursor.execute(
                """INSERT INTO conversation_turns
                   (id, idempotency_key, conversation_id, user_id, scope, user_text, assistant_text,
                    turn_state, metadata, extraction_status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 'complete', %s::jsonb, 'complete')""",
                (turn_id, idempotency_key, conversation_id, user_id, scope, user_text.strip(),
                 assistant_text.strip(), json.dumps(metadata)),
            )
            self._learn_turn_fact(cursor, user_text, user_id, scope, turn_id)
        return {"status": "success", "content": {"stored": True, "duplicate": False, "turn_id": turn_id, "extraction_status": "complete"}}

    def _learn_turn_fact(self, cursor: Any, content: str, user_id: str, scope: str, turn_id: str) -> None:
        match = _FAVORITE_FACT.search(content)
        if not match:
            return
        subject = " ".join(match.group("subject").lower().split())
        object_value = match.group("object").strip(" .!?")
        cursor.execute(
            """INSERT INTO facts
               (id, user_id, scope, subject, predicate, object, confidence, status, source_turn_id, source, source_role)
               VALUES (%s, %s, %s, %s, 'is', %s, 0.95, 'confirmed', %s, 'conversation', 'user')
               ON CONFLICT (user_id, scope, subject, predicate, object) DO UPDATE
               SET reinforcement_count = facts.reinforcement_count + 1, last_reinforced_at = now()""",
            (str(uuid.uuid4()), user_id, scope, subject, object_value, turn_id),
        )

    def _store(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        content, role = payload.get("content"), payload.get("role", "user")
        user_id = payload.get("user_id", "default")
        if not self._is_safe_memory(role, content) or not isinstance(user_id, str) or not user_id:
            return {"status": "error", "message": "Memory must be clean, user-scoped content"}
        memory_id = str(uuid.uuid4())
        concepts = self._extract_concepts(content)
        with self._cursor() as cursor:
            cursor.execute(
                """INSERT INTO memories
                   (id, user_id, role, memory_type, content, concepts, embedding, embedding_model)
                   VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::vector, 'hashing-v1')""",
                (memory_id, user_id, role, payload.get("memory_type", "conversation"),
                 content.strip(), json.dumps(concepts), self._vector(content)),
            )
            self._learn_fact(cursor, content, user_id, memory_id)
        return {"status": "success", "content": {"stored": True, "id": memory_id}}

    def retrieve_memories(self, query: str = "", user_id: str = "default", limit: int = 15) -> List[Dict[str, Any]]:
        if not isinstance(user_id, str) or not user_id:
            return []
        limit = max(1, min(int(limit), 100))
        vector = self._vector(query)
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT id, role, content, memory_type, created_at, concepts,
                          1 - (embedding <=> %s::vector) AS similarity
                   FROM memories WHERE user_id = %s AND role IN ('user', 'fact', 'note')
                     AND deleted_at IS NULL AND embedding <=> %s::vector < 0.9
                   ORDER BY similarity DESC NULLS LAST, importance DESC, created_at DESC LIMIT %s""",
                (vector, user_id, vector, limit),
            )
            rows = cursor.fetchall()
            if rows:
                cursor.execute("UPDATE memories SET access_count = access_count + 1, last_accessed_at = now() WHERE id = ANY(%s::uuid[])", ([str(row[0]) for row in rows],))
        memories = [{"id": str(row[0]), "role": row[1], "content": row[2], "user_id": user_id,
                 "memory_type": row[3], "timestamp": row[4].isoformat(), "concepts": row[5],
                 "similarity": float(row[6] or 0)} for row in rows if self._is_safe_memory(row[1], row[2])]
        if memories:
            return memories
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT id, user_text, created_at FROM conversation_turns
                   WHERE user_id = %s AND scope = 'general' AND user_text ILIKE %s
                   ORDER BY created_at DESC LIMIT %s""",
                (user_id, f"%{query.strip()}%", limit),
            )
            return [{"id": str(row[0]), "role": "user", "content": row[1], "user_id": user_id,
                     "memory_type": "conversation", "timestamp": row[2].isoformat()}
                    for row in cursor.fetchall()]

    def _facts(self, query: str, user_id: str, scope: str, limit: int) -> List[Dict[str, Any]]:
        terms = [f"%{term}%" for term in self._extract_concepts(query)] or ["%%"]
        with self._cursor() as cursor:
            cursor.execute("""SELECT subject, predicate, object, value, confidence, source
                              FROM facts WHERE user_id = %s AND scope = %s AND invalidated_at IS NULL
                              AND status = 'confirmed'
                              AND (subject ILIKE ANY(%s) OR predicate ILIKE ANY(%s) OR object ILIKE ANY(%s))
                              ORDER BY confidence DESC, last_reinforced_at DESC LIMIT %s""",
                           (user_id, scope, terms, terms, terms, limit))
            return [{"subject": row[0], "predicate": row[1], "object": row[2], "value": row[3], "confidence": row[4], "source": row[5]} for row in cursor.fetchall()]

    def _context(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        query, user_id = payload.get("text", payload.get("query", "")), payload.get("user_id", "default")
        scope = payload.get("scope", "general")
        limits = payload.get("limits", {})
        turn_limit = min(max(int(limits.get("turns", payload.get("max_results", 8))), 1), 50)
        with self._cursor() as cursor:
            cursor.execute(
                """SELECT id, conversation_id, user_text, assistant_text, created_at, importance
                   FROM conversation_turns
                   WHERE user_id = %s AND scope = %s
                     AND to_tsvector('simple', user_text || ' ' || COALESCE(assistant_text, ''))
                         @@ websearch_to_tsquery('simple', %s)
                   ORDER BY created_at DESC LIMIT %s""",
                (user_id, scope, query, turn_limit),
            )
            turns = [{"id": str(row[0]), "conversation_id": str(row[1]), "user_text": row[2],
                      "assistant_text": row[3], "timestamp": row[4].isoformat(), "importance": row[5]}
                     for row in cursor.fetchall()]
        facts = self._facts(query, user_id, scope, min(max(int(limits.get("facts", 12)), 1), 50))
        memories = [{"role": "user", "content": turn["user_text"], "timestamp": turn["timestamp"]}
                    for turn in turns]
        return {"status": "success", "content": {"query": query, "user_id": user_id, "scope": scope,
                "turns": turns, "memories": memories, "semantic": memories, "facts": facts,
                "episodes": [], "patterns": [], "working_set": memories, "conflicts": [],
                "concepts": self._extract_concepts(query),
                "retrieval": {"lexical_available": True, "semantic_available": True,
                              "candidate_count": len(turns), "returned_count": len(turns), "truncated": False},
                "summary": f"Found {len(turns)} turns and {len(facts)} facts"}}

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("content", message)
        if message.get("type") == "health":
            return {"status": "success", "content": {"healthy": self.running, "ready": self.memory_ready.is_set()}}
        if message.get("type") == "store":
            return self._store(payload)
        if message.get("type") == "store_turn":
            return self._store_turn(payload)
        if message.get("type") in {"query", "query_semantic"}:
            memories = self.retrieve_memories(payload.get("query", payload.get("text", "")), payload.get("user_id", "default"), payload.get("limit", 15))
            return {"status": "success", "content": {"results": memories, "memories": memories}}
        if message.get("type") in {"query_context", "context"}:
            return self._context(payload)
        if message.get("type") == "query_facts":
            facts = self._facts(
                payload.get("query", payload.get("subject", "")),
                payload.get("user_id", "default"),
                payload.get("scope", "general"),
                payload.get("limit", 10),
            )
            return {"status": "success", "content": {"facts": facts}}
        return {"status": "error", "message": f"Unknown message type: {message.get('type')}", "content": {}}

    def shutdown(self) -> None:
        with self._lock:
            if self.running:
                self.running = False
                self._pool.closeall()
