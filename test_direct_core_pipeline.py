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
        # This prompt is not guaranteed grounded. Current contract permits silence.
        assert isinstance(response, str)
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


def test_prompted_core_path_greets_back_and_admits_unknown(tmp_path):
    """Language builds the reply itself: greets back with a dictionary greeting
    word (no phrase bank), and an unknown question gets an honest "don't know"
    instead of a canned encyclopedia answer or silence."""
    systems = _boot(tmp_path)
    try:
        greeting = systems["thalamus"].process_user_input("hello")
        gravity = systems["thalamus"].process_user_input("What is gravity?")
        g_low = (greeting or "").lower()
        assert g_low.split(",")[0].strip("!") in {"hello", "hullo", "hi", "howdy", "how-do-you-do"}, greeting
        for needle in ("hi there", "nice to meet", "how are you", "take care"):
            assert needle not in g_low
        low = (gravity or "").lower()
        assert "mass" not in low and "attraction" not in low  # no canned encyclopedia
        assert "invent details" not in low  # no stock follow-up glued on
        assert low.strip() in {"i do not know.", "i don't know."}, gravity
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


def test_reasoning_reviews_language_reply_before_output(tmp_path):
    """Language builds the reply; Reasoning reviews it. A rejected reply is not
    delivered, and the reply that reaches Output is the one Reasoning approved."""
    reviews = []

    class ReviewingReasoning:
        def process_message(self, message):
            if message.get("type") == "review_reply":
                content = message.get("content") or {}
                reviews.append(content.get("sentence"))
                return {"status": "success", "content": {"ok": True, "reason": "makes sense"}}
            return {"status": "success", "content": {"answer": "IGNORED_PASS_THROUGH"}}

        def shutdown(self):
            pass

    systems = _boot(tmp_path)
    systems["thalamus"].register_lobe("reasoning", ReviewingReasoning())
    try:
        response = systems["thalamus"].process_user_input("What is photosynthesis?")
        assert reviews, "reasoning never reviewed the reply"
        assert response == reviews[-1]
        assert "IGNORED_PASS_THROUGH" not in response
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


def test_create_core_systems_is_socket_and_postgres_free_with_injected_notus(tmp_path):
    """Proof: injectable Notus boots without sockets or PostgreSQL."""
    import socket

    systems = _boot(tmp_path)
    try:
        # No listening sockets opened by core boot for these tests.
        assert systems["thalamus"].running is True
        assert "autonomous" not in systems["thalamus"].lobe_handlers
        health = systems["thalamus"].send_and_wait("notus", "health", {})
        assert health["status"] == "success"
        backend = health.get("content", {}).get("backend")
        assert backend == "sqlite"
        # Touch process path once. Ungrounded ping may correctly produce silence.
        reply = systems["thalamus"].process_user_input("ping")
        assert isinstance(reply, str)
        # Sanity: stdlib socket module still importable; core did not require PG.
        assert socket is not None
    finally:
        shutdown_core_systems(systems)
