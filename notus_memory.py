"""Active Notus memory lobe.

One job: memory.
One database backend: PostgreSQL.

This uses the strongest memory primitives already present in ``notus.py``
(retrieval via hash-or-transformer embeddings, episodic memory, durable facts, working memory and memory
associations) but deliberately does not expose the old response-generation or
"EnhancedMonday" compatibility layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
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

    # Clean single-speaker rows only — never combined transcript poison.
    _ALLOWED_MEMORY_ROLES = frozenset(
        {"user", "assistant", "monday", "abin", "fact", "note"}
    )
    _TRANSCRIPT_LINE = re.compile(
        r"(?im)^\s*(?:user|assistant|monday|abin)\s*:"
    )
    _COMBINED_TRANSCRIPT = re.compile(
        r"(?is)(?:^|\n)\s*(?:user|assistant|monday|abin)\s*:.*"
        r"\n\s*(?:user|assistant|monday|abin)\s*:"
    )

    # Experience / synthetic-summary / internal-state poison markers.
    _POISON_MARKERS = (
        "How it felt:",
        "What it meant:",
        "How this feels:",
        "What I notice in myself:",
        "Internal state:",
        "Synthetic summary:",
        "Experience digest:",
    )
    _ROLE_PREFIX_ANYWHERE = re.compile(
        r"(?im)(?:^|\n)\s*(?:user|assistant|monday|abin|system)\s*:"
    )

    @classmethod
    def _is_clean_memory_content(cls, role: Any, content: Any) -> bool:
        """True when role is allowed and content is not transcript/experience poison."""
        if not isinstance(role, str) or role.strip().lower() not in cls._ALLOWED_MEMORY_ROLES:
            return False
        if not isinstance(content, str):
            return False
        stripped = content.strip()
        if not stripped:
            return False
        # Reject experience / synthetic / internal-state contamination before persistence.
        for marker in cls._POISON_MARKERS:
            if marker in stripped:
                return False
        # Transcript-like: any role-prefixed line (start OR mid-blob), or multi-speaker.
        if cls._COMBINED_TRANSCRIPT.search(stripped):
            return False
        if cls._TRANSCRIPT_LINE.search(stripped) or cls._ROLE_PREFIX_ANYWHERE.search(stripped):
            return False
        return True


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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS abin_persistent_state (
                    scope TEXT NOT NULL DEFAULT 'reasoning',
                    user_id TEXT NOT NULL DEFAULT 'default',
                    state_json TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (scope, user_id)
                )
                """
            )
        self._db_connection.commit()

    # ------------------------------------------------------------------
    # Whole-history retrieval (empty means empty)
    # ------------------------------------------------------------------

    _RETRIEVAL_STOPWORDS = frozenset(
        {
            "a", "an", "the", "is", "are", "was", "were", "be", "been", "am",
            "i", "my", "me", "mine", "you", "your", "yours", "we", "our",
            "what", "whats", "who", "whom", "where", "when", "why", "how",
            "do", "does", "did", "can", "could", "would", "should", "please",
            "remember", "that", "this", "these", "those", "with", "from",
            "about", "tell", "of", "to", "in", "on", "at", "for", "and", "or",
            "it", "its", "have", "has", "had", "will", "just", "also", "so",
            "as", "if", "but", "not", "no", "yes", "ok", "okay", "hey", "hi",
            "hello", "got", "know", "which", "whose",
            "there", "here", "into", "over", "under", "again", "any", "some",
        }
    )
    # Durable identity tokens must survive stopword stripping on BOTH query and
    # content sides — otherwise "What is my name?" yields empty tokens and the
    # name predicate can never match "Your name is Matthew."
    _RETRIEVAL_KEEPWORDS = frozenset({"name", "named", "called"})
    # Ask-verbs / fillers that must not AND-gate identity recall
    # ("remind me my name", "what am I called name").
    _WEAK_QUERY_TOKENS = frozenset(
        {
            "remind", "call", "tell", "please", "know", "said", "say",
            # Speech-recall meta fillers must not AND-gate Monday's own lines
            # ("the thing you said", "exact words", "earlier about…").
            "thing", "things", "word", "words", "exact", "earlier", "before",
            "previously", "phrase", "told", "called", "mention", "mentioned",
        }
    )
    # Minimum share of query content-tokens that must appear in a hit.
    _MIN_RELEVANCE = 0.34
    # Hard cap so pathological corpora stay bounded; still far beyond the old ~50 window.
    _CORPUS_SCAN_CAP = 5000

    _FRAGILE_FACT_NOUNS = frozenset(
        {
            "day", "life", "mood", "feeling", "feelings", "time", "thing",
            "stuff", "question", "answer", "message", "chat", "conversation",
            "thought", "idea", "problem", "issue", "way", "point", "one",
            "friend", "world", "today", "tonight", "morning", "afternoon",
            "evening", "week", "month", "year", "everything", "nothing",
        }
    )
    # Secret/label nouns that are durable even without a leading "my".
    _DURABLE_KEY_NOUNS = frozenset(
        {
            "codeword", "password", "passphrase", "passcode", "pin", "secret",
            "callsign", "codename", "username", "nickname", "alias", "handle",
            "birthday", "hometown", "timezone", "badge", "key", "token",
            "access_code", "access code", "safe word", "safeword",
        }
    )
    _VAGUE_VALUE_PREFIXES = (
        "going", "feeling", "looking", "doing", "getting", "being", "having",
        "trying", "thinking", "wondering", "hoping", "wanting", "needing",
        "really", "just", "kinda", "kind of", "sort of", "pretty",
    )
    # Bidirectional aliases so "job" finds work_as facts / "live" finds lives_in.
    _TOKEN_ALIASES = {
        "job": frozenset({"job", "work", "occupation", "profession"}),
        "work": frozenset({"job", "work", "occupation", "profession"}),
        "occupation": frozenset({"job", "work", "occupation", "profession"}),
        "profession": frozenset({"job", "work", "occupation", "profession"}),
        "live": frozenset({"live", "lives", "living", "hometown", "city", "location"}),
        "lives": frozenset({"live", "lives", "living", "hometown", "city", "location"}),
        "living": frozenset({"live", "lives", "living", "hometown", "city", "location"}),
        "hometown": frozenset({"live", "lives", "living", "hometown", "city", "location"}),
        "city": frozenset({"live", "lives", "living", "hometown", "city", "location"}),
        "location": frozenset({"live", "lives", "living", "hometown", "city", "location"}),
        "hike": frozenset({"hike", "hiking", "hiked"}),
        "hiking": frozenset({"hike", "hiking", "hiked"}),
        "hiked": frozenset({"hike", "hiking", "hiked"}),
        # Identity asks: "what am I called" / name predicate / readable "name is".
        # "what am I called" is handled by _augment_identity_query (+ name),
        # not by aliasing everyday "call" onto the name predicate.
        "name": frozenset({"name", "named"}),
        "named": frozenset({"name", "named"}),
    }

    @classmethod
    def _alias_set(cls, token: str) -> set:
        return set(cls._TOKEN_ALIASES.get(token, frozenset())) | {token}

    @classmethod
    def _expand_tokens(cls, tokens: set) -> set:
        out = set(tokens or set())
        for t in list(out):
            out |= cls._alias_set(t)
        return out

    @classmethod
    def _stem_token(cls, w: str) -> str:
        """Light stemming for ranking (possessives, -ing/-ed, simple plurals)."""
        if w.endswith("'s") and len(w) > 3:
            w = w[:-2]
        elif w.endswith("s'") and len(w) > 3:
            w = w[:-2]
        short_ing = {
            "going": "go",
            "being": "be",
            "doing": "do",
            "having": "have",
            "nothing": "nothing",
        }
        irregular = {"called": "call", "named": "name"}
        if w in irregular:
            return irregular[w]
        if w in short_ing:
            return short_ing[w]
        if len(w) > 5 and w.endswith("ing"):
            base = w[:-3]
            if len(base) >= 3 and base[-1] == base[-2] and base[-1] not in "aeiou":
                w = base[:-1]  # running -> run
            else:
                w = base + "e"  # hiking -> hike
        elif len(w) > 4 and w.endswith("ed") and not w.endswith(("eed", "ied")):
            base = w[:-2]
            if len(base) >= 3 and base[-1] == base[-2] and base[-1] not in "aeiou":
                w = base[:-1]
            else:
                w = base + "e" if not base.endswith("e") else base  # hiked -> hike
        # Very light plural fold: dogs->dog, names->name (keep ss/us/is).
        if (
            len(w) > 3
            and w.endswith("s")
            and not w.endswith(("ss", "us", "is", "ous", "ics"))
        ):
            w = w[:-1]
        return w

    @classmethod
    def _content_token_list(cls, text: str) -> list:
        """Ordered content tokens (stemmed) for phrase / AND scoring."""
        import re

        words = re.findall(r"[a-z0-9']+", (text or "").lower())
        out = []
        for w in words:
            w = cls._stem_token(w)
            if len(w) <= 1:
                continue
            if w in cls._RETRIEVAL_STOPWORDS and w not in cls._RETRIEVAL_KEEPWORDS:
                continue
            out.append(w)
        return out

    @classmethod
    def _content_tokens(cls, text: str) -> set:
        return set(cls._content_token_list(text))

    @classmethod
    def _significant_tokens(cls, tokens: set) -> set:
        """Content tokens that count for multi-token AND gates."""
        return {
            t for t in (tokens or set())
            if len(t) >= 4 and t not in cls._WEAK_QUERY_TOKENS
        }

    @classmethod
    def _overlap_score(cls, query_tokens: set, text: str) -> float:
        """Fraction of query tokens covered, counting durable aliases as hits."""
        if not query_tokens:
            return 0.0
        cand = cls._content_tokens(text)
        if not cand:
            return 0.0
        cand_exp = cls._expand_tokens(cand)
        hits = 0
        for qt in query_tokens:
            if cls._alias_set(qt) & cand_exp:
                hits += 1
        return hits / float(len(query_tokens))

    @classmethod
    def _phrase_bonus(cls, query: str, text: str) -> float:
        """Reward contiguous multi-word matches (dog name, favorite color, …)."""
        q = cls._content_token_list(query)
        if len(q) < 2:
            return 0.0
        c = cls._content_token_list(text)
        if len(c) < 2:
            return 0.0
        cset_bigrams = {(c[i], c[i + 1]) for i in range(len(c) - 1)}
        hits = 0
        total = 0
        for i in range(len(q) - 1):
            total += 1
            if (q[i], q[i + 1]) in cset_bigrams:
                hits += 1
        if total == 0:
            return 0.0
        return 0.12 * (hits / float(total))

    @classmethod
    def _augment_identity_query(cls, query: str) -> str:
        """Ensure identity asks keep a retrievable 'name' signal.

        'who am I' has no content tokens after stopword strip; append 'name'
        so recall can hit the name predicate / readable fact line.
        """
        import re

        q = (query or "").strip()
        if not q:
            return q
        if re.search(
            r"(?i)\b(?:"
            r"who\s+am\s+i|"
            r"what(?:'s|s)?\s+am\s+i\s+called|"
            r"what\s+am\s+i\s+called|"
            r"remind\s+me\s+(?:of\s+)?my\s+name|"
            r"what(?:'s|s)?\s+my\s+name|"
            r"what\s+is\s+my\s+name|"
            r"my\s+name"
            r")\b",
            q,
        ):
            # Keepwords already preserve 'name' when present; inject when absent.
            # Always ensure a 'name' token for identity asks — "what am I called"
            # only yields {call}, which must not block the name inject.
            if "name" not in cls._content_tokens(q):
                if not re.search(r"(?i)\bname\b", q):
                    return q + " name"
        return q

    @classmethod
    def _is_fact_shaped_query(cls, query: str) -> bool:
        import re

        q = (query or "").strip()
        if not q:
            return False
        return bool(
            re.search(
                r"(?i)\b(?:"
                r"what(?:'s|s|\s+is|\s+was)|"
                r"who(?:'s|s|\s+is|\s+was)|"
                r"where(?:'s|s|\s+is|\s+was)|"
                r"remind\s+me|tell\s+me|"
                r"do\s+you\s+(?:remember|know)|"
                r"what(?:'s|s)?\s+(?:my|the|our)\b"
                r")",
                q,
            )
        )

    @staticmethod
    def _simple_greeting(query: str) -> bool:
        import re

        return bool(
            re.match(
                r"^\s*(?:hello|hi|hey|sup|yo|hiya|howdy)"
                r"(?:\s+(?:there|you|friend))?"
                r"(?:\s*[!.,]*)?\s*$",
                query or "",
                re.IGNORECASE,
            )
        )

    def _score_memory_row(
        self,
        query: str,
        query_tokens: set,
        content: str,
        role: str = "",
    ) -> float:
        """Coverage + phrase + AND bias; weak cosine only as a tiny tie-break.

        Multi-token queries must clear a higher overlap bar. Fact rows matching
        every significant token still pass. Fact-shaped questions prefer facts.
        """
        overlap = self._overlap_score(query_tokens, content)
        if overlap <= 0.0:
            return 0.0
        cand = self._content_tokens(content)
        cand_exp = self._expand_tokens(cand)
        significant = self._significant_tokens(query_tokens)
        role_l = str(role or "").strip().lower()

        def _sig_covered(tokens: set) -> bool:
            return bool(tokens) and all(
                self._alias_set(t) & cand_exp for t in tokens
            )

        def _sig_hit_count(tokens: set) -> int:
            return sum(1 for t in tokens if self._alias_set(t) & cand_exp)

        if len(query_tokens) >= 2:
            # Require clear signal — not a single OR-hit from a long filler row.
            # Multi-significant queries (favorite food vs favorite color) need AND
            # coverage, not a 50% OR hit on the shared adjective.
            min_needed = max(self._MIN_RELEVANCE, 0.5)
            if significant and len(significant) >= 2 and not _sig_covered(significant):
                if overlap < 0.75:
                    return 0.0
            elif overlap < min_needed:
                # Allow fact rows that still hit every significant token (AND).
                # Monday/assistant/abin rows: topic-token hit is enough for
                # own-speech recall (meta fillers already excluded from significant).
                monday_ok = (
                    role_l in {"monday", "assistant", "abin"}
                    and significant
                    and _sig_hit_count(significant) >= 1
                )
                if not (
                    (role_l == "fact" and _sig_covered(significant))
                    or monday_ok
                ):
                    return 0.0
        elif significant and not _sig_hit_count(significant):
            return 0.0
        cosine = 0.0
        try:
            cosine = float(
                self.embedding_engine.calculate_similarity(query, content, "default")
            )
        except Exception:
            cosine = 0.0
        and_bonus = 0.0
        if _sig_covered(significant):
            # Stronger AND bias so buried multi-word memories beat filler OR hits.
            and_bonus = 0.14 if len(significant) >= 2 else 0.10
        elif significant:
            # Partial significant coverage still ranks above pure short-token noise.
            and_bonus = 0.04 * (
                _sig_hit_count(significant) / float(len(significant))
            )
        phrase = self._phrase_bonus(query, content)
        fact_boost = 0.0
        if role_l == "fact" and self._is_fact_shaped_query(query):
            fact_boost = 0.12
        return (
            0.72 * overlap
            + 0.12 * max(0.0, cosine)
            + and_bonus
            + phrase
            + fact_boost
        )

    def retrieve_memories(
        self,
        query: str,
        user_id: str = "default",
        limit: int = None,
    ) -> List[Dict[str, Any]]:
        """Whole-corpus search over superhuman_memories.

        Does not restrict to a tiny recent window. Returns [] when nothing is
        relevant — never pads with unrelated recency.
        """
        limit = max(1, int(limit or getattr(self.config, "max_context_memories", 15)))
        query = self._augment_identity_query((query or "").strip())
        if not query or self._simple_greeting(query):
            return []
        query_tokens = self._content_tokens(query)
        if not query_tokens:
            return []

        user_id = (user_id or "default").strip()
        # Expand LIKE tokens so "job" also scans rows containing "work".
        tokens = sorted(
            self._expand_tokens(query_tokens), key=len, reverse=True
        )[:12]
        like_clauses = []
        params: List[Any] = [user_id]
        for tok in tokens:
            like_clauses.append("lower(content) LIKE %s")
            params.append(f"%{tok}%")
        # Always include durable fact-role rows for this user (may use different wording).
        where_text = " OR ".join(like_clauses) if like_clauses else "FALSE"
        params.append(self._CORPUS_SCAN_CAP)

        try:
            with self._db_connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT id, timestamp, role, content, tag, importance_score, mode,
                           personality, entities, concepts, semantic_hash, access_count,
                           last_accessed, user_id, memory_type, conversation_id
                    FROM superhuman_memories
                    WHERE (user_id = %s OR user_id IS NULL)
                      AND (
                        role = 'fact'
                        OR ({where_text})
                      )
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """,
                    params,
                )
                rows = cursor.fetchall()
        except Exception:
            return []

        scored: List[Dict[str, Any]] = []
        for row in rows:
            content = row[3] if isinstance(row[3], str) else ""
            role = str(row[2] or "").strip().lower()
            # Skip poison / disallowed roles even if tokens matched.
            if not self._is_clean_memory_content(role, content):
                continue
            score = self._score_memory_row(query, query_tokens, content, role=role)
            if score < self._MIN_RELEVANCE:
                continue
            # Require at least one real token hit — no cosine-only invention.
            # Alias coverage counts (job↔work, live↔lives).
            content_tokens = self._expand_tokens(self._content_tokens(content))
            if not any(self._alias_set(qt) & content_tokens for qt in query_tokens):
                continue
            scored.append(
                {
                    "id": row[0],
                    "timestamp": row[1],
                    "role": row[2],
                    "content": content,
                    "tag": row[4],
                    "importance_score": row[5],
                    "mode": row[6],
                    "personality": row[7],
                    "entities": json.loads(row[8]) if row[8] else {},
                    "concepts": json.loads(row[9]) if row[9] else [],
                    "semantic_hash": row[10],
                    "access_count": row[11],
                    "last_accessed": row[12],
                    "user_id": row[13],
                    "memory_type": row[14],
                    "conversation_id": row[15],
                    "similarity": score,
                    "relevance": score,
                }
            )

        scored.sort(
            key=lambda m: (
                float(m.get("similarity") or 0.0),
                float(m.get("importance_score") or 0.0),
                str(m.get("timestamp") or ""),
            ),
            reverse=True,
        )
        results = scored[:limit]
        if results:
            try:
                self._update_access_counts([m["id"] for m in results if m.get("id")])
            except Exception:
                pass
        return results

    def retrieve_memories_smart(
        self,
        query: str,
        user_id: str = "default",
        limit: int = None,
        story_text: str = None,
    ) -> List[Dict[str, Any]]:
        """Smart path that still searches the full corpus — never recency-fills."""
        limit = max(1, int(limit or getattr(self.config, "max_context_memories", 15)))
        if self._simple_greeting(query or ""):
            return []
        # Full-corpus keyword/relevance retrieval; ignore story/chat recency padding.
        return self.retrieve_memories(query, user_id=user_id, limit=limit)

    def recall_facts(
        self,
        query: str,
        user_id: str = "default",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Whole-corpus fact recall with hard relevance gate.

        Empty means empty: unrelated high-confidence/recent facts are not returned.
        Contradicted facts are suppressed.
        """
        limit = max(1, int(limit))
        query = self._augment_identity_query((query or "").strip())
        if not query or self._simple_greeting(query):
            return []
        query_tokens = self._content_tokens(query)
        if not query_tokens:
            return []

        user_id = (user_id or "default").strip()
        try:
            with self._db_connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, subject, predicate, object, value, confidence, permanent,
                           usage_count, created_at, last_reinforced, user_id, source,
                           COALESCE(is_contradicted, FALSE), conflicts_with
                    FROM brain_facts
                    WHERE (user_id = %s OR user_id IS NULL)
                      AND COALESCE(is_contradicted, FALSE) = FALSE
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (user_id, self._CORPUS_SCAN_CAP),
                )
                rows = cursor.fetchall()
        except Exception:
            return []

        scored: List[tuple] = []
        for r in rows:
            subject, predicate, obj, value = r[1], r[2], r[3], r[4]
            fact_text = f"{subject} {predicate} {obj}" + (f" = {value}" if value else "")
            try:
                readable = self.format_personal_fact(
                    str(subject or ""), str(predicate or ""), str(obj or "")
                )
            except Exception:
                readable = fact_text
            blob = f"{fact_text} {readable}"
            # Expand underscore predicates so dog_name matches query token "dog".
            blob = blob.replace("_", " ")
            overlap = self._overlap_score(query_tokens, blob)
            if overlap < self._MIN_RELEVANCE:
                continue
            blob_tokens = self._content_tokens(blob)
            blob_exp = self._expand_tokens(blob_tokens)
            if not any(self._alias_set(qt) & blob_exp for qt in query_tokens):
                continue
            significant = self._significant_tokens(query_tokens)
            # Multi-word fact questions: require majority / AND on significant tokens.
            if len(query_tokens) >= 2 and significant:
                sig_covered = all(
                    self._alias_set(t) & blob_exp for t in significant
                )
                # favorite food must not retrieve favorite_color (50% OR on "favorite")
                if len(significant) >= 2 and not sig_covered and overlap < 0.75:
                    continue
                if overlap < max(self._MIN_RELEVANCE, 0.5) and not sig_covered:
                    continue
            conf = float(r[5] or 0.0)
            perm = 0.05 if (r[6] or 0) else 0.0
            and_bonus = 0.0
            if significant and all(self._alias_set(t) & blob_exp for t in significant):
                and_bonus = 0.14 if len(significant) >= 2 else 0.10
            phrase = self._phrase_bonus(query, blob)
            # Predicate slug tokens (dog_name -> dog name) already in blob via replace.
            pred_boost = 0.0
            pred_l = str(predicate or "").strip().lower()
            pred_tokens = self._content_tokens(pred_l.replace("_", " "))
            if pred_tokens and pred_tokens.issubset(query_tokens | blob_tokens):
                if pred_tokens & query_tokens:
                    pred_boost = 0.08
            # Identity name asks: exact predicate "name" beats dog_name / *_name.
            identity_name_ask = bool(
                re.search(
                    r"(?i)\b(?:what(?:'s|s)?\s+my\s+name|what\s+is\s+my\s+name|"
                    r"who\s+am\s+i|what\s+am\s+i\s+called|remind\s+me\s+(?:of\s+)?my\s+name)\b",
                    query or "",
                )
            )
            if identity_name_ask:
                if pred_l == "name":
                    pred_boost += 0.40
                elif pred_l.endswith("_name"):
                    noun = pred_l[: -len("_name")]
                    noun_toks = self._content_tokens(noun.replace("_", " "))
                    q_exp = self._expand_tokens(query_tokens)
                    if noun_toks and not any(self._alias_set(t) & q_exp for t in noun_toks):
                        # "What is my name?" must not rank dog_name first.
                        continue
            fact_shaped = 0.06 if self._is_fact_shaped_query(query) else 0.0
            score = (
                0.70 * overlap
                + 0.12 * conf
                + perm
                + and_bonus
                + phrase
                + pred_boost
                + fact_shaped
            )
            scored.append(
                (
                    score,
                    {
                        "id": r[0],
                        "subject": subject,
                        "predicate": predicate,
                        "object": obj,
                        "value": value,
                        "confidence": conf,
                        "permanent": bool(r[6]),
                        "usage_count": r[7],
                        "created_at": r[8],
                        "last_reinforced": r[9],
                        "user_id": r[10],
                        "source": r[11],
                        "text": fact_text,
                        "content": readable,
                        "conflicts_with": r[13] or [],
                        "relevance": score,
                    },
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        results = [item for _, item in scored[:limit]]
        if not results:
            return []

        # Only reinforce facts that actually matched — never invent usage on misses.
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._db_connection.cursor() as cursor:
                for fact in results:
                    cursor.execute(
                        """
                        UPDATE brain_facts
                        SET usage_count = COALESCE(usage_count, 0) + 1,
                            confidence = LEAST(1.0, COALESCE(confidence, 0) + %s),
                            last_reinforced = %s
                        WHERE id = %s
                        """,
                        (
                            float(getattr(self.config, "online_learning_rate", 0.01) or 0.01),
                            now,
                            fact["id"],
                        ),
                    )
            self._db_connection.commit()
        except Exception:
            try:
                self._db_connection.rollback()
            except Exception:
                pass
        return results

    def recall_episodes(
        self,
        query: str,
        user_id: str = "default",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Episodic recall with the same empty-means-empty discipline."""
        limit = max(1, int(limit))
        query = (query or "").strip()
        if not query or self._simple_greeting(query):
            return []
        query_tokens = self._content_tokens(query)
        if not query_tokens:
            return []
        user_id = (user_id or "default").strip()
        try:
            with self._db_connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, timestamp, actor, action, object, place, cause, effect,
                           note, sentiment, confidence, source, usage_count
                    FROM episodic_events
                    WHERE user_id = %s OR user_id IS NULL
                    ORDER BY timestamp ASC
                    LIMIT %s
                    """,
                    (user_id, self._CORPUS_SCAN_CAP),
                )
                rows = cursor.fetchall()
        except Exception:
            return []

        scored = []
        for r in rows:
            parts = [p for p in [r[2], r[3], r[4], r[5], r[6], r[7], r[8]] if p]
            text_blob = " ".join(str(p) for p in parts)
            overlap = self._overlap_score(query_tokens, text_blob)
            if overlap < self._MIN_RELEVANCE:
                continue
            if not (query_tokens & self._content_tokens(text_blob)):
                continue
            conf = float(r[10] or 0.0)
            score = 0.85 * overlap + 0.15 * conf
            scored.append(
                (
                    score,
                    {
                        "id": r[0],
                        "timestamp": r[1],
                        "actor": r[2],
                        "action": r[3],
                        "object": r[4],
                        "place": r[5],
                        "cause": r[6],
                        "effect": r[7],
                        "note": r[8],
                        "sentiment": r[9],
                        "confidence": conf,
                        "source": r[11],
                        "usage_count": r[12],
                        "relevance": score,
                    },
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def list_recent_episodes(
        self,
        user_id: str = "default",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """List recent episodic events for one user (no free-text gate).

        Used by the Reasoning↔Notus bridge when counting recorded interactions
        without a relevance query. Strict user_id scope — no cross-user leak.
        """
        limit = max(1, min(int(limit), 100))
        user_id = (user_id or "default").strip()
        try:
            with self._db_connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, timestamp, actor, action, object, place, cause, effect,
                           note, sentiment, confidence, source, usage_count, user_id
                    FROM episodic_events
                    WHERE user_id = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                rows = cursor.fetchall()
        except Exception:
            return []
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "id": r[0],
                    "timestamp": r[1],
                    "actor": r[2],
                    "action": r[3],
                    "object": r[4],
                    "place": r[5],
                    "cause": r[6],
                    "effect": r[7],
                    "note": r[8],
                    "sentiment": r[9],
                    "confidence": float(r[10] or 0.0),
                    "source": r[11],
                    "usage_count": r[12],
                    "user_id": r[13],
                }
            )
        return out

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

    # ------------------------------------------------------------------
    # Auto-extract discipline (tight, contradict/update via remember_fact)
    # ------------------------------------------------------------------

    @classmethod
    def extract_personal_fact_triples(cls, text: str):
        """Durable personal facts only — not fragile chatter.

        Keeps name / favorite / named patterns. Also learns codeword/password-
        style ``(the) X is Y`` and remember-taught durable claims. Generic
        ``my X is Y`` only when the noun looks durable and the value is not a
        vague clause.
        """
        import re
        from typing import List, Optional, Tuple

        if not text or not text.strip():
            return []
        t = text.strip()
        out: List[Tuple[str, str, str, Optional[str]]] = []
        seen = set()

        def _slug(noun: str) -> str:
            return re.sub(r"\s+", "_", noun.strip().lower())

        def _value_ok(val: str) -> bool:
            v = (val or "").strip(" .!?")
            if not v or len(v) > 80:
                return False
            if any(v.lower().startswith(p) for p in cls._VAGUE_VALUE_PREFIXES):
                return False
            # Compound-clause bleed: "Boulder and I work as…" / "Matthew and my dog…"
            if re.search(r"\b(?:and\s+(?:i|my|you|we|he|she|they)\b)", v, re.I):
                return False
            if len(v.split()) > 6:
                return False
            if any(ch in v for ch in (",", ";", ":")) and len(v.split()) > 3:
                return False
            return True

        def _noun_ok(noun: str, *, allow_fragile: bool = False) -> bool:
            n = (noun or "").strip().lower()
            if not n or len(n.split()) > 4:
                return False
            # Reject clause bleed through noun groups ("name is Matthew and my dog").
            if re.search(r"\b(?:is|are|was|were|and|or|named)\b", n):
                return False
            if not allow_fragile and n in cls._FRAGILE_FACT_NOUNS:
                return False
            # Reject pronoun / determiner-only leftovers.
            if n in {"the", "a", "an", "this", "that", "it", "he", "she", "they"}:
                return False
            return True

        def _add(sub: str, pred: str, obj: str) -> None:
            key = (sub.lower(), pred.lower(), obj.lower())
            if key in seen or not sub or not pred or not obj:
                return
            if len(obj) > 80:
                return
            seen.add(key)
            out.append((sub, pred, obj, None))

        def _is_durable_key(noun: str) -> bool:
            n = re.sub(r"\s+", " ", (noun or "").strip().lower())
            if n in cls._DURABLE_KEY_NOUNS:
                return True
            if n.replace(" ", "_") in {
                x.replace(" ", "_") for x in cls._DURABLE_KEY_NOUNS
            }:
                return True
            # Exact soft forms only — never substring-match inside a longer phrase.
            return bool(
                re.fullmatch(
                    r"(?:code\s*word|password|pass\s*phrase|pass\s*code|"
                    r"safe\s*word|access\s*code|call\s*sign|code\s*name|"
                    r"secret|pin|token|badge|username|nickname|alias|handle)",
                    n,
                )
            )

        def _clean_noun(noun: str) -> str:
            n = re.sub(r"\s+", " ", (noun or "").strip().lower())
            # Drop leading teaching / determiner junk if a broader pattern caught it.
            n = re.sub(
                r"^(?:please\s+)?(?:remember\s+)?(?:that\s+)?(?:(?:my|the)\s+)+",
                "",
                n,
            ).strip()
            return n

        # my dog's name is Pixel / my dogs name is Pixel (tight noun — no "is"/"and")
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?(?:remember\s+(?:that\s+)?)?my\s+"
            r"([a-z]+(?:\s+[a-z]+){0,3})(?:'s|s')\s+name\s+is\s+"
            r"([A-Za-z0-9][\w-]{0,40})\b",
            t,
        ):
            if _noun_ok(m.group(1), allow_fragile=True):
                _add("user", f"{_slug(m.group(1))}_name", m.group(2).strip())

        # my dog is named Pixel (tight noun — no clause bleed)
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?(?:remember\s+(?:that\s+)?)?my\s+"
            r"([a-z]+(?:\s+[a-z]+){0,3})\s+is\s+named\s+"
            r"([A-Za-z0-9][\w-]{0,40})\b",
            t,
        ):
            if _noun_ok(m.group(1), allow_fragile=True):
                _add("user", f"{_slug(m.group(1))}_name", m.group(2).strip())

        # my name is Matthew (stop before compound "and …")
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?(?:remember\s+(?:that\s+)?)?my\s+name\s+is\s+"
            r"([A-Za-z][\w-]{0,40})(?=\s+and\b|[.!?,]|$)",
            t,
        ):
            _add("user", "name", m.group(1).strip())

        # my favorite color is blue (value stops before compound "and I/my")
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?(?:remember\s+(?:that\s+)?)?my\s+"
            r"(favorite\s+[a-z]+(?:\s+[a-z]+){0,3})\s+is\s+"
            r"([A-Za-z0-9][\w\s-]{0,60}?)(?=\s+and\s+(?:i|my)\b|[.!?]|$)",
            t,
        ):
            val = m.group(2).strip(" .!?")
            if _value_ok(val):
                _add("user", _slug(m.group(1)), val)

        # Codeword / password / passphrase style (with or without "the"/"my").
        # "Remember the codeword is NebulaQuartz" / "codeword is Alpha"
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?(?:remember\s+(?:that\s+)?)?(?:(?:my|the)\s+)?"
            r"(code\s*word|password|pass\s*phrase|pass\s*code|safe\s*word|"
            r"access\s*code|call\s*sign|code\s*name|secret|pin|token|badge|"
            r"username|nickname|alias|handle)\s+is\s+"
            r"([A-Za-z0-9][\w\s-]{0,60}?)(?:[.!?]|\s*$)",
            t,
        ):
            noun = _clean_noun(m.group(1))
            val = m.group(2).strip(" .!?")
            if noun and _value_ok(val):
                _add("user", _slug(noun), val)

        # Explicit teaching without "my": remember (that) (the) X is Y
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?remember\s+(?:that\s+)?(?:the\s+)?"
            r"([a-z][a-z\s]{0,40}?)\s+is\s+"
            r"([A-Za-z0-9][\w\s-]{0,60}?)(?:[.!?]|\s*$)",
            t,
        ):
            noun = _clean_noun(m.group(1))
            val = m.group(2).strip(" .!?")
            if not noun or noun.startswith("favorite "):
                continue
            if val.lower().startswith("named "):
                continue
            if not _noun_ok(noun):
                continue
            if not _value_ok(val):
                continue
            _add("user", _slug(noun), val)

        # Explicit teaching: remember my X is Y
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?remember\s+(?:that\s+)?my\s+"
            r"([a-z][a-z\s]{0,40}?)\s+is\s+"
            r"([A-Za-z0-9][\w\s-]{0,60}?)(?:[.!?]|\s*$)",
            t,
        ):
            noun = m.group(1).strip()
            val = m.group(2).strip(" .!?")
            if noun.lower().startswith("favorite "):
                continue
            if val.lower().startswith("named "):
                continue
            if not _noun_ok(noun):
                continue
            if not _value_ok(val):
                continue
            _add("user", _slug(noun), val)

        # Generic my X is Y — only short durable nouns, concrete values.
        for m in re.finditer(
            r"(?i)\bmy\s+"
            r"([a-z]+(?:\s+[a-z]+){0,3})\s+is\s+"
            r"([A-Za-z0-9][\w\s-]{0,60}?)(?=\s+and\s+(?:i|my)\b|[.!?]|$)",
            t,
        ):
            noun = m.group(1).strip()
            val = m.group(2).strip(" .!?")
            noun_l = noun.lower()
            if noun_l.startswith("favorite "):
                continue
            if val.lower().startswith("named "):
                continue
            if not _noun_ok(noun):
                continue
            if not _value_ok(val):
                continue
            _add("user", _slug(noun), val)

        # Bare / the X is Y for exact durable key nouns only (no chatter).
        # Uses the specialized key regex above; this only backfills exact set hits
        # that the soft-spaced regex may have missed (e.g. "pin").
        for m in re.finditer(
            r"(?i)\b(?:(?:my|the)\s+)?([a-z][a-z_]{1,40})\s+is\s+"
            r"([A-Za-z0-9][\w\s-]{0,60}?)(?:[.!?]|\s*$)",
            t,
        ):
            noun = _clean_noun(m.group(1))
            val = m.group(2).strip(" .!?")
            if not _is_durable_key(noun):
                continue
            if not _noun_ok(noun):
                continue
            if not _value_ok(val):
                continue
            _add("user", _slug(noun), val)

        # I live in / I work as|at|in — durable location/job.
        # Stop before compound clauses ("… and I work as …").
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?(?:remember\s+(?:that\s+)?)?i\s+live\s+in\s+"
            r"([A-Za-z0-9][A-Za-z0-9\s,.-]{0,60}?)(?=\s+and\s+i\b|[.!?]|$)",
            t,
        ):
            place = m.group(1).strip(" .!?")
            # Drop trailing tense/hedge so "Denver now" -> "Denver".
            place = re.sub(
                r"(?i)\s+\b(?:now|currently|these\s+days|at\s+the\s+moment|"
                r"these\s+days|anymore|again)\s*$",
                "",
                place,
            ).strip(" .!?")
            if place and _value_ok(place):
                _add("user", "lives_in", place)
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?(?:remember\s+(?:that\s+)?)?i\s+work\s+(as|at|in)\s+"
            r"([A-Za-z0-9][A-Za-z0-9\s,.-]{0,60}?)(?=\s+and\s+i\b|[.!?]|$)",
            t,
        ):
            job = m.group(2).strip(" .!?")
            if job and _value_ok(job):
                _add("user", f"work_{m.group(1).lower()}", job)

        return out

    def learn_facts_from_text(
        self,
        text: str,
        user_id: str = "default",
        default_conf: float = 0.85,
    ):
        """Only durable personal facts — no eager X-is-Y / likes / math spam."""
        if not text or not text.strip():
            return []
        ids = []
        for sub, pred, obj, val in self.extract_personal_fact_triples(text):
            fid = self.remember_fact(
                sub,
                pred,
                obj,
                value=val,
                confidence=default_conf,
                user_id=user_id,
                source="learn_text",
                permanent=True,
            )
            if fid:
                ids.append(fid)
        return ids


    @staticmethod
    def format_personal_fact(subject: str, predicate: str, obj: str) -> str:
        """Turn a stored triple into a short, answerable sentence."""
        pred = (predicate or "").strip()
        obj = (obj or "").strip()
        if pred.endswith("_name"):
            noun = pred[:-5].replace("_", " ").strip() or "thing"
            return f"Your {noun}'s name is {obj}."
        if pred.startswith("favorite_") or pred.startswith("favourite_"):
            return f"Your {pred.replace('_', ' ')} is {obj}."
        if pred == "lives_in":
            return f"You live in {obj}."
        if pred.startswith("work_"):
            prep = pred[5:] or "as"
            return f"You work {prep} {obj}."
        if (subject or "").lower() in {"user", "i", "me"}:
            return f"Your {pred.replace('_', ' ')} is {obj}."
        return f"{subject} {pred.replace('_', ' ')} {obj}".strip()

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

    def _ingest_personal_facts_from_text(
        self,
        text: str,
        user_id: str = "default",
        source: str = "user",
        confidence: float = 0.95,
    ) -> List[Dict[str, Any]]:
        """Parse personal facts, store triples, and mirror as role=fact memories."""
        triples = self.extract_personal_fact_triples(text)
        stored: List[Dict[str, Any]] = []
        for subject, predicate, obj, value in triples:
            fact_id = self.remember_fact(
                subject=subject,
                predicate=predicate,
                obj=obj,
                value=value,
                confidence=confidence,
                user_id=user_id,
                source=source,
                permanent=True,
            )
            if not fact_id:
                continue
            readable = self.format_personal_fact(subject, predicate, obj)
            try:
                self.store_memory(
                    role="fact",
                    content=readable,
                    user_id=user_id,
                    tag="Fact",
                    importance=8.5,
                    mode="memory",
                    memory_type="fact",
                    personality="neutral",
                )
            except Exception:
                pass
            stored.append(
                {
                    "id": fact_id,
                    "role": "fact",
                    "content": readable,
                    "subject": subject,
                    "predicate": predicate,
                    "object": obj,
                }
            )
        return stored

    def _facts_as_memories(self, facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Present durable facts in the same shape as conversation memories."""
        out: List[Dict[str, Any]] = []
        for fact in facts or []:
            if not isinstance(fact, dict):
                continue
            subject = str(fact.get("subject", "") or "")
            predicate = str(fact.get("predicate", "") or "")
            obj = str(fact.get("object", "") or "")
            if subject and predicate and obj:
                readable = self.format_personal_fact(subject, predicate, obj)
            else:
                readable = fact.get("content") or fact.get("text")
            if not readable:
                continue
            item = dict(fact)
            item["role"] = "fact"
            item["content"] = readable
            out.append(item)
        return out


    def list_active_facts(
        self,
        user_id: str = "default",
        subject: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List non-contradicted facts for a user (optionally filtered by subject).

        Used by the Reasoning↔Notus bridge when Reasoning asks what is known
        about the user without a free-text relevance query.
        """
        limit = max(1, min(int(limit), 200))
        user_id = (user_id or "default").strip()
        params: List[Any] = [user_id]
        subject_clause = ""
        if subject:
            subject_clause = " AND lower(subject) = lower(%s)"
            params.append(str(subject).strip())
        params.append(limit)
        try:
            with self._db_connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT id, subject, predicate, object, value, confidence, permanent,
                           usage_count, created_at, last_reinforced, user_id, source,
                           COALESCE(is_contradicted, FALSE), conflicts_with
                    FROM brain_facts
                    WHERE (user_id = %s OR user_id IS NULL)
                      AND COALESCE(is_contradicted, FALSE) = FALSE
                      {subject_clause}
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    params,
                )
                rows = cursor.fetchall()
        except Exception:
            return []
        out: List[Dict[str, Any]] = []
        for r in rows:
            subject_v, predicate, obj, value = r[1], r[2], r[3], r[4]
            fact_text = f"{subject_v} {predicate} {obj}" + (f" = {value}" if value else "")
            try:
                readable = self.format_personal_fact(
                    str(subject_v or ""), str(predicate or ""), str(obj or "")
                )
            except Exception:
                readable = fact_text
            out.append(
                {
                    "id": r[0],
                    "subject": subject_v,
                    "predicate": predicate,
                    "object": obj,
                    "value": value,
                    "confidence": float(r[5] or 0.0),
                    "permanent": bool(r[6]),
                    "usage_count": r[7],
                    "created_at": r[8],
                    "last_reinforced": r[9],
                    "user_id": r[10],
                    "source": r[11],
                    "text": fact_text,
                    "content": readable,
                    "conflicts_with": r[13] or [],
                }
            )
        return out


    @classmethod
    def _is_identity_name_query(cls, query: str) -> bool:
        return bool(
            re.search(
                r"(?i)\b(?:what(?:'s|s)?\s+my\s+name|what\s+is\s+my\s+name|"
                r"who\s+am\s+i|what\s+am\s+i\s+called|remind\s+me\s+(?:of\s+)?my\s+name)\b",
                query or "",
            )
        )

    @classmethod
    def _prefer_identity_name_rows(
        cls, query: str, rows: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """For identity name asks, put exact name first; drop unrelated *_name lines."""
        if not cls._is_identity_name_query(query):
            return rows
        name_rows: List[Dict[str, Any]] = []
        other: List[Dict[str, Any]] = []
        for m in rows or []:
            if not isinstance(m, dict):
                continue
            pred = str(m.get("predicate") or "").strip().lower()
            content = str(m.get("content") or m.get("text") or "")
            content_l = content.casefold()
            is_exact_name = pred == "name" or bool(
                re.search(r"(?i)\byour\s+name\s+is\b", content)
            )
            is_other_named = (
                pred.endswith("_name") and pred != "name"
            ) or bool(
                re.search(r"(?i)\byour\s+\w+(?:\s+\w+){0,2}'s\s+name\s+is\b", content)
            )
            if is_exact_name:
                name_rows.append(m)
            elif is_other_named:
                # dog/cat/etc name is not the answer to "What is my name?"
                continue
            else:
                other.append(m)
        return name_rows + other

    @staticmethod
    def _dedupe_memory_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

        """Drop duplicate fact/memory lines (same normalized content)."""
        seen = set()
        out: List[Dict[str, Any]] = []
        for m in rows or []:
            if not isinstance(m, dict):
                continue
            content = str(m.get("content") or m.get("text") or "").strip()
            key = re.sub(r"\s+", " ", content).casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(m)
        return out

    def _filter_superseded_location_memories(
        self,
        memories: List[Dict[str, Any]],
        facts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """If an active lives_in fact exists, drop older location claims as current."""
        active = {
            str(f.get("object") or "").strip().casefold()
            for f in (facts or [])
            if isinstance(f, dict)
            and str(f.get("predicate") or "").strip().lower() == "lives_in"
            and str(f.get("object") or "").strip()
        }
        if not active:
            return memories
        loc_claim = re.compile(
            r"(?i)\b(?:you\s+live\s+in|i\s+live\s+in|lives\s+in)\s+"
            r"([A-Za-z0-9][A-Za-z0-9\s,.-]{0,60})"
        )
        out: List[Dict[str, Any]] = []
        for m in memories or []:
            if not isinstance(m, dict):
                continue
            content = str(m.get("content") or "")
            match = loc_claim.search(content)
            if match:
                place = match.group(1).strip(" .!?")
                place = re.sub(
                    r"(?i)\s+\b(?:now|currently|these\s+days|at\s+the\s+moment)\s*$",
                    "",
                    place,
                ).strip(" .!?")
                if place and place.casefold() not in active:
                    # Superseded location — keep out of CURRENT context.
                    continue
            out.append(m)
        return out


    def _embedding_honesty(self) -> Dict[str, Any]:
        """Surface real embedding backend — hash is not semantic understanding."""
        eng = getattr(self, "embedding_engine", None)
        model_type = getattr(eng, "model_type", "unknown") if eng is not None else "unknown"
        is_basic = model_type == "basic"
        return {
            "embedding_model_type": model_type,
            "retrieval_kind": "hash_similarity" if is_basic else "sentence_transformer",
            "semantic_understanding": False if is_basic else True,
            "note": (
                "basic=deterministic hash fingerprint vectors; not semantic NLU"
                if is_basic
                else "sentence-transformers MiniLM embeddings available"
            ),
        }


    def _save_abin_persistent_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert Reasoning durable-self JSON (beliefs / narrative / changes)."""
        scope = str(payload.get("scope") or "reasoning").strip() or "reasoning"
        user_id = str(payload.get("user_id") or "default").strip() or "default"
        state = payload.get("state")
        if not isinstance(state, dict):
            return {"status": "error", "message": "state must be a dict"}
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
        now = datetime.now(timezone.utc)
        with self._db_connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO abin_persistent_state(scope, user_id, state_json, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (scope, user_id) DO UPDATE SET
                    state_json = EXCLUDED.state_json,
                    updated_at = EXCLUDED.updated_at
                """,
                (scope, user_id, state_json, now),
            )
        self._db_connection.commit()
        belief_count = len(state.get("beliefs") or []) if isinstance(state.get("beliefs"), list) else 0
        return {
            "status": "success",
            "content": {
                "saved": True,
                "scope": scope,
                "user_id": user_id,
                "belief_count": belief_count,
                "updated_at": now.isoformat(),
                "backend": "postgresql",
            },
        }

    def _get_abin_persistent_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return durable-self JSON previously saved for scope/user."""
        scope = str(payload.get("scope") or "reasoning").strip() or "reasoning"
        user_id = str(payload.get("user_id") or "default").strip() or "default"
        with self._db_connection.cursor() as cursor:
            cursor.execute(
                "SELECT state_json, updated_at FROM abin_persistent_state "
                "WHERE scope = %s AND user_id = %s",
                (scope, user_id),
            )
            row = cursor.fetchone()
        if row is None:
            return {
                "status": "success",
                "content": {
                    "state": None,
                    "found": False,
                    "scope": scope,
                    "user_id": user_id,
                    "backend": "postgresql",
                },
            }
        raw, updated_at = row[0], row[1]
        try:
            state = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"status": "error", "message": "stored state_json is corrupt"}
        if not isinstance(state, dict):
            return {"status": "error", "message": "stored state is not a dict"}
        updated = (
            updated_at.isoformat()
            if hasattr(updated_at, "isoformat")
            else str(updated_at)
        )
        return {
            "status": "success",
            "content": {
                "state": state,
                "found": True,
                "scope": scope,
                "user_id": user_id,
                "updated_at": updated,
                "backend": "postgresql",
            },
        }

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
                    **self._embedding_honesty(),
                },
            }

        if msg_type == "store":
            content = payload.get("content")
            role = str(payload.get("role", "user") or "user").strip().lower()
            # Normalize aliases onto the spoken-self role Monday uses elsewhere.
            if role in {"assistant", "abin"}:
                role = "monday"
            if not isinstance(content, str) or not content.strip():
                return {"status": "error", "message": "content must be non-empty text"}
            stripped = content.strip()
            if not self._is_clean_memory_content(role, stripped):
                return {
                    "status": "success",
                    "content": {
                        "stored": False,
                        "skipped": "unsafe_or_disallowed_memory",
                        "role": role,
                    },
                }
            memory_id = self.store_memory(
                role=str(role),
                content=stripped,
                user_id=user_id,
                tag=str(payload.get("tag", "General")),
                importance=float(payload.get("importance", 5.0)),
                mode=str(payload.get("mode", "memory")),
                memory_type=str(payload.get("memory_type", "conversation")),
                personality=str(payload.get("personality", "neutral")),
            )
            if not memory_id:
                return {"status": "error", "message": "memory was not stored"}
            learned: List[Dict[str, Any]] = []
            if str(role) == "user":
                learned = self._ingest_personal_facts_from_text(
                    stripped,
                    user_id=user_id,
                    source=str(payload.get("source", message.get("source", "user"))),
                )
            return {
                "status": "success",
                "content": {
                    "stored": True,
                    "id": memory_id,
                    "content": stripped,
                    "facts_learned": learned,
                },
            }

        if msg_type in {"query", "query_semantic", "query_memories"}:
            query = str(payload.get("query", payload.get("text", "")) or "")
            limit = max(1, min(int(payload.get("limit", 15)), 100))
            memories = self.retrieve_memories_smart(query, user_id=user_id, limit=limit)
            honesty = self._embedding_honesty()
            return {
                "status": "success",
                "content": {
                    "results": memories,
                    "memories": memories,
                    "count": len(memories),
                    **honesty,
                    # Keep key name "semantic" for compat but flag when hash-only.
                    "semantic_label": (
                        "compat_key_only_hash_retrieval"
                        if honesty["embedding_model_type"] == "basic"
                        else "sentence_transformer_retrieval"
                    ),
                },
            }

        if msg_type == "query_context":
            query = str(payload.get("query", payload.get("text", "")) or "")
            limit = max(1, min(int(payload.get("limit", payload.get("max_results", 10))), 50))
            memories = self.retrieve_memories_smart(query, user_id=user_id, limit=limit)
            facts = self.recall_facts(query, user_id=user_id, limit=limit)
            episodes = self.recall_episodes(query, user_id=user_id, limit=limit)
            self._update_working_set(facts, episodes)
            fact_memories = self._facts_as_memories(facts)
            # Put facts first so answer paths see durable knowledge before chatter.
            combined = fact_memories + [
                m for m in memories
                if not (
                    isinstance(m, dict)
                    and str(m.get("role", "")) == "system"
                    and "How it felt:" in str(m.get("content", ""))
                )
            ]
            # Drop superseded location chatter so Boulder cannot look CURRENT.
            combined = self._filter_superseded_location_memories(combined, facts)
            combined = self._dedupe_memory_rows(combined)
            facts = self._dedupe_memory_rows(facts)
            combined = self._prefer_identity_name_rows(query, combined)
            facts = self._prefer_identity_name_rows(query, facts)
            honesty = self._embedding_honesty()
            return {
                "status": "success",
                "content": {
                    "memories": combined,
                    # "semantic" key retained for envelope compat; when
                    # embedding_model_type=basic this is hash retrieval, not NLU.
                    "semantic": combined,
                    "facts": facts,
                    "episodic": episodes,
                    "working_set": self.get_working_set(),
                    **honesty,
                },
            }

        if msg_type in {"remember_fact", "store_fact"}:
            subject = str(payload.get("subject", "") or "")
            predicate = str(payload.get("predicate", "") or "")
            obj = str(payload.get("object", payload.get("obj", "")) or "")
            source = str(payload.get("source", message.get("source", "user")))
            confidence = float(payload.get("confidence", 0.9))
            permanent = bool(payload.get("permanent", False))
            # Schema bridge: learn_fact historically sent only {content}.
            if (not subject or not predicate or not obj) and payload.get("content"):
                learned = self._ingest_personal_facts_from_text(
                    str(payload.get("content")),
                    user_id=user_id,
                    source=source,
                    confidence=confidence,
                )
                if learned:
                    return {
                        "status": "success",
                        "content": {
                            "id": learned[0]["id"],
                            "facts": learned,
                            "count": len(learned),
                        },
                    }
                # Fall back to generic learn_facts_from_text for non-personal content.
                ids = self.learn_facts_from_text(
                    str(payload.get("content")),
                    user_id=user_id,
                    default_conf=confidence,
                )
                if ids:
                    return {
                        "status": "success",
                        "content": {"id": ids[0], "ids": ids, "count": len(ids)},
                    }
                return {
                    "status": "error",
                    "message": "could not extract subject/predicate/object from content",
                }
            fact_id = self.remember_fact(
                subject=subject,
                predicate=predicate,
                obj=obj,
                value=payload.get("value"),
                confidence=confidence,
                user_id=user_id,
                source=source,
                permanent=permanent,
            )
            if not fact_id:
                return {"status": "error", "message": "subject, predicate and object are required"}
            try:
                readable = self.format_personal_fact(subject, predicate, obj)
                self.store_memory(
                    role="fact",
                    content=readable,
                    user_id=user_id,
                    tag="Fact",
                    importance=8.5,
                    mode="memory",
                    memory_type="fact",
                    personality="neutral",
                )
            except Exception:
                pass
            return {"status": "success", "content": {"id": fact_id}}

        if msg_type == "query_facts":
            query = str(payload.get("query", payload.get("text", "")) or "")
            subject = payload.get("subject")
            limit = max(1, min(int(payload.get("limit", 10)), 100))
            # Empty / subject-scoped listing feeds the Reasoning↔Notus bridge.
            if not query.strip():
                facts = self.list_active_facts(
                    user_id=user_id,
                    subject=str(subject).strip() if subject else None,
                    limit=limit,
                )
            else:
                facts = self.recall_facts(query, user_id=user_id, limit=limit)
                # Optional subject filter when Reasoning scopes to "user".
                if subject:
                    sub_l = str(subject).strip().lower()
                    facts = [
                        f for f in facts
                        if str(f.get("subject", "") or "").strip().lower() == sub_l
                    ]
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
            # Active contract: query/text (+ optional legacy pattern as query alias).
            # user_id from payload scopes isolation. Empty query → recent list.
            query = str(
                payload.get("query", payload.get("text", payload.get("pattern", "")))
                or ""
            )
            limit = max(1, min(int(payload.get("limit", 10)), 100))
            if not query.strip():
                episodes = self.list_recent_episodes(user_id=user_id, limit=limit)
            else:
                episodes = self.recall_episodes(
                    query,
                    user_id=user_id,
                    limit=limit,
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


        if msg_type == "save_abin_persistent_state":
            return self._save_abin_persistent_state(payload)

        if msg_type == "get_abin_persistent_state":
            return self._get_abin_persistent_state(payload)

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
