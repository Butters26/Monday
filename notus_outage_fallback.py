"""Bounded per-user Notus outage queue for the direct-call Thalamus path.

When Notus store/query fails (error response or raised exception caught by
Thalamus.send_message), records stay in a short-term in-memory queue so the
prompted pipeline can continue. On recovery, records flush back to Notus in
strict FIFO order; each queued record has its own stable event_id used for
retry idempotency so identical content is never collapsed into one event.

This is the current-architecture equivalent of the legacy monday_memory dict
fallback from PR #3/#4 — it does NOT restore retrieve_relevant_memory,
sync_memory_to_notus, or monday_memory.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Set, Tuple


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


def _content_fingerprint(role: str, content: str) -> str:
    """Context-merge helper only — NOT used for queue identity / idempotency."""
    return f"{_normalize_role(role)}\0{(content or '').strip()}"


def new_event_id() -> str:
    """Stable unique id for one queued outage record (retry idempotency key)."""
    return str(uuid.uuid4())


class NotusOutageFallback:
    """Per-user FIFO outage queue + query buffer, isolated by user_id."""

    def __init__(self, max_records_per_user: int = MAX_RECORDS_PER_USER) -> None:
        if max_records_per_user < 1:
            raise ValueError("max_records_per_user must be >= 1")
        self.max_records_per_user = int(max_records_per_user)
        self._lock = threading.RLock()
        self._queues: Dict[str, Deque[Dict[str, Any]]] = {}
        # Synced *event_ids* — same content may appear again as a new event.
        self._synced_event_ids: Dict[str, Set[str]] = {}
        # Cap remembered synced ids per user to avoid unbounded growth.
        self._synced_id_order: Dict[str, Deque[str]] = {}

    def enqueue(
        self,
        *,
        user_id: str,
        role: str,
        content: str,
        memory_type: str = "conversation",
        extra: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Queue a record that failed to reach Notus.

        Each call creates a distinct event (unless ``event_id`` matches an
        already-synced or already-queued record — retry idempotency only).
        Identical content is intentionally allowed as separate events.
        Returns None only when this exact event_id was already synced or is
        already pending (re-queue of the same record).
        """
        uid = _normalize_user_id(user_id)
        normalized_role = _normalize_role(role)
        text = (content or "").strip()
        if not text:
            return None
        eid = str(event_id or new_event_id()).strip() or new_event_id()
        record = {
            "event_id": eid,
            "user_id": uid,
            "role": normalized_role,
            "content": text,
            "memory_type": str(memory_type or "conversation"),
            # Back-compat alias: idempotency key is the event_id, not content.
            "dedupe_key": eid,
            "enqueued_at": time.time(),
            "durable": False,
        }
        if extra:
            for k, v in extra.items():
                if k not in record:
                    record[k] = v

        with self._lock:
            synced = self._synced_event_ids.setdefault(uid, set())
            if eid in synced:
                # This exact queued record already flushed — do not re-queue.
                return None
            queue = self._queues.setdefault(
                uid, deque(maxlen=self.max_records_per_user)
            )
            for existing in queue:
                if existing.get("event_id") == eid:
                    return existing
            queue.append(record)
            return record

    def memories_for(self, user_id: str, limit: int = 15) -> List[Dict[str, Any]]:
        """In-memory context for query fallback, oldest→newest (pipeline order)."""
        uid = _normalize_user_id(user_id)
        lim = max(1, min(int(limit or 15), self.max_records_per_user))
        with self._lock:
            queue = self._queues.get(uid)
            if not queue:
                return []
            items = list(queue)[-lim:]
        return [self._memory_view(item) for item in items]

    def merge_pending_into(
        self,
        user_id: str,
        notus_memories: Optional[List[Dict[str, Any]]],
        *,
        limit: int = 15,
    ) -> List[Dict[str, Any]]:
        """Merge this user's pending fallback rows into a successful Notus query.

        - Same user only (caller must pass the active user_id).
        - Preserves Notus order, then appends pending FIFO rows not already
          present by role+content (avoid duplicate context if already in Notus).
        - Pending rows are marked durable=False / source=notus_outage_fallback;
          they are not claimed durable until synced.
        """
        base: List[Dict[str, Any]] = [
            dict(m) for m in (notus_memories or []) if isinstance(m, dict)
        ]
        lim = max(1, min(int(limit or 15), self.max_records_per_user))
        seen: Set[str] = set()
        for m in base:
            seen.add(
                _content_fingerprint(
                    str(m.get("role") or "user"),
                    str(m.get("content") or ""),
                )
            )
        pending = self.memories_for(user_id, limit=self.max_records_per_user)
        for item in pending:
            fp = _content_fingerprint(item["role"], item["content"])
            if fp in seen:
                continue
            seen.add(fp)
            base.append(item)
        if len(base) > lim:
            return base[-lim:]
        return base

    @staticmethod
    def _memory_view(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "role": item["role"],
            "content": item["content"],
            "user_id": item["user_id"],
            "memory_type": item.get("memory_type", "conversation"),
            "source": "notus_outage_fallback",
            "event_id": item.get("event_id") or item.get("dedupe_key"),
            "dedupe_key": item.get("event_id") or item.get("dedupe_key"),
            "durable": False,
        }

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

    def mark_synced(self, user_id: str, event_id: str) -> None:
        uid = _normalize_user_id(user_id)
        eid = str(event_id or "").strip()
        if not eid:
            return
        with self._lock:
            synced = self._synced_event_ids.setdefault(uid, set())
            order = self._synced_id_order.setdefault(
                uid, deque(maxlen=self.max_records_per_user * 4)
            )
            if eid not in synced:
                synced.add(eid)
                order.append(eid)
            # Drop ids that fell off the order deque.
            live = set(order)
            stale = [k for k in synced if k not in live]
            for k in stale:
                synced.discard(k)

    def flush(
        self,
        store_fn: Callable[[Dict[str, Any]], bool],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retry unsaved records in strict FIFO order.

        ``store_fn(record)`` returns True on successful Notus store.
        On the first sync failure for a user, STOP — do not attempt later
        records for that user (preserves store order). Successfully synced
        event_ids are remembered so a second retry of the same queued record
        does not double-store.
        """
        synced = 0
        failed = 0
        skipped = 0
        stopped = 0
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
            i = 0
            while i < len(snapshot):
                record = snapshot[i]
                eid = str(
                    record.get("event_id") or record.get("dedupe_key") or ""
                )
                with self._lock:
                    already = eid in self._synced_event_ids.get(uid, set())
                if already:
                    skipped += 1
                    i += 1
                    continue
                try:
                    ok = bool(store_fn(record))
                except Exception:
                    ok = False
                if ok:
                    self.mark_synced(uid, eid)
                    synced += 1
                    i += 1
                    continue
                # Strict FIFO: stop; keep this record and every later one.
                kept.extend(snapshot[i:])
                failed += 1
                remaining_unattempted = len(snapshot) - i - 1
                if remaining_unattempted > 0:
                    stopped += remaining_unattempted
                break

            with self._lock:
                if kept:
                    self._queues[uid] = kept
                else:
                    self._queues.pop(uid, None)

        return {
            "synced": synced,
            "failed": failed,
            "skipped_duplicate": skipped,
            "stopped_unattempted": stopped,
            "remaining": self.pending_count(user_id),
        }


# Back-compat name used by older call sites / docs.
def dedupe_key(user_id: str, role: str, content: str) -> str:
    """Deprecated content-key helper — do not use for queue identity.

    Retained so imports do not break; prefer event_id via ``new_event_id``.
    """
    return f"{_normalize_user_id(user_id)}\0{_normalize_role(role)}\0{(content or '').strip()}"
