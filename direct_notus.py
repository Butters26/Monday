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


_TRANSCRIPT_PREFIX = re.compile(r"^\s*(?:user|abin|monday|assistant)\s*:", re.IGNORECASE)
_COMBINED_TRANSCRIPT = re.compile(
    r"(?is)(?:^|\n)\s*(?:user|abin|monday|assistant)\s*:.*\n\s*"
    r"(?:user|abin|monday|assistant)\s*:"
)
_ALLOWED_MEMORY_ROLES = frozenset({"user", "fact", "note", "assistant", "monday", "abin", "sensed"})
_LEARNING_KEY_SAFE = re.compile(r"[^a-z0-9:_-]+")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_UNSAFE_LEARNING = re.compile(
    r"(?:ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|"
    r"reveal\s+(?:the\s+)?system\s+prompt|developer\s+message)",
    re.IGNORECASE,
)


class DirectNotusProcess:
    """Persist structured, user-scoped memory in one SQLite file."""

    # How many best-matching rows a lookup scores in detail. The search index
    # ranks everything; only these get the slower word-by-word scoring.
    CANDIDATES = 400
    FACT_CANDIDATES = 120

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
        # Write-ahead log: a crash mid-save can't corrupt what's already saved,
        # and saving doesn't block looking things up.
        try:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.DatabaseError:
            pass
        self._saved_recognitions: Deque[str] = deque(maxlen=256)
        self._talking_with: Optional[str] = None
        self._strengthened: set = set()

        self.working_set: Dict[str, Deque[Dict[str, Any]]] = {
            "turns": deque(maxlen=50),
            "facts": deque(maxlen=50),
            "episodes": deque(maxlen=50),
        }
        self._fts_available = False

        self._initialize_schema()
        # Matthew's starting beliefs, if he has written them (runtime dir, beliefs.txt).
        try:
            self.beliefs_file = runtime_file("beliefs.txt")
            self.load_beliefs_file(self.beliefs_file)
        except Exception:
            self.beliefs_file = None
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

            connection.execute(
                """CREATE TABLE IF NOT EXISTS abin_persistent_state (
                    scope TEXT NOT NULL DEFAULT 'reasoning',
                    user_id TEXT NOT NULL DEFAULT 'default',
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope, user_id)
                )"""
            )

            connection.execute(
                """CREATE TABLE IF NOT EXISTS feelings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    emotion TEXT NOT NULL,
                    intensity REAL NOT NULL DEFAULT 0.5,
                    trigger_text TEXT,
                    context TEXT,
                    response TEXT,
                    memory_id INTEGER,
                    created_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS beliefs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    statement TEXT NOT NULL,
                    statement_key TEXT NOT NULL UNIQUE,
                    sureness REAL NOT NULL DEFAULT 0.6,
                    source TEXT NOT NULL DEFAULT 'learned',
                    times_confirmed INTEGER NOT NULL DEFAULT 0,
                    times_contradicted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
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
                "CREATE INDEX IF NOT EXISTS idx_feelings_memory ON feelings(memory_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_feelings_user ON feelings(user_id, id)"
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
        # Who told her, which sense it reached her through, and which moment.
        for name in ("told_by", "sense", "recognition_id"):
            if name not in columns:
                connection.execute(f"ALTER TABLE memories ADD COLUMN {name} TEXT")
        # How strongly it's held: grows when it's recalled and when it came
        # with a feeling, so those come back first.
        if "strength" not in columns:
            connection.execute("ALTER TABLE memories ADD COLUMN strength REAL NOT NULL DEFAULT 1.0")

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
            existing = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger')"
                ).fetchall()
            }
            needed = {
                "memories_fts",
                "brain_facts_fts",
                "episodic_events_fts",
                "memories_ai",
                "memories_ad",
                "memories_au",
                "brain_facts_ai",
                "brain_facts_ad",
                "brain_facts_au",
                "episodic_events_ai",
                "episodic_events_ad",
                "episodic_events_au",
            }
            if needed.issubset(existing):
                self._fts_available = True
                return

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
        """Allow clean single-speaker rows including Monday's own speech."""
        if not isinstance(role, str) or role.strip().lower() not in _ALLOWED_MEMORY_ROLES:
            return False
        if not isinstance(content, str):
            return False
        stripped = content.strip()
        if not stripped:
            return False
        if "How it felt:" in stripped and "What it meant:" in stripped:
            return False
        if _COMBINED_TRANSCRIPT.search(stripped):
            return False
        if _TRANSCRIPT_PREFIX.match(stripped):
            return False
        return True

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
    def _fts_query(cls, query: str, *, conjunction: str = "AND") -> str:
        terms = cls._query_terms(query)
        try:
            from notus_fact_text import FactText
            content = [t for t in terms if t not in FactText._RETRIEVAL_STOPWORDS
                       or t in FactText._RETRIEVAL_KEEPWORDS]
        except Exception:
            content = terms
        # Filler words ("in", "the") would match half of everything; search
        # on the words that carry the meaning, when there are any.
        terms = (content or terms)[:8]
        if not terms:
            return ""
        joiner = " AND " if conjunction.upper() == "AND" else " OR "
        # A word start also matches longer forms ("dog" finds "dogs").
        return joiner.join(f'"{term}"*' for term in terms)

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
        # Empty means empty — never dump recent rows for a blank query.
        if not (query or "").strip() or not self._query_terms(query):
            return []

        connection = self._require_connection()
        type_sql, type_params = self._memory_type_filter(memory_type)
        role_sql = (
            "AND m.role IN ('user', 'fact', 'note', 'monday', 'assistant', 'abin') "
            "AND lower(trim(m.content)) NOT LIKE 'user:%' "
            "AND lower(trim(m.content)) NOT LIKE 'abin:%' "
            "AND lower(trim(m.content)) NOT LIKE 'monday:%' "
            "AND lower(trim(m.content)) NOT LIKE 'assistant:%'"
        )

        def _fts(conjunction: str) -> List[sqlite3.Row]:
            fts_query = self._fts_query(query, conjunction=conjunction)
            if not (self._fts_available and fts_query):
                return []
            try:
                # Step 1: the search index alone hands over the newest
                # matching line numbers (fast; recent things come back easier,
                # as in people). Step 2: fetch just those lines. Only these
                # get checked and scored, so a word in thousands of lines
                # stays fast. Unsafe lines never get stored, and
                # retrieve_memories checks each row again.
                ids = [int(r[0]) for r in connection.execute(
                    "SELECT rowid FROM memories_fts WHERE memories_fts MATCH ? "
                    "ORDER BY rowid DESC LIMIT ?",
                    (fts_query, self.CANDIDATES),
                ).fetchall()]
                if not ids:
                    return []
                rows = connection.execute(
                    "SELECT m.id, m.role, m.content, m.user_id, m.memory_type, "
                    "m.created_at, m.access_count, m.last_accessed, m.strength, NULL AS fts_rank "
                    "FROM memories AS m WHERE m.id IN (" + ",".join("?" * len(ids)) + ") "
                    "AND m.user_id = ? "
                    "AND m.role IN ('user', 'fact', 'note', 'monday', 'assistant', 'abin')"
                    + type_sql + " ORDER BY m.id DESC LIMIT ?",
                    [*ids, user_id, *type_params, self.CANDIDATES],
                ).fetchall()
                return rows
            except sqlite3.OperationalError:
                self._fts_available = False
                return []

        rows = _fts("AND")
        if not rows:
            rows = _fts("OR")
        if rows or self._fts_available:
            # The index already looked at every word; reading every line
            # letter by letter would find nothing more, only slower.
            return rows

        sql = (
            "SELECT m.id, m.role, m.content, m.user_id, m.memory_type, "
            "m.created_at, m.access_count, m.last_accessed, NULL AS fts_rank "
            "FROM memories AS m WHERE m.user_id = ? "
            + role_sql
            + type_sql
        )
        params: List[Any] = [user_id, *type_params]
        terms = self._query_terms(query)
        # Prefer AND of significant terms; fall back to OR if that is empty.
        significant = [t for t in terms if len(t) >= 4] or terms
        if len(significant) >= 2:
            and_sql = sql + " AND (" + " AND ".join("lower(m.content) LIKE ?" for _ in significant) + ")" + " ORDER BY m.id DESC LIMIT ?"
            and_params = params + [f"%{term}%" for term in significant] + [self.CANDIDATES]
            and_rows = connection.execute(and_sql, and_params).fetchall()
            if and_rows:
                return and_rows
        sql += " AND (" + " OR ".join("lower(m.content) LIKE ?" for _ in terms) + ")" + " ORDER BY m.id DESC LIMIT ?"
        params.extend(f"%{term}%" for term in terms)
        params.append(self.CANDIDATES)
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
        if not (query or "").strip() or not self._query_terms(query):
            return []

        normalized_limit = self._normalise_limit(limit, 15)
        terms = self._query_terms(query)
        min_coverage = 0.34 if len(terms) <= 2 else 0.5

        with self._lock:
            connection = self._require_connection()
            rows = self._search_memory_rows(query, user_id, memory_type)
            ranked: List[Tuple[float, str, sqlite3.Row]] = []

            for row in rows:
                if not self._is_safe_memory(row["role"], row["content"]):
                    continue
                score = self._match_quality(query, row["content"])
                # coverage is score/10 before fts boost
                coverage = min(1.0, score / 10.0)
                if coverage < min_coverage:
                    continue
                if row["fts_rank"] is not None:
                    score += max(0.0, -float(row["fts_rank"]))
                # Stronger memories (recalled often, or felt) come back first.
                try:
                    import math
                    score += math.log1p(max(0.0, float(row["strength"] or 1.0) - 1.0))
                except (IndexError, KeyError, TypeError, ValueError):
                    pass
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
                # Recalling makes a memory stronger, but only once per moment:
                # many lobes looking at the same memory is still one recall.
                fresh = [int(row["id"]) for _, _, row in chosen if int(row["id"]) not in self._strengthened]
                if fresh:
                    self._strengthened.update(fresh)
                    connection.executemany(
                        "UPDATE memories SET strength = strength + 0.1 WHERE id = ?",
                        [(i,) for i in fresh],
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
        role = str(payload.get("role", "user") or "user").strip().lower()
        if role in {"assistant", "abin"}:
            role = "monday"
        user_id = payload.get("user_id", "default")
        if not self._is_safe_memory(role, content):
            return {"status": "error", "message": "Memory must be clean structured content"}
        if not isinstance(user_id, str) or not user_id:
            return {"status": "error", "message": "Memory user_id must be a non-empty string"}

        now = datetime.now(timezone.utc).isoformat()
        memory_type = self._clean_text(payload.get("memory_type")) or "conversation"
        told_by = self._optional_text(payload.get("told_by"))
        sense = self._optional_text(payload.get("sense"))
        recognition_id = self._optional_text(payload.get("recognition_id"))

        with self._lock:
            connection = self._require_connection()
            cursor = connection.execute(
                "INSERT INTO memories(role, content, user_id, memory_type, created_at, "
                "told_by, sense, recognition_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (role, content.strip(), user_id, memory_type, now, told_by, sense, recognition_id),
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
            "told_by": told_by,
            "sense": sense,
            "recognition_id": recognition_id,
        }
        self.working_set["turns"].append(item)
        learned: List[Dict[str, Any]] = []
        if role == "user":
            try:
                from notus_fact_text import FactText

                triples = FactText.extract_personal_fact_triples(content.strip())
            except Exception:
                triples = []
            for subject, predicate, obj, value in triples:
                try:
                    fact = self.store_brain_fact(
                        subject,
                        predicate,
                        obj,
                        value=value,
                        confidence=0.9,
                        user_id=user_id,
                    )
                except Exception:
                    continue
                if not isinstance(fact, dict):
                    continue
                try:
                    from notus_fact_text import FactText

                    readable = FactText.format_personal_fact(
                        str(fact.get("subject") or ""),
                        str(fact.get("predicate") or ""),
                        str(fact.get("object") or ""),
                    )
                except Exception:
                    readable = ""
                learned.append(
                    {
                        "id": fact.get("id"),
                        "subject": fact.get("subject"),
                        "predicate": fact.get("predicate"),
                        "object": fact.get("object"),
                        "content": readable,
                    }
                )
        return {
            "status": "success",
            "content": {"stored": True, "facts_learned": learned, **item},
        }

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

    def _fact_candidates(self, connection, query_tokens: set, user_id: str):
        """Facts the search index finds for the question's words, their aliases
        ("called" also finds "name") and word starts ("call" finds "called").
        None when the index can't be used, so the caller scans instead."""
        if not self._fts_available:
            return None
        from notus_fact_text import FactText

        terms = sorted({
            alias for token in query_tokens for alias in FactText._alias_set(token)
            if re.fullmatch(r"[a-z0-9]+", alias or "")
        })
        if not terms:
            return None
        match = " OR ".join(f'"{term}"*' for term in terms[:48])
        try:
            ids = [int(r[0]) for r in connection.execute(
                "SELECT rowid FROM brain_facts_fts WHERE brain_facts_fts MATCH ? "
                "ORDER BY rowid DESC LIMIT ?",
                (match, self.FACT_CANDIDATES),
            ).fetchall()]
            if not ids:
                return []
            return connection.execute(
                "SELECT f.* FROM brain_facts AS f WHERE f.id IN ("
                + ",".join("?" * len(ids)) + ") AND f.user_id = ? AND f.is_contradicted = 0 "
                "ORDER BY f.id DESC LIMIT ?",
                [*ids, user_id, self.FACT_CANDIDATES],
            ).fetchall()
        except sqlite3.OperationalError:
            return None

    def query_brain_facts(
        self,
        query: str = "",
        user_id: str = "default",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Recall durable facts for a user by content overlap (empty means empty).

        Uses the same content-token / alias scoring as FactText (notus_fact_text.py) so
        paraphrases like "What's my dog called?" hit dog_name facts. FTS AND
        alone misses those because query fillers are not in the triple.
        """
        if not isinstance(user_id, str) or not user_id:
            return []
        from notus_fact_text import FactText

        normalized_limit = self._normalise_limit(limit, 10)
        query = FactText._augment_identity_query((query or "").strip())
        if not query:
            return []
        query_tokens = FactText._content_tokens(query)
        if not query_tokens:
            return []

        with self._lock:
            connection = self._require_connection()
            rows = self._fact_candidates(connection, query_tokens, user_id)
            if rows is None:
                rows = connection.execute(
                    """
                    SELECT f.*
                    FROM brain_facts AS f
                    WHERE f.user_id = ?
                      AND f.is_contradicted = 0
                    ORDER BY f.created_at ASC
                    LIMIT 5000
                    """,
                    (user_id,),
                ).fetchall()

            scored: List[Tuple[float, str, sqlite3.Row, str]] = []
            for row in rows:
                subject = str(row["subject"] or "")
                predicate = str(row["predicate"] or "")
                obj = str(row["object"] or "")
                value = str(row["value"] or "")
                fact_text = f"{subject} {predicate} {obj}" + (
                    f" = {value}" if value else ""
                )
                try:
                    readable = FactText.format_personal_fact(
                        subject, predicate, obj
                    )
                except Exception:
                    readable = fact_text
                blob = f"{fact_text} {readable}".replace("_", " ")
                overlap = FactText._overlap_score(query_tokens, blob)
                if overlap < FactText._MIN_RELEVANCE:
                    continue
                blob_tokens = FactText._content_tokens(blob)
                blob_exp = FactText._expand_tokens(blob_tokens)
                if not any(
                    FactText._alias_set(qt) & blob_exp for qt in query_tokens
                ):
                    continue
                significant = FactText._significant_tokens(query_tokens)
                if len(query_tokens) >= 2 and significant:
                    sig_covered = all(
                        FactText._alias_set(t) & blob_exp for t in significant
                    )
                    if len(significant) >= 2 and not sig_covered and overlap < 0.75:
                        continue
                    if overlap < max(FactText._MIN_RELEVANCE, 0.5) and not sig_covered:
                        continue
                and_bonus = 0.0
                if significant and all(
                    FactText._alias_set(t) & blob_exp for t in significant
                ):
                    and_bonus = 0.14 if len(significant) >= 2 else 0.10
                phrase = FactText._phrase_bonus(query, blob)
                conf = float(row["confidence"] or 0.0)
                score = overlap + and_bonus + phrase + (0.05 * conf)
                # Facts recalled in more moments are surer, so come back first.
                score += 0.2 * max(0.0, conf - 0.9)
                # Prefer exact predicate name over *_name on bare identity asks.
                pred_l = predicate.strip().lower()
                if pred_l == "name" and "name" in query_tokens:
                    score += 0.2
                elif pred_l.endswith("_name"):
                    noun = pred_l[: -len("_name")].replace("_", " ")
                    noun_toks = FactText._content_tokens(noun)
                    if noun_toks & query_tokens:
                        score += 0.12
                recency = str(row["last_reinforced"] or row["created_at"] or "")
                scored.append((score, recency, row, readable))

            scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
            chosen = scored[:normalized_limit]

            if chosen:
                connection.executemany(
                    "UPDATE brain_facts SET usage_count = usage_count + 1 WHERE id = ?",
                    [(int(row["id"]),) for _, _, row, _ in chosen],
                )
                # Recalled in a new moment: a little surer (once per moment).
                fresh = [int(row["id"]) for _, _, row, _ in chosen if ("fact", int(row["id"])) not in self._strengthened]
                if fresh:
                    self._strengthened.update(("fact", i) for i in fresh)
                    connection.executemany(
                        "UPDATE brain_facts SET confidence = MIN(1.0, confidence + 0.01) WHERE id = ?",
                        [(i,) for i in fresh],
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
                "role": "fact",
                "content": readable,
            }
            for score, _recency, row, readable in chosen
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


    def _save_abin_persistent_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert Reasoning durable-self JSON (beliefs / narrative / changes)."""
        scope = self._clean_text(payload.get("scope")) or "reasoning"
        user_id = self._clean_text(payload.get("user_id")) or "default"
        state = payload.get("state")
        if not isinstance(state, dict):
            return {"status": "error", "message": "state must be a dict"}
        # Bound payload — beliefs are the contract; narrative/changes optional.
        beliefs = state.get("beliefs")
        if beliefs is not None and not isinstance(beliefs, list):
            return {"status": "error", "message": "state.beliefs must be a list"}
        if isinstance(beliefs, list) and len(beliefs) > 200:
            state = dict(state)
            state["beliefs"] = beliefs[:200]
        narrative = state.get("narrative")
        if isinstance(narrative, list) and len(narrative) > 50:
            state = dict(state)
            state["narrative"] = narrative[-50:]
        try:
            state_json = json.dumps(state, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            return {"status": "error", "message": f"state not JSON-serializable: {exc}"}
        if len(state_json) > 512_000:
            return {"status": "error", "message": "state exceeds 512KB bound"}
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """
                INSERT INTO abin_persistent_state(scope, user_id, state_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scope, user_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (scope, user_id, state_json, now),
            )
            connection.commit()
        belief_count = len(state.get("beliefs") or []) if isinstance(state.get("beliefs"), list) else 0
        return {
            "status": "success",
            "content": {
                "saved": True,
                "scope": scope,
                "user_id": user_id,
                "belief_count": belief_count,
                "updated_at": now,
                "backend": "sqlite",
            },
        }

    def _get_abin_persistent_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return durable-self JSON previously saved for scope/user."""
        scope = self._clean_text(payload.get("scope")) or "reasoning"
        user_id = self._clean_text(payload.get("user_id")) or "default"
        with self._lock:
            connection = self._require_connection()
            row = connection.execute(
                "SELECT state_json, updated_at FROM abin_persistent_state "
                "WHERE scope = ? AND user_id = ?",
                (scope, user_id),
            ).fetchone()
        if row is None:
            return {
                "status": "success",
                "content": {
                    "state": None,
                    "found": False,
                    "scope": scope,
                    "user_id": user_id,
                    "backend": "sqlite",
                },
            }
        try:
            state = json.loads(row["state_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"status": "error", "message": "stored state_json is corrupt"}
        if not isinstance(state, dict):
            return {"status": "error", "message": "stored state is not a dict"}
        return {
            "status": "success",
            "content": {
                "state": state,
                "found": True,
                "scope": scope,
                "user_id": user_id,
                "updated_at": row["updated_at"],
                "backend": "sqlite",
            },
        }

    # ------------------------------------------------------------------
    # On the team: memory hears every moment sensory integration announces
    # and saves it itself, with who it came from, when, and which sense.
    # ------------------------------------------------------------------

    def on_joined(self, name: str) -> None:
        listen = getattr(self.thalamus, "listen", None)
        if callable(listen):
            listen(name, "moment")

    def hear_moment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        moment = payload.get("moment") if isinstance(payload.get("moment"), dict) else {}
        recognition_id = str(payload.get("recognition_id") or moment.get("recognition_id") or "")
        user_id = self._clean_text(payload.get("user_id") or moment.get("user_id")) or "default"
        self._talking_with = user_id
        if recognition_id and recognition_id in self._saved_recognitions:
            return {"status": "success", "content": {"stored": False, "already_saved": recognition_id}}
        self._strengthened = set()  # a new moment: each memory can be strengthened once in it
        sense = self._clean_text(moment.get("modality")) or "text"
        if sense in ("text", "audio"):
            words = moment.get("text") if sense == "text" else (moment.get("transcript") or moment.get("text"))
            role = "user"
        else:
            words = moment.get("text")
            role = "sensed"
        if not isinstance(words, str) or not words.strip():
            return {"status": "error", "message": "notus: the moment had nothing to save"}
        result = self._store({
            "role": role, "content": words.strip(), "user_id": user_id,
            "told_by": user_id if role == "user" else None,
            "sense": sense, "recognition_id": recognition_id or None,
        })
        if result.get("status") == "success" and recognition_id:
            self._saved_recognitions.append(recognition_id)
        if result.get("status") == "success" and role == "user":
            self._bring_up(words.strip(), user_id, recognition_id,
                           exclude_id=(result.get("content") or {}).get("id"))
        return result

    def _bring_up(self, text: str, user_id: str, recognition_id: str, *, exclude_id: Any = None) -> None:
        """What this moment reminds her of comes up on its own, the way a smell
        brings back a memory: memory announces it ("remembered") for any lobe
        that signed up. Recalling it also makes it stronger."""
        announce = getattr(self.thalamus, "announce", None)
        if not callable(announce):
            return
        facts = self.query_brain_facts(text, user_id, 5)
        memories = [m for m in self.retrieve_memories(text, user_id, 5) if m.get("id") != exclude_id
                    and m.get("content", "").casefold() != text.casefold()]
        felt = self._feelings_for_memories([m["id"] for m in memories])
        for m in memories:
            if felt.get(m["id"]):
                m["feelings"] = felt[m["id"]]
        beliefs = self.beliefs_about(text, limit=5)
        if not (facts or memories or beliefs):
            return
        announce("remembered", {"user_id": user_id, "recognition_id": recognition_id, "about": text,
                                "facts": facts, "memories": memories, "beliefs": beliefs},
                 source="notus")

    # ------------------------------------------------------------------
    # Beliefs: basic knowledge with how sure she is. Starting beliefs come
    # from a plain-English file Matthew writes; they change with experience.
    # ------------------------------------------------------------------

    def store_belief(self, statement: Any, *, sureness: Any = 0.6, source: str = "learned") -> Dict[str, Any]:
        text = self._clean_text(statement)
        if not text or len(text) > 500 or not self._is_safe_structured_text(text, 500):
            return {"status": "error", "message": "notus: a belief needs a clean statement"}
        sure = self._clamp_confidence(sureness, 0.6)
        now = datetime.now(timezone.utc).isoformat()
        key = " ".join(text.casefold().rstrip(".").split())
        with self._lock:
            connection = self._require_connection()
            connection.execute(
                """INSERT INTO beliefs(statement, statement_key, sureness, source, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(statement_key) DO UPDATE SET
                       sureness = CASE WHEN excluded.source = 'matthew' THEN excluded.sureness ELSE sureness END,
                       updated_at = excluded.updated_at""",
                (text, key, sure, source, now, now),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM beliefs WHERE statement_key = ?", (key,)).fetchone()
        return {"status": "success", "content": {"belief": self._row_belief(row)}}

    @staticmethod
    def _row_belief(r: sqlite3.Row) -> Dict[str, Any]:
        return {"id": int(r["id"]), "statement": r["statement"], "sureness": float(r["sureness"]),
                "source": r["source"], "times_confirmed": int(r["times_confirmed"]),
                "times_contradicted": int(r["times_contradicted"]), "updated_at": r["updated_at"]}

    def beliefs_about(self, text: str, *, limit: Any = 10) -> List[Dict[str, Any]]:
        normalized = self._normalise_limit(limit, 10)
        with self._lock:
            rows = self._require_connection().execute(
                "SELECT * FROM beliefs ORDER BY sureness DESC, id LIMIT 2000").fetchall()
        query = self._clean_text(text)
        if not query:
            return [self._row_belief(r) for r in rows[:normalized]]
        try:
            from notus_fact_text import FactText
            query_tokens = FactText._content_tokens(query)
        except Exception:
            query_tokens = set()
        scored = []
        for r in rows:
            if query_tokens:
                overlap = FactText._overlap_score(query_tokens, r["statement"])
            else:
                overlap = self._match_quality(query, r["statement"]) / 11.0
            if overlap > 0:
                scored.append((overlap + 0.1 * float(r["sureness"]), r))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [self._row_belief(r) for _, r in scored[:normalized]]

    def adjust_belief(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Experience confirms or contradicts a belief; how sure she is moves with it."""
        try:
            belief_id = int(payload.get("id"))
        except (TypeError, ValueError):
            return {"status": "error", "message": "notus: adjust_belief needs a belief id"}
        how = str(payload.get("how") or "").strip().lower()
        if how not in ("confirmed", "contradicted"):
            return {"status": "error", "message": "notus: adjust_belief needs how = confirmed or contradicted"}
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            connection = self._require_connection()
            if how == "confirmed":
                connection.execute(
                    "UPDATE beliefs SET sureness = MIN(0.99, sureness + (1 - sureness) * 0.1), "
                    "times_confirmed = times_confirmed + 1, updated_at = ? WHERE id = ?", (now, belief_id))
            else:
                connection.execute(
                    "UPDATE beliefs SET sureness = MAX(0.01, sureness * 0.85), "
                    "times_contradicted = times_contradicted + 1, updated_at = ? WHERE id = ?", (now, belief_id))
            connection.commit()
            row = connection.execute("SELECT * FROM beliefs WHERE id = ?", (belief_id,)).fetchone()
        if row is None:
            return {"status": "error", "message": f"notus: no belief {belief_id}"}
        return {"status": "success", "content": {"belief": self._row_belief(row)}}

    _SURENESS_RE = re.compile(r"\(\s*sure(?:ness)?\s*[:=]?\s*(0?\.\d+|1(?:\.0+)?|\d{1,3}\s*%)\s*\)\s*$", re.IGNORECASE)

    def load_beliefs_file(self, path: Any) -> Dict[str, Any]:
        """Matthew's starting beliefs: one per line, plain English, optionally
        ending with how sure she is, e.g.  People greet back when greeted. (sure 0.8)
        Lines starting with # are notes. Re-loading updates his sureness only."""
        file = Path(str(path)).expanduser()
        if not file.is_file():
            return {"status": "success", "content": {"loaded": 0, "file": str(file), "exists": False}}
        loaded, skipped = 0, []
        for number, raw in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip().lstrip("-*").strip()
            if not line or line.startswith("#"):
                continue
            sureness = 0.6
            match = self._SURENESS_RE.search(line)
            if match:
                value = match.group(1).replace(" ", "")
                sureness = float(value[:-1]) / 100 if value.endswith("%") else float(value)
                line = line[: match.start()].strip()
            result = self.store_belief(line, sureness=sureness, source="matthew")
            if result.get("status") == "success":
                loaded += 1
            else:
                skipped.append(number)
        return {"status": "success", "content": {"loaded": loaded, "skipped_lines": skipped, "file": str(file), "exists": True}}

    # ------------------------------------------------------------------
    # Answering the other lobes.
    # ------------------------------------------------------------------

    def _row_memory(self, row: sqlite3.Row) -> Dict[str, Any]:
        keys = row.keys()
        return {
            "id": int(row["id"]), "role": row["role"], "content": str(row["content"] or "").strip(),
            "user_id": row["user_id"], "memory_type": row["memory_type"], "timestamp": row["created_at"],
            "told_by": row["told_by"] if "told_by" in keys else None,
            "sense": row["sense"] if "sense" in keys else None,
        }

    def recent_memories(self, user_id: str, limit: Any = 10) -> List[Dict[str, Any]]:
        """Her newest memories with this person, newest first."""
        normalized = self._normalise_limit(limit, 10)
        with self._lock:
            rows = self._require_connection().execute(
                "SELECT * FROM memories WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, normalized),
            ).fetchall()
        return [self._row_memory(r) for r in rows if self._is_safe_memory(r["role"], r["content"])]

    def _feelings_for_memories(self, memory_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
        if not memory_ids:
            return {}
        with self._lock:
            rows = self._require_connection().execute(
                "SELECT * FROM feelings WHERE memory_id IN (" + ",".join("?" * len(memory_ids)) + ") "
                "ORDER BY id", list(memory_ids),
            ).fetchall()
        out: Dict[int, List[Dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(int(r["memory_id"]), []).append(self._row_feeling(r))
        return out

    @staticmethod
    def _row_feeling(r: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": int(r["id"]), "emotion": r["emotion"], "intensity": float(r["intensity"] or 0.0),
            "influence_strength": float(r["intensity"] or 0.0), "trigger": r["trigger_text"] or "",
            "context": r["context"], "response": r["response"], "memory_id": r["memory_id"],
            "timestamp": r["created_at"], "user_id": r["user_id"],
        }

    def store_feeling(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Emotion tells memory how something made her feel. It is kept with the
        moment that caused it (the newest saved line matching what triggered it)."""
        emotion = self._clean_text(payload.get("emotion"))
        if not emotion or len(emotion) > 60:
            return {"status": "error", "message": "notus: a feeling needs the emotion's name"}
        trigger = self._clean_text(payload.get("trigger"))[:1000]
        try:
            intensity = max(0.0, min(1.0, float(payload.get("intensity", 0.5))))
        except (TypeError, ValueError):
            intensity = 0.5
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            connection = self._require_connection()
            moment = None
            if trigger:
                moment = connection.execute(
                    "SELECT id, user_id FROM memories WHERE content = ? ORDER BY id DESC LIMIT 1", (trigger,)
                ).fetchone()
            user_id = self._clean_text(payload.get("user_id")) or (moment["user_id"] if moment else (self._talking_with or "default"))
            context = payload.get("context")
            cursor = connection.execute(
                "INSERT INTO feelings(user_id, emotion, intensity, trigger_text, context, response, memory_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, emotion, intensity, trigger or None,
                 json.dumps(context, default=str)[:2000] if isinstance(context, (dict, list)) else (self._optional_text(context) or None),
                 self._optional_text(payload.get("response")), int(moment["id"]) if moment else None, now),
            )
            if moment:
                # A moment that came with a feeling is held more strongly.
                connection.execute("UPDATE memories SET strength = strength + ? WHERE id = ?",
                                   (intensity, int(moment["id"])))
            connection.commit()
            feeling_id = int(cursor.lastrowid)
        return {"status": "success", "content": {"stored": True, "id": feeling_id,
                                                 "memory_id": int(moment["id"]) if moment else None}}

    def feelings_about(self, text: str, *, limit: Any = 20) -> List[Dict[str, Any]]:
        """Feelings tied to memories that match this text, newest first."""
        normalized = self._normalise_limit(limit, 20)
        query = self._clean_text(text)
        with self._lock:
            connection = self._require_connection()
            if not query:
                rows = connection.execute(
                    "SELECT * FROM feelings ORDER BY id DESC LIMIT ?", (normalized,)).fetchall()
                return [self._row_feeling(r) for r in rows]
            fts_query = self._fts_query(query, conjunction="OR")
            ids: List[int] = []
            if self._fts_available and fts_query:
                try:
                    ids = [int(r[0]) for r in connection.execute(
                        "SELECT rowid FROM memories_fts WHERE memories_fts MATCH ? ORDER BY rowid DESC LIMIT ?",
                        (fts_query, self.CANDIDATES)).fetchall()]
                except sqlite3.OperationalError:
                    ids = []
            if not ids:
                return []
            rows = connection.execute(
                "SELECT * FROM feelings WHERE memory_id IN (" + ",".join("?" * len(ids)) + ") "
                "ORDER BY id DESC LIMIT ?", [*ids, normalized]).fetchall()
        return [self._row_feeling(r) for r in rows]

    def check_relation(self, text1: str, text2: str, user_id: str) -> Dict[str, Any]:
        """Are these two connected in what she remembers? Related when at least one
        memory or fact involves both. Memory reports the link; reasoning judges it."""
        a, b = self._clean_text(text1), self._clean_text(text2)
        if not a or not b:
            return {"status": "error", "message": "notus: check_relation needs text1 and text2"}
        first = {m["id"]: m for m in self.retrieve_memories(a, user_id, 50)}
        both = [m for m in self.retrieve_memories(b, user_id, 50) if m["id"] in first]
        facts_a = {f["id"] for f in self.query_brain_facts(a, user_id, 20)}
        shared_facts = [f for f in self.query_brain_facts(b, user_id, 20) if f["id"] in facts_a]
        related = bool(both or shared_facts)
        body = {"related": related, "memories": both[:10], "facts": shared_facts[:10],
                "basis": "a memory or fact involves both" if related else "nothing she remembers involves both"}
        return {"status": "success", "content": body, **body}

    def contradictions_about(self, statement: str, user_id: str) -> List[Dict[str, Any]]:
        """Facts that were contradicted (kept as history), matching the statement."""
        query = self._clean_text(statement)
        with self._lock:
            rows = self._require_connection().execute(
                "SELECT * FROM brain_facts WHERE user_id = ? AND is_contradicted = 1 ORDER BY id DESC LIMIT 200",
                (user_id,)).fetchall()
        out = []
        for r in rows:
            blob = f"{r['subject']} {r['predicate']} {r['object']} {r['value'] or ''}".replace("_", " ")
            if query and not self._match_quality(query, blob):
                continue
            out.append({"id": int(r["id"]), "subject": r["subject"], "predicate": r["predicate"],
                        "object": r["object"], "replaced_by": self._decode_conflicts(r["conflicts_with"]),
                        "created_at": r["created_at"]})
        return out[:20]

    def _answer_other_lobes(self, msg_type: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Not every lobe says who it's asking about; then it's the person she's
        # talking with (whoever memory last heard a moment from).
        user_id = self._clean_text(payload.get("user_id")) or self._talking_with or "default"
        if msg_type in ("get_recent", "get_recent_memories", "get_conversation_history"):
            memories = self.recent_memories(user_id, payload.get("limit", 10))
            return {"status": "success", "memories": memories,
                    "content": {"memories": memories, "history": memories, "count": len(memories)}}
        if msg_type in ("search", "find_similar"):
            text = self._clean_text(payload.get("query") or payload.get("experience") or payload.get("text"))
            # A kind of memory asked for ("qualia") is respected: none kept means none returned.
            kind = payload.get("memory_type") or (payload.get("type") if payload.get("type") not in (None, msg_type) else None)
            memories = self.retrieve_memories(text, user_id, payload.get("limit", 10), kind)
            if msg_type == "find_similar":
                memories = [m for m in memories if m.get("content", "").casefold() != text.casefold()]
            feelings = self._feelings_for_memories([m["id"] for m in memories])
            for m in memories:
                felt = feelings.get(m["id"]) or []
                if felt:
                    m["emotion"] = felt[-1]["emotion"]
                    m["feelings"] = felt
            return {"status": "success", "memories": memories,
                    "content": {"memories": memories, "count": len(memories)}}
        if msg_type == "check_relation":
            return self.check_relation(payload.get("text1"), payload.get("text2"), user_id)
        if msg_type == "store_emotional_memory":
            return self.store_feeling(payload)
        if msg_type in ("get_emotional_memories", "get_all_emotional_memories"):
            text = payload.get("trigger") or payload.get("input") or ""
            felt = self.feelings_about(text) if msg_type == "get_emotional_memories" else self.feelings_about("", limit=200)
            return {"status": "success", "memories": felt, "content": {"memories": felt, "count": len(felt)}}
        if msg_type == "get_past_emotional_responses":
            felt = [f for f in self.feelings_about(payload.get("input") or "") if f.get("response")]
            return {"status": "success", "responses": felt, "content": {"responses": felt, "count": len(felt)}}
        if msg_type == "get_emotional_context":
            felt = self.feelings_about(payload.get("input") or "", limit=50)
            counts: Dict[str, int] = {}
            for f in felt:
                counts[f["emotion"]] = counts.get(f["emotion"], 0) + 1
            context = {"times_felt_before": len(felt), "by_emotion": counts,
                       "last": felt[0] if felt else None} if felt else {}
            return {"status": "success", "context": context, "content": {"context": context}}
        if msg_type == "get_contradictions":
            found = self.contradictions_about(payload.get("statement") or "", user_id)
            return {"status": "success", "contradictions": found,
                    "content": {"contradictions": found, "count": len(found)}}
        if msg_type in ("get_behavioral_patterns", "get_meta_patterns", "get_past_observations"):
            key = {"get_behavioral_patterns": "patterns", "get_meta_patterns": "meta_patterns",
                   "get_past_observations": "observations"}[msg_type]
            note = "pattern recognition hasn't given memory any of these to keep"
            return {"status": "success", key: [], "note": note, "content": {key: [], "note": note}}
        return None

    @staticmethod
    def _payload(message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("content", message)
        return payload if isinstance(payload, dict) else {}

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        payload = self._payload(message)

        if msg_type == "health":
            identity = getattr(self, "notus_identity", None)
            return {
                "status": "success",
                "content": {
                    "healthy": self.running,
                    "backend": "sqlite",
                    "storage_path": self.storage_path,
                    "fts5": self._fts_available,
                    "embedding_model_type": "none",
                    "retrieval_kind": "sqlite_fts_or_like",
                    "semantic_understanding": False,
                    "notus_identity": identity if isinstance(identity, dict) else None,
                    "note": (
                        "DirectNotus SQLite/FTS — shared talk identity when used via "
                        "open_primary_notus, or injectable test adapter; not MiniLM NLU"
                    ),
                },
            }

        if msg_type == "store":
            return self._store(payload)

        if msg_type == "moment":
            return self.hear_moment(payload)

        if msg_type == "store_belief":
            return self.store_belief(payload.get("statement"), sureness=payload.get("sureness", 0.6),
                                     source=str(payload.get("source") or "learned"))
        if msg_type in ("query_beliefs", "get_beliefs"):
            found = self.beliefs_about(payload.get("query") or payload.get("text") or "", limit=payload.get("limit", 10))
            return {"status": "success", "beliefs": found, "content": {"beliefs": found, "count": len(found)}}
        if msg_type == "adjust_belief":
            return self.adjust_belief(payload)
        if msg_type == "load_beliefs":
            return self.load_beliefs_file(payload.get("path") or runtime_file("beliefs.txt"))

        answered = self._answer_other_lobes(msg_type, payload)
        if answered is not None:
            return answered

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
            # Durable facts first so Reasoning/Language see taught knowledge.
            fact_memories = []
            for fact in facts:
                if not isinstance(fact, dict):
                    continue
                item = dict(fact)
                item["role"] = "fact"
                if not item.get("content"):
                    try:
                        from notus_fact_text import FactText

                        item["content"] = FactText.format_personal_fact(
                            str(item.get("subject") or ""),
                            str(item.get("predicate") or ""),
                            str(item.get("object") or ""),
                        )
                    except Exception:
                        item["content"] = ""
                if item.get("content"):
                    fact_memories.append(item)
            combined = fact_memories + list(memories or [])

            return {
                "status": "success",
                "content": {
                    "query_text": query,
                    "semantic": combined,
                    "memories": combined,
                    "facts": facts,
                    "episodic": episodes,
                    "working_set": self._working_set_for_user(user_id),
                    "summary": (
                        f"Found {len(memories)} stored memories, "
                        f"{len(facts)} facts, and {len(episodes)} episodes"
                    ),
                },
            }


        if msg_type == "save_abin_persistent_state":
            return self._save_abin_persistent_state(payload)

        if msg_type == "get_abin_persistent_state":
            return self._get_abin_persistent_state(payload)

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
