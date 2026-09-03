"""SQLite memory adapter for the direct Monday core.

This module deliberately has no dependency on the historical Notus process or
its optional database and ML dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from runtime_paths import runtime_file
from thalamus import get_thalamus


_TRANSCRIPT_PREFIX = re.compile(r"^\s*(?:user|abin)\s*:", re.IGNORECASE)


class DirectNotusProcess:
    """Persist structured, user-scoped conversation input in SQLite."""

    def __init__(self, storage_path: Optional[str] = None, thalamus: Any = None) -> None:
        self.running = True
        self.thalamus = thalamus or get_thalamus()
        self.storage_path = storage_path or runtime_file("notus_memory.sqlite3")
        Path(self.storage_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection: Optional[sqlite3.Connection] = sqlite3.connect(
            self.storage_path, check_same_thread=False
        )
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                user_id TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        self._connection.commit()
        self.memory_ready = threading.Event()
        self.memory_ready.set()

    @staticmethod
    def _is_safe_memory(role: Any, content: Any) -> bool:
        """Reject legacy combined transcript rows before they reach a renderer."""
        return (
            isinstance(role, str)
            and role in {"user", "fact", "note"}
            and isinstance(content, str)
            and bool(content.strip())
            and not _TRANSCRIPT_PREFIX.match(content)
        )

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("Notus is closed")
        return self._connection

    def start(self) -> "DirectNotusProcess":
        if not self.running:
            raise RuntimeError("Cannot restart a closed Notus adapter")
        self.thalamus.register_lobe("notus", self)
        return self

    def retrieve_memories(
        self,
        query: str = "",
        user_id: str = "default",
        limit: int = 15,
        memory_type: Any = None,
    ) -> List[Dict[str, Any]]:
        """Return only clean, structured records belonging to ``user_id``."""
        if not isinstance(user_id, str):
            return []
        terms = [
            term.lower() for term in query.split()
            if len(term) > 2 and not _TRANSCRIPT_PREFIX.match(term)
        ]
        sql = (
            "SELECT role, content, user_id, memory_type, created_at FROM memories "
            "WHERE user_id = ? "
            "AND role IN ('user', 'fact', 'note') "
            "AND lower(trim(content)) NOT LIKE 'user:%' "
            "AND lower(trim(content)) NOT LIKE 'abin:%'"
        )
        params: List[Any] = [user_id]
        if isinstance(memory_type, str) and memory_type.strip():
            sql += " AND memory_type = ?"
            params.append(memory_type.strip())
        elif isinstance(memory_type, (list, tuple, set)):
            memory_types = [
                item.strip()
                for item in memory_type
                if isinstance(item, str) and item.strip()
            ]
            if memory_types:
                sql += " AND (" + " OR ".join("memory_type = ?" for _ in memory_types) + ")"
                params.extend(memory_types)
        if terms:
            sql += " AND (" + " OR ".join("lower(content) LIKE ?" for _ in terms) + ")"
            params.extend(f"%{term}%" for term in terms)
        try:
            normalized_limit = int(limit)
        except (TypeError, ValueError):
            normalized_limit = 15
        normalized_limit = max(1, min(normalized_limit, 100))
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(normalized_limit)

        with self._lock:
            rows = self._require_connection().execute(sql, params).fetchall()
        return [
            {
                "role": role,
                "content": content.strip(),
                "user_id": stored_user,
                "memory_type": memory_type,
                "timestamp": created_at,
            }
            for role, content, stored_user, memory_type, created_at in rows
            if self._is_safe_memory(role, content)
        ][:normalized_limit]

    def _store(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        content = payload.get("content")
        role = payload.get("role", "user")
        user_id = payload.get("user_id", "default")
        if not self._is_safe_memory(role, content):
            return {"status": "error", "message": "Memory must be clean structured content"}
        if not isinstance(user_id, str) or not user_id:
            return {"status": "error", "message": "Memory user_id must be a non-empty string"}

        with self._lock:
            connection = self._require_connection()
            connection.execute(
                "INSERT INTO memories(role, content, user_id, memory_type, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    role,
                    content.strip(),
                    user_id,
                    payload.get("memory_type", "conversation"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()
        return {"status": "success", "content": {"stored": True, "content": content.strip()}}

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        payload = message.get("content", message)
        if msg_type == "health":
            return {"status": "success", "content": {"healthy": self.running}}
        if msg_type == "store":
            return self._store(payload)
        if msg_type in {"query", "query_semantic"}:
            query = payload.get("query", payload.get("text", ""))
            memories = self.retrieve_memories(
                query,
                payload.get("user_id", "default"),
                payload.get("limit", 15),
                payload.get("memory_type"),
            )
            return {"status": "success", "content": {"results": memories, "memories": memories}}
        if msg_type == "query_context":
            query = payload.get("text", "")
            memories = self.retrieve_memories(
                query,
                payload.get("user_id", "default"),
                payload.get("max_results", 15),
                payload.get("memory_type"),
            )
            return {
                "status": "success",
                "content": {
                    "query_text": query,
                    "semantic": memories,
                    "episodic": [],
                    "facts": [],
                    "summary": f"Found {len(memories)} stored memories",
                },
            }
        if msg_type in {"query_episodic", "query_facts", "query_patterns"}:
            key = {"query_episodic": "events", "query_facts": "facts", "query_patterns": "patterns"}[msg_type]
            return {"status": "success", "content": {key: []}}
        return {"status": "error", "message": f"Unknown message type: {msg_type}"}

    def shutdown(self) -> None:
        """Close once; repeat shutdown calls are harmless."""
        with self._lock:
            self.running = False
            if self._connection is not None:
                self._connection.close()
                self._connection = None
