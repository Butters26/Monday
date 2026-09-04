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
_LEARNING_KEY_SAFE = re.compile(r"[^a-z0-9:_-]+")
_UNSAFE_LEARNING = re.compile(
    r"(?:ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|"
    r"reveal\s+(?:the\s+)?system\s+prompt|developer\s+message)",
    re.IGNORECASE,
)


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
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS lobe_learning (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lobe TEXT NOT NULL,
                user_id TEXT NOT NULL,
                learning_key TEXT NOT NULL,
                fact TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_count INTEGER NOT NULL DEFAULT 1,
                contradiction_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                source TEXT NOT NULL DEFAULT 'thalamus',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(lobe, user_id, learning_key)
            )"""
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_lobe_learning_scope "
            "ON lobe_learning(lobe, user_id, status, confidence, updated_at)"
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

    @staticmethod
    def _clean_text(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _clamp_confidence(value: Any, default: float = 0.6) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
        return max(0.0, min(number, 1.0))

    @staticmethod
    def _normalise_learning_key(raw_key: Any, fact: str) -> str:
        if isinstance(raw_key, str) and raw_key.strip():
            key_source = raw_key.strip().lower()
        else:
            key_source = fact.strip().lower()[:96]
        key = _LEARNING_KEY_SAFE.sub("_", key_source).strip("_")
        return key[:96] if key else "general_fact"

    @staticmethod
    def _is_safe_learning_fact(fact: str) -> bool:
        return (
            bool(fact)
            and len(fact) <= 500
            and not _TRANSCRIPT_PREFIX.match(fact)
            and not _UNSAFE_LEARNING.search(fact)
        )

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

    def _learn_lobe_fact(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        lobe = self._clean_text(payload.get("lobe"))
        user_id = self._clean_text(payload.get("user_id")) or "default"
        fact = self._clean_text(
            payload.get("fact", payload.get("content", payload.get("text", payload.get("value", ""))))
        )
        if not lobe:
            return {"status": "error", "message": "lobe is required"}
        if not self._is_safe_learning_fact(fact):
            return {"status": "error", "message": "Unsafe or invalid learning fact"}
        learning_key = self._normalise_learning_key(payload.get("key"), fact)
        confidence = self._clamp_confidence(payload.get("confidence"), default=0.6)
        source = self._clean_text(payload.get("source")) or "thalamus"
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            connection = self._require_connection()
            existing = connection.execute(
                "SELECT id, fact, confidence, evidence_count, contradiction_count "
                "FROM lobe_learning WHERE lobe = ? AND user_id = ? AND learning_key = ?",
                (lobe, user_id, learning_key),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO lobe_learning("
                    "lobe, user_id, learning_key, fact, confidence, evidence_count, "
                    "contradiction_count, status, source, created_at, updated_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)",
                    (lobe, user_id, learning_key, fact, confidence, 1, 0, source, now, now),
                )
                action = "created"
                resulting_confidence = confidence
                evidence_count = 1
                contradiction_count = 0
            else:
                row_id, old_fact, old_confidence, old_evidence, old_contradictions = existing
                same_fact = self._clean_text(old_fact).casefold() == fact.casefold()
                if same_fact:
                    reinforcement = self._clamp_confidence(payload.get("reinforcement"), default=0.7)
                    delta = 0.03 + (0.07 * reinforcement)
                    resulting_confidence = min(1.0, self._clamp_confidence(old_confidence, 0.6) + delta)
                    evidence_count = int(old_evidence) + 1
                    contradiction_count = int(old_contradictions)
                    action = "reinforced"
                else:
                    contradiction_count = int(old_contradictions) + 1
                    resulting_confidence = max(0.2, min(0.8, confidence * 0.85))
                    evidence_count = 1
                    action = "replaced_conflict"
                connection.execute(
                    "UPDATE lobe_learning SET fact = ?, confidence = ?, evidence_count = ?, "
                    "contradiction_count = ?, status = 'active', source = ?, updated_at = ? "
                    "WHERE id = ?",
                    (
                        fact,
                        resulting_confidence,
                        evidence_count,
                        contradiction_count,
                        source,
                        now,
                        row_id,
                    ),
                )
            connection.commit()
        return {
            "status": "success",
            "content": {
                "lobe": lobe,
                "user_id": user_id,
                "key": learning_key,
                "fact": fact,
                "confidence": resulting_confidence,
                "evidence_count": evidence_count,
                "contradiction_count": contradiction_count,
                "action": action,
            },
        }

    def _recall_lobe_facts(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        lobe = self._clean_text(payload.get("lobe"))
        user_id = self._clean_text(payload.get("user_id")) or "default"
        if not lobe:
            return {"status": "error", "message": "lobe is required"}
        query_text = self._clean_text(payload.get("query", payload.get("text", "")))
        terms = [term.lower() for term in query_text.split() if len(term) > 2]
        key_prefix = self._clean_text(payload.get("key_prefix")).lower()
        min_confidence = self._clamp_confidence(payload.get("min_confidence"), default=0.0)
        include_deprecated = bool(payload.get("include_deprecated", False))
        try:
            normalized_limit = int(payload.get("limit", 15))
        except (TypeError, ValueError):
            normalized_limit = 15
        normalized_limit = max(1, min(normalized_limit, 100))

        sql = (
            "SELECT learning_key, fact, confidence, evidence_count, contradiction_count, "
            "status, source, created_at, updated_at FROM lobe_learning "
            "WHERE lobe = ? AND user_id = ? AND confidence >= ?"
        )
        params: List[Any] = [lobe, user_id, min_confidence]
        if not include_deprecated:
            sql += " AND status = 'active'"
        if key_prefix:
            sql += " AND lower(learning_key) LIKE ?"
            params.append(f"{key_prefix}%")
        if terms:
            sql += " AND (" + " OR ".join("lower(fact) LIKE ?" for _ in terms) + ")"
            params.extend(f"%{term}%" for term in terms)
        sql += " ORDER BY confidence DESC, evidence_count DESC, updated_at DESC LIMIT ?"
        params.append(normalized_limit)

        with self._lock:
            rows = self._require_connection().execute(sql, params).fetchall()
        memories = [
            {
                "key": key,
                "content": fact,
                "fact": fact,
                "confidence": confidence,
                "evidence_count": evidence_count,
                "contradiction_count": contradiction_count,
                "status": status,
                "source": source,
                "created_at": created_at,
                "updated_at": updated_at,
            }
            for (
                key,
                fact,
                confidence,
                evidence_count,
                contradiction_count,
                status,
                source,
                created_at,
                updated_at,
            ) in rows
        ]
        return {"status": "success", "content": {"lobe": lobe, "memories": memories, "count": len(memories)}}

    def _adjust_lobe_fact(self, payload: Dict[str, Any], mode: str) -> Dict[str, Any]:
        lobe = self._clean_text(payload.get("lobe"))
        user_id = self._clean_text(payload.get("user_id")) or "default"
        if not lobe:
            return {"status": "error", "message": "lobe is required"}
        fallback_fact = self._clean_text(payload.get("fact", payload.get("text", payload.get("content", ""))))
        learning_key = self._normalise_learning_key(payload.get("key"), fallback_fact)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            connection = self._require_connection()
            existing = connection.execute(
                "SELECT id, confidence, evidence_count, contradiction_count, status "
                "FROM lobe_learning WHERE lobe = ? AND user_id = ? AND learning_key = ?",
                (lobe, user_id, learning_key),
            ).fetchone()
            if existing is None:
                return {"status": "error", "message": f"No learned fact for key: {learning_key}"}
            row_id, confidence, evidence_count, contradiction_count, status = existing
            confidence_value = self._clamp_confidence(confidence, 0.5)
            evidence_value = int(evidence_count)
            contradiction_value = int(contradiction_count)
            status_value = status if isinstance(status, str) else "active"
            if mode == "reinforce":
                delta = self._clamp_confidence(payload.get("delta"), default=0.08)
                new_confidence = min(1.0, confidence_value + max(0.01, delta))
                evidence_value += 1
                action = "reinforced"
            elif mode == "contradict":
                penalty = self._clamp_confidence(payload.get("penalty"), default=0.2)
                new_confidence = max(0.0, confidence_value - max(0.05, penalty))
                contradiction_value += 1
                if new_confidence < 0.15:
                    status_value = "deprecated"
                action = "contradicted"
            elif mode == "forget":
                new_confidence = confidence_value
                status_value = "deprecated"
                action = "forgotten"
            else:
                return {"status": "error", "message": f"Unknown adjustment mode: {mode}"}
            connection.execute(
                "UPDATE lobe_learning SET confidence = ?, evidence_count = ?, "
                "contradiction_count = ?, status = ?, updated_at = ? WHERE id = ?",
                (new_confidence, evidence_value, contradiction_value, status_value, now, row_id),
            )
            connection.commit()
        return {
            "status": "success",
            "content": {
                "lobe": lobe,
                "user_id": user_id,
                "key": learning_key,
                "confidence": new_confidence,
                "evidence_count": evidence_value,
                "contradiction_count": contradiction_value,
                "status": status_value,
                "action": action,
            },
        }

    def _lobe_learning_stats(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        lobe = self._clean_text(payload.get("lobe"))
        user_id = self._clean_text(payload.get("user_id")) or "default"
        if not lobe:
            return {"status": "error", "message": "lobe is required"}
        with self._lock:
            connection = self._require_connection()
            totals = connection.execute(
                "SELECT COUNT(*), COALESCE(AVG(confidence), 0.0), "
                "SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN status = 'deprecated' THEN 1 ELSE 0 END), "
                "COALESCE(SUM(evidence_count), 0), COALESCE(SUM(contradiction_count), 0) "
                "FROM lobe_learning WHERE lobe = ? AND user_id = ?",
                (lobe, user_id),
            ).fetchone()
        total_count, avg_confidence, active_count, deprecated_count, evidence_sum, contradiction_sum = totals
        return {
            "status": "success",
            "content": {
                "lobe": lobe,
                "user_id": user_id,
                "total_facts": int(total_count),
                "active_facts": int(active_count or 0),
                "deprecated_facts": int(deprecated_count or 0),
                "average_confidence": float(avg_confidence),
                "total_evidence": int(evidence_sum),
                "total_contradictions": int(contradiction_sum),
            },
        }

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
        if msg_type == "learn_lobe_fact":
            return self._learn_lobe_fact(payload)
        if msg_type == "recall_lobe_facts":
            return self._recall_lobe_facts(payload)
        if msg_type == "reinforce_lobe_fact":
            return self._adjust_lobe_fact(payload, "reinforce")
        if msg_type == "contradict_lobe_fact":
            return self._adjust_lobe_fact(payload, "contradict")
        if msg_type == "forget_lobe_fact":
            return self._adjust_lobe_fact(payload, "forget")
        if msg_type == "lobe_learning_stats":
            return self._lobe_learning_stats(payload)
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
