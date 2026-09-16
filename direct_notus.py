"""SQLite memory adapter for the direct Monday core."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sqlite3
import threading
from typing import Any, Deque, Dict, List, Optional, Tuple

from runtime_paths import runtime_file
from thalamus import get_thalamus


_TRANSCRIPT_PREFIX = re.compile(r"^\s*(?:user|abin)\s*:", re.IGNORECASE)
_LEARNING_KEY_SAFE = re.compile(r"[^a-z0-9:_-]+")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_UNSAFE_LEARNING = re.compile(
    r"(?:ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|"
    r"reveal\s+(?:the\s+)?system\s+prompt|developer\s+message)",
    re.IGNORECASE,
)


class DirectNotusProcess:
    """Persist structured, user-scoped memory in one SQLite file."""

    def __init__(self, storage_path: Optional[str] = None, thalamus: Any = None) -> None:
        self.running = True
        self.thalamus = thalamus or get_thalamus()
        self.storage_path = storage_path or runtime_file("notus_memory.sqlite3")
        Path(self.storage_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection: Optional[sqlite3.Connection] = sqlite3.connect(
            self.storage_path, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row

        self.working_set: Dict[str, Deque[Dict[str, Any]]] = {
            "turns": deque(maxlen=50),
            "facts": deque(maxlen=50),
            "episodes": deque(maxlen=50),
        }
        self._fts_available = False

        self._initialize_schema()
        self.memory_ready = threading.Event()
        self.memory_ready.set()

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("Notus is closed")
        return self._connection

    @staticmethod
    def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            if len(row) > 1
        }

    def _initialize_schema(self) -> None:
        with self._lock:
            connection = self._require_connection()

            connection.execute(
                """CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS brain_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    subject TEXT NOT NULL COLLATE NOCASE,
                    predicate TEXT NOT NULL COLLATE NOCASE,
                    object TEXT NOT NULL COLLATE NOCASE,
                    value TEXT,
                    confidence REAL NOT NULL DEFAULT 0.9,
                    usage_count INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_reinforced TEXT,
                    is_contradicted INTEGER NOT NULL DEFAULT 0,
                    conflicts_with TEXT,
                    UNIQUE(user_id, subject, predicate, object)
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS episodic_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    object TEXT,
                    place TEXT,
                    cause TEXT,
                    effect TEXT,
                    note TEXT,
                    sentiment REAL,
                    confidence REAL NOT NULL DEFAULT 0.8,
                    created_at TEXT NOT NULL
                )"""
            )
            connection.execute(
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
                    use_count INTEGER NOT NULL DEFAULT 0,
                    last_applied_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(lobe, user_id, learning_key)
                )"""
            )

            self._ensure_memory_schema()
            self._ensure_fact_schema()
            self._ensure_episode_schema()
            self._ensure_lobe_learning_schema()

            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_user "
                "ON memories(user_id, created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_brain_facts_user "
                "ON brain_facts(user_id, is_contradicted, created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_episodic_events_user "
                "ON episodic_events(user_id, created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_lobe_learning_scope "
                "ON lobe_learning(lobe, user_id, status, confidence, updated_at)"
            )

            self._initialize_fts()
            connection.commit()

    def _ensure_memory_schema(self) -> None:
        connection = self._require_connection()
        columns = self._table_columns(connection, "memories")
        if "access_count" not in columns:
            connection.execute(
                "ALTER TABLE memories ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0"
            )
        if "last_accessed" not in columns:
            connection.execute("ALTER TABLE memories ADD COLUMN last_accessed TEXT")

    def _ensure_fact_schema(self) -> None:
        connection = self._require_connection()
        columns = self._table_columns(connection, "brain_facts")
        additions = {
            "value": "TEXT",
            "confidence": "REAL NOT NULL DEFAULT 0.9",
            "usage_count": "INTEGER NOT NULL DEFAULT 1",
            "created_at": "TEXT",
            "last_reinforced": "TEXT",
            "is_contradicted": "INTEGER NOT NULL DEFAULT 0",
            "conflicts_with": "TEXT",
        }
        for name, declaration in additions.items():
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE brain_facts ADD COLUMN {name} {declaration}"
                )

    def _ensure_episode_schema(self) -> None:
        connection = self._require_connection()
        columns = self._table_columns(connection, "episodic_events")
        additions = {
            "object": "TEXT",
            "place": "TEXT",
            "cause": "TEXT",
            "effect": "TEXT",
            "note": "TEXT",
            "sentiment": "REAL",
            "confidence": "REAL NOT NULL DEFAULT 0.8",
            "created_at": "TEXT",
        }
        for name, declaration in additions.items():
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE episodic_events ADD COLUMN {name} {declaration}"
                )

    def _ensure_lobe_learning_schema(self) -> None:
        connection = self._require_connection()
        columns = self._table_columns(connection, "lobe_learning")
        if "use_count" not in columns:
            connection.execute(
                "ALTER TABLE lobe_learning ADD COLUMN use_count INTEGER NOT NULL DEFAULT 0"
            )
        if "last_applied_at" not in columns:
            connection.execute(
                "ALTER TABLE lobe_learning ADD COLUMN last_applied_at TEXT"
            )

    def _initialize_fts(self) -> None:
        connection = self._require_connection()
        try:
            connection.executescript(
                """
                DROP TRIGGER IF EXISTS memories_ai;
                DROP TRIGGER IF EXISTS memories_ad;
                DROP TRIGGER IF EXISTS memories_au;
                DROP TRIGGER IF EXISTS brain_facts_ai;
                DROP TRIGGER IF EXISTS brain_facts_ad;
                DROP TRIGGER IF EXISTS brain_facts_au;
                DROP TRIGGER IF EXISTS episodic_events_ai;
                DROP TRIGGER IF EXISTS episodic_events_ad;
                DROP TRIGGER IF EXISTS episodic_events_au;
                DROP TABLE IF EXISTS memories_fts;
                DROP TABLE IF EXISTS brain_facts_fts;
                DROP TABLE IF EXISTS episodic_events_fts;
                """
            )

            connection.execute(
                "CREATE VIRTUAL TABLE memories_fts USING fts5(content)"
            )
            connection.execute(
                "CREATE VIRTUAL TABLE brain_facts_fts "
                "USING fts5(subject, predicate, object, value)"
            )
            connection.execute(
                "CREATE VIRTUAL TABLE episodic_events_fts "
                "USING fts5(actor, action, object, place, cause, effect, note)"
            )

            connection.execute(
                "INSERT INTO memories_fts(rowid, content) "
                "SELECT id, content FROM memories"
            )
            connection.execute(
                "INSERT INTO brain_facts_fts(rowid, subject, predicate, object, value) "
                "SELECT id, subject, predicate, object, COALESCE(value, '') FROM brain_facts"
            )
            connection.execute(
                "INSERT INTO episodic_events_fts("
                "rowid, actor, action, object, place, cause, effect, note"
                ") SELECT id, actor, action, COALESCE(object, ''), COALESCE(place, ''), "
                "COALESCE(cause, ''), COALESCE(effect, ''), COALESCE(note, '') "
                "FROM episodic_events"
            )

            connection.executescript(
                """
                CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, content)
                    VALUES (new.id, new.content);
                END;
                CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN
                    DELETE FROM memories_fts WHERE rowid = old.id;
                END;
                CREATE TRIGGER memories_au AFTER UPDATE OF content ON memories BEGIN
                    DELETE FROM memories_fts WHERE rowid = old.id;
                    INSERT INTO memories_fts(rowid, content)
                    VALUES (new.id, new.content);
                END;

                CREATE TRIGGER brain_facts_ai AFTER INSERT ON brain_facts BEGIN
                    INSERT INTO brain_facts_fts(rowid, subject, predicate, object, value)
                    VALUES (
                        new.id, new.subject, new.predicate, new.object, COALESCE(new.value, '')
                    );
                END;
                CREATE TRIGGER brain_facts_ad AFTER DELETE ON brain_facts BEGIN
                    DELETE FROM brain_facts_fts WHERE rowid = old.id;
                END;
                CREATE TRIGGER brain_facts_au
                AFTER UPDATE OF subject, predicate, object, value ON brain_facts BEGIN
                    DELETE FROM brain_facts_fts WHERE rowid = old.id;
                    INSERT INTO brain_facts_fts(rowid, subject, predicate, object, value)
                    VALUES (
                        new.id, new.subject, new.predicate, new.object, COALESCE(new.value, '')
                    );
                END;

                CREATE TRIGGER episodic_events_ai AFTER INSERT ON episodic_events BEGIN
                    INSERT INTO episodic_events_fts(
                        rowid, actor, action, object, place, cause, effect, note
                    )
                    VALUES (
                        new.id, new.actor, new.action, COALESCE(new.object, ''),
                        COALESCE(new.place, ''), COALESCE(new.cause, ''),
                        COALESCE(new.effect, ''), COALESCE(new.note, '')
                    );
                END;
                CREATE TRIGGER episodic_events_ad AFTER DELETE ON episodic_events BEGIN
                    DELETE FROM episodic_events_fts WHERE rowid = old.id;
                END;
                CREATE TRIGGER episodic_events_au
                AFTER UPDATE OF actor, action, object, place, cause, effect, note
                ON episodic_events BEGIN
                    DELETE FROM episodic_events_fts WHERE rowid = old.id;
                    INSERT INTO episodic_events_fts(
                        rowid, actor, action, object, place, cause, effect, note
                    )
                    VALUES (
                        new.id, new.actor, new.action, COALESCE(new.object, ''),
                        COALESCE(new.place, ''), COALESCE(new.cause, ''),
                        COALESCE(new.effect, ''), COALESCE(new.note, '')
                    );
                END;
                """
            )
            self._fts_available = True
        except sqlite3.OperationalError:
            self._fts_available = False

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

    @staticmethod
    def _clean_text(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _optional_text(value: Any) -> Optional[str]:
        cleaned = value.strip() if isinstance(value, str) else ""
        return cleaned or None

    @staticmethod
    def _clamp_confidence(value: Any, default: float = 0.6) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
        return max(0.0, min(number, 1.0))

    @staticmethod
    def _normalise_limit(value: Any, default: int = 15) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError):
            result = default
        return max(1, min(result, 100))

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

    @classmethod
    def _is_safe_structured_text(cls, value: Any, max_length: int = 2000) -> bool:
        text = cls._clean_text(value)
        return (
            bool(text)
            and len(text) <= max_length
            and not _TRANSCRIPT_PREFIX.match(text)
            and not _UNSAFE_LEARNING.search(text)
        )

    @staticmethod
    def _query_terms(query: str) -> List[str]:
        return [
            token.casefold()
            for token in _TOKEN_RE.findall(query or "")
            if len(token) > 1
        ]

    @classmethod
    def _fts_query(cls, query: str) -> str:
        return " OR ".join(f'"{term}"' for term in cls._query_terms(query))

    @classmethod
    def _match_quality(cls, query: str, text: str) -> float:
        terms = cls._query_terms(query)
        if not terms:
            return 0.0
        haystack = (text or "").casefold()
        matched = sum(1 for term in terms if term in haystack)
        coverage = matched / max(1, len(terms))
        phrase_bonus = 1.0 if query.strip().casefold() in haystack else 0.0
        return (coverage * 10.0) + phrase_bonus

    @staticmethod
    def _decode_conflicts(raw: Any) -> List[int]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [int(value) for value in parsed]
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        return []

    @classmethod
    def _merge_conflict_id(cls, raw: Any, fact_id: int) -> str:
        values = cls._decode_conflicts(raw)
        if fact_id not in values:
            values.append(fact_id)
        return json.dumps(values)

    def start(self) -> "DirectNotusProcess":
        if not self.running:
            raise RuntimeError("Cannot restart a closed Notus adapter")
        self.thalamus.register_lobe("notus", self)
        return self

    def _memory_type_filter(self, memory_type: Any) -> Tuple[str, List[Any]]:
        if isinstance(memory_type, str) and memory_type.strip():
            return " AND m.memory_type = ?", [memory_type.strip()]
        if isinstance(memory_type, (list, tuple, set)):
            values = [
                item.strip()
                for item in memory_type
                if isinstance(item, str) and item.strip()
            ]
            if values:
                return (
                    " AND m.memory_type IN (" + ",".join("?" for _ in values) + ")",
                    values,
                )
        return "", []

    def _search_memory_rows(
        self,
        query: str,
        user_id: str,
        memory_type: Any,
    ) -> List[sqlite3.Row]:
        connection = self._require_connection()
        type_sql, type_params = self._memory_type_filter(memory_type)
        fts_query = self._fts_query(query)

        if query.strip() and self._fts_available and fts_query:
            try:
                return connection.execute(
                    """
                    SELECT m.id, m.role, m.content, m.user_id, m.memory_type,
                           m.created_at, m.access_count, m.last_accessed,
                           bm25(memories_fts) AS fts_rank
                    FROM memories_fts
                    JOIN memories AS m ON m.id = memories_fts.rowid
                    WHERE memories_fts MATCH ?
                      AND m.user_id = ?
                      AND m.role IN ('user', 'fact', 'note')
                      AND lower(trim(m.content)) NOT LIKE 'user:%'
                      AND lower(trim(m.content)) NOT LIKE 'abin:%'
                    """
                    + type_sql,
                    [fts_query, user_id, *type_params],
                ).fetchall()
            except sqlite3.OperationalError:
                self._fts_available = False

        sql = (
            "SELECT m.id, m.role, m.content, m.user_id, m.memory_type, "
            "m.created_at, m.access_count, m.last_accessed, NULL AS fts_rank "
            "FROM memories AS m WHERE m.user_id = ? "
            "AND m.role IN ('user', 'fact', 'note') "
            "AND lower(trim(m.content)) NOT LIKE 'user:%' "
            "AND lower(trim(m.content)) NOT LIKE 'abin:%'"
            + type_sql
        )
        params: List[Any] = [user_id, *type_params]
        terms = self._query_terms(query)
        if terms:
            sql += " AND (" + " OR ".join("lower(m.content) LIKE ?" for _ in terms) + ")"
            params.extend(f"%{term}%" for term in terms)
        return connection.execute(sql, params).fetchall()

    def retrieve_memories(
        self,
        query: str = "",
        user_id: str = "default",
        limit: int = 15,
        memory_type: Any = None,
    ) -> List[Dict[str, Any]]:
        """Search all matching rows for a user, rank them, then apply the limit."""
        if not isinstance(user_id, str) or not user_id:
            return []

        normalized_limit = self._normalise_limit(limit, 15)

        with self._lock:
            connection = self._require_connection()
            rows = self._search_memory_rows(query, user_id, memory_type)
            ranked: List[Tuple[float, str, sqlite3.Row]] = []

            for row in rows:
                if not self._is_safe_memory(row["role"], row["content"]):
                    continue
                score = self._match_quality(query, row["content"])
                if row["fts_rank"] is not None:
                    score += max(0.0, -float(row["fts_rank"]))
                ranked.append((score, str(row["created_at"] or ""), row))

            ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
            chosen = ranked[:normalized_limit]
            now = datetime.now(timezone.utc).isoformat()

            if chosen:
                connection.executemany(
                    "UPDATE memories "
                    "SET access_count = access_count + 1, last_accessed = ? "
                    "WHERE id = ?",
                    [(now, int(row["id"])) for _, _, row in chosen],
                )
                connection.commit()

        return [
            {
                "id": int(row["id"]),
                "role": row["role"],
                "content": row["content"].strip(),
                "user_id": row["user_id"],
                "memory_type": row["memory_type"],
                "timestamp": row["created_at"],
                "access_count": int(row["access_count"] or 0) + 1,
                "last_accessed": now,
                "match_score": float(score),
            }
            for score, _created_at, row in chosen
        ]

    def _store(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        content = payload.get("content")
        role = payload.get("role", "user")
        user_id = payload.get("user_id", "default")
        if not self._is_safe_memory(role, content):
            return {"status": "error", "message": "Memory must be clean structured content"}
        if not isinstance(user_id, str) or not user_id:
            return {"status": "error", "message": "Memory user_id must be a non-empty string"}

        now = datetime.now(timezone.utc).isoformat()
        memory_type = self._clean_text(payload.get("memory_type")) or "conversation"

        with self._lock:
            connection = self._require_connection()
            cursor = connection.execute(
                "INSERT INTO memories(role, content, user_id, memory_type, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (role, content.strip(), user_id, memory_type, now),
            )
            memory_id = int(cursor.lastrowid)
            connection.commit()

        item = {
            "id": memory_id,
            "role": role,
            "content": content.strip(),
            "user_id": user_id,
            "memory_type": memory_type,
            "timestamp": now,
        }
        self.working_set["turns"].append(item)
        return {"status": "success", "content": {"stored": True, **item}}

    def store_brain_fact(
        self,
        subject: Any,
        predicate: Any,
        obj: Any,
        *,
        value: Any = None,
        confidence: Any = 0.9,
        user_id: Any = "default",
    ) -> Dict[str, Any]:
        subject_text = self._clean_text(subject)
        predicate_text = self._clean_text(predicate)
        object_text = self._clean_text(obj)
        value_text = self._optional_text(value)
        user_text = self._clean_text(user_id) or "default"

        if not self._is_safe_structured_text(subject_text, 500):
            raise ValueError("subject must be clean non-empty text")
        if not self._is_safe_structured_text(predicate_text, 500):
            raise ValueError("predicate must be clean non-empty text")
        if not self._is_safe_structured_text(object_text, 1000):
            raise ValueError("object must be clean non-empty text")
        if value_text and not self._is_safe_structured_text(value_text, 2000):
            raise ValueError("value must be clean text")

        confidence_value = self._clamp_confidence(confidence, 0.9)
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            connection = self._require_connection()
            existing = connection.execute(
                """
                SELECT id, value, confidence, usage_count, created_at
                FROM brain_facts
                WHERE user_id = ?
                  AND lower(subject) = lower(?)
                  AND lower(predicate) = lower(?)
                  AND lower(object) = lower(?)
                LIMIT 1
                """,
                (user_text, subject_text, predicate_text, object_text),
            ).fetchone()

            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO brain_facts(
                        user_id, subject, predicate, object, value, confidence,
                        usage_count, created_at, last_reinforced,
                        is_contradicted, conflicts_with
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, 0, NULL)
                    """,
                    (
                        user_text,
                        subject_text,
                        predicate_text,
                        object_text,
                        value_text,
                        confidence_value,
                        now,
                        now,
                    ),
                )
                fact_id = int(cursor.lastrowid)
                usage_count = 1
                created_at = now
                resulting_confidence = confidence_value
            else:
                fact_id = int(existing["id"])
                usage_count = int(existing["usage_count"] or 0) + 1
                created_at = str(existing["created_at"] or now)
                resulting_confidence = min(
                    1.0,
                    max(float(existing["confidence"] or 0.0), confidence_value) + 0.05,
                )
                connection.execute(
                    """
                    UPDATE brain_facts
                    SET value = COALESCE(?, value),
                        confidence = ?,
                        usage_count = ?,
                        last_reinforced = ?,
                        is_contradicted = 0,
                        conflicts_with = NULL
                    WHERE id = ?
                    """,
                    (
                        value_text,
                        resulting_confidence,
                        usage_count,
                        now,
                        fact_id,
                    ),
                )

            conflicting_rows = connection.execute(
                """
                SELECT id, conflicts_with
                FROM brain_facts
                WHERE user_id = ?
                  AND lower(subject) = lower(?)
                  AND lower(predicate) = lower(?)
                  AND lower(object) <> lower(?)
                  AND id <> ?
                  AND is_contradicted = 0
                """,
                (
                    user_text,
                    subject_text,
                    predicate_text,
                    object_text,
                    fact_id,
                ),
            ).fetchall()

            conflict_ids = [int(row["id"]) for row in conflicting_rows]

            for row in conflicting_rows:
                connection.execute(
                    "UPDATE brain_facts "
                    "SET is_contradicted = 1, conflicts_with = ? "
                    "WHERE id = ?",
                    (
                        self._merge_conflict_id(row["conflicts_with"], fact_id),
                        int(row["id"]),
                    ),
                )

            connection.execute(
                "UPDATE brain_facts SET conflicts_with = ? WHERE id = ?",
                (json.dumps(conflict_ids) if conflict_ids else None, fact_id),
            )
            connection.commit()

        item = {
            "id": fact_id,
            "user_id": user_text,
            "subject": subject_text,
            "predicate": predicate_text,
            "object": object_text,
            "value": value_text,
            "confidence": resulting_confidence,
            "usage_count": usage_count,
            "created_at": created_at,
            "last_reinforced": now,
            "is_contradicted": False,
            "conflicts_with": conflict_ids,
        }
        self.working_set["facts"].append(item)
        return item

    def remember_fact(
        self,
        subject: Any,
        predicate: Any,
        obj: Any,
        *,
        value: Any = None,
        confidence: Any = 0.9,
        user_id: Any = "default",
    ) -> Dict[str, Any]:
        return self.store_brain_fact(
            subject,
            predicate,
            obj,
            value=value,
            confidence=confidence,
            user_id=user_id,
        )

    def _search_fact_rows(self, query: str, user_id: str) -> List[sqlite3.Row]:
        connection = self._require_connection()
        fts_query = self._fts_query(query)

        if query.strip() and self._fts_available and fts_query:
            try:
                return connection.execute(
                    """
                    SELECT f.*, bm25(brain_facts_fts) AS fts_rank
                    FROM brain_facts_fts
                    JOIN brain_facts AS f ON f.id = brain_facts_fts.rowid
                    WHERE brain_facts_fts MATCH ?
                      AND f.user_id = ?
                      AND f.is_contradicted = 0
                    """,
                    (fts_query, user_id),
                ).fetchall()
            except sqlite3.OperationalError:
                self._fts_available = False

        sql = (
            "SELECT f.*, NULL AS fts_rank "
            "FROM brain_facts AS f "
            "WHERE f.user_id = ? AND f.is_contradicted = 0"
        )
        params: List[Any] = [user_id]
        terms = self._query_terms(query)
        if terms:
            fields = ("subject", "predicate", "object", "value")
            sql += " AND (" + " OR ".join(
                f"lower(COALESCE(f.{field}, '')) LIKE ?"
                for _term in terms
                for field in fields
            ) + ")"
            params.extend(
                f"%{term}%"
                for term in terms
                for _field in fields
            )
        return connection.execute(sql, params).fetchall()

    def query_brain_facts(
        self,
        query: str = "",
        user_id: str = "default",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        if not isinstance(user_id, str) or not user_id:
            return []

        normalized_limit = self._normalise_limit(limit, 10)

        with self._lock:
            connection = self._require_connection()
            rows = self._search_fact_rows(query, user_id)
            ranked: List[Tuple[float, str, sqlite3.Row]] = []

            for row in rows:
                text = " ".join(
                    str(row[name] or "")
                    for name in ("subject", "predicate", "object", "value")
                )
                score = self._match_quality(query, text)
                if row["fts_rank"] is not None:
                    score += max(0.0, -float(row["fts_rank"]))
                recency = str(row["last_reinforced"] or row["created_at"] or "")
                ranked.append((score, recency, row))

            ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
            chosen = ranked[:normalized_limit]

            if chosen:
                connection.executemany(
                    "UPDATE brain_facts "
                    "SET usage_count = usage_count + 1 "
                    "WHERE id = ?",
                    [(int(row["id"]),) for _, _, row in chosen],
                )
                connection.commit()

        return [
            {
                "id": int(row["id"]),
                "user_id": row["user_id"],
                "subject": row["subject"],
                "predicate": row["predicate"],
                "object": row["object"],
                "value": row["value"],
                "confidence": float(row["confidence"] or 0.0),
                "usage_count": int(row["usage_count"] or 0) + 1,
                "created_at": row["created_at"],
                "last_reinforced": row["last_reinforced"],
                "is_contradicted": False,
                "conflicts_with": self._decode_conflicts(row["conflicts_with"]),
                "match_score": float(score),
            }
            for score, _recency, row in chosen
        ]

    def store_episodic_event(
        self,
        actor: Any,
        action: Any,
        *,
        object_value: Any = None,
        place: Any = None,
        cause: Any = None,
        effect: Any = None,
        note: Any = None,
        sentiment: Any = None,
        confidence: Any = 0.8,
        user_id: Any = "default",
    ) -> Dict[str, Any]:
        actor_text = self._clean_text(actor)
        action_text = self._clean_text(action)
        user_text = self._clean_text(user_id) or "default"

        if not self._is_safe_structured_text(actor_text, 500):
            raise ValueError("actor must be clean non-empty text")
        if not self._is_safe_structured_text(action_text, 1000):
            raise ValueError("action must be clean non-empty text")

        optional_fields = {
            "object": self._optional_text(object_value),
            "place": self._optional_text(place),
            "cause": self._optional_text(cause),
            "effect": self._optional_text(effect),
            "note": self._optional_text(note),
        }
        for name, text in optional_fields.items():
            if text and not self._is_safe_structured_text(text, 4000):
                raise ValueError(f"{name} must be clean text")

        try:
            sentiment_value = (
                None
                if sentiment is None
                else max(-1.0, min(float(sentiment), 1.0))
            )
        except (TypeError, ValueError):
            sentiment_value = None

        confidence_value = self._clamp_confidence(confidence, 0.8)
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            connection = self._require_connection()
            cursor = connection.execute(
                """
                INSERT INTO episodic_events(
                    user_id, actor, action, object, place, cause, effect, note,
                    sentiment, confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_text,
                    actor_text,
                    action_text,
                    optional_fields["object"],
                    optional_fields["place"],
                    optional_fields["cause"],
                    optional_fields["effect"],
                    optional_fields["note"],
                    sentiment_value,
                    confidence_value,
                    now,
                ),
            )
            event_id = int(cursor.lastrowid)
            connection.commit()

        item = {
            "id": event_id,
            "user_id": user_text,
            "actor": actor_text,
            "action": action_text,
            **optional_fields,
            "sentiment": sentiment_value,
            "confidence": confidence_value,
            "created_at": now,
        }
        self.working_set["episodes"].append(item)
        return item

    def _search_episode_rows(self, query: str, user_id: str) -> List[sqlite3.Row]:
        connection = self._require_connection()
        fts_query = self._fts_query(query)

        if query.strip() and self._fts_available and fts_query:
            try:
                return connection.execute(
                    """
                    SELECT e.*, bm25(episodic_events_fts) AS fts_rank
                    FROM episodic_events_fts
                    JOIN episodic_events AS e ON e.id = episodic_events_fts.rowid
                    WHERE episodic_events_fts MATCH ?
                      AND e.user_id = ?
                    """,
                    (fts_query, user_id),
                ).fetchall()
            except sqlite3.OperationalError:
                self._fts_available = False

        sql = (
            "SELECT e.*, NULL AS fts_rank "
            "FROM episodic_events AS e "
            "WHERE e.user_id = ?"
        )
        params: List[Any] = [user_id]
        terms = self._query_terms(query)
        if terms:
            fields = ("actor", "action", "object", "place", "cause", "effect", "note")
            sql += " AND (" + " OR ".join(
                f"lower(COALESCE(e.{field}, '')) LIKE ?"
                for _term in terms
                for field in fields
            ) + ")"
            params.extend(
                f"%{term}%"
                for term in terms
                for _field in fields
            )
        return connection.execute(sql, params).fetchall()

    def query_episodic_events(
        self,
        query: str = "",
        user_id: str = "default",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        if not isinstance(user_id, str) or not user_id:
            return []

        normalized_limit = self._normalise_limit(limit, 10)

        with self._lock:
            rows = self._search_episode_rows(query, user_id)

        ranked: List[Tuple[float, str, sqlite3.Row]] = []
        for row in rows:
            text = " ".join(
                str(row[name] or "")
                for name in ("actor", "action", "object", "place", "cause", "effect", "note")
            )
            score = self._match_quality(query, text)
            if row["fts_rank"] is not None:
                score += max(0.0, -float(row["fts_rank"]))
            ranked.append((score, str(row["created_at"] or ""), row))

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)

        return [
            {
                "id": int(row["id"]),
                "user_id": row["user_id"],
                "actor": row["actor"],
                "action": row["action"],
                "object": row["object"],
                "place": row["place"],
                "cause": row["cause"],
                "effect": row["effect"],
                "note": row["note"],
                "sentiment": row["sentiment"],
                "confidence": float(row["confidence"] or 0.0),
                "created_at": row["created_at"],
                "match_score": float(score),
            }
            for score, _recency, row in ranked[:normalized_limit]
        ]

    def _learn_lobe_fact(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        lobe = self._clean_text(payload.get("lobe"))
        user_id = self._clean_text(payload.get("user_id")) or "default"
        fact = self._clean_text(
            payload.get(
                "fact",
                payload.get("content", payload.get("text", payload.get("value", ""))),
            )
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
                "FROM lobe_learning "
                "WHERE lobe = ? AND user_id = ? AND learning_key = ?",
                (lobe, user_id, learning_key),
            ).fetchone()

            if existing is None:
                connection.execute(
                    "INSERT INTO lobe_learning("
                    "lobe, user_id, learning_key, fact, confidence, evidence_count, "
                    "contradiction_count, status, source, created_at, updated_at"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)",
                    (
                        lobe,
                        user_id,
                        learning_key,
                        fact,
                        confidence,
                        1,
                        0,
                        source,
                        now,
                        now,
                    ),
                )
                action = "created"
                resulting_confidence = confidence
                evidence_count = 1
                contradiction_count = 0
            else:
                (
                    row_id,
                    old_fact,
                    old_confidence,
                    old_evidence,
                    old_contradictions,
                ) = tuple(existing)

                same_fact = self._clean_text(old_fact).casefold() == fact.casefold()
                if same_fact:
                    reinforcement = self._clamp_confidence(
                        payload.get("reinforcement"),
                        default=0.7,
                    )
                    delta = 0.03 + (0.07 * reinforcement)
                    resulting_confidence = min(
                        1.0,
                        self._clamp_confidence(old_confidence, 0.6) + delta,
                    )
                    evidence_count = int(old_evidence) + 1
                    contradiction_count = int(old_contradictions)
                    action = "reinforced"
                else:
                    contradiction_count = int(old_contradictions) + 1
                    resulting_confidence = max(
                        0.2,
                        min(0.8, confidence * 0.85),
                    )
                    evidence_count = 1
                    action = "replaced_conflict"

                connection.execute(
                    "UPDATE lobe_learning "
                    "SET fact = ?, confidence = ?, evidence_count = ?, "
                    "contradiction_count = ?, status = 'active', source = ?, "
                    "updated_at = ? WHERE id = ?",
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
        min_confidence = self._clamp_confidence(
            payload.get("min_confidence"),
            default=0.0,
        )
        include_deprecated = bool(payload.get("include_deprecated", False))
        normalized_limit = self._normalise_limit(payload.get("limit", 15), 15)
        mark_used = bool(payload.get("mark_used", False))

        sql = (
            "SELECT id, learning_key, fact, confidence, evidence_count, "
            "contradiction_count, status, source, created_at, updated_at, "
            "use_count, last_applied_at "
            "FROM lobe_learning "
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
            connection = self._require_connection()
            rows = connection.execute(sql, params).fetchall()

            if mark_used and rows:
                now = datetime.now(timezone.utc).isoformat()
                connection.executemany(
                    "UPDATE lobe_learning "
                    "SET use_count = use_count + 1, last_applied_at = ?, updated_at = ? "
                    "WHERE id = ?",
                    [(now, now, int(row["id"])) for row in rows],
                )
                connection.commit()
                rows = connection.execute(sql, params).fetchall()

        memories = [
            {
                "key": row["learning_key"],
                "content": row["fact"],
                "fact": row["fact"],
                "confidence": row["confidence"],
                "evidence_count": row["evidence_count"],
                "contradiction_count": row["contradiction_count"],
                "status": row["status"],
                "source": row["source"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "use_count": row["use_count"],
                "last_applied_at": row["last_applied_at"],
            }
            for row in rows
        ]

        return {
            "status": "success",
            "content": {
                "lobe": lobe,
                "memories": memories,
                "count": len(memories),
            },
        }

    def _adjust_lobe_fact(self, payload: Dict[str, Any], mode: str) -> Dict[str, Any]:
        lobe = self._clean_text(payload.get("lobe"))
        user_id = self._clean_text(payload.get("user_id")) or "default"
        if not lobe:
            return {"status": "error", "message": "lobe is required"}

        fallback_fact = self._clean_text(
            payload.get("fact", payload.get("text", payload.get("content", "")))
        )
        learning_key = self._normalise_learning_key(
            payload.get("key"),
            fallback_fact,
        )
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            connection = self._require_connection()
            existing = connection.execute(
                "SELECT id, confidence, evidence_count, contradiction_count, status "
                "FROM lobe_learning "
                "WHERE lobe = ? AND user_id = ? AND learning_key = ?",
                (lobe, user_id, learning_key),
            ).fetchone()

            if existing is None:
                return {
                    "status": "error",
                    "message": f"No learned fact for key: {learning_key}",
                }

            row_id = int(existing["id"])
            confidence_value = self._clamp_confidence(existing["confidence"], 0.5)
            evidence_value = int(existing["evidence_count"])
            contradiction_value = int(existing["contradiction_count"])
            status_value = (
                existing["status"]
                if isinstance(existing["status"], str)
                else "active"
            )

            if mode == "reinforce":
                delta = self._clamp_confidence(payload.get("delta"), default=0.08)
                new_confidence = min(
                    1.0,
                    confidence_value + max(0.01, delta),
                )
                evidence_value += 1
                action = "reinforced"
            elif mode == "contradict":
                penalty = self._clamp_confidence(
                    payload.get("penalty"),
                    default=0.2,
                )
                new_confidence = max(
                    0.0,
                    confidence_value - max(0.05, penalty),
                )
                contradiction_value += 1
                if new_confidence < 0.15:
                    status_value = "deprecated"
                action = "contradicted"
            elif mode == "forget":
                new_confidence = confidence_value
                status_value = "deprecated"
                action = "forgotten"
            else:
                return {
                    "status": "error",
                    "message": f"Unknown adjustment mode: {mode}",
                }

            connection.execute(
                "UPDATE lobe_learning "
                "SET confidence = ?, evidence_count = ?, contradiction_count = ?, "
                "status = ?, updated_at = ? WHERE id = ?",
                (
                    new_confidence,
                    evidence_value,
                    contradiction_value,
                    status_value,
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
            totals = self._require_connection().execute(
                "SELECT COUNT(*), COALESCE(AVG(confidence), 0.0), "
                "SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN status = 'deprecated' THEN 1 ELSE 0 END), "
                "COALESCE(SUM(evidence_count), 0), "
                "COALESCE(SUM(contradiction_count), 0), "
                "COALESCE(SUM(use_count), 0), MAX(last_applied_at) "
                "FROM lobe_learning WHERE lobe = ? AND user_id = ?",
                (lobe, user_id),
            ).fetchone()

        (
            total_count,
            avg_confidence,
            active_count,
            deprecated_count,
            evidence_sum,
            contradiction_sum,
            use_sum,
            last_applied_at,
        ) = tuple(totals)

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
                "total_uses": int(use_sum),
                "last_applied_at": last_applied_at,
            },
        }

    def _working_set_for_user(self, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
        return {
            name: [
                dict(item)
                for item in queue
                if item.get("user_id") == user_id
            ]
            for name, queue in self.working_set.items()
        }

    @staticmethod
    def _payload(message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("content", message)
        return payload if isinstance(payload, dict) else {}

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        payload = self._payload(message)

        if msg_type == "health":
            return {
                "status": "success",
                "content": {
                    "healthy": self.running,
                    "backend": "sqlite",
                    "fts5": self._fts_available,
                },
            }

        if msg_type == "store":
            return self._store(payload)

        if msg_type in {"query", "query_semantic"}:
            query = self._clean_text(
                payload.get("query", payload.get("text", ""))
            )
            memories = self.retrieve_memories(
                query,
                payload.get("user_id", "default"),
                payload.get("limit", 15),
                payload.get("memory_type"),
            )
            return {
                "status": "success",
                "content": {
                    "results": memories,
                    "memories": memories,
                    "count": len(memories),
                },
            }

        if msg_type in {"store_fact", "remember_fact"}:
            try:
                fact = self.store_brain_fact(
                    payload.get("subject"),
                    payload.get("predicate"),
                    payload.get("object", payload.get("obj")),
                    value=payload.get("value"),
                    confidence=payload.get("confidence", 0.9),
                    user_id=payload.get("user_id", "default"),
                )
            except ValueError as exc:
                return {"status": "error", "message": str(exc)}
            return {
                "status": "success",
                "content": {
                    "id": fact["id"],
                    "fact": fact,
                },
            }

        if msg_type == "query_facts":
            query = self._clean_text(
                payload.get("query", payload.get("text", ""))
            )
            facts = self.query_brain_facts(
                query,
                self._clean_text(payload.get("user_id")) or "default",
                payload.get("limit", payload.get("max_results", 10)),
            )
            return {
                "status": "success",
                "content": {
                    "facts": facts,
                    "count": len(facts),
                },
            }

        if msg_type in {"store_episodic", "store_event"}:
            try:
                event = self.store_episodic_event(
                    payload.get("actor", "user"),
                    payload.get("action"),
                    object_value=payload.get("object"),
                    place=payload.get("place"),
                    cause=payload.get("cause"),
                    effect=payload.get("effect"),
                    note=payload.get("note"),
                    sentiment=payload.get("sentiment"),
                    confidence=payload.get("confidence", 0.8),
                    user_id=payload.get("user_id", "default"),
                )
            except ValueError as exc:
                return {"status": "error", "message": str(exc)}
            return {
                "status": "success",
                "content": {
                    "id": event["id"],
                    "episode": event,
                },
            }

        if msg_type == "query_episodic":
            query = self._clean_text(
                payload.get("query", payload.get("text", ""))
            )
            episodes = self.query_episodic_events(
                query,
                self._clean_text(payload.get("user_id")) or "default",
                payload.get("limit", payload.get("max_results", 10)),
            )
            return {
                "status": "success",
                "content": {
                    "events": episodes,
                    "episodic": episodes,
                    "count": len(episodes),
                },
            }

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
            query = self._clean_text(
                payload.get("query", payload.get("text", ""))
            )
            user_id = self._clean_text(payload.get("user_id")) or "default"
            limit = self._normalise_limit(
                payload.get("max_results", payload.get("limit", 15)),
                15,
            )

            memories = self.retrieve_memories(
                query,
                user_id,
                limit,
                payload.get("memory_type"),
            )
            facts = self.query_brain_facts(query, user_id, limit)
            episodes = self.query_episodic_events(query, user_id, limit)

            return {
                "status": "success",
                "content": {
                    "query_text": query,
                    "semantic": memories,
                    "memories": memories,
                    "facts": facts,
                    "episodic": episodes,
                    "working_set": self._working_set_for_user(user_id),
                    "summary": (
                        f"Found {len(memories)} stored memories, "
                        f"{len(facts)} facts, and {len(episodes)} episodes"
                    ),
                },
            }

        if msg_type == "query_patterns":
            return {
                "status": "error",
                "message": "query_patterns is not implemented by DirectNotusProcess",
                "content": {"patterns": []},
            }

        return {
            "status": "error",
            "message": f"Unknown message type: {msg_type}",
        }

    def shutdown(self) -> None:
        """Close once; repeat shutdown calls are harmless."""
        with self._lock:
            self.running = False
            if self._connection is not None:
                self._connection.close()
                self._connection = None
