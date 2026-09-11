"""Deterministic E2E coverage for the prompted direct-call core path."""

import json
import random
import sqlite3

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
            "conversation", "notus", "emotion", "reasoning", "pattern", "language", "output"
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
    core_lobes = ["conversation", "notus", "emotion", "reasoning", "pattern", "language", "output"]
    try:
        contracts = systems["thalamus"].handle_request({"type": "learning_contracts"})
        contract_map = contracts.get("contracts", {})
        for lobe_name in core_lobes:
            contract = contract_map.get(lobe_name, {})
            allowed = contract.get("allowed_record_types", ["fact"])
            allowed = allowed if isinstance(allowed, list) and allowed else ["fact"]
            record_type = "fact" if "fact" in allowed else allowed[0]
            mutable = contract.get("mutable_surfaces", ["behavior_rules"])
            mutable = mutable if isinstance(mutable, list) and mutable else ["behavior_rules"]
            surface = mutable[0]
            result = systems["thalamus"].send_message(
                lobe_name,
                "learn",
                {
                    "fact": f"{lobe_name} can learn direct facts",
                    "user_id": "alice",
                    "record": {"type": record_type, "subject": surface, "surface": surface},
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
        assert replaced["action"] in {"pending_conflict", "replaced_conflict"}
        assert replaced["contradiction_count"] >= 1

        recalled = systems["thalamus"].send_message(
            "reasoning",
            "recall",
            {"query": "Pluto", "user_id": "alice", "limit": 5, "include_disputed": True},
        )
        assert recalled["status"] == "success"
        assert recalled["memories"]
        assert any(memory.get("status") in {"disputed", "active", "provisional"} for memory in recalled["memories"])
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
                "record": {
                    "type": "rule",
                    "subject": "emotion_response_guidance",
                    "surface": "emotion_response_guidance",
                },
            },
        )
        contradicted = systems["thalamus"].send_message(
            "emotion",
            "contradict_learning",
            {
                "key": "trigger_preference",
                "user_id": "alice",
                "penalty": 0.4,
                "correction_fact": "Sudden loud noises increase stress unless expected.",
                "correction_evidence": [
                    "before:Loud noises increase stress.",
                    "after:Sudden loud noises increase stress unless expected.",
                    "validated:manual_review",
                ],
            },
        )
        assert contradicted["status"] == "success"
        assert contradicted["action"] == "corrected_replace"
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
        systems["thalamus"].auto_adapt_enabled = True
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
            {
                "query": "status success stable content",
                "user_id": "alice",
                "limit": 10,
                "include_disputed": True,
            },
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
        assert taught["status"] in {"success", "partial"}
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
        assert taught["status"] in {"success", "partial"}
        promoted = systems["thalamus"].send_message(
            "echo",
            "promote_learning",
            {
                "key": "skill:respectful_reply",
                "user_id": "alice",
                "evidence": ["saved", "retrieved", "applied", "behavior_changed", "validated"],
                "before_output": "default",
                "after_output": "guided",
                "expected_difference": "guided",
                "observed_difference": "guided",
                "test_input": "emotionally intense user text",
                "equivalent_inputs": ["intense user text"],
                "validator": "test",
            },
        )
        assert promoted["status"] == "success"

        response = systems["thalamus"].send_message(
            "echo",
            "reply",
            {"user_input": "emotionally intense user text", "user_id": "alice"},
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
        assert len(taught_lobes) >= 1

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
        assert "conversation" in taught_lobes
        assert "emotion" in taught_lobes
        assert "output" in taught_lobes
    finally:
        shutdown_core_systems(systems)


def test_teach_monday_returns_unresolved_target_without_modification(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        lobes = ("conversation", "reasoning", "emotion", "pattern", "language", "output")
        before = {
            lobe: systems["thalamus"].send_message(
                lobe, "learning_stats", {"user_id": "alice"}
            )
            for lobe in lobes
        }
        result = systems["thalamus"].handle_request(
            {
                "type": "teach_monday",
                "content": {
                    "lesson": "Please improve this generally.",
                    "user_id": "alice",
                },
            }
        )
        assert result["status"] == "error"
        assert result["content"]["routing_condition"] == "unresolved_target"
        assert result["content"]["targets"] == []

        after = {
            lobe: systems["thalamus"].send_message(
                lobe, "learning_stats", {"user_id": "alice"}
            )
            for lobe in lobes
        }
        for lobe in lobes:
            assert before[lobe]["status"] == "success"
            assert after[lobe]["status"] == "success"
            assert before[lobe]["total_facts"] == after[lobe]["total_facts"]
            assert before[lobe]["active_facts"] == after[lobe]["active_facts"]
    finally:
        shutdown_core_systems(systems)


def test_learn_from_experience_delivers_to_all_registered_direct_core_lobes(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        result = systems["thalamus"].handle_request(
            {
                "type": "learn_from_experience",
                "content": {
                    "event_type": "explicit_lesson",
                    "user_id": "alice",
                    "raw_experience": "When uncertain, be respectful, clear, and logically consistent.",
                    "examples": ["Use calm wording when the user is upset."],
                    "counterexamples": [],
                    "confidence": 0.8,
                },
            }
        )
        assert result["status"] in {"success", "partial"}
        rows = {row["lobe"]: row for row in result["content"]["results"]}
        expected = {"conversation", "reasoning", "pattern", "language", "emotion", "output"}
        assert set(rows.keys()) == expected
        for lobe in expected:
            assert rows[lobe]["delivered"] is True
            assert rows[lobe]["status"] != "error"
    finally:
        shutdown_core_systems(systems)


def test_learn_from_experience_routes_by_contract_capabilities(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        result = systems["thalamus"].handle_request(
            {
                "type": "learn_from_experience",
                "content": {
                    "event_type": "explicit_lesson",
                    "user_id": "alice",
                    "raw_experience": "Follow a reproducible multi-step calculation procedure.",
                    "record": {
                        "type": "procedure",
                        "subject": "heuristic_selection",
                        "surface": "heuristic_selection",
                        "status": "provisional",
                    },
                },
            }
        )
        assert result["status"] in {"success", "partial"}
        rows = {row["lobe"]: row for row in result["content"]["results"]}
        assert set(rows.keys()) == {"reasoning", "pattern", "language"}
        for lobe in ("reasoning", "pattern", "language"):
            assert rows[lobe]["delivered"] is True
    finally:
        shutdown_core_systems(systems)


def test_learn_from_experience_returns_error_when_no_contract_match(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        result = systems["thalamus"].handle_request(
            {
                "type": "learn_from_experience",
                "content": {
                    "event_type": "explicit_lesson",
                    "user_id": "alice",
                    "raw_experience": "Apply a novel memory schema.",
                    "record": {
                        "type": "schema",
                        "subject": "memory_schema",
                        "surface": "memory_schema",
                        "status": "provisional",
                    },
                },
            }
        )
        assert result["status"] == "error"
        assert result["content"]["routing_condition"] == "no_capability_match"
        assert result["content"]["targets"] == []
        assert result["content"]["results"] == []
    finally:
        shutdown_core_systems(systems)


def test_learning_contracts_are_declared_per_lobe(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        contracts = systems["thalamus"].handle_request({"type": "learning_contracts"})
        assert contracts["status"] == "success"
        declared = contracts["content"]["contracts"]
        assert set(declared.keys()) == {
            "conversation",
            "emotion",
            "reasoning",
            "pattern",
            "language",
            "output",
        }
        reasoning = contracts["content"]["contracts"]["reasoning"]
        assert reasoning["learning_enabled"] is True
        assert "rules" in reasoning["capabilities"]
        assert "message_routing" in reasoning["fixed_surfaces"]
        assert "missing_required_evidence" in reasoning["rejection_conditions"]
    finally:
        shutdown_core_systems(systems)


def test_contract_scoped_lobes_can_disable_learning_requirements(tmp_path):
    class ReadOnlyLobe:
        learning_contract = {
            "learning_enabled": False,
            "capabilities": set(),
            "allowed_record_types": set(),
        }

        def process_message(self, message):
            return {"status": "success", "content": {"observed": message.get("type")}}

        def shutdown(self):
            pass

    systems = create_core_systems(str(tmp_path / "runtime"))
    systems["thalamus"].register_lobe("readonly", ReadOnlyLobe())
    try:
        taught = systems["thalamus"].handle_request(
            {
                "type": "teach_monday",
                "content": {"lesson": "Use calm wording with users.", "user_id": "alice"},
            }
        )
        taught_lobes = {entry.get("lobe") for entry in taught.get("taught", [])}
        assert "readonly" not in taught_lobes
        direct = systems["thalamus"].send_message(
            "readonly",
            "teach_skill",
            {
                "skill": "tone",
                "behavior": "Keep responses short.",
                "user_id": "alice",
            },
        )
        assert direct["status"] == "error"
        assert direct["content"]["action"] == "contract_rejected"
        assert direct["content"]["condition"] == "learning_disabled"
    finally:
        shutdown_core_systems(systems)


def test_contract_rejects_fixed_surface_mutation_and_missing_required_evidence(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        fixed_surface = systems["thalamus"].send_message(
            "reasoning",
            "learn",
            {
                "key": "routing_change",
                "fact": "Change reasoning transport internals.",
                "record": {
                    "type": "rule",
                    "subject": "message_routing",
                    "surface": "message_routing",
                },
                "user_id": "alice",
            },
        )
        assert fixed_surface["status"] == "error"
        assert fixed_surface["content"]["condition"] == "fixed_surface_mutation"

        missing_evidence = systems["thalamus"].send_message(
            "reasoning",
            "learn",
            {
                "key": "validated_without_evidence",
                "fact": "Use reciprocal checks for arithmetic.",
                "record": {
                    "type": "rule",
                    "subject": "inference_preferences",
                    "status": "validated",
                    "evidence": ["saved"],
                },
                "user_id": "alice",
            },
        )
        assert missing_evidence["status"] == "error"
        assert missing_evidence["content"]["condition"] == "missing_required_evidence"
    finally:
        shutdown_core_systems(systems)


def test_teach_monday_assigns_destination_surface_from_contract(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        taught = systems["thalamus"].handle_request(
            {
                "type": "teach_monday",
                "content": {"lesson": "Use reciprocal checks for arithmetic.", "user_id": "alice"},
            }
        )
        assert taught["status"] in {"success", "partial"}

        reasoning = systems["thalamus"].send_message(
            "reasoning",
            "list_skills",
            {"user_id": "alice", "limit": 20},
        )
        assert reasoning["status"] == "success"
        memories = reasoning.get("memories", [])
        assert memories
        target = memories[0]
        learning_record = target.get("learning_record", {})
        assert learning_record.get("surface") in {
            "inference_preferences",
            "heuristic_selection",
        }
        assert learning_record.get("subject") == learning_record.get("surface")
    finally:
        shutdown_core_systems(systems)


def test_custom_experience_updates_are_contract_checked(tmp_path):
    class CustomExperienceLobe:
        supports_experience_learning = True
        learning_contract = {
            "learning_enabled": True,
            "allowed_record_types": {"rule"},
            "mutable_surfaces": {"custom_surface"},
            "fixed_surfaces": {"core_logic"},
            "required_evidence": {"saved", "retrieved", "applied", "behavior_changed", "validated"},
        }

        def __init__(self):
            self.called = 0

        def process_message(self, message):
            self.called += 1
            return {"status": "success", "content": {"handled": True}}

        def shutdown(self):
            pass

    systems = create_core_systems(str(tmp_path / "runtime"))
    custom = CustomExperienceLobe()
    systems["thalamus"].register_lobe("custom_experience", custom)
    try:
        rejected = systems["thalamus"].send_message(
            "custom_experience",
            "learn_from_experience",
            {
                "raw_experience": "Adopt new strategy.",
                "event_type": "explicit_lesson",
                "status": "validated",
                "evidence": ["saved"],
                "user_id": "alice",
            },
        )
        assert rejected["status"] == "error"
        assert rejected["content"]["condition"] == "missing_required_evidence"
        assert custom.called == 0
    finally:
        shutdown_core_systems(systems)


def test_contradiction_rejects_false_claim_and_applies_valid_correction(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        learned = systems["thalamus"].send_message(
            "reasoning",
            "learn",
            {
                "key": "math_fact",
                "fact": "Two plus two equals four.",
                "user_id": "alice",
                "confidence": 0.9,
            },
        )
        assert learned["status"] == "success"

        rejected = systems["thalamus"].send_message(
            "reasoning",
            "contradict_learning",
            {"key": "math_fact", "user_id": "alice", "penalty": 0.3},
        )
        assert rejected["status"] == "error"
        assert rejected["content"]["action"] == "contradiction_rejected"

        corrected = systems["thalamus"].send_message(
            "reasoning",
            "contradict_learning",
            {
                "key": "math_fact",
                "user_id": "alice",
                "penalty": 0.1,
                "correction_fact": "Two plus two equals 4.",
                "correction_evidence": [
                    "before:Two plus two equals four.",
                    "after:Two plus two equals 4.",
                    "validated:test_proof",
                ],
            },
        )
        assert corrected["status"] == "success"
        assert corrected["action"] == "corrected_replace"

        recalled = systems["thalamus"].send_message(
            "reasoning",
            "recall",
            {"query": "two plus two", "user_id": "alice", "limit": 3, "include_disputed": True},
        )
        assert recalled["status"] == "success"
        assert any(memory.get("fact") == "Two plus two equals 4." for memory in recalled["memories"])
    finally:
        shutdown_core_systems(systems)


def test_learning_event_reports_explicit_lifecycle_states(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        result = systems["thalamus"].handle_request(
            {
                "type": "learn_from_experience",
                "content": {
                    "event_type": "explicit_lesson",
                    "user_id": "alice",
                    "raw_experience": "Use calm wording for intense prompts.",
                    "examples": ["Respond respectfully when user sounds upset."],
                    "counterexamples": [],
                    "confidence": 0.8,
                },
            }
        )
        assert result["status"] in {"success", "partial"}
        status = result["content"]["delivery_status"]
        for key in (
            "delivered",
            "interpreted",
            "proposed",
            "saved",
            "retrieved",
            "applied",
            "behavior_changed",
            "validated",
        ):
            assert key in status
        baseline_changed = status["behavior_changed"]

        proof = systems["thalamus"].handle_request(
            {
                "type": "learn_from_experience",
                "content": {
                    "event_type": "explicit_lesson",
                    "user_id": "alice",
                    "raw_experience": "Use calm wording for intense prompts.",
                    "examples": ["Respond respectfully when user sounds upset."],
                    "counterexamples": [],
                    "confidence": 0.8,
                    "behavior_delta_observed": True,
                },
            }
        )
        assert proof["status"] in {"success", "partial"}
        assert proof["content"]["delivery_status"]["behavior_changed"] >= baseline_changed
        assert proof["content"]["delivery_status"]["validated"] >= status["validated"]
    finally:
        shutdown_core_systems(systems)


def test_direct_learning_does_not_promote_without_required_evidence(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        for _ in range(3):
            result = systems["thalamus"].send_message(
                "reasoning",
                "learn",
                {
                    "key": "evidence_gate",
                    "fact": "Prefer grounded reasoning with explicit support.",
                    "user_id": "alice",
                    "record": {
                        "type": "rule",
                        "subject": "inference_preferences",
                        "surface": "inference_preferences",
                    },
                },
            )
            assert result["status"] == "success"

        recalled = systems["thalamus"].send_message(
            "reasoning",
            "recall",
            {"query": "grounded reasoning", "user_id": "alice", "limit": 5},
        )
        assert recalled["status"] == "success"
        matching = [
            row for row in recalled.get("memories", [])
            if row.get("key") == "evidence_gate"
        ]
        assert matching
        assert matching[0].get("status") == "proposed"
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
        assert taught["status"] in {"success", "partial"}
        promoted = systems["thalamus"].send_message(
            "echo",
            "promote_learning",
            {
                "key": "skill:deescalate",
                "user_id": "alice",
                "evidence": ["saved", "retrieved", "applied", "behavior_changed", "validated"],
                "before_output": "default",
                "after_output": "deescalated",
                "expected_difference": "deescalated",
                "observed_difference": "deescalated",
                "test_input": "This conflict needs calm wording.",
                "equivalent_inputs": ["use calm wording during conflict"],
                "validator": "test",
            },
        )
        assert promoted["status"] == "success"

        used = systems["thalamus"].send_message(
            "echo",
            "reply",
            {"user_input": "This conflict needs calm wording.", "user_id": "alice"},
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


def test_lobe_learning_persists_across_restart_without_notus_learning_backend(tmp_path):
    runtime = tmp_path / "runtime"
    first = create_core_systems(str(runtime))
    try:
        taught = first["thalamus"].send_message(
            "reasoning",
            "teach_skill",
            {
                "skill": "fraction_math",
                "behavior": "Reduce and compare fractions correctly.",
                "user_id": "alice",
                "confidence": 0.85,
            },
        )
        assert taught["status"] in {"success", "partial"}
    finally:
        shutdown_core_systems(first)

    second = create_core_systems(str(runtime))
    try:
        recalled = second["thalamus"].send_message(
            "reasoning", "list_skills", {"user_id": "alice", "limit": 20}
        )
        assert recalled["status"] == "success"
        assert any(
            memory.get("key") == "skill:fraction_math"
            for memory in recalled.get("memories", [])
        )
    finally:
        shutdown_core_systems(second)


def test_each_lobe_uses_own_learning_file(tmp_path):
    runtime = tmp_path / "runtime"
    systems = create_core_systems(str(runtime))
    try:
        systems["thalamus"].send_message(
            "conversation",
            "teach_skill",
            {"skill": "tone_control", "behavior": "Keep responses calm.", "user_id": "alice"},
        )
        systems["thalamus"].send_message(
            "reasoning",
            "teach_skill",
            {"skill": "logic_cleanup", "behavior": "Avoid contradictions.", "user_id": "alice"},
        )

        overview = systems["thalamus"].handle_request(
            {"type": "learning_overview", "content": {"user_id": "alice"}}
        )
        assert overview["status"] == "success"
        rows = {row["lobe"]: row for row in overview.get("lobes", [])}
        conversation_path = rows["conversation"]["stats"].get("storage_path", "")
        reasoning_path = rows["reasoning"]["stats"].get("storage_path", "")
        assert conversation_path and reasoning_path
        assert conversation_path != reasoning_path
        assert conversation_path.endswith("conversation.json")
        assert reasoning_path.endswith("reasoning.json")
        assert str(runtime) in conversation_path
        assert str(runtime) in reasoning_path
    finally:
        shutdown_core_systems(systems)


def test_domain_neutral_production_learning_unknown_info_then_correction(tmp_path):
    runtime = tmp_path / "runtime"
    concept = f"neutralconcept{random.randint(10000, 99999)}"
    initial_fact = f"{concept} means a silent triad marker."
    corrected_fact = f"{concept} means a rotating checksum marker."

    first = create_core_systems(str(runtime))
    try:
        baseline = first["thalamus"].process_user_input(
            f"What is {concept}?", user_id="alice"
        )
        assert "do not have enough grounded information" in baseline.lower()
        assert "silent triad marker" not in baseline.lower()
        assert "rotating checksum marker" not in baseline.lower()

        lifecycle = first["thalamus"].handle_request(
            {
                "type": "learn_from_experience",
                "content": {
                    "event_type": "explicit_lesson",
                    "user_id": "alice",
                    "raw_experience": f"{concept} is newly defined information.",
                },
            }
        )
        assert lifecycle["status"] in {"success", "partial"}
        assert lifecycle["content"]["delivery_status"]["behavior_changed"] == 0
        assert lifecycle["content"]["delivery_status"]["validated"] == 0

        taught = first["thalamus"].handle_request(
            {
                "type": "teach_monday",
                "content": {
                    "lesson": initial_fact,
                    "user_id": "alice",
                    "target_lobes": ["reasoning"],
                },
            }
        )
        assert taught["status"] == "success"
        reasoning_taught = [
            entry for entry in taught.get("taught", [])
            if entry.get("lobe") == "reasoning" and isinstance(entry.get("key"), str)
        ]
        assert reasoning_taught
        reasoning_key = reasoning_taught[0]["key"]

        learned_answer = first["thalamus"].process_user_input(
            f"Explain the meaning of {concept}.", user_id="alice"
        )
        assert "silent triad marker" in learned_answer.lower()
        assert "rotating checksum marker" not in learned_answer.lower()

        first_reasoning_key = reasoning_key
    finally:
        shutdown_core_systems(first)

    second = create_core_systems(str(runtime))
    try:
        persisted_after_teach = second["thalamus"].process_user_input(
            f"Define {concept}.",
            user_id="alice",
        )
        assert "silent triad marker" in persisted_after_teach.lower()
        assert "rotating checksum marker" not in persisted_after_teach.lower()
        recalled_before_correction = second["thalamus"].send_message(
            "reasoning",
            "recall",
            {"query": concept, "user_id": "alice", "limit": 10, "include_disputed": True},
        )
        assert recalled_before_correction["status"] == "success"
        matching_before = [
            memory for memory in recalled_before_correction.get("memories", [])
            if memory.get("key") == first_reasoning_key and isinstance(memory.get("fact"), str)
        ]
        assert matching_before
        before_fact = matching_before[0]["fact"]

        corrected = second["thalamus"].send_message(
            "reasoning",
            "contradict_learning",
            {
                "key": first_reasoning_key,
                "user_id": "alice",
                "penalty": 0.2,
                "correction_fact": corrected_fact,
                "correction_evidence": [
                    f"before:{before_fact}",
                    f"after:{corrected_fact}",
                    "validated:domain_neutral_production_test",
                ],
            },
        )
        assert corrected["status"] == "success"
        assert corrected["action"] == "corrected_replace"
        promoted = second["thalamus"].send_message(
            "reasoning",
            "promote_learning",
            {
                "key": first_reasoning_key,
                "user_id": "alice",
                "evidence": [
                    "saved",
                    "retrieved",
                    "applied",
                    "behavior_changed",
                    "validated",
                    f"before_output:{before_fact}",
                    f"after_output:{corrected_fact}",
                ],
                "before_output": before_fact,
                "after_output": corrected_fact,
                "expected_difference": corrected_fact,
                "observed_difference": corrected_fact,
                "test_input": f"What is {concept}?",
                "equivalent_inputs": [f"Under equivalent wording, what does {concept} mean?"],
                "validator": "test_domain_neutral",
            },
        )
        assert promoted["status"] == "success"

        corrected_answer = second["thalamus"].process_user_input(
            f"Under equivalent wording, what does {concept} mean?",
            user_id="alice",
        )
        assert "rotating checksum marker" in corrected_answer.lower()
        assert "silent triad marker" not in corrected_answer.lower()
    finally:
        shutdown_core_systems(second)

    third = create_core_systems(str(runtime))
    try:
        corrected_after_restart = third["thalamus"].process_user_input(
            f"Define {concept}.",
            user_id="alice",
        )
        assert "rotating checksum marker" in corrected_after_restart.lower()
        assert "silent triad marker" not in corrected_after_restart.lower()
    finally:
        shutdown_core_systems(third)


def test_production_lobes_consume_learned_guidance(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        for lobe in ("conversation", "reasoning", "language"):
            taught = systems["thalamus"].send_message(
                lobe,
                "teach_skill",
                {
                    "skill": f"{lobe}_guidance",
                    "behavior": "Use respectful calm wording when responding to upset users.",
                    "user_id": "alice",
                    "confidence": 0.9,
                },
            )
            assert taught["status"] == "success"
            promoted = systems["thalamus"].send_message(
                lobe,
                "promote_learning",
                {
                    "key": f"skill:{lobe}_guidance",
                    "user_id": "alice",
                    "evidence": ["saved", "retrieved", "applied", "behavior_changed", "validated"],
                    "before_output": "default",
                    "after_output": "guided",
                    "expected_difference": "guided",
                    "observed_difference": "guided",
                    "test_input": "Please use respectful calm wording now.",
                    "equivalent_inputs": ["use respectful calm wording"],
                    "validator": "test",
                },
            )
            assert promoted["status"] == "success"

        conversation = systems["thalamus"].send_message(
            "conversation",
            "understand",
            {"user_input": "Please use respectful calm wording now.", "user_id": "alice"},
        )
        assert conversation["status"] == "success"
        assert conversation["content"]["learned_guidance_used"] is True

        reasoning = systems["thalamus"].send_message(
            "reasoning",
            "think",
            {
                "user_input": "Please use respectful calm wording now.",
                "user_id": "alice",
                "input": {
                    "user_input": "Please use respectful calm wording now.",
                    "user_id": "alice",
                    "understanding": {},
                    "memory_context": {"memories": []},
                    "emotion_result": {},
                },
            },
        )
        assert reasoning["status"] == "success"
        assert reasoning["content"]["learned_guidance_used"] is True

        language = systems["thalamus"].send_message(
            "language",
            "generate",
            {
                "semantic_input": {"intent": "state_fact"},
                "user_input": "Please use respectful calm wording now.",
                "user_id": "alice",
            },
        )
        assert language["status"] == "success"
        assert language["learned_guidance_used"] is True
    finally:
        shutdown_core_systems(systems)


def test_process_user_input_scopes_learning_to_actual_user(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        systems["thalamus"].auto_adapt_enabled = True
        systems["thalamus"].process_user_input(
            "Please answer with respectful calm wording.", user_id="alice"
        )

        expected_key = {
            "emotion": "behavior:process_input",
            "reasoning": "behavior:think",
            "language": "behavior:generate",
        }
        for lobe, key in expected_key.items():
            alice_recall = systems["thalamus"].send_message(
                lobe, "recall", {"user_id": "alice", "query": key, "limit": 10}
            )
            default_recall = systems["thalamus"].send_message(
                lobe, "recall", {"user_id": "default", "query": key, "limit": 10}
            )
            assert alice_recall["status"] == "success"
            assert default_recall["status"] == "success"
            assert any(memory.get("key") == key for memory in alice_recall.get("memories", []))
            assert not any(memory.get("key") == key for memory in default_recall.get("memories", []))
    finally:
        shutdown_core_systems(systems)


def test_real_production_arithmetic_learning_correction_and_isolation(tmp_path):
    runtime_a = tmp_path / "runtime_a"
    runtime_b = tmp_path / "runtime_b"
    question_before = "What is two plus two?"
    question_after = "If I have two objects and receive two more, how many do I have?"
    question_restart = "If there are two things and I add two things, how many total?"
    unrelated_question = "How are you?"

    first = create_core_systems(str(runtime_a))
    try:
        before_output = first["thalamus"].process_user_input(question_before, user_id="alice")
        assert "4" not in before_output

        unrelated_lobes = ("conversation", "emotion", "pattern", "language", "output")
        before_stats = {
            lobe: first["thalamus"].send_message(lobe, "learning_stats", {"user_id": "alice"})
            for lobe in unrelated_lobes
        }

        taught = first["thalamus"].handle_request(
            {
                "type": "teach_monday",
                "content": {
                    "lesson": "2 + 2 = 4",
                    "user_id": "alice",
                },
            }
        )
        assert taught["status"] == "success"
        assert taught["targets"] == ["reasoning"]
        assert taught["targeted"] == [{"lobe": "reasoning", "reasons": ["arithmetic_relevance_match"]}]
        rejected_lobes = {entry["lobe"] for entry in taught.get("rejected", [])}
        assert {"conversation", "pattern", "language"}.issubset(rejected_lobes)

        after_output = first["thalamus"].process_user_input(question_after, user_id="alice")
        assert after_output.strip() == "4"
        unrelated_output = first["thalamus"].process_user_input(unrelated_question, user_id="alice")
        assert "4" not in unrelated_output

        bob_output = first["thalamus"].process_user_input(question_after, user_id="bob")
        assert bob_output.strip() != "4"

        after_stats = {
            lobe: first["thalamus"].send_message(lobe, "learning_stats", {"user_id": "alice"})
            for lobe in unrelated_lobes
        }
        for lobe in unrelated_lobes:
            assert before_stats[lobe]["status"] == "success"
            assert after_stats[lobe]["status"] == "success"
            assert before_stats[lobe]["total_facts"] == after_stats[lobe]["total_facts"]
            assert before_stats[lobe]["active_facts"] == after_stats[lobe]["active_facts"]

        reasoning_rows = first["thalamus"].send_message(
            "reasoning",
            "recall",
            {"user_id": "alice", "query": "2 + 2 = 4", "include_disputed": True, "include_deprecated": True, "limit": 10},
        )
        assert reasoning_rows["status"] == "success"
        matching = [row for row in reasoning_rows.get("memories", []) if "2 + 2 = 4" in str(row.get("fact", ""))]
        assert matching
        learned_key = matching[0]["key"]

        correction = first["thalamus"].send_message(
            "reasoning",
            "contradict_learning",
            {
                "user_id": "alice",
                "key": learned_key,
                "penalty": 0.1,
                "correction_fact": "2 + 2 = 5",
                "correction_evidence": [
                    "before:2 + 2 = 4",
                    "after:2 + 2 = 5",
                    "validated:test_real_production_arithmetic_learning_correction_and_isolation",
                ],
            },
        )
        assert correction["status"] == "success"
        assert correction["action"] == "corrected_replace"

        promoted = first["thalamus"].send_message(
            "reasoning",
            "promote_learning",
            {
                "user_id": "alice",
                "key": learned_key,
                "evidence": ["saved", "retrieved", "applied", "behavior_changed", "validated"],
                "before_output": "4",
                "after_output": "5",
                "expected_difference": "5",
                "observed_difference": "5",
                "test_input": question_after,
                "equivalent_inputs": [question_restart],
                "validator": "test_real_production_arithmetic_learning_correction_and_isolation",
            },
        )
        assert promoted["status"] == "success"

        corrected_output = first["thalamus"].process_user_input(question_after, user_id="alice")
        assert corrected_output.strip() == "5"
        still_unrelated = first["thalamus"].process_user_input(unrelated_question, user_id="alice")
        assert "5" not in still_unrelated

        post_correction = first["thalamus"].send_message(
            "reasoning",
            "recall",
            {"user_id": "alice", "query": "2 + 2", "include_disputed": True, "include_deprecated": True, "limit": 10},
        )
        assert post_correction["status"] == "success"
        current = [row for row in post_correction.get("memories", []) if row.get("key") == learned_key]
        assert current
        history = current[0].get("history", [])
        assert any(
            isinstance(entry, dict)
            and entry.get("status") == "superseded"
            and entry.get("fact") == "2 + 2 = 4"
            and entry.get("replaced_by") == "2 + 2 = 5"
            for entry in history
        )

        db = sqlite3.connect(runtime_a / "notus_memory.sqlite3")
        try:
            cursor = db.cursor()
            cursor.execute(
                "SELECT content FROM memories WHERE user_id = ? AND role = ? AND memory_type = ? ORDER BY id DESC LIMIT 1",
                ("alice", "note", "learning_event"),
            )
            row = cursor.fetchone()
            assert row is not None
            event_payload = json.loads(row[0])
            assert event_payload.get("raw_experience") == "2 + 2 = 4"
            cursor.execute("SELECT COUNT(*) FROM lobe_learning WHERE user_id = ?", ("alice",))
            lobe_learning_rows = cursor.fetchone()[0]
            assert lobe_learning_rows == 0
        finally:
            db.close()
    finally:
        shutdown_core_systems(first)

    restarted = create_core_systems(str(runtime_a))
    try:
        restart_output = restarted["thalamus"].process_user_input(question_restart, user_id="alice")
        assert restart_output.strip() == "5"
    finally:
        shutdown_core_systems(restarted)

    fresh_runtime = create_core_systems(str(runtime_b))
    try:
        cross_runtime_output = fresh_runtime["thalamus"].process_user_input(question_restart, user_id="alice")
        assert cross_runtime_output.strip() != "5"
    finally:
        shutdown_core_systems(fresh_runtime)
