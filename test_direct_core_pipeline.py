"""Deterministic E2E coverage for the prompted direct-call core path."""

import random

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


def test_all_core_lobes_support_learn_and_recall_contract(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    core_lobes = ["conversation", "notus", "emotion", "reasoning", "language", "output"]
    try:
        for lobe_name in core_lobes:
            result = systems["thalamus"].send_message(
                lobe_name,
                "learn",
                {
                    "fact": f"{lobe_name} can learn direct facts",
                    "user_id": "alice",
                },
            )
            assert result["status"] == "success"

        for lobe_name in core_lobes:
            result = systems["thalamus"].send_message(
                lobe_name,
                "recall",
                {
                    "query": "learn direct facts",
                    "user_id": "alice",
                    "limit": 5,
                },
            )
            assert result["status"] == "success"
            memories = result.get("memories", [])
            assert any(
                memory.get("content") == f"{lobe_name} can learn direct facts"
                for memory in memories
            )
    finally:
        shutdown_core_systems(systems)


def test_lobe_learning_recall_is_scoped_to_destination(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        systems["thalamus"].send_message(
            "conversation",
            "learn",
            {"fact": "SCOPE_TEST: conversation-only", "user_id": "alice"},
        )
        systems["thalamus"].send_message(
            "language",
            "learn",
            {"fact": "SCOPE_TEST: language-only", "user_id": "alice"},
        )

        conversation = systems["thalamus"].send_message(
            "conversation",
            "recall",
            {"query": "SCOPE_TEST", "user_id": "alice", "limit": 10},
        )
        language = systems["thalamus"].send_message(
            "language",
            "recall",
            {"query": "SCOPE_TEST", "user_id": "alice", "limit": 10},
        )

        assert conversation["status"] == "success"
        assert language["status"] == "success"

        conversation_memories = [m.get("content") for m in conversation.get("memories", [])]
        language_memories = [m.get("content") for m in language.get("memories", [])]

        assert "SCOPE_TEST: conversation-only" in conversation_memories
        assert "SCOPE_TEST: language-only" not in conversation_memories
        assert "SCOPE_TEST: language-only" in language_memories
        assert "SCOPE_TEST: conversation-only" not in language_memories
    finally:
        shutdown_core_systems(systems)


def test_lobe_adaptive_learning_conflict_and_reinforcement(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        first = systems["thalamus"].send_message(
            "reasoning",
            "learn",
            {
                "key": "planet_status",
                "fact": "Pluto is a planet.",
                "user_id": "alice",
                "confidence": 0.7,
            },
        )
        assert first["status"] == "success"
        assert first["action"] == "created"
        initial_confidence = first["confidence"]

        reinforced = systems["thalamus"].send_message(
            "reasoning",
            "learn",
            {
                "key": "planet_status",
                "fact": "Pluto is a planet.",
                "user_id": "alice",
                "reinforcement": 1.0,
            },
        )
        assert reinforced["status"] == "success"
        assert reinforced["action"] == "reinforced"
        assert reinforced["confidence"] > initial_confidence
        assert reinforced["evidence_count"] >= 2

        replaced = systems["thalamus"].send_message(
            "reasoning",
            "learn",
            {
                "key": "planet_status",
                "fact": "Pluto is classified as a dwarf planet.",
                "user_id": "alice",
                "confidence": 0.8,
            },
        )
        assert replaced["status"] == "success"
        assert replaced["action"] == "replaced_conflict"
        assert replaced["contradiction_count"] >= 1

        recalled = systems["thalamus"].send_message(
            "reasoning",
            "recall",
            {"query": "Pluto", "user_id": "alice", "limit": 5},
        )
        assert recalled["status"] == "success"
        assert any(
            memory.get("fact") == "Pluto is classified as a dwarf planet."
            for memory in recalled["memories"]
        )
    finally:
        shutdown_core_systems(systems)


def test_lobe_adaptive_contradict_forget_and_stats(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        systems["thalamus"].send_message(
            "emotion",
            "learn",
            {
                "key": "trigger_preference",
                "fact": "Loud noises increase stress.",
                "user_id": "alice",
                "confidence": 0.5,
            },
        )
        contradicted = systems["thalamus"].send_message(
            "emotion",
            "contradict_learning",
            {"key": "trigger_preference", "user_id": "alice", "penalty": 0.4},
        )
        assert contradicted["status"] == "success"
        assert contradicted["action"] == "contradicted"
        assert contradicted["contradiction_count"] >= 1

        forgotten = systems["thalamus"].send_message(
            "emotion",
            "forget_learning",
            {"key": "trigger_preference", "user_id": "alice"},
        )
        assert forgotten["status"] == "success"
        assert forgotten["action"] == "forgotten"

        recalled = systems["thalamus"].send_message(
            "emotion",
            "recall",
            {"query": "stress", "user_id": "alice", "limit": 10},
        )
        assert recalled["status"] == "success"
        assert all(memory.get("status") == "active" for memory in recalled["memories"])

        stats = systems["thalamus"].send_message(
            "emotion",
            "learning_stats",
            {"user_id": "alice"},
        )
        assert stats["status"] == "success"
        assert stats["total_facts"] >= 1
        assert stats["deprecated_facts"] >= 1
    finally:
        shutdown_core_systems(systems)


def test_thalamus_auto_adapts_success_and_failure_for_lobe(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        success = systems["thalamus"].send_message(
            "conversation",
            "understand",
            {"user_input": "Hello there", "user_id": "alice"},
        )
        assert success["status"] == "success"

        learned_behavior = systems["thalamus"].send_message(
            "conversation",
            "recall",
            {"query": "status success stable content", "user_id": "alice", "limit": 10},
        )
        assert learned_behavior["status"] == "success"
        assert any(
            memory.get("key") == "behavior:understand"
            for memory in learned_behavior.get("memories", [])
        )

        # Force a lobe-level failure to trigger contradiction and recovery learning.
        failure = systems["thalamus"].send_message(
            "conversation",
            "understand",
            {"user_input": 123, "user_id": "alice"},
        )
        assert failure["status"] == "error"

        behavior_after_failure = systems["thalamus"].send_message(
            "conversation",
            "recall",
            {"query": "status success stable content", "user_id": "alice", "limit": 10},
        )
        assert behavior_after_failure["status"] == "success"
        behavior_entries = [
            memory for memory in behavior_after_failure.get("memories", [])
            if memory.get("key") == "behavior:understand"
        ]
        assert behavior_entries
        assert behavior_entries[0].get("contradiction_count", 0) >= 1

        recovery = systems["thalamus"].send_message(
            "conversation",
            "recall",
            {"query": "safe non-crashing fallback", "user_id": "alice", "limit": 10},
        )
        assert recovery["status"] == "success"
        assert any(
            memory.get("key") == "recovery:understand"
            for memory in recovery.get("memories", [])
        )
    finally:
        shutdown_core_systems(systems)


def test_teach_skill_and_list_skills_for_any_lobe(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        taught = systems["thalamus"].send_message(
            "reasoning",
            "teach_skill",
            {
                "skill": "math_patterns",
                "behavior": "Detect arithmetic relationships from user text.",
                "trigger": "numbers and operators in message",
                "outcome": "return structured math pattern insight",
                "user_id": "alice",
                "confidence": 0.8,
            },
        )
        assert taught["status"] == "success"
        assert taught["key"] == "skill:math_patterns"

        listed = systems["thalamus"].send_message(
            "reasoning",
            "list_skills",
            {"user_id": "alice", "limit": 20},
        )
        assert listed["status"] == "success"
        assert any(
            memory.get("key") == "skill:math_patterns"
            for memory in listed.get("memories", [])
        )
    finally:
        shutdown_core_systems(systems)


def test_learned_skill_guidance_is_applied_to_message_envelope(tmp_path):
    class EchoLobe:
        def process_message(self, message):
            return {"status": "success", "content": {"seen": message.get("content", {})}}

        def shutdown(self):
            pass

    systems = create_core_systems(str(tmp_path / "runtime"))
    systems["thalamus"].register_lobe("echo", EchoLobe())
    try:
        taught = systems["thalamus"].send_message(
            "echo",
            "teach_skill",
            {
                "skill": "respectful_reply",
                "behavior": "Use calm, respectful wording even when the input is intense.",
                "trigger": "emotionally intense user text",
                "user_id": "alice",
                "confidence": 0.9,
            },
        )
        assert taught["status"] == "success"

        response = systems["thalamus"].send_message(
            "echo",
            "reply",
            {"user_input": "I am upset", "user_id": "alice"},
        )
        assert response["status"] == "success"
        seen = response["content"]["seen"]
        assert "learned_guidance" in seen
        assert any("Skill behavior:" in item for item in seen["learned_guidance"])
        assert seen.get("applied_learning", {}).get("count", 0) >= 1
    finally:
        shutdown_core_systems(systems)


def test_teach_monday_routes_one_lesson_to_multiple_lobes(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        result = systems["thalamus"].handle_request(
            {
                "type": "teach_monday",
                "content": {
                    "lesson": "Learn grammar and better sentence structure for clearer responses.",
                    "user_id": "alice",
                },
            }
        )
        assert result["status"] == "success"
        taught_lobes = {entry.get("lobe") for entry in result.get("taught", [])}
        assert "language" in taught_lobes
        assert "conversation" in taught_lobes
        assert len(taught_lobes) >= 2

        language_skills = systems["thalamus"].send_message(
            "language", "list_skills", {"user_id": "alice", "limit": 10}
        )
        assert language_skills["status"] == "success"
        assert language_skills["memories"]
    finally:
        shutdown_core_systems(systems)


def test_teach_monday_feedback_reaches_behavior_lobes(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        result = systems["thalamus"].handle_request(
            {
                "type": "teach_monday",
                "content": {
                    "lesson": "When tone sounds rude, respond calm, respectful, and kind instead.",
                    "user_id": "alice",
                },
            }
        )
        assert result["status"] == "success"
        taught_lobes = {entry.get("lobe") for entry in result.get("taught", [])}
        assert "language" in taught_lobes
        assert "emotion" in taught_lobes
        assert "reasoning" in taught_lobes
    finally:
        shutdown_core_systems(systems)


def test_learning_overview_shows_per_lobe_skills_and_usage(tmp_path):
    class EchoLobe:
        def process_message(self, message):
            return {"status": "success", "content": {"seen": message.get("content", {})}}

        def shutdown(self):
            pass

    systems = create_core_systems(str(tmp_path / "runtime"))
    systems["thalamus"].register_lobe("echo", EchoLobe())
    try:
        taught = systems["thalamus"].send_message(
            "echo",
            "teach_skill",
            {
                "skill": "deescalate",
                "behavior": "Use calm wording during conflict.",
                "user_id": "alice",
                "confidence": 0.9,
            },
        )
        assert taught["status"] == "success"

        used = systems["thalamus"].send_message(
            "echo",
            "reply",
            {"user_input": "I am angry", "user_id": "alice"},
        )
        assert used["status"] == "success"

        overview = systems["thalamus"].handle_request(
            {"type": "learning_overview", "content": {"user_id": "alice", "limit": 10}}
        )
        assert overview["status"] == "success"
        echo_rows = [entry for entry in overview.get("lobes", []) if entry.get("lobe") == "echo"]
        assert echo_rows
        echo_row = echo_rows[0]
        assert echo_row["stats"].get("total_facts", 0) >= 1
        assert echo_row["stats"].get("total_uses", 0) >= 1
        assert any(skill.get("key") == "skill:deescalate" for skill in echo_row.get("skills", []))
    finally:
        shutdown_core_systems(systems)
