"""Regression coverage for Reasoning-owned imagination and Executive intents."""

from __future__ import annotations

import sys
from pathlib import Path

from autonomous_selection import THOUGHT_MODES
from autonomous_speech import AutonomousSpeechSystem
from autonomous_thinking import AutonomousThought, AutonomousThinkingLoop
from direct_notus import DirectNotusProcess
from executive_control_lobe import ExecutiveControlLobe
from run_abin import create_core_systems, shutdown_core_systems


def _sqlite_notus_factory(*, thalamus, runtime_directory):
    return DirectNotusProcess(
        storage_path=str(Path(runtime_directory) / "notus.sqlite3"),
        thalamus=thalamus,
    )


def _boot(tmp_path):
    return create_core_systems(
        runtime_directory=str(tmp_path / "runtime"),
        notus_factory=_sqlite_notus_factory,
        enable_autonomous=False,
    )


def test_reasoning_adapter_simulates_without_notus_contamination(tmp_path):
    systems = _boot(tmp_path)
    try:
        thalamus = systems["thalamus"]
        stored = thalamus.send_and_wait(
            "notus",
            "store",
            {"role": "user", "content": "Matthew left.", "user_id": "alice"},
        )
        assert stored["status"] == "success"
        store_route_count = sum(
            route["to"] == "notus" and route["type"] == "store"
            for route in thalamus.message_routes
        )
        systems["reasoning"].reasoner.causal_links.append(
            {"cause": "Matthew stayed", "effect": "They had more time together"}
        )

        before = systems["emotion"].engine.core_affect.to_dict()
        response = thalamus.send_and_wait(
            "reasoning",
            "imagine_what_if",
            {
                "scenario": "What if Matthew stayed?",
                "anchor_memory_id": "memory-anchor",
                "source_topic": "matthew-left",
                "user_id": "alice",
            },
        )
        after = systems["emotion"].engine.core_affect.to_dict()
        simulation = response.get("simulation") or response["content"]

        adapter_result = systems["reasoning"].imagine_what_if(
            "What if Matthew returned?", user_id="alice"
        )
        assert adapter_result["simulation_id"]
        assert response["status"] == "success"
        assert simulation["simulation_id"]
        assert simulation["simulation_type"] == "counterfactual"
        assert simulation["epistemic_status"] == "counterfactual"
        assert simulation["branches"]
        assert len(simulation["branches"]) > 1
        assert len(simulation["branches"]) <= simulation["branch_limit"]
        assert max(branch["depth"] for branch in simulation["branches"]) <= simulation["depth_limit"]
        assert simulation["proposition_ids"]
        assert before == after
        assert simulation["affect_projection"]["state_before"] == before
        assert simulation["affect_projection"]["state_after"] == after
        for proposition_id in simulation["proposition_ids"]:
            proposition = systems["shared_representation"].get_proposition(proposition_id)
            assert proposition is not None
            assert proposition.provenance.source_type == "counterfactual"
            assert proposition.qualifiers["hypothetical"] is True
            assert proposition.qualifiers["observed"] is False

        memories = systems["notus"].retrieve_memories("Matthew", user_id="alice")
        contents = [memory.get("content", "") for memory in memories]
        assert "Matthew left." in contents
        assert "Matthew stayed." not in contents
        assert sum(
            route["to"] == "notus" and route["type"] == "store"
            for route in thalamus.message_routes
        ) == store_route_count
    finally:
        shutdown_core_systems(systems)


def test_imagination_is_first_class_without_wordnet_and_repetition_is_satiated(
    tmp_path, monkeypatch
):
    systems = _boot(tmp_path)
    autonomous = AutonomousThinkingLoop(thalamus=systems["thalamus"])
    try:
        monkeypatch.setitem(sys.modules, "wn", None)
        assert "imagination" in THOUGHT_MODES
        payload = {"scenario": "What if the quiet lasted longer?", "user_id": "default"}
        first = autonomous.process_message({"type": "imagine_what_if", **payload})
        second = autonomous.process_message({"type": "imagine_what_if", **payload})
        assert first["simulation"]["status"] == "complete"
        assert first["thought"]["mode"] == "imagination"
        assert first["thought"]["simulation_result"]["simulation_id"]
        assert first["thought"]["communication_intent"]["type"] == "share_insight"
        assert second["simulation"]["status"] == "suppressed"
        assert second["thought"] is None
    finally:
        autonomous.shutdown()
        shutdown_core_systems(systems)


def test_executive_approves_or_rejects_without_emotion_as_gate():
    executive = ExecutiveControlLobe()
    calm_insight = executive.evaluate_communication_intent(
        {"type": "share_insight", "priority": 0.48, "novelty": 0.6}
    )
    calm_question = executive.evaluate_communication_intent(
        {"type": "inquire", "priority": 0.48, "novelty": 0.6, "requires_user": True}
    )
    strong_feeling = executive.evaluate_communication_intent(
        {"type": "express_feeling", "priority": 0.92, "novelty": 0.6}
    )
    private_feeling = executive.evaluate_communication_intent(
        {
            "type": "express_feeling",
            "priority": 0.92,
            "novelty": 0.6,
            "force_private": True,
        }
    )
    chatter = executive.evaluate_communication_intent(
        {"type": "social_initiation", "priority": 0.1, "novelty": 0.2}
    )
    executive.set_goal("social", priority=0.55)
    lowered = executive.evaluate_communication_intent(
        {"type": "express_feeling", "priority": 0.9, "novelty": 0.6}
    )

    assert calm_insight["intent"]["type"] == "share_insight"
    assert calm_question["decision"] == "request_user_input"
    assert strong_feeling["intent"]["type"] == "express_feeling"
    assert private_feeling["decision"] == "rejected"
    assert chatter["decision"] == "rejected"
    assert lowered["decision"] == "lowered"
    assert lowered["intent"]["priority"] == 0.6


def test_thought_intent_mirror_and_speech_wait_preserve_pending_intent(tmp_path):
    systems = _boot(tmp_path)
    autonomous = AutonomousThinkingLoop(thalamus=systems["thalamus"])
    try:
        thought = AutonomousThought(
            id="calm-insight",
            content="I noticed a new connection in that pattern.",
            thought_type="reflection",
            trigger="test",
            intensity=0.2,
            speak_worthy=True,
            timestamp=1.0,
            communication_intent={
                "type": "share_insight",
                "source": "executive_control",
                "priority": 0.9,
                "novelty": 0.7,
                "requires_user": False,
                "epistemic_status": "grounded",
                "thought_id": "calm-insight",
            },
        )
        autonomous._accept_thought(thought)
        systems["speech"].user_is_busy = True
        result = systems["thalamus"].deliver_unprompted_speech()
        assert result["spoke"] is False
        assert result["decision"]["timing"] == "wait"
        assert result["intent_pending"] is True
        pending = autonomous.process_message({"type": "peek_communication_intent"})
        assert pending["thought"]["communication_intent"]["type"] == "share_insight"
    finally:
        autonomous.shutdown()
        shutdown_core_systems(systems)


def test_emotionally_neutral_thought_can_get_intent_and_speech_uses_priority():
    executive = ExecutiveControlLobe()
    loop = object.__new__(AutonomousThinkingLoop)
    loop.thalamus = None
    loop.current_goal = None
    loop.user_present = True
    loop.last_user_text = ""
    loop.current_conversation_topic = ""
    loop._speak_satiation = {}
    loop._speak_sat_updated = {}
    loop._topic_reactivated_at = {}
    loop._topic_select_count = {}
    loop._SPEAK_SAT_DECAY_HALFLIFE = 300.0
    loop._SPEAK_COOLDOWN_SEC = 120.0
    # Use a direct Executive response while exercising Autonomous Thinking's proposal.
    class Router:
        def send_and_wait(self, _lobe, _msg, content, **_kwargs):
            return executive.process_message(
                {"type": "evaluate_communication_intent", "content": content}
            )
    loop.thalamus = Router()
    allowed, _, intent = loop._evaluate_speak_worthy(
        thought_type="question",
        mode="uncertainty",
        topic_key="topic:calm-question",
        content="What else could explain this?",
        emotional_state={"emotion": "neutral", "intensity": 0.1},
        candidate={"weight": 0.7},
        user_text="",
        thought_id="calm-question",
    )
    assert allowed is True
    assert intent["type"] == "inquire"
    assert intent["requires_user"] is True

    speech = AutonomousSpeechSystem(thalamus=object())
    speech.last_speech_time = 0.0
    decision = speech._evaluate_thought(
        {
            "thought": {
                "id": "calm-question",
                "content": "What else could explain this?",
                "thought_type": "question",
                "intensity": 0.1,
                "communication_intent": intent,
            }
        }
    )["decision"]
    assert decision["priority"] == intent["priority"]
    assert decision["intent_type"] == "inquire"
    assert decision["timing"] == "wait"


def test_approved_unprompted_intent_flows_through_language_and_output(tmp_path):
    systems = _boot(tmp_path)
    autonomous = AutonomousThinkingLoop(thalamus=systems["thalamus"])
    try:
        intent_result = systems["executive_control"].evaluate_communication_intent(
            {
                "type": "report_discovery",
                "source": "autonomous_thinking",
                "reason": "new grounded pattern",
                "priority": 0.9,
                "novelty": 0.8,
                "epistemic_status": "grounded",
                "thought_id": "discovery",
            }
        )
        thought = AutonomousThought(
            id="discovery",
            content="I found a new connection between those ideas.",
            thought_type="reflection",
            trigger="pattern",
            intensity=0.1,
            speak_worthy=True,
            timestamp=1.0,
            communication_intent=intent_result["intent"],
        )
        autonomous._accept_thought(thought)
        result = systems["thalamus"].deliver_unprompted_speech()

        assert result["spoke"] is True
        assert "new connection" in result["text"]
        routes = [(item["to"], item["type"]) for item in systems["thalamus"].message_routes]
        assert ("speech", "evaluate_thought") in routes
        assert ("language", "generate") in routes
        assert ("output", "generate_output") in routes
        assert not autonomous.thought_queue
    finally:
        autonomous.shutdown()
        shutdown_core_systems(systems)
