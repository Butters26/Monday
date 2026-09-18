"""Active Notus memory lobe.

One job: memory.
One database backend: PostgreSQL.

This uses the strongest memory primitives already present in ``notus.py``
(semantic retrieval, episodic memory, durable facts, working memory and memory
associations) but deliberately does not expose the old response-generation or
"EnhancedMonday" compatibility layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import threading
import uuid
from typing import Any, Dict, List, Optional

try:
    import psycopg2
    from psycopg2.extras import Json
except ImportError as exc:  # PostgreSQL is intentionally mandatory.
    raise RuntimeError(
        "Notus requires PostgreSQL. Install psycopg2-binary; SQLite fallback was removed."
    ) from exc

from notus import SuperhumanConfig, SuperhumanMemorySystem
from thalamus import get_thalamus


class NotusMemorySystem(SuperhumanMemorySystem):
    """PostgreSQL-only memory lobe used by the active Monday core."""

    def __init__(
        self,
        thalamus: Any = None,
        dsn: Optional[str] = None,
        config: Optional[SuperhumanConfig] = None,
    ) -> None:
        self.thalamus = thalamus or get_thalamus()
        self.running = True
        self.memory_ready = threading.Event()

        # Establish the connection before SuperhumanMemorySystem.__init__ runs.
        # The parent sees the existing PostgreSQL connection and initializes its
        # full memory schema without ever entering its legacy SQLite fallback.
        self._db_connection = self._connect_postgres(dsn)
        self._db_connection.set_session(autocommit=False)

        super().__init__(config=config or SuperhumanConfig(), storage_path=None)
        self._ensure_memory_integrity_schema()
        self.memory_ready.set()

    @staticmethod
    def _connect_postgres(dsn: Optional[str] = None):
        configured_dsn = dsn or os.getenv("NOTUS_POSTGRES_DSN")
        if configured_dsn:
            return psycopg2.connect(configured_dsn, connect_timeout=5)

        return psycopg2.connect(
            dbname=os.getenv("NOTUS_POSTGRES_DB", "notus_memory"),
            user=os.getenv("NOTUS_POSTGRES_USER", os.getenv("USER", "matthew")),
            password=os.getenv("NOTUS_POSTGRES_PASSWORD") or None,
            host=os.getenv("NOTUS_POSTGRES_HOST", "localhost"),
            port=int(os.getenv("NOTUS_POSTGRES_PORT", "5432")),
            connect_timeout=5,
        )

    def _ensure_memory_integrity_schema(self) -> None:
        """Add contradiction metadata missing from the older PostgreSQL schema."""
        with self._db_connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE brain_facts "
                "ADD COLUMN IF NOT EXISTS conflicts_with JSONB"
            )
            cursor.execute(
                "ALTER TABLE brain_facts "
                "ADD COLUMN IF NOT EXISTS is_contradicted BOOLEAN NOT NULL DEFAULT FALSE"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_fact_contradicted "
                "ON brain_facts(user_id, is_contradicted)"
            )
        self._db_connection.commit()

    # ------------------------------------------------------------------
    # Durable facts with contradiction tracking
    # ------------------------------------------------------------------

    def _detect_contradictory_facts(
        self,
        subject: str,
        predicate: str,
        obj: str,
        user_id: str,
    ) -> List[Dict[str, str]]:
        with self._db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, object
                FROM brain_facts
                WHERE lower(subject) = lower(%s)
                  AND lower(predicate) = lower(%s)
                  AND lower(object) <> lower(%s)
                  AND (user_id = %s OR user_id IS NULL)
                  AND COALESCE(is_contradicted, FALSE) = FALSE
                ORDER BY confidence DESC
                """,
                (subject, predicate, obj, user_id),
            )
            return [
                {"id": str(row[0]), "object": str(row[1])}
                for row in cursor.fetchall()
            ]

    def remember_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        value: Optional[str] = None,
        confidence: float = 0.9,
        user_id: str = "default",
        source: str = "user",
        permanent: bool = False,
    ) -> Optional[str]:
        """Store/reinforce a fact and mark incompatible values as contradicted."""
        subject = (subject or "").strip()
        predicate = (predicate or "").strip()
        obj = (obj or "").strip()
        user_id = (user_id or "default").strip()
        if not subject or not predicate or not obj:
            return None

        confidence = max(0.0, min(float(confidence), 1.0))
        contradictions = self._detect_contradictory_facts(
            subject, predicate, obj, user_id
        )
        now = datetime.now(timezone.utc)

        with self._db_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, confidence, permanent, usage_count
                FROM brain_facts
                WHERE lower(subject) = lower(%s)
                  AND lower(predicate) = lower(%s)
                  AND lower(object) = lower(%s)
                  AND (user_id = %s OR user_id IS NULL)
                LIMIT 1
                """,
                (subject, predicate, obj, user_id),
            )
            existing = cursor.fetchone()
            conflict_json = Json(contradictions) if contradictions else None

            if existing:
                fact_id, old_confidence, old_permanent, usage_count = existing
                new_confidence = min(
                    1.0,
                    float(old_confidence or 0.0)
                    + 0.05
                    + 0.5 * max(0.0, confidence - 0.8),
                )
                cursor.execute(
                    """
                    UPDATE brain_facts
                    SET value = COALESCE(%s, value),
                        confidence = %s,
                        permanent = %s,
                        usage_count = %s,
                        last_reinforced = %s,
                        source = COALESCE(%s, source),
                        conflicts_with = %s,
                        is_contradicted = FALSE
                    WHERE id = %s
                    """,
                    (
                        value,
                        new_confidence,
                        1 if (old_permanent or permanent) else 0,
                        int(usage_count or 0) + 1,
                        now.isoformat(),
                        source,
                        conflict_json,
                        fact_id,
                    ),
                )
            else:
                fact_id = str(uuid.uuid4())
                semantic_hash = __import__("hashlib").sha256(
                    f"{subject}|{predicate}|{obj}|{user_id}".encode("utf-8")
                ).hexdigest()
                cursor.execute(
                    """
                    INSERT INTO brain_facts
                    (id, subject, predicate, object, value, confidence, permanent,
                     usage_count, created_at, last_reinforced, user_id, source,
                     semantic_hash, conflicts_with, is_contradicted)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s,
                            %s, %s, FALSE)
                    """,
                    (
                        fact_id,
                        subject,
                        predicate,
                        obj,
                        value,
                        confidence,
                        1 if permanent else 0,
                        now.isoformat(),
                        now.isoformat(),
                        user_id,
                        source,
                        semantic_hash,
                        conflict_json,
                    ),
                )

            for conflict in contradictions:
                cursor.execute(
                    "UPDATE brain_facts SET is_contradicted = TRUE WHERE id = %s",
                    (conflict["id"],),
                )

        self._db_connection.commit()
        return str(fact_id)

    def recall_facts(
        self,
        query: str,
        user_id: str = "default",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Use the parent semantic ranking, but suppress contradicted facts."""
        results = super().recall_facts(query, user_id=user_id, limit=max(limit * 3, 20))
        if not results:
            return []

        ids = [str(item.get("id")) for item in results if item.get("id")]
        if not ids:
            return results[:limit]

        with self._db_connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, COALESCE(is_contradicted, FALSE), conflicts_with "
                "FROM brain_facts WHERE id = ANY(%s)",
                (ids,),
            )
            integrity = {
                str(row[0]): {
                    "is_contradicted": bool(row[1]),
                    "conflicts_with": row[2] or [],
                }
                for row in cursor.fetchall()
            }

        clean: List[Dict[str, Any]] = []
        for item in results:
            state = integrity.get(str(item.get("id")), {})
            if state.get("is_contradicted"):
                continue
            item = dict(item)
            item["conflicts_with"] = state.get("conflicts_with", [])
            clean.append(item)
            if len(clean) >= max(1, int(limit)):
                break
        return clean

    # ------------------------------------------------------------------
    # Direct Thalamus interface
    # ------------------------------------------------------------------

    def start(self) -> "NotusMemorySystem":
        self.thalamus.register_lobe("notus", self)
        return self

    @staticmethod
    def _payload(message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("content", message)
        return payload if isinstance(payload, dict) else {}

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        payload = self._payload(message)
        user_id = str(payload.get("user_id", "default") or "default")

        if msg_type == "health":
            return {
                "status": "success",
                "content": {
                    "healthy": self.running,
                    "backend": "postgresql",
                    "ready": self.memory_ready.is_set(),
                },
            }

        if msg_type == "store":
            content = payload.get("content")
            role = payload.get("role", "user")
            if not isinstance(content, str) or not content.strip():
                return {"status": "error", "message": "content must be non-empty text"}
            memory_id = self.store_memory(
                role=str(role),
                content=content.strip(),
                user_id=user_id,
                tag=str(payload.get("tag", "General")),
                importance=float(payload.get("importance", 5.0)),
                mode=str(payload.get("mode", "memory")),
                memory_type=str(payload.get("memory_type", "conversation")),
                personality=str(payload.get("personality", "neutral")),
            )
            if not memory_id:
                return {"status": "error", "message": "memory was not stored"}
            return {
                "status": "success",
                "content": {"stored": True, "id": memory_id, "content": content.strip()},
            }

        if msg_type in {"query", "query_semantic", "query_memories"}:
            query = str(payload.get("query", payload.get("text", "")) or "")
            limit = max(1, min(int(payload.get("limit", 15)), 100))
            memories = self.retrieve_memories_smart(query, user_id=user_id, limit=limit)
            return {
                "status": "success",
                "content": {"results": memories, "memories": memories, "count": len(memories)},
            }

        if msg_type == "query_context":
            query = str(payload.get("query", payload.get("text", "")) or "")
            limit = max(1, min(int(payload.get("limit", payload.get("max_results", 10))), 50))
            memories = self.retrieve_memories_smart(query, user_id=user_id, limit=limit)
            facts = self.recall_facts(query, user_id=user_id, limit=limit)
            episodes = self.recall_episodes(query, user_id=user_id, limit=limit)
            self._update_working_set(facts, episodes)
            return {
                "status": "success",
                "content": {
                    "memories": memories,
                    "semantic": memories,
                    "facts": facts,
                    "episodic": episodes,
                    "working_set": self.get_working_set(),
                },
            }

        if msg_type in {"remember_fact", "store_fact"}:
            fact_id = self.remember_fact(
                subject=str(payload.get("subject", "")),
                predicate=str(payload.get("predicate", "")),
                obj=str(payload.get("object", payload.get("obj", ""))),
                value=payload.get("value"),
                confidence=float(payload.get("confidence", 0.9)),
                user_id=user_id,
                source=str(payload.get("source", message.get("source", "user"))),
                permanent=bool(payload.get("permanent", False)),
            )
            if not fact_id:
                return {"status": "error", "message": "subject, predicate and object are required"}
            return {"status": "success", "content": {"id": fact_id}}

        if msg_type == "query_facts":
            query = str(payload.get("query", payload.get("text", "")) or "")
            facts = self.recall_facts(
                query,
                user_id=user_id,
                limit=max(1, min(int(payload.get("limit", 10)), 100)),
            )
            return {"status": "success", "content": {"facts": facts, "count": len(facts)}}

        if msg_type in {"store_event", "remember_event"}:
            event_id = self.store_event(
                actor=str(payload.get("actor", "user")),
                action=str(payload.get("action", "observed")),
                object=payload.get("object"),
                place=payload.get("place"),
                cause=payload.get("cause"),
                effect=payload.get("effect"),
                note=payload.get("note"),
                sentiment=payload.get("sentiment"),
                confidence=float(payload.get("confidence", 0.8)),
                user_id=user_id,
                source=str(payload.get("source", message.get("source", "user"))),
            )
            if not event_id:
                return {"status": "error", "message": "event was not stored"}
            return {"status": "success", "content": {"id": event_id}}

        if msg_type == "query_episodic":
            query = str(payload.get("query", payload.get("text", "")) or "")
            episodes = self.recall_episodes(
                query,
                user_id=user_id,
                limit=max(1, min(int(payload.get("limit", 10)), 100)),
            )
            return {
                "status": "success",
                "content": {"events": episodes, "episodes": episodes, "count": len(episodes)},
            }

        if msg_type == "query_associations":
            memory_id = str(payload.get("memory_id", "") or "")
            if not memory_id:
                return {"status": "error", "message": "memory_id is required"}
            associations = self.get_associated_memories(
                memory_id,
                limit=max(1, min(int(payload.get("limit", 10)), 100)),
            )
            return {
                "status": "success",
                "content": {"associations": associations, "count": len(associations)},
            }

        if msg_type in {"get_recent", "get_recent_memories"}:
            limit = max(1, min(int(payload.get("limit", 5)), 50))
            with self._db_connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, timestamp, role, content, tag, importance_score,
                           memory_type, conversation_id
                    FROM superhuman_memories
                    WHERE user_id = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                rows = cursor.fetchall()
            memories = [
                {
                    "id": row[0],
                    "timestamp": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
                    "role": row[2],
                    "content": row[3],
                    "tag": row[4],
                    "importance": row[5],
                    "memory_type": row[6],
                    "conversation_id": row[7],
                }
                for row in rows
            ]
            return {
                "status": "success",
                "content": {"memories": memories, "results": memories, "count": len(memories)},
            }

        if msg_type == "get_conversation_history":
            limit = max(1, min(int(payload.get("limit", 20)), 100))
            with self._db_connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, timestamp, role, content, tag, importance_score,
                           memory_type, conversation_id
                    FROM superhuman_memories
                    WHERE user_id = %s AND memory_type = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """,
                    (user_id, "conversation", limit),
                )
                rows = cursor.fetchall()
            history = [
                {
                    "id": row[0],
                    "timestamp": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
                    "role": row[2],
                    "content": row[3],
                    "tag": row[4],
                    "importance": row[5],
                    "memory_type": row[6],
                    "conversation_id": row[7],
                }
                for row in reversed(rows)
            ]
            return {"status": "success", "content": {"history": history, "count": len(history)}}

        if msg_type in {"get_emotional_memories", "get_all_emotional_memories"}:
            query = str(payload.get("trigger", payload.get("input", "")) or "")
            memories = self.retrieve_memories_smart(query, user_id=user_id, limit=30)
            emotional = [
                item for item in memories
                if str(item.get("tag", "")).lower().startswith("emotion")
                or str(item.get("memory_type", "")).lower() == "emotional"
            ]
            return {"status": "success", "content": {"memories": emotional}}

        if msg_type == "get_past_emotional_responses":
            memories = self.retrieve_memories_smart(
                str(payload.get("input", "") or ""), user_id=user_id, limit=20
            )
            responses = [
                {"response": item.get("content", ""), **item}
                for item in memories
                if str(item.get("memory_type", "")).lower() == "emotional_response"
            ]
            return {"status": "success", "content": {"responses": responses}}

        if msg_type == "query_patterns":
            return {"status": "success", "content": {"patterns": []}}

        return {"status": "error", "message": f"Unknown message type: {msg_type}"}

    def shutdown(self) -> None:
        if not self.running:
            return
        self.running = False
        try:
            self.snapshot()
        except Exception:
            pass
        try:
            self._db_connection.commit()
        finally:
            self._db_connection.close()


# Compatibility name for code that expects a Notus process object.
NotusProcess = NotusMemorySystem
