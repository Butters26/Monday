"""Bounded per-user Notus outage queue for the direct-call Thalamus path.

When Notus store/query fails (error response or raised exception caught by
Thalamus.send_message), records stay in a short-term in-memory queue so the
prompted pipeline can continue. On recovery, records flush back to Notus with
dedupe keys so a double retry cannot double-store.

This is the current-architecture equivalent of the legacy monday_memory dict
fallback from PR #3/#4 — it does NOT restore retrieve_relevant_memory,
sync_memory_to_notus, or monday_memory.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Set


# Hard bound: oldest records evict first (FIFO) when a user's queue is full.
MAX_RECORDS_PER_USER = 64


def _normalize_user_id(user_id: Any) -> str:
    text = str(user_id or "default").strip()
    return text or "default"


def _normalize_role(role: Any) -> str:
    text = str(role or "user").strip().lower() or "user"
    if text in {"assistant", "abin"}:
        return "monday"
    return text


def dedupe_key(user_id: str, role: str, content: str) -> str:
    """Stable identity for retry deduplication (user + role + exact content)."""
    return f"{_normalize_user_id(user_id)}\0{_normalize_role(role)}\0{(content or '').strip()}"


class NotusOutageFallback:
    """Per-user FIFO outage queue + query buffer, isolated by user_id."""

    def __init__(self, max_records_per_user: int = MAX_RECORDS_PER_USER) -> None:
        if max_records_per_user < 1:
            raise ValueError("max_records_per_user must be >= 1")
        self.max_records_per_user = int(max_records_per_user)
        self._lock = threading.RLock()
        self._queues: Dict[str, Deque[Dict[str, Any]]] = {}
        self._synced_keys: Dict[str, Set[str]] = {}
        # Cap remembered synced keys per user to avoid unbounded growth.
        self._synced_key_order: Dict[str, Deque[str]] = {}

    def enqueue(
        self,
        *,
        user_id: str,
        role: str,
        content: str,
        memory_type: str = "conversation",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Queue a record that failed to reach Notus. Returns None if skipped."""
        uid = _normalize_user_id(user_id)
        normalized_role = _normalize_role(role)
        text = (content or "").strip()
        if not text:
            return None
        key = dedupe_key(uid, normalized_role, text)
        record = {
            "user_id": uid,
            "role": normalized_role,
            "content": text,
            "memory_type": str(memory_type or "conversation"),
            "dedupe_key": key,
            "enqueued_at": time.time(),
        }
        if extra:
            for k, v in extra.items():
                if k not in record:
                    record[k] = v

        with self._lock:
            synced = self._synced_keys.setdefault(uid, set())
            if key in synced:
                # Already flushed successfully in a prior retry — do not re-queue.
                return None
            queue = self._queues.setdefault(
                uid, deque(maxlen=self.max_records_per_user)
            )
            # Avoid duplicate pending rows for the same key while still queued.
            for existing in queue:
                if existing.get("dedupe_key") == key:
                    return existing
            queue.append(record)
            return record

    def memories_for(self, user_id: str, limit: int = 15) -> List[Dict[str, Any]]:
        """In-memory context for query fallback, newest last (pipeline order)."""
        uid = _normalize_user_id(user_id)
        lim = max(1, min(int(limit or 15), self.max_records_per_user))
        with self._lock:
            queue = self._queues.get(uid)
            if not queue:
                return []
            items = list(queue)[-lim:]
        return [
            {
                "role": item["role"],
                "content": item["content"],
                "user_id": item["user_id"],
                "memory_type": item.get("memory_type", "conversation"),
                "source": "notus_outage_fallback",
                "dedupe_key": item["dedupe_key"],
            }
            for item in items
        ]

    def pending_records(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if user_id is None:
                out: List[Dict[str, Any]] = []
                for queue in self._queues.values():
                    out.extend(dict(item) for item in queue)
                return out
            uid = _normalize_user_id(user_id)
            queue = self._queues.get(uid)
            return [dict(item) for item in queue] if queue else []

    def pending_count(self, user_id: Optional[str] = None) -> int:
        return len(self.pending_records(user_id))

    def mark_synced(self, user_id: str, key: str) -> None:
        uid = _normalize_user_id(user_id)
        with self._lock:
            synced = self._synced_keys.setdefault(uid, set())
            order = self._synced_key_order.setdefault(
                uid, deque(maxlen=self.max_records_per_user * 4)
            )
            if key not in synced:
                synced.add(key)
                order.append(key)
            # Drop keys that fell off the order deque.
            live = set(order)
            stale = [k for k in synced if k not in live]
            for k in stale:
                synced.discard(k)

    def flush(
        self,
        store_fn: Callable[[Dict[str, Any]], bool],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retry unsaved records.

        ``store_fn(record)`` returns True on successful Notus store.
        Only successfully synchronized records are removed. Failures stay queued.
        Already-synced dedupe keys are dropped without calling store again.
        """
        synced = 0
        failed = 0
        skipped = 0
        users: Iterable[str]
        with self._lock:
            if user_id is None:
                users = list(self._queues.keys())
            else:
                users = [_normalize_user_id(user_id)]

        for uid in users:
            with self._lock:
                queue = self._queues.get(uid)
                if not queue:
                    continue
                snapshot = list(queue)

            kept: Deque[Dict[str, Any]] = deque(maxlen=self.max_records_per_user)
            for record in snapshot:
                key = str(record.get("dedupe_key") or "")
                with self._lock:
                    already = key in self._synced_keys.get(uid, set())
                if already:
                    skipped += 1
                    continue
                try:
                    ok = bool(store_fn(record))
                except Exception:
                    ok = False
                if ok:
                    self.mark_synced(uid, key)
                    synced += 1
                else:
                    kept.append(record)
                    failed += 1

            with self._lock:
                if kept:
                    self._queues[uid] = kept
                else:
                    self._queues.pop(uid, None)

        return {
            "synced": synced,
            "failed": failed,
            "skipped_duplicate": skipped,
            "remaining": self.pending_count(user_id),
        }
