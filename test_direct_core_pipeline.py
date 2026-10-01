"""Deterministic coverage for the prompted direct-call core path (current main).

Uses an injectable SQLite Notus so acceptance stays PostgreSQL-free and
socket-free, with autonomous background loops disabled.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Dict

from direct_notus import DirectNotusProcess
from reasoning import MaximumSophisticationReasoning
from run_abin import create_core_systems, shutdown_core_systems


PROMPTED_CORE = (
    "conversation",
    "notus",
    "emotion",
    "reasoning",
    "language",
    "output",
)


def _sqlite_notus_factory(*, thalamus: Any, runtime_directory: str) -> DirectNotusProcess:
    path = str(Path(runtime_directory) / "notus_memory.sqlite3")
    return DirectNotusProcess(storage_path=path, thalamus=thalamus)


def _boot(tmp_path, **kwargs) -> Dict[str, Any]:
    opts = {
        "runtime_directory": str(tmp_path / "runtime"),
        "notus_factory": _sqlite_notus_factory,
        "enable_autonomous": False,
    }
    opts.update(kwargs)
    return create_core_systems(**opts)


def test_prompted_core_path_order_and_output(tmp_path):
    random.seed(0)
    systems = _boot(tmp_path)
    try:
        response = systems["thalamus"].process_user_input(
            "Hello Monday, explain memory?"
        )
        assert response
        assert systems["output"].last_output == response

        handlers = list(systems["thalamus"].lobe_handlers)
        for name in PROMPTED_CORE:
            assert name in handlers

        # Autonomous must stay off for these acceptance tests.
        assert "autonomous" not in handlers

        # Primary prompted envelope order (ignore earlier side routes).
        route_pairs = [
            (r.get("to"), r.get("type")) for r in systems["thalamus"].message_routes
        ]
        primary = [
            ("conversation", "understand"),
            ("notus", "store"),
            ("emotion", "process_input"),
            ("reasoning", "think"),
            ("language", "generate"),
            ("output", "generate_output"),
        ]
        positions = []
        cursor = 0
        for step in primary:
            try:
                idx = route_pairs.index(step, cursor)
            except ValueError as exc:
                raise AssertionError(f"missing prompted step {step}") from exc
            positions.append(idx)
            cursor = idx + 1
        assert positions == sorted(positions)
        store_idx = positions[1]
        emotion_idx = positions[2]
        context_indices = [
            i
            for i, pair in enumerate(route_pairs)
            if pair[0] == "notus" and pair[1] in {"query", "query_context"}
        ]
        assert context_indices, "expected Notus query/query_context on prompted path"
        assert store_idx < min(context_indices) < emotion_idx

        memories = systems["notus"].retrieve_memories("Hello Monday", user_id="default")
        assert any(
            memory.get("content") == "Hello Monday, explain memory?"
            for memory in memories
        )
    finally:
        shutdown_core_systems(systems)


def test_prompted_core_path_keeps_user_memory_isolated(tmp_path):
    systems = _boot(tmp_path)
    try:
        systems["thalamus"].process_user_input(
            "ALICE_PRIVATE_TOKEN", user_id="alice"
        )
        alice_memories = systems["notus"].retrieve_memories(
            "ALICE_PRIVATE_TOKEN", user_id="alice"
        )
        default_memories = systems["notus"].retrieve_memories(
            "ALICE_PRIVATE_TOKEN", user_id="default"
        )
        assert alice_memories
        assert not default_memories
    finally:
        shutdown_core_systems(systems)


def test_prompted_core_path_renders_greeting_and_ungrounded_fail_closed(tmp_path):
    """Greeting still speaks; ungrounded encyclopedia asks fail closed (no canned gravity)."""
    systems = _boot(tmp_path)
    try:
        greeting = systems["thalamus"].process_user_input("hello")
        gravity = systems["thalamus"].process_user_input("What is gravity?")
        assert "hello" in greeting.lower() or "hi" in greeting.lower()
        low = gravity.lower()
        # Provider canned encyclopedias ripped; Language Mad Libs quarantined.
        assert "mass" not in low
        assert "attraction" not in low
        assert (
            "enough to go on" in low
            or "enough grounded" in low
            or low.rstrip().endswith("?")
        )
    finally:
        shutdown_core_systems(systems)


def test_prompted_core_recalls_stable_fact_after_restart(tmp_path):
    runtime = tmp_path / "runtime"

    def factory(*, thalamus, runtime_directory):
        return DirectNotusProcess(
            storage_path=str(Path(runtime_directory) / "notus_memory.sqlite3"),
            thalamus=thalamus,
        )

    first = create_core_systems(
        str(runtime),
        notus_factory=factory,
        enable_autonomous=False,
    )
    try:
        learned = first["thalamus"].process_user_input(
            "My favorite color is violet", user_id="alice"
        )
        assert isinstance(learned, str) and learned.strip()
        stored = first["notus"].retrieve_memories(
            "favorite color violet", user_id="alice"
        )
        assert any(
            "violet" in str(m.get("content", "")).lower() for m in stored
        ), "user utterance must persist in Notus for alice"
    finally:
        shutdown_core_systems(first)

    reopened = create_core_systems(
        str(runtime),
        notus_factory=factory,
        enable_autonomous=False,
    )
    try:
        # Current DirectNotus public behavior: durable rows survive restart.
        # Fact-answer wording is owned by Reasoning/Language and is out of
        # Notus-fallback scope — assert memory survival, not reply prose.
        recalled_memories = reopened["notus"].retrieve_memories(
            "favorite color violet", user_id="alice"
        )
        assert any(
            "violet" in str(m.get("content", "")).lower() for m in recalled_memories
        )
        reply = reopened["thalamus"].process_user_input(
            "What is my favorite color?", user_id="alice"
        )
        assert isinstance(reply, str) and reply.strip()
    finally:
        shutdown_core_systems(reopened)


def test_reasoning_answer_reaches_output_without_provider_replacement(tmp_path):
    class InjectedReasoning:
        def process_message(self, message):
            return {
                "status": "success",
                "content": {
                    "answer": "UNMISTAKABLE_REASONING_RESULT",
                    "conclusion": "A lower-priority conclusion",
                    "propositions": ["A lower-priority proposition"],
                },
            }

        def shutdown(self):
            pass

    systems = _boot(tmp_path)
    systems["thalamus"].register_lobe("reasoning", InjectedReasoning())
    try:
        response = systems["thalamus"].process_user_input("What is photosynthesis?")
        assert response == "UNMISTAKABLE_REASONING_RESULT"
        assert systems["output"].last_output == response
    finally:
        shutdown_core_systems(systems)


def test_full_reasoner_think_about_runs_for_every_direct_prompt(tmp_path):
    class SpyFullReasoner(MaximumSophisticationReasoning):
        calls = []

        def think_about(self, input_data):
            type(self).calls.append(input_data)
            return super().think_about(input_data)

    SpyFullReasoner.calls = []
    systems = _boot(tmp_path, reasoning_factory=SpyFullReasoner)
    try:
        systems["thalamus"].process_user_input("hello")
        systems["thalamus"].process_user_input("What is gravity?")
        assert len(SpyFullReasoner.calls) == 2
        assert all(call["user_id"] == "default" for call in SpyFullReasoner.calls)
        assert all(
            call["memory_result"]["status"] == "success"
            for call in SpyFullReasoner.calls
        )
    finally:
        shutdown_core_systems(systems)


def test_create_core_systems_is_socket_and_postgres_free_with_injected_notus(tmp_path, monkeypatch):
    """Proof: injectable Notus boots without sockets or PostgreSQL."""
    import socket
    import builtins

    original_import = builtins.__import__

    def reject_postgres(name, *args, **kwargs):
        if name == "psycopg2" or name.startswith("psycopg2."):
            raise AssertionError("Injected Notus must not load PostgreSQL")
        return original_import(name, *args, **kwargs)

    def reject_socket(*args, **kwargs):
        raise AssertionError("The direct core must not open a socket")

    monkeypatch.setattr(builtins, "__import__", reject_postgres)
    monkeypatch.setattr(socket, "socket", reject_socket)

    systems = _boot(tmp_path)
    try:
        # No listening sockets opened by core boot for these tests.
        assert systems["thalamus"].running is True
        assert "autonomous" not in systems["thalamus"].lobe_handlers
        health = systems["thalamus"].send_and_wait("notus", "health", {})
        assert health["status"] == "success"
        backend = health.get("content", {}).get("backend")
        assert backend == "sqlite"
        # Touch process path once.
        reply = systems["thalamus"].process_user_input("ping")
        assert isinstance(reply, str) and reply.strip()
    finally:
        shutdown_core_systems(systems)


def test_default_notus_falls_back_when_postgres_driver_is_missing(tmp_path, monkeypatch):
    """Missing optional driver must reach durable SQLite, not fail at import."""
    import builtins

    original_import = builtins.__import__

    def without_postgres(name, *args, **kwargs):
        if name == "psycopg2" or name.startswith("psycopg2."):
            raise ImportError("simulated missing PostgreSQL driver")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_postgres)
    monkeypatch.setenv("MONDAY_NOTUS_SQLITE", str(tmp_path / "shared.sqlite3"))
    systems = create_core_systems(str(tmp_path / "runtime"), enable_autonomous=False)
    try:
        assert systems["notus_identity"]["backend"] == "sqlite"
        assert systems["notus_identity"]["role"] == "shared_direct_fallback"
        assert Path(systems["notus_identity"]["sqlite_path"]) == tmp_path / "shared.sqlite3"
        result = systems["notus"].process_message({
            "type": "store",
            "content": {"role": "user", "content": "fallback survives restart", "user_id": "audit"},
        })
        assert result["status"] == "success"
    finally:
        shutdown_core_systems(systems)

    reopened = create_core_systems(str(tmp_path / "other-runtime"), enable_autonomous=False)
    try:
        rows = reopened["notus"].retrieve_memories("fallback survives restart", user_id="audit")
        assert any(row["content"] == "fallback survives restart" for row in rows)
    finally:
        shutdown_core_systems(reopened)


def test_explicit_runtime_directory_isolates_non_notus_state(tmp_path):
    """Independent cores must not silently share Pattern or lobe learning files."""
    first = _boot(tmp_path / "first")
    second = _boot(tmp_path / "second")
    try:
        first_dir = tmp_path / "first" / "runtime"
        second_dir = tmp_path / "second" / "runtime"
        for systems, directory in ((first, first_dir), (second, second_dir)):
            assert systems["pattern"].knowledge_path == directory / "pattern_knowledge.json"
            assert systems["output"]._speech_buffer_path == directory / "output_speech_buffer.txt"
            for name, lobe in systems["thalamus"].lobe_handlers.items():
                if name != "notus":
                    assert lobe._lobe_learning_store.path == directory / "lobe_learning" / f"{name}.json"
        lesson = {"user_id": "audit", "key": "isolated_lesson", "fact": "This lesson belongs to the first core."}
        store = first["reasoning"]._lobe_learning_store
        assert store.learn(lesson)["status"] == "success"
        assert not second["reasoning"]._lobe_learning_store.path.exists()
        assert first["reasoning"]._lobe_learning_store.path.exists()
    finally:
        shutdown_core_systems(first)
        shutdown_core_systems(second)
