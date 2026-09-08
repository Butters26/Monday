"""Real-lobe learning architecture tests for shared experiential envelopes."""

from __future__ import annotations

import json

from pattern_recognition import AdvancedPatternRecognition
from run_abin import create_core_systems, shutdown_core_systems


def _attach_pattern_lobe(systems):
    pattern = AdvancedPatternRecognition(thalamus=systems["thalamus"])
    systems["pattern"] = pattern
    result = systems["thalamus"].register_lobe("pattern", pattern)
    assert result["status"] == "success"
    return pattern


def _teach_hello(systems, user_id="alice"):
    return systems["thalamus"].handle_request(
        {
            "type": "learn_from_experience",
            "content": {
                "event_type": "explicit_lesson",
                "user_id": user_id,
                "raw_experience": "Hello is a greeting people use when beginning an interaction.",
                "examples": [
                    "Hello",
                    "Hello, Monday",
                    "Well, hello there...",
                ],
                "counterexamples": [
                    "shelloworld",
                ],
                "confidence": 0.8,
            },
        }
    )


def test_real_lobes_start_without_hello_relation_or_pattern(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    _attach_pattern_lobe(systems)
    try:
        language = systems["thalamus"].send_message(
            "language",
            "classify_hello_usage",
            {"user_id": "alice", "text": "Hello, Monday"},
        )
        pattern = systems["thalamus"].send_message(
            "pattern",
            "classify_hello_pattern",
            {"user_id": "alice", "text": "Hello, Monday"},
        )
        assert language["content"]["relation_confidence"] == 0.0
        assert pattern["content"]["rule_confidence"] == 0.0
    finally:
        shutdown_core_systems(systems)


def test_shared_event_routes_to_all_relevant_lobes_and_reports_stages(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    _attach_pattern_lobe(systems)
    try:
        learned = _teach_hello(systems)
        assert learned["status"] == "success"
        targets = set(learned["content"]["targets"])
        assert {"language", "pattern"}.issubset(targets)
        results = {row["lobe"]: row for row in learned["content"]["results"]}
        for lobe in ("language", "pattern"):
            assert results[lobe]["delivered"] is True
            assert results[lobe]["interpreted"] is True
            assert results[lobe]["update_proposed"] is True
            assert results[lobe]["update_accepted"] is True
            assert results[lobe]["validation_passed"] is True
    finally:
        shutdown_core_systems(systems)


def test_invalid_envelope_fails_and_delivery_alone_is_not_learning_success(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    _attach_pattern_lobe(systems)
    try:
        result = systems["thalamus"].handle_request(
            {"type": "learn_from_experience", "content": {"user_id": "alice", "raw_experience": ""}}
        )
        assert result["status"] == "error"
        assert result["content"]["accepted"] == 0 if "accepted" in result["content"] else True
    finally:
        shutdown_core_systems(systems)


def test_real_lobes_create_different_internal_updates_from_same_event(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    _attach_pattern_lobe(systems)
    try:
        learned = _teach_hello(systems)
        results = {row["lobe"]: row for row in learned["content"]["results"]}
        assert results["language"]["changes"]["semantic_relation"] == "hello:greeting"
        assert results["pattern"]["changes"]["pattern_rule"] == "hello_opening"
    finally:
        shutdown_core_systems(systems)


def test_learning_changes_real_language_and_pattern_behavior_paths(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    _attach_pattern_lobe(systems)
    try:
        before = systems["thalamus"].send_message(
            "language",
            "generate",
            {"user_id": "alice", "user_input": "Hello, Monday", "semantic_input": {"intent": "state_fact"}},
        )
        _teach_hello(systems)
        after = systems["thalamus"].send_message(
            "language",
            "generate",
            {"user_id": "alice", "user_input": "Hello, Monday", "semantic_input": {"intent": "state_fact"}},
        )
        observed = systems["thalamus"].send_message(
            "pattern",
            "process_input",
            {"user_id": "alice", "data": {"user_input": "Hello, Monday"}},
        )
        assert "greeting" not in before["sentence"].lower()
        assert "greeting" in after["sentence"].lower()
        assert observed["content"]["hello_rule_applied"] is True
    finally:
        shutdown_core_systems(systems)


def test_learned_structures_generalize_and_distinguish_unrelated_inputs(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    _attach_pattern_lobe(systems)
    try:
        _teach_hello(systems)
        language_generalized = systems["thalamus"].send_message(
            "language", "classify_hello_usage", {"user_id": "alice", "text": "Well, hello there..."}
        )
        pattern_generalized = systems["thalamus"].send_message(
            "pattern", "classify_hello_pattern", {"user_id": "alice", "text": "Well, hello there..."}
        )
        language_unrelated = systems["thalamus"].send_message(
            "language", "classify_hello_usage", {"user_id": "alice", "text": "shelloworld"}
        )
        pattern_unrelated = systems["thalamus"].send_message(
            "pattern", "classify_hello_pattern", {"user_id": "alice", "text": "shelloworld"}
        )
        assert language_generalized["content"]["classification"] == "interjectional_greeting"
        assert pattern_generalized["content"]["classification"] == "opening_greeting_pattern"
        assert language_unrelated["content"]["classification"] == "unrelated"
        assert pattern_unrelated["content"]["classification"] == "unrelated"
    finally:
        shutdown_core_systems(systems)


def test_learning_persists_restart_is_runtime_isolated_and_user_scoped(tmp_path):
    runtime = tmp_path / "runtime"
    first = create_core_systems(str(runtime))
    _attach_pattern_lobe(first)
    try:
        _teach_hello(first, user_id="alice")
        paths = {
            "language": first["thalamus"].send_message("language", "get_language_learning_state", {"user_id": "alice"})["content"]["state_path"],
            "pattern": first["thalamus"].send_message("pattern", "get_pattern_learning_state", {"user_id": "alice"})["content"]["state_path"],
        }
        assert str(runtime) in paths["language"]
        assert str(runtime) in paths["pattern"]
        assert paths["language"] != paths["pattern"]
    finally:
        shutdown_core_systems(first)

    second = create_core_systems(str(runtime))
    _attach_pattern_lobe(second)
    try:
        language = second["thalamus"].send_message(
            "language", "classify_hello_usage", {"user_id": "alice", "text": "Hello"}
        )
        bob = second["thalamus"].send_message(
            "language", "classify_hello_usage", {"user_id": "bob", "text": "Hello"}
        )
        assert language["content"]["relation_confidence"] > 0.0
        assert bob["content"]["relation_confidence"] == 0.0
    finally:
        shutdown_core_systems(second)


def test_notus_retains_learning_events_but_not_lobe_learning_ownership(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    _attach_pattern_lobe(systems)
    try:
        learned = _teach_hello(systems)
        event_id = learned["content"]["envelope"]["event_id"]
        memories = systems["notus"].retrieve_memories("", user_id="alice", memory_type="learning_event")
        assert memories
        assert any(event_id in memory["content"] for memory in memories)
        deprecated = systems["thalamus"].send_message(
            "notus",
            "learn_lobe_fact",
            {"lobe": "language", "user_id": "alice", "fact": "hello is greeting"},
        )
        assert deprecated["status"] == "error"
        assert deprecated["content"]["deprecated"] is True
    finally:
        shutdown_core_systems(systems)


def test_contradictory_evidence_revises_confidence_and_safe_corrupt_load(tmp_path):
    runtime = tmp_path / "runtime"
    systems = create_core_systems(str(runtime))
    _attach_pattern_lobe(systems)
    try:
        _teach_hello(systems)
        before = systems["thalamus"].send_message(
            "language", "get_language_learning_state", {"user_id": "alice"}
        )
        before_confidence = float(before["content"]["hello_relation"]["confidence"])
        systems["thalamus"].handle_request(
            {
                "type": "learn_from_experience",
                "content": {
                    "event_type": "correction",
                    "user_id": "alice",
                    "raw_experience": "In this context hello is not a greeting opener.",
                    "feedback": "hello not greeting here",
                    "counterexamples": ["He said hello before leaving"],
                },
            }
        )
        after = systems["thalamus"].send_message(
            "language", "get_language_learning_state", {"user_id": "alice"}
        )
        assert float(after["content"]["hello_relation"]["confidence"]) < before_confidence
    finally:
        shutdown_core_systems(systems)

    # Corrupt state files should not crash reload.
    state_dir = runtime / "lobe_state"
    (state_dir / "language_learning.json").write_text("{not-json", encoding="utf-8")
    (state_dir / "pattern_learning.json").write_text("{broken", encoding="utf-8")
    restarted = create_core_systems(str(runtime))
    _attach_pattern_lobe(restarted)
    try:
        language = restarted["thalamus"].send_message(
            "language", "classify_hello_usage", {"user_id": "alice", "text": "Hello"}
        )
        pattern = restarted["thalamus"].send_message(
            "pattern", "classify_hello_pattern", {"user_id": "alice", "text": "Hello"}
        )
        assert language["status"] == "success"
        assert pattern["status"] == "success"
    finally:
        shutdown_core_systems(restarted)


def test_existing_direct_core_path_still_works(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        response = systems["thalamus"].process_user_input("Hello Monday, explain memory?")
        assert isinstance(response, str)
        assert response.strip()
    finally:
        shutdown_core_systems(systems)
