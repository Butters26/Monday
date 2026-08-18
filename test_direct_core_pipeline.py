"""Deterministic E2E coverage for the prompted direct-call core path."""

import random
import threading

from reasoning import MaximumSophisticationReasoning
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


def test_prompted_core_recalls_stable_fact_after_restart(tmp_path):
    runtime = tmp_path / "runtime"
    first_core = create_core_systems(str(runtime))
    try:
        learned = first_core["thalamus"].process_user_input(
            "My favorite color is violet", user_id="alice"
        )
        assert "favorite color is violet" in learned.lower()
    finally:
        shutdown_core_systems(first_core)

    reopened_core = create_core_systems(str(runtime))
    try:
        recalled = reopened_core["thalamus"].process_user_input(
            "What is my favorite color?", user_id="alice"
        )
        assert recalled == "Your favorite color is violet."
    finally:
        shutdown_core_systems(reopened_core)


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

    systems = create_core_systems(str(tmp_path / "runtime"))
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

    systems = create_core_systems(
        str(tmp_path / "runtime"), reasoning_factory=SpyFullReasoner
    )
    try:
        systems["thalamus"].process_user_input("hello")
        systems["thalamus"].process_user_input("What is gravity?")

        assert len(SpyFullReasoner.calls) == 2
        assert all(call["user_id"] == "default" for call in SpyFullReasoner.calls)
        assert all(call["memory_result"]["status"] == "success" for call in SpyFullReasoner.calls)
    finally:
        shutdown_core_systems(systems)


def test_injected_full_reasoner_conclusion_reaches_language_and_output(tmp_path):
    class InjectedFullReasoner(MaximumSophisticationReasoning):
        def think_about(self, input_data):
            return {
                "composed_response": "FULL_REASONER_CONCLUSION",
                "theories": [{"components": ["injected evidence"]}],
            }

    systems = create_core_systems(
        str(tmp_path / "runtime"), reasoning_factory=InjectedFullReasoner
    )
    try:
        response = systems["thalamus"].process_user_input("Any prompt")
        assert response == "FULL_REASONER_CONCLUSION"
        assert systems["output"].last_output == response
    finally:
        shutdown_core_systems(systems)


def test_grounded_theory_explanation_reaches_output_without_provider_fallback(tmp_path):
    class InjectedTheoryReasoner(MaximumSophisticationReasoning):
        def think_about(self, input_data):
            return {
                "composed_response": "",
                "theories": [
                    {
                        "explanation": "Gravity is the force of attraction between masses.",
                        "components": ["baseline evidence"],
                    }
                ],
            }

    systems = create_core_systems(
        str(tmp_path / "runtime"), reasoning_factory=InjectedTheoryReasoner
    )
    try:
        response = systems["thalamus"].process_user_input("What is gravity?")
        assert response == "Gravity is the force of attraction between masses."
        assert systems["output"].last_output == response
    finally:
        shutdown_core_systems(systems)


def test_greeting_with_request_keeps_request_response(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        response = systems["thalamus"].process_user_input(
            "Hello Monday, explain memory?"
        )
        assert "memory is information retained" in response.lower()
        assert response != "Hello! How can I help?"
    finally:
        shutdown_core_systems(systems)


def test_unseen_question_gets_honest_grounded_fallback(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        response = systems["thalamus"].process_user_input("Tell me about Mercy.")
        assert response.startswith("I do not have enough grounded information")
        assert "concept" not in response.lower()
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
    class NoAnswerReasoning:
        def process_message(self, message):
            return {"status": "success", "content": {"semantic_input": {}}}

        def shutdown(self):
            pass

    systems["thalamus"].register_lobe("reasoning", NoAnswerReasoning())
    try:
        assert (
            systems["thalamus"].process_user_input("an unknown prompt")
            == "I am unable to formulate a response right now."
        )
    finally:
        shutdown_core_systems(systems)


def test_reasoning_notus_automatic_update_uses_content_payload():
    class FakeThalamus:
        def __init__(self):
            self.lobe_handlers = {}

        def send_message(self, destination, msg_type, content=None, source="thalamus"):
            return {"status": "error", "content": {}}

    reasoner = MaximumSophisticationReasoning(thalamus=FakeThalamus())
    received = {}
    seen = threading.Event()

    def capture(payload):
        received.update(payload)
        seen.set()

    reasoner._process_perception_input = capture
    response = reasoner.process_message(
        {
            "type": "notus_automatic_update",
            "content": {
                "user_input": "Hello Monday",
                "user_id": "alice",
                "understanding": {"intent": "greeting", "confidence": 0.9},
                "concepts": [{"word": "hello"}, "monday"],
                "memories": [{"role": "fact", "content": "Hello is a greeting."}],
                "memory_context": {"summary": "Found 1 stored memory"},
            },
        }
    )

    assert response["status"] == "success"
    assert seen.wait(1.0)
    assert received["user_input"] == "Hello Monday"
    assert received["user_id"] == "alice"
    assert received["understanding"]["intent"] == "greeting"
    assert received["concepts"] == ["hello", "monday"]
    assert received["memories"] == [{"role": "fact", "content": "Hello is a greeting."}]


def test_process_perception_input_accepts_direct_core_payload():
    class FakeThalamus:
        def __init__(self):
            self.lobe_handlers = {}

        def send_message(self, destination, msg_type, content=None, source="thalamus"):
            return {"status": "error", "content": {}}

    reasoner = MaximumSophisticationReasoning(thalamus=FakeThalamus())
    captured = {}

    def fake_think_about(input_data):
        captured.update(input_data)
        return {"composed_response": "ok", "theories": []}

    reasoner.think_about = fake_think_about
    reasoner._process_perception_input(
        {
            "user_input": "What is gravity?",
            "user_id": "alice",
            "understanding": {"intent": "question", "confidence": 0.8},
            "concepts": [{"word": "gravity"}, "mass"],
            "memories": [{"role": "fact", "content": "Gravity attracts masses."}],
            "memory_context": {"summary": "Found 1 stored memory"},
        }
    )

    assert captured["user_input"] == "What is gravity?"
    assert captured["user_id"] == "alice"
    assert captured["understanding"]["intent"] == "question"
    assert captured["concepts"] == ["gravity", "mass"]
    assert captured["memories"] == [{"role": "fact", "content": "Gravity attracts masses."}]


def test_build_semantic_input_uses_explicit_thinking_data_without_input_data():
    class FakeThalamus:
        def __init__(self):
            self.lobe_handlers = {}

        def send_message(self, destination, msg_type, content=None, source="thalamus"):
            return {"status": "error", "content": {}}

    reasoner = MaximumSophisticationReasoning(thalamus=FakeThalamus())

    semantic_input = reasoner._build_semantic_input(
        {"key_concepts": ["gravity", "mass"]},
        "What is gravity?",
        True,
        {"intent": "question", "confidence": 0.8},
    )

    assert semantic_input["intent"] == "question"
    assert semantic_input["concepts"][:2] == ["gravity", "mass"]


def test_prompted_core_path_still_runs_all_six_lobes_after_reasoning_fixes(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        response = systems["thalamus"].process_user_input("What is photosynthesis?")
        route_names = [route["to"] for route in systems["thalamus"].message_routes]
        prompted_path = [
            "conversation",
            "notus",
            "notus",
            "emotion",
            "reasoning",
            "language",
            "output",
        ]

        assert response
        positions = [route_names.index(stage) for stage in prompted_path]
        assert positions == sorted(positions)
        assert systems["output"].last_output == response
    finally:
        shutdown_core_systems(systems)
