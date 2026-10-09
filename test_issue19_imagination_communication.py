from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from autonomous_selection import THOUGHT_MODES
from autonomous_speech import AutonomousSpeechSystem
from autonomous_thinking import AutonomousThinkingLoop
from direct_notus import DirectNotusProcess
from executive_control_lobe import ExecutiveControlLobe
from run_abin import create_core_systems, shutdown_core_systems


def _notus_factory(*, thalamus: Any, runtime_directory: str) -> DirectNotusProcess:
    return DirectNotusProcess(
        storage_path=str(Path(runtime_directory) / "notus_memory.sqlite3"),
        thalamus=thalamus,
    )


def _boot(tmp_path) -> Dict[str, Any]:
    return create_core_systems(
        runtime_directory=str(tmp_path / "runtime"),
        notus_factory=_notus_factory,
        enable_autonomous=False,
    )


def test_imagination_route_is_hypothetical_transient_and_does_not_contaminate_notus(tmp_path):
    systems = _boot(tmp_path)
    try:
        thalamus = systems["thalamus"]
        assert thalamus.send_and_wait(
            "notus",
            "store",
            {"role": "user", "content": "Matthew left.", "user_id": "default"},
        )["status"] == "success"
        reasoner = systems["reasoning"].reasoner
        reasoner.causal_links.extend(
            [
                {"cause": "Matthew stayed", "effect": "They could have talked longer."},
                {"cause": "Matthew stayed", "effect": "His departure would not have occurred then."},
            ]
        )

        response = thalamus.send_and_wait(
            "reasoning",
            "imagine_what_if",
            {
                "scenario": "What if Matthew stayed?",
                "anchor_memory_id": "real-memory",
                "source_topic": "Matthew",
                "user_id": "default",
                "max_branches": 2,
                "max_depth": 2,
            },
        )
        simulation = response["simulation"]
        assert response["status"] == "success"
        assert simulation["simulation_type"] == "counterfactual"
        assert simulation["epistemic_status"] == "hypothetical"
        assert simulation["anchor_memory_id"] == "real-memory"
        assert len(simulation["branches"]) == 2
        assert simulation["proposition_ids"]
        proposition = systems["shared_representation"].get_proposition(
            simulation["proposition_ids"][0], user_id="default"
        )
        assert proposition is not None
        assert proposition.qualifiers["hypothetical"] is True
        assert proposition.qualifiers["counterfactual"] is True
        assert proposition.to_public()["storage_tier"] == "transient"

        repeated = thalamus.send_and_wait(
            "reasoning",
            "imagine_what_if",
            {
                "scenario": "What if Matthew stayed?",
                "anchor_memory_id": "real-memory",
                "user_id": "default",
            },
        )["simulation"]
        assert repeated["repetition_suppressed"] is True
        assert repeated["simulation_id"] == simulation["simulation_id"]
        memories = systems["notus"].retrieve_memories("Matthew", user_id="default")
        contents = [memory.get("content", "") for memory in memories]
        assert any("Matthew left." in content for content in contents)
        assert not any("Matthew stayed." in content for content in contents)
    finally:
        shutdown_core_systems(systems)


def test_imagination_is_an_autonomous_mode_and_returns_to_thought_stream(tmp_path):
    systems = _boot(tmp_path)
    try:
        thalamus = systems["thalamus"]
        autonomous = AutonomousThinkingLoop(thalamus=thalamus)
        topic = "mem:memory"
        autonomous._topic_select_count[topic] = 1
        assert "imagination" in THOUGHT_MODES
        assert autonomous._select_mode_for_candidate(
            {"kind": "memory", "topic_key": topic},
            {"intensity": 0.5, "unresolved_appraisals": []},
        ) == "imagination"

        result = autonomous.process_message(
            {
                "type": "imagine_what_if",
                "content": {
                    "scenario": "What if Matthew stayed?",
                    "user_id": "default",
                },
            }
        )
        assert result["status"] == "success"
        assert result["thought"]["mode"] == "imagination"
        assert result["thought"]["simulation_result"]["simulation_id"]
        assert result["continuation_options"] == ["branch", "compare", "abandon"]
        assert any(
            route["to"] == "reasoning" and route["type"] == "imagine_what_if"
            for route in thalamus.message_routes
        )
    finally:
        shutdown_core_systems(systems)


def test_hypothetical_affect_probe_is_non_mutating(tmp_path):
    systems = _boot(tmp_path)
    try:
        emotion = systems["emotion"]
        engine = emotion.engine
        before = {
            "affect": engine.core_affect.to_dict(),
            "emotion": engine.current_emotion,
            "memories": list(engine.emotional_memories),
            "mood_history": list(engine.mood_history),
            "pad": (engine.pad.v, engine.pad.a, engine.pad.d),
        }
        result = systems["thalamus"].send_and_wait(
            "emotion",
            "probe_affect",
            {"scenario": "What if Matthew stayed?", "simulation_type": "counterfactual"},
        )
        assert result["status"] == "success"
        assert result["projection"]["state_mutated"] is False
        assert engine.core_affect.to_dict() == before["affect"]
        assert engine.current_emotion == before["emotion"]
        assert engine.emotional_memories == before["memories"]
        assert engine.mood_history == before["mood_history"]
        assert (engine.pad.v, engine.pad.a, engine.pad.d) == before["pad"]
    finally:
        shutdown_core_systems(systems)


def test_executive_approves_calm_intents_and_can_keep_strong_feeling_private():
    executive = ExecutiveControlLobe()
    insight = executive.evaluate_communication_intent(
        {
            "type": "share_insight",
            "priority": 0.55,
            "thought_id": "calm-insight",
            "content": "A calm, grounded insight.",
        }
    )
    question = executive.evaluate_communication_intent(
        {
            "type": "inquire",
            "priority": 0.5,
            "thought_id": "calm-question",
            "content": "A calm question worth asking?",
        }
    )
    feeling = executive.evaluate_communication_intent(
        {
            "type": "express_feeling",
            "priority": 0.95,
            "thought_id": "strong-feeling",
            "content": "I feel strongly about this.",
        }
    )
    private = executive.evaluate_communication_intent(
        {
            "type": "express_feeling",
            "priority": 0.95,
            "thought_id": "private-feeling",
            "force_private": True,
            "content": "I feel strongly about this.",
        }
    )
    assert insight["approved"] and insight["communication_intent"]["type"] == "share_insight"
    assert question["approved"] and question["communication_intent"]["type"] == "inquire"
    assert feeling["approved"] and feeling["communication_intent"]["type"] == "express_feeling"
    assert private["approved"] is False
    assert private["communication_intent"] is None


def test_speech_waits_without_discarding_approved_intent_and_uses_priority():
    speech = AutonomousSpeechSystem(thalamus=object())
    speech.user_is_typing = True
    thought = {
        "id": "calm-insight",
        "content": "I noticed a useful connection.",
        "thought_type": "reflection",
        "intensity": 0.1,
        "communication_intent": {
            "type": "share_insight",
            "priority": 0.55,
            "requires_user": True,
            "thought_id": "calm-insight",
        },
    }
    response = speech.process_message({"type": "evaluate_thought", "thought": thought})
    decision = response["decision"]
    assert decision["should_speak"] is True
    assert decision["timing"] == "wait"
    assert speech.pending_intents[0]["thought_id"] == "calm-insight"

    speech.user_is_typing = False
    speech.min_speech_interval = 0
    thought["communication_intent"]["priority"] = 0.9
    now = speech.process_message({"type": "evaluate_thought", "thought": thought})
    assert now["decision"]["timing"] == "now"
    assert not speech.pending_intents


def test_approved_autonomous_intent_routes_through_language_and_output(tmp_path):
    systems = _boot(tmp_path)
    try:
        systems["executive_control"].clear_goal()
        systems["speech"].last_speech_time = 0
        result = systems["thalamus"].deliver_autonomous_thought(
            {
                "id": "calm-insight",
                "content": "I noticed a useful connection.",
                "thought_type": "reflection",
                "timestamp": 1,
                "communication_intent": {
                    "type": "share_insight",
                    "source": "autonomous_thinking",
                    "reason": "grounded_cognitive_result",
                    "priority": 0.95,
                    "requires_user": True,
                    "novelty": 0.7,
                    "epistemic_status": "known",
                    "thought_id": "calm-insight",
                },
            }
        )
        assert result["delivered"] is True
        assert result["text"]
        route_pairs = [
            (route.get("to"), route.get("type"))
            for route in systems["thalamus"].message_routes
        ]
        assert ("speech", "evaluate_thought") in route_pairs
        assert ("language", "generate") in route_pairs
        assert ("output", "generate_output") in route_pairs
        assert systems["output"].last_output == result["text"]
    finally:
        shutdown_core_systems(systems)
