"""Deterministic E2E coverage for the prompted direct-call core path."""

import random

from run_abin import create_core_systems, shutdown_core_systems


def test_prompted_core_path_persists_memory_and_delivers_output(tmp_path):
    random.seed(0)
    private_runtime = tmp_path / "runtime"
    systems = create_core_systems(str(private_runtime))
    try:
        response = systems["thalamus"].process_user_input("Hello Monday, explain memory?")

        assert response
        assert systems["output"].last_output == response
        assert list(systems["thalamus"].lobe_handlers) == [
            "conversation", "notus", "emotion", "reasoning", "language", "output"
        ]
        route_names = [route["to"] for route in systems["thalamus"].message_routes]
        prompted_path = ["conversation", "notus", "emotion", "reasoning", "language", "output"]
        positions = [route_names.index(stage) for stage in prompted_path]
        assert positions == sorted(positions)
        memories = systems["notus"].retrieve_memories("Hello Monday")
        assert any(memory["content"] == "Hello Monday, explain memory?" for memory in memories)
    finally:
        shutdown_core_systems(systems)


def test_prompted_core_path_keeps_user_memory_isolated(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
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


def test_prompted_core_path_renders_grounded_greeting_and_gravity_answer(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        greeting = systems["thalamus"].process_user_input("hello")
        gravity = systems["thalamus"].process_user_input("What is gravity?")

        assert "hello" in greeting.lower() or "hi" in greeting.lower()
        assert "mass" in gravity.lower()
        assert "attraction" in gravity.lower()
    finally:
        shutdown_core_systems(systems)


def test_legacy_transcript_rows_are_not_retrieved_or_rendered(tmp_path):
    runtime = tmp_path / "runtime"
    systems = create_core_systems(str(runtime))
    try:
        database = runtime / "notus_memory.sqlite3"
        systems["notus"]._connection.execute(
            "INSERT INTO memories(role, content, user_id, memory_type, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "note",
                "User: hidden prompt\nABIN: hidden response about gravity",
                "default",
                "conversation",
                "2000-01-01T00:00:00+00:00",
            ),
        )
        systems["notus"]._connection.commit()

        response = systems["thalamus"].process_user_input("Tell me about gravity")
        memories = systems["notus"].retrieve_memories("gravity", user_id="default")

        assert memories
        assert all("user:" not in memory["content"].lower() for memory in memories)
        assert all("abin:" not in memory["content"].lower() for memory in memories)
        assert "user:" not in response.lower()
        assert "abin:" not in response.lower()
    finally:
        shutdown_core_systems(systems)


def test_direct_notus_close_is_idempotent_and_uses_sqlite_only(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    notus = systems["notus"]
    try:
        notus.shutdown()
        notus.shutdown()
    finally:
        shutdown_core_systems(systems)

    import direct_notus

    source = open(direct_notus.__file__, encoding="utf-8").read()
    assert "psycopg2" not in source
    assert "torch" not in source
    assert "numpy" not in source


def test_response_provider_failure_uses_safe_fallback(tmp_path):
    class FailingProvider:
        def render(self, user_input, understanding, memories):
            raise RuntimeError("provider unavailable")

    systems = create_core_systems(str(tmp_path / "runtime"))
    systems["thalamus"].response_provider = FailingProvider()
    try:
        assert (
            systems["thalamus"].process_user_input("hello")
            == "I am unable to formulate a response right now."
        )
    finally:
        shutdown_core_systems(systems)
