"""Real-lobe generic experiential learning tests."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from run_abin import create_core_systems, shutdown_core_systems


def _new_token(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _assert_token_not_in_production_sources(token: str) -> None:
    root = _repo_root()
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if path.name.startswith("test_") or "/tests/" in f"/{rel}/":
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        assert token not in content


def _teach_relation(
    systems,
    *,
    user_id: str,
    token: str,
    concept: str,
    positives: list[str],
    negatives: list[str],
    event_type: str = "explicit_lesson",
):
    return systems["thalamus"].handle_request(
        {
            "type": "learn_from_experience",
            "content": {
                "event_type": event_type,
                "user_id": user_id,
                "raw_experience": f"{token} is a {concept}.",
                "examples": positives,
                "counterexamples": negatives,
                "metadata": {"relation": {"token": token, "concept": concept}},
                "confidence": 0.8,
            },
        }
    )


def test_generic_real_lobe_learning_random_tokens_generalizes_and_rejects_counterexample(tmp_path):
    runtime = tmp_path / "runtime"
    token = _new_token("tok")
    concept = _new_token("concept")
    held_out_positive = f"Now {token} appears in this completely new sentence."
    held_out_negative = f"x{token}x is a larger alphanumeric chunk, not a standalone token."

    _assert_token_not_in_production_sources(token)
    _assert_token_not_in_production_sources(concept)

    systems = create_core_systems(str(runtime))
    try:
        before_language = systems["thalamus"].send_message(
            "language", "assess_token_usage", {"user_id": "alice", "token": token, "text": held_out_positive}
        )
        before_pattern = systems["thalamus"].send_message(
            "pattern", "classify_token_pattern", {"user_id": "alice", "token": token, "text": held_out_positive}
        )
        before_generate = systems["thalamus"].send_message(
            "language",
            "generate",
            {"user_id": "alice", "user_input": held_out_positive, "semantic_input": {"intent": "state_fact"}},
        )
        before_observe = systems["thalamus"].send_message(
            "pattern", "process_input", {"user_id": "alice", "data": {"user_input": held_out_positive}}
        )
        assert before_language["content"]["known"] is False
        assert before_pattern["content"]["rule_confidence"] == 0.0
        assert before_generate["content"]["token_matches"] == []
        assert before_observe["content"]["token_rule_applied"] is False

        lesson = _teach_relation(
            systems,
            user_id="alice",
            token=token,
            concept=concept,
            positives=[
                f"{token} starts this first training sentence.",
                f"{token} starts this second training sentence.",
            ],
            negatives=[held_out_negative],
        )
        assert lesson["status"] == "success"
        assert {"language", "pattern"}.issubset(set(lesson["content"]["targets"]))
        results = {row["lobe"]: row for row in lesson["content"]["results"]}
        for lobe in ("language", "pattern"):
            assert results[lobe]["delivered"] is True
            assert results[lobe]["interpreted"] is True
            assert results[lobe]["update_proposed"] is True
            assert results[lobe]["update_accepted"] is True
            assert results[lobe]["validation_passed"] is True

        assert "relation_updates" in results["language"]["changes"]
        assert "token_rule_updates" in results["pattern"]["changes"]
        assert json.dumps(results["language"]["changes"]) != f"{token} is a {concept}."
        assert json.dumps(results["pattern"]["changes"]) != f"{token} is a {concept}."

        after_language = systems["thalamus"].send_message(
            "language", "assess_token_usage", {"user_id": "alice", "token": token, "text": held_out_positive}
        )
        after_pattern = systems["thalamus"].send_message(
            "pattern", "classify_token_pattern", {"user_id": "alice", "token": token, "text": held_out_positive}
        )
        after_generate = systems["thalamus"].send_message(
            "language",
            "generate",
            {"user_id": "alice", "user_input": held_out_positive, "semantic_input": {"intent": "state_fact"}},
        )
        after_observe = systems["thalamus"].send_message(
            "pattern", "process_input", {"user_id": "alice", "data": {"user_input": held_out_positive}}
        )
        counter_generate = systems["thalamus"].send_message(
            "language",
            "generate",
            {"user_id": "alice", "user_input": held_out_negative, "semantic_input": {"intent": "state_fact"}},
        )
        counter_observe = systems["thalamus"].send_message(
            "pattern", "process_input", {"user_id": "alice", "data": {"user_input": held_out_negative}}
        )

        assert after_language["content"]["known"] is True
        assert after_language["content"]["concept"] == concept
        assert after_language["content"]["boundary_match"] is True
        assert after_pattern["content"]["rule_confidence"] > 0.0
        assert after_generate["content"]["token_matches"]
        assert after_observe["content"]["token_rule_applied"] is True
        assert counter_generate["content"]["token_matches"] == []
        assert counter_observe["content"]["token_rule_applied"] is False
    finally:
        shutdown_core_systems(systems)

    restarted = create_core_systems(str(runtime))
    try:
        persisted = restarted["thalamus"].send_message(
            "language", "assess_token_usage", {"user_id": "alice", "token": token, "text": held_out_positive}
        )
        isolated = restarted["thalamus"].send_message(
            "language", "assess_token_usage", {"user_id": "bob", "token": token, "text": held_out_positive}
        )
        assert persisted["content"]["known"] is True
        assert isolated["content"]["known"] is False

        second_token = _new_token("tok2")
        second_concept = _new_token("concept2")
        _assert_token_not_in_production_sources(second_token)
        _assert_token_not_in_production_sources(second_concept)
        second = _teach_relation(
            restarted,
            user_id="alice",
            token=second_token,
            concept=second_concept,
            positives=[f"{second_token} is now in an unrelated lesson example."],
            negatives=[f"z{second_token}z should not match token boundaries."],
        )
        assert second["status"] == "success"
        second_assess = restarted["thalamus"].send_message(
            "language", "assess_token_usage", {"user_id": "alice", "token": second_token, "text": second_token}
        )
        assert second_assess["content"]["known"] is True
        assert second_assess["content"]["concept"] == second_concept
    finally:
        shutdown_core_systems(restarted)


def test_contradictory_evidence_can_lower_confidence_or_retire_generic_relation(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    token = _new_token("tok")
    concept = _new_token("concept")
    try:
        _teach_relation(
            systems,
            user_id="alice",
            token=token,
            concept=concept,
            positives=[f"{token} starts here."],
            negatives=[],
        )
        before = systems["thalamus"].send_message(
            "language", "get_language_learning_state", {"user_id": "alice", "token": token}
        )
        before_entry = before["content"]["concept_relations"][concept]
        before_confidence = float(before_entry["confidence"])

        _teach_relation(
            systems,
            user_id="alice",
            token=token,
            concept=concept,
            positives=[],
            negatives=[f"{token} appears but should not be treated as {concept} here."],
            event_type="correction",
        )
        after = systems["thalamus"].send_message(
            "language", "get_language_learning_state", {"user_id": "alice", "token": token}
        )
        after_entry = after["content"]["concept_relations"][concept]
        assert float(after_entry["confidence"]) < before_confidence or bool(after_entry.get("retired", False))
    finally:
        shutdown_core_systems(systems)


def test_delivery_without_interpretation_is_not_counted_as_learning_acceptance(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    token = _new_token("tok")
    try:
        result = systems["thalamus"].handle_request(
            {
                "type": "learn_from_experience",
                "content": {
                    "event_type": "explicit_lesson",
                    "user_id": "alice",
                    "raw_experience": f"{token} has no supported relation phrase in this envelope",
                    "examples": [f"{token} appears once"],
                    "counterexamples": [],
                },
            }
        )
        assert result["status"] in {"partial", "success"}
        rows = {row["lobe"]: row for row in result["content"]["results"]}
        assert rows["language"]["delivered"] is True
        assert rows["pattern"]["delivered"] is True
        assert rows["language"]["interpreted"] is False
        assert rows["pattern"]["interpreted"] is False
        assert rows["language"]["update_accepted"] is False
        assert rows["pattern"]["update_accepted"] is False
    finally:
        shutdown_core_systems(systems)
