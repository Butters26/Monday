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


def test_recovery_retry_removes_only_successes_and_dedupes(tmp_path):
    systems, holder = _factory(tmp_path)
    ctl = holder["ctl"]
    thalamus = systems["thalamus"]
    try:
        fb = thalamus.notus_fallback
        fb.enqueue(user_id="erin", role="user", content="unsaved-1")
        fb.enqueue(user_id="erin", role="user", content="unsaved-2")
        fb.enqueue(user_id="erin", role="monday", content="unsaved-reply")
        assert fb.pending_count("erin") == 3

        # Partial failure: only first store succeeds, rest fail.
        ctl._store_successes = 0
        ctl.fail_store_after = 1
        result = thalamus.retry_unsaved_notus_records(user_id="erin")
        assert result["synced"] == 1
        assert result["failed"] >= 1
        assert fb.pending_count("erin") == 2

        # Heal Notus and retry again — remaining should sync.
        ctl.fail_store_after = None
        ctl.fail_store_with_error = False
        ctl.raise_on_store = False
        result2 = thalamus.retry_unsaved_notus_records(user_id="erin")
        assert result2["failed"] == 0
        assert fb.pending_count("erin") == 0

        # Double retry must not create duplicate Notus rows for already-synced keys.
        stores_before = len(ctl.store_calls)
        result3 = thalamus.retry_unsaved_notus_records(user_id="erin")
        assert result3["synced"] == 0
        assert len(ctl.store_calls) == stores_before

        # Re-enqueue the same content after successful sync — should be skipped
        # by dedupe (already synced keys).
        skipped = fb.enqueue(user_id="erin", role="user", content="unsaved-1")
        assert skipped is None

        memories = ctl.retrieve_memories("unsaved", user_id="erin", limit=50)
        contents = [m.get("content") for m in memories]
        assert contents.count("unsaved-1") == 1
        assert contents.count("unsaved-2") == 1
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
