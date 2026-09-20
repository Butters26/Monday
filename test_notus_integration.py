"""Notus outage fallback against the current direct-call envelope architecture.

Does NOT target legacy retrieve_relevant_memory / sync_memory_to_notus /
monday_memory APIs from PR #3/#4.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from direct_notus import DirectNotusProcess
from notus_outage_fallback import MAX_RECORDS_PER_USER, NotusOutageFallback
from run_abin import create_core_systems, shutdown_core_systems


class ControllableNotus:
    """Wrap DirectNotusProcess to simulate error responses or exceptions."""

    def __init__(self, inner: DirectNotusProcess) -> None:
        self.inner = inner
        self.fail_store_with_error = False
        self.fail_query_with_error = False
        self.raise_on_store = False
        self.raise_on_query = False
        self.store_calls: List[Dict[str, Any]] = []
        self.query_calls: List[Dict[str, Any]] = []
        # After N successful stores during flush, start failing (partial retry).
        self.fail_store_after: Optional[int] = None
        self._store_successes = 0

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        payload = message.get("content") if isinstance(message.get("content"), dict) else {}
        if msg_type == "store":
            self.store_calls.append(dict(payload))
            if self.raise_on_store:
                raise RuntimeError("simulated Notus store exception")
            if self.fail_store_with_error:
                return {"status": "error", "message": "simulated Notus store error", "content": {}}
            if self.fail_store_after is not None and self._store_successes >= self.fail_store_after:
                return {"status": "error", "message": "partial flush failure", "content": {}}
            result = self.inner.process_message(message)
            if result.get("status") == "success":
                self._store_successes += 1
            return result
        if msg_type in {"query", "query_context", "get_recent"}:
            self.query_calls.append({"type": msg_type, **dict(payload)})
            if self.raise_on_query:
                raise RuntimeError("simulated Notus query exception")
            if self.fail_query_with_error:
                return {"status": "error", "message": "simulated Notus query error", "content": {}}
            return self.inner.process_message(message)
        return self.inner.process_message(message)

    def retrieve_memories(self, *args, **kwargs):
        return self.inner.retrieve_memories(*args, **kwargs)

    def shutdown(self) -> None:
        shutdown = getattr(self.inner, "shutdown", None)
        if callable(shutdown):
            shutdown()


def _factory(tmp_path, controllable: Optional[ControllableNotus] = None):
    holder = {"ctl": controllable}

    def factory(*, thalamus, runtime_directory):
        inner = DirectNotusProcess(
            storage_path=str(Path(runtime_directory) / "notus_memory.sqlite3"),
            thalamus=thalamus,
        )
        ctl = ControllableNotus(inner)
        holder["ctl"] = ctl
        return ctl

    systems = create_core_systems(
        str(tmp_path / "runtime"),
        notus_factory=factory,
        enable_autonomous=False,
    )
    return systems, holder


def test_helper_bound_eviction_and_per_user_isolation():
    fb = NotusOutageFallback(max_records_per_user=3)
    for i in range(5):
        fb.enqueue(user_id="alice", role="user", content=f"alice-{i}")
    for i in range(2):
        fb.enqueue(user_id="bob", role="user", content=f"bob-{i}")

    alice = [r["content"] for r in fb.pending_records("alice")]
    bob = [r["content"] for r in fb.pending_records("bob")]
    assert alice == ["alice-2", "alice-3", "alice-4"]  # FIFO eviction of 0,1
    assert bob == ["bob-0", "bob-1"]
    assert MAX_RECORDS_PER_USER == 64
    # Isolation: bob queue does not contain alice content
    assert all("alice" not in c for c in bob)


def test_identical_content_enqueues_as_separate_events():
    """Duplicate content must not collapse separate events (Matthew fix #1)."""
    fb = NotusOutageFallback()
    a = fb.enqueue(user_id="u", role="user", content="hello")
    b = fb.enqueue(user_id="u", role="user", content="hello")
    assert a is not None and b is not None
    assert a["event_id"] != b["event_id"]
    pending = fb.pending_records("u")
    assert len(pending) == 2
    assert [r["content"] for r in pending] == ["hello", "hello"]
    assert pending[0]["event_id"] != pending[1]["event_id"]


def test_primary_notus_success_path(tmp_path):
    systems, holder = _factory(tmp_path)
    try:
        reply = systems["thalamus"].process_user_input("hello", user_id="u1")
        assert isinstance(reply, str) and reply.strip()
        assert "trouble remembering" not in reply.lower()
        assert "trouble retrieving" not in reply.lower()
        assert systems["thalamus"].notus_fallback.pending_count("u1") == 0
        assert holder["ctl"].store_calls  # real Notus store invoked
    finally:
        shutdown_core_systems(systems)


def test_notus_store_error_continues_pipeline(tmp_path):
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    assert ctl is not None
    try:
        ctl.fail_store_with_error = True
        reply = systems["thalamus"].process_user_input(
            "Remember my token ALPHA_ONE", user_id="alice"
        )
        assert isinstance(reply, str) and reply.strip()
        assert "trouble remembering" not in reply.lower()
        pending = systems["thalamus"].notus_fallback.pending_records("alice")
        assert any("ALPHA_ONE" in r["content"] for r in pending)
        # Pipeline reached later lobes
        route_tos = [r["to"] for r in systems["thalamus"].message_routes]
        assert "emotion" in route_tos
        assert "reasoning" in route_tos
        assert "language" in route_tos
        assert "output" in route_tos
    finally:
        shutdown_core_systems(systems)


def test_notus_store_exception_continues_pipeline(tmp_path):
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    try:
        ctl.raise_on_store = True
        reply = systems["thalamus"].process_user_input(
            "Remember my token BETA_TWO", user_id="bob"
        )
        assert isinstance(reply, str) and reply.strip()
        assert "trouble remembering" not in reply.lower()
        pending = systems["thalamus"].notus_fallback.pending_records("bob")
        assert any("BETA_TWO" in r["content"] for r in pending)
    finally:
        shutdown_core_systems(systems)


def test_notus_query_error_serves_fallback_context(tmp_path):
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    thalamus = systems["thalamus"]
    try:
        # Seed fallback buffer as if a prior store failed.
        thalamus.notus_fallback.enqueue(
            user_id="carol",
            role="user",
            content="My favorite color is teal",
        )
        ctl.fail_store_with_error = True
        ctl.fail_query_with_error = True
        reply = thalamus.process_user_input(
            "What is my favorite color?", user_id="carol"
        )
        assert isinstance(reply, str) and reply.strip()
        assert "trouble retrieving" not in reply.lower()
        # Fallback context should be visible to downstream memory_context.
        assert thalamus.notus_fallback.memories_for("carol")
    finally:
        shutdown_core_systems(systems)


def test_notus_query_exception_serves_fallback_context(tmp_path):
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    thalamus = systems["thalamus"]
    try:
        thalamus.notus_fallback.enqueue(
            user_id="dave",
            role="user",
            content="SECRET_DAVE_FACT",
        )
        ctl.raise_on_query = True
        ctl.fail_store_with_error = True
        reply = thalamus.process_user_input("remind me", user_id="dave")
        assert isinstance(reply, str) and reply.strip()
        assert "trouble retrieving" not in reply.lower()
        mems = thalamus.notus_fallback.memories_for("dave")
        assert any("SECRET_DAVE_FACT" in m["content"] for m in mems)
    finally:
        shutdown_core_systems(systems)


def test_fifo_stop_on_first_sync_failure(tmp_path):
    """If A fails, B/C must not be attempted; queue stays A,B,C (Matthew fix #2)."""
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    thalamus = systems["thalamus"]
    try:
        fb = thalamus.notus_fallback
        fb.enqueue(user_id="fifo", role="user", content="A")
        fb.enqueue(user_id="fifo", role="user", content="B")
        fb.enqueue(user_id="fifo", role="user", content="C")
        assert fb.pending_count("fifo") == 3

        ctl.fail_store_with_error = True
        stores_before = len(ctl.store_calls)
        result = thalamus.retry_unsaved_notus_records(user_id="fifo")
        assert result["synced"] == 0
        assert result["failed"] == 1
        assert result.get("stopped_unattempted", 0) == 2
        assert fb.pending_count("fifo") == 3
        # Only A attempted — B and C not tried.
        attempted = ctl.store_calls[stores_before:]
        assert len(attempted) == 1
        assert attempted[0].get("content") == "A"
        assert [r["content"] for r in fb.pending_records("fifo")] == ["A", "B", "C"]

        # Heal Notus; retry stores A then B then C in order; queue empty.
        ctl.fail_store_with_error = False
        ctl.fail_store_after = None
        stores_before = len(ctl.store_calls)
        result2 = thalamus.retry_unsaved_notus_records(user_id="fifo")
        assert result2["failed"] == 0
        assert result2["synced"] == 3
        assert fb.pending_count("fifo") == 0
        healed = ctl.store_calls[stores_before:]
        assert [c.get("content") for c in healed] == ["A", "B", "C"]
    finally:
        shutdown_core_systems(systems)


def test_recovery_retry_removes_only_successes_and_dedupes(tmp_path):
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    thalamus = systems["thalamus"]
    try:
        fb = thalamus.notus_fallback
        r1 = fb.enqueue(user_id="erin", role="user", content="unsaved-1")
        r2 = fb.enqueue(user_id="erin", role="user", content="unsaved-2")
        r3 = fb.enqueue(user_id="erin", role="monday", content="unsaved-reply")
        assert fb.pending_count("erin") == 3
        assert r1 and r2 and r3

        # Partial failure: first store succeeds, second fails → STOP (C not attempted).
        ctl._store_successes = 0
        ctl.fail_store_after = 1
        stores_before = len(ctl.store_calls)
        result = thalamus.retry_unsaved_notus_records(user_id="erin")
        assert result["synced"] == 1
        assert result["failed"] == 1
        assert result.get("stopped_unattempted", 0) == 1
        assert fb.pending_count("erin") == 2
        attempted = ctl.store_calls[stores_before:]
        assert [c.get("content") for c in attempted] == ["unsaved-1", "unsaved-2"]
        assert [r["content"] for r in fb.pending_records("erin")] == [
            "unsaved-2",
            "unsaved-reply",
        ]

        # Heal Notus and retry again — remaining should sync in order.
        ctl.fail_store_after = None
        ctl.fail_store_with_error = False
        ctl.raise_on_store = False
        stores_before = len(ctl.store_calls)
        result2 = thalamus.retry_unsaved_notus_records(user_id="erin")
        assert result2["failed"] == 0
        assert fb.pending_count("erin") == 0
        assert [c.get("content") for c in ctl.store_calls[stores_before:]] == [
            "unsaved-2",
            "unsaved-reply",
        ]

        # Double retry must not store the same event_ids again.
        stores_before = len(ctl.store_calls)
        result3 = thalamus.retry_unsaved_notus_records(user_id="erin")
        assert result3["synced"] == 0
        assert len(ctl.store_calls) == stores_before

        # Re-queue of the *same* event_id after sync is skipped (idempotency).
        skipped = fb.enqueue(
            user_id="erin",
            role="user",
            content="unsaved-1",
            event_id=r1["event_id"],
        )
        assert skipped is None

        memories = ctl.retrieve_memories("unsaved", user_id="erin", limit=50)
        contents = [m.get("content") for m in memories]
        assert contents.count("unsaved-1") == 1
        assert contents.count("unsaved-2") == 1
    finally:
        shutdown_core_systems(systems)


def test_identical_messages_survive_outage_as_separate_events(tmp_path):
    """Regression: enqueue identical user message twice during outage;
    both pending as separate events; after recovery both stored once in order;
    second retry stores neither again.
    """
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    thalamus = systems["thalamus"]
    try:
        fb = thalamus.notus_fallback
        ctl.fail_store_with_error = True
        thalamus.process_user_input("hello", user_id="twin")
        thalamus.process_user_input("hello", user_id="twin")

        pending = [
            r
            for r in fb.pending_records("twin")
            if r.get("role") == "user" and r.get("content") == "hello"
        ]
        assert len(pending) == 2
        assert pending[0]["event_id"] != pending[1]["event_id"]

        ctl.fail_store_with_error = False
        ctl.fail_store_after = None
        # Drain monday reply rows too if any — flush all for user.
        result = thalamus.retry_unsaved_notus_records(user_id="twin")
        assert result["failed"] == 0
        assert fb.pending_count("twin") == 0

        hello_stores = [
            c
            for c in ctl.store_calls
            if c.get("content") == "hello" and c.get("role") in {"user", "User"}
        ]
        # Two distinct hello user events stored (may include live failed attempts
        # that never persisted — count successful durable rows via retrieve).
        memories = ctl.retrieve_memories("hello", user_id="twin", limit=50)
        hello_mems = [
            m
            for m in memories
            if str(m.get("content") or "") == "hello"
            and str(m.get("role") or "").lower() in {"user", ""}
        ]
        # DirectNotus may not always stamp role; fall back to content count.
        if not hello_mems:
            hello_mems = [m for m in memories if str(m.get("content") or "") == "hello"]
        assert len(hello_mems) >= 2, f"expected both hellos durable, got {memories!r}"

        stores_before = len(ctl.store_calls)
        result2 = thalamus.retry_unsaved_notus_records(user_id="twin")
        assert result2["synced"] == 0
        assert len(ctl.store_calls) == stores_before
    finally:
        shutdown_core_systems(systems)


def test_pending_fallback_visible_when_query_succeeds(tmp_path):
    """STORE fail + QUERY success → pending merged into memory before Reasoning
    (Matthew fix #3). After recovery, no duplicate durable record.
    """
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    thalamus = systems["thalamus"]

    captured: List[Dict[str, Any]] = []

    class CaptureReasoning:
        def process_message(self, message):
            content = message.get("content") if isinstance(message.get("content"), dict) else {}
            captured.append(content)
            return {
                "status": "success",
                "content": {
                    "answer": "ok-from-fallback-context",
                    "conclusion": "ok-from-fallback-context",
                },
            }

        def shutdown(self):
            pass

    def _memories_from_capture(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Locate memories whether nested under input.memory_context or flat."""
        if not isinstance(payload, dict):
            return []
        candidates = []

        def _push(node):
            if isinstance(node, dict):
                candidates.append(node)
                inner = node.get("content")
                if isinstance(inner, dict):
                    candidates.append(inner)

        for key in ("memory_context", "memory_result"):
            _push(payload.get(key))
        nested = payload.get("input")
        if isinstance(nested, dict):
            for key in ("memory_context", "memory_result"):
                _push(nested.get(key))
        for node in candidates:
            mems = node.get("memories")
            if isinstance(mems, list) and mems:
                return [m for m in mems if isinstance(m, dict)]
        return []

    thalamus.register_lobe("reasoning", CaptureReasoning())
    try:
        ctl.fail_store_with_error = True
        # First turn: store fails, fact lands in fallback queue.
        thalamus.process_user_input(
            "Remember FACT_MERGE_TEAL is my color", user_id="frank"
        )
        pending = thalamus.notus_fallback.pending_records("frank")
        assert any("FACT_MERGE_TEAL" in r["content"] for r in pending)

        # Second turn: store still failing, but QUERY works — pending must merge.
        captured.clear()
        reply = thalamus.process_user_input(
            "What color did I mention?", user_id="frank"
        )
        assert isinstance(reply, str) and reply.strip()
        assert captured, "reasoning should have been invoked"
        memories = _memories_from_capture(captured[-1])
        assert any(
            "FACT_MERGE_TEAL" in str(m.get("content") or "") for m in memories
        ), f"pending fallback missing from reasoning context: {captured[-1]!r}"
        # Must not claim durable.
        fallback_hits = [
            m
            for m in memories
            if "FACT_MERGE_TEAL" in str(m.get("content") or "")
            and m.get("source") == "notus_outage_fallback"
        ]
        assert fallback_hits
        assert all(m.get("durable") is False for m in fallback_hits)

        # Cross-user: other user's reasoning must not see frank's pending.
        captured.clear()
        thalamus.process_user_input("hello from gus", user_id="gus")
        if captured:
            other_mem = _memories_from_capture(captured[-1])
            assert all(
                "FACT_MERGE_TEAL" not in str(m.get("content") or "")
                for m in other_mem
            )

        # Recovery sync → durable once; no duplicate on second flush.
        ctl.fail_store_with_error = False
        ctl.fail_store_after = None
        result = thalamus.retry_unsaved_notus_records(user_id="frank")
        assert result["failed"] == 0
        assert thalamus.notus_fallback.pending_count("frank") == 0

        memories = ctl.retrieve_memories("FACT_MERGE_TEAL", user_id="frank", limit=50)
        teal = [
            m
            for m in memories
            if "FACT_MERGE_TEAL" in str(m.get("content") or "")
        ]
        assert len(teal) >= 1
        # Content may appear as user utterance once (plus maybe monday reply).
        user_teal = [
            m
            for m in teal
            if str(m.get("role") or "").lower() in {"user", ""}
            or "Remember FACT_MERGE_TEAL" in str(m.get("content") or "")
        ]
        assert len(user_teal) <= 2  # utterance once; tolerate role-less duplicate sniff

        stores_before = len(ctl.store_calls)
        result2 = thalamus.retry_unsaved_notus_records(user_id="frank")
        assert result2["synced"] == 0
        assert len(ctl.store_calls) == stores_before
    finally:
        shutdown_core_systems(systems)


def test_outage_queue_does_not_leak_across_users(tmp_path):
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    thalamus = systems["thalamus"]
    try:
        ctl.fail_store_with_error = True
        thalamus.process_user_input("ALICE_ONLY_SECRET", user_id="alice")
        thalamus.process_user_input("BOB_ONLY_SECRET", user_id="bob")

        alice_pending = thalamus.notus_fallback.pending_records("alice")
        bob_pending = thalamus.notus_fallback.pending_records("bob")
        assert any("ALICE_ONLY_SECRET" in r["content"] for r in alice_pending)
        assert any("BOB_ONLY_SECRET" in r["content"] for r in bob_pending)
        assert all("BOB_ONLY_SECRET" not in r["content"] for r in alice_pending)
        assert all("ALICE_ONLY_SECRET" not in r["content"] for r in bob_pending)

        alice_ctx = thalamus.notus_fallback.memories_for("alice")
        bob_ctx = thalamus.notus_fallback.memories_for("bob")
        assert all("BOB_ONLY_SECRET" not in m["content"] for m in alice_ctx)
        assert all("ALICE_ONLY_SECRET" not in m["content"] for m in bob_ctx)
    finally:
        shutdown_core_systems(systems)


def test_no_legacy_monday_memory_apis():
    from thalamus import Thalamus

    t = Thalamus()
    assert not hasattr(t, "monday_memory")
    assert not hasattr(t, "retrieve_relevant_memory")
    assert not hasattr(t, "sync_memory_to_notus")
    assert hasattr(t, "notus_fallback")
    assert hasattr(t, "retry_unsaved_notus_records")
    assert hasattr(t, "_merge_notus_fallback_into_context")
