from __future__ import annotations

import inspect
import json
from pathlib import Path

from conversation import ConversationSystem
from direct_reasoning import DirectReasoningAdapter
from language_generation import LanguageGenerator
from shared_representation import SharedRepresentationSystem
from thalamus import Thalamus


class NoRawTextSharedRepresentation(SharedRepresentationSystem):
    def process_message(self, message):
        if message.get("type") == "resolve_from_text":
            raise AssertionError("Thalamus must never ask SR to interpret raw text")
        return super().process_message(message)


def _stack(tmp_path):
    thalamus = Thalamus()
    shared = NoRawTextSharedRepresentation(
        thalamus=thalamus, store_path=tmp_path / "shared.json"
    )
    language = LanguageGenerator(thalamus=thalamus)
    conversation = ConversationSystem(thalamus=thalamus)
    assert thalamus.register_lobe("shared_representation", shared)["status"] == "success"
    assert thalamus.register_lobe("language", language)["status"] == "success"
    assert thalamus.register_lobe("conversation", conversation)["status"] == "success"
    return thalamus, shared, language, conversation


def test_thalamus_is_native_router_not_wrapper():
    assert Thalamus.__module__ == "thalamus"
    assert Thalamus.__bases__ == (object,)


def test_route_trace_is_written_before_dispatch_and_records_result(tmp_path):
    thalamus = Thalamus(runtime_directory=str(tmp_path))

    class TraceCheckingLobe:
        def process_message(self, message):
            records = [
                json.loads(line)
                for line in thalamus.route_trace_path.read_text(encoding="utf-8").splitlines()
            ]
            assert records[0]["event"] == "dispatch"
            assert records[0]["envelope"] == message
            return {"status": "success", "content": {"received": True}}

    thalamus.register_lobe("language", TraceCheckingLobe())
    response = thalamus.send_message(
        "language",
        "generate",
        {"content": "A grounded sentence.", "intent": "share_insight"},
        source="reasoning",
    )

    records = [
        json.loads(line)
        for line in thalamus.route_trace_path.read_text(encoding="utf-8").splitlines()
    ]
    assert response["status"] == "success"
    assert [record["event"] for record in records] == ["dispatch", "result"]
    assert records[0]["destination"] == "language"
    assert records[0]["envelope"]["content"]["content"] == "A grounded sentence."
    assert records[0]["message_id"] == records[1]["message_id"]
    assert records[1]["response"] == response


def test_route_trace_records_unknown_destinations_and_rejected_content(tmp_path):
    thalamus = Thalamus(runtime_directory=str(tmp_path))
    unknown = thalamus.send_message("missing", "generate", {"content": "raw"})
    rejected = thalamus.send_message("language", "generate", ["not", "a", "dict"])

    records = [
        json.loads(line)
        for line in thalamus.route_trace_path.read_text(encoding="utf-8").splitlines()
    ]
    assert unknown["status"] == "error"
    assert rejected["status"] == "error"
    assert [record["event"] for record in records] == [
        "dispatch",
        "result",
        "rejected",
    ]
    assert records[0]["destination"] == "missing"
    assert records[1]["response"]["message"] == "Unknown destination: missing"
    assert records[2]["reason"] == "Message content must be a dictionary"


def test_language_first_then_sr_ids(tmp_path):
    thalamus, shared, _, _ = _stack(tmp_path)
    perception = {"modality": "text"}
    result = thalamus._resolve_representation_live(
        "Steve gave the dog a ball yesterday.",
        perception_payload=perception,
        user_id="u1",
    )
    assert result["status"] == "success"
    assert result["language_first"] is True
    assert result["raw_text_parser_used"] is False
    assert result["language_comprehension_available"] is True
    assert result["proposition_ids"]
    assert any(
        route.get("to") == "language" and route.get("type") == "comprehend"
        for route in thalamus.message_routes
    )
    assert not any(
        route.get("to") == "shared_representation"
        and route.get("type") == "resolve_from_text"
        for route in thalamus.message_routes
    )
    proposition = shared.get_proposition(result["proposition_ids"][0], user_id="u1")
    assert proposition is not None
    assert proposition.provenance.producer_lobe == "language"


def test_conversation_natively_receives_language_structure(tmp_path):
    thalamus, _, _, conversation = _stack(tmp_path)
    perception = {"modality": "text"}
    representation = thalamus._resolve_representation_live(
        "Steve gave the dog a ball yesterday.",
        perception_payload=perception,
        user_id="u1",
    )
    response = conversation.process_message(
        {
            "type": "understand",
            "source": "thalamus",
            "content": {
                "user_input": "Steve gave the dog a ball yesterday.",
                "user_id": "u1",
                "perception": perception,
                "language_understanding": representation["language_understanding"],
                "concept_ids": representation["concept_ids"],
                "referent_ids": representation["referent_ids"],
                "proposition_ids": representation["proposition_ids"],
            },
        }
    )
    understanding = response["content"]["understanding"]
    assert understanding["language_understanding"] == representation["language_understanding"]
    assert understanding["representation_proposition_ids"] == representation["proposition_ids"]
    assert understanding["linguistic_context_source"] == "language_via_shared_representation"


def test_reasoning_native_finalizes_semantics_and_publishes_to_sr(tmp_path):
    class QuietReasoner:
        def __init__(self, thalamus=None):
            self.thalamus = thalamus
            self.facts = {}
            self._direct_core = True
        def think_about(self, input_data):
            return {"composed_response": None, "theories": []}
        def shutdown(self):
            return None

    thalamus, _, _, _ = _stack(tmp_path)
    reasoning = DirectReasoningAdapter(thalamus=thalamus, reasoner_factory=QuietReasoner)
    thalamus.register_lobe("reasoning", reasoning)
    result = reasoning.process_message(
        {
            "type": "think",
            "message_id": "native-reasoning",
            "content": {
                "input": {
                    "user_input": "What is my favorite color?",
                    "user_id": "u1",
                    "understanding": {"intent": "question", "confidence": 0.95},
                    "memory_context": {
                        "memories": [{"role": "fact", "content": "Your favorite color is teal."}],
                        "facts": [],
                    },
                    "emotion_result": {"current_emotion": "neutral", "intensity": 0.4},
                    "representation_result": {
                        "status": "success",
                        "concept_ids": ["c_input"],
                        "referent_ids": ["i_input"],
                        "proposition_ids": ["p_input"],
                        "language_understanding": {"contract": "language_understanding_v1"},
                    },
                }
            },
        }
    )
    semantic = result["content"]["semantic_input"]
    assert semantic["native_semantics_finalized"] is True
    assert semantic["semantic_owner"] == "reasoning"
    assert semantic["representation_referent_ids"] == ["i_input"]
    assert semantic["input_representation_proposition_ids"] == ["p_input"]
    assert semantic["representation_proposition_ids"]


def test_language_does_not_select_memory_evidence():
    source = inspect.getsource(LanguageGenerator._salvage_grounded_answer)
    for forbidden in (
        "structures_from_grounded_memories",
        "answer_from_grounded_memories",
        "prose_answer_to_structures",
    ):
        assert forbidden not in source


def test_shared_representation_does_not_parse_text_or_discover_cooccurrence(tmp_path):
    shared = SharedRepresentationSystem(store_path=tmp_path / "shared.json")
    denied = shared.process_message(
        {"type": "resolve_from_text", "content": {"text": "dog chases cat"}}
    )
    assert denied["status"] == "error"
    resolved = shared.resolve_terms(["dog", "cat"], user_id="u1", activate=False)
    assert resolved["co_occurrence_edges_added"] == 0
    assert shared.get_relationships(resolved["concept_ids"][0], user_id="u1") == []


def test_thalamus_has_no_semantic_repair_or_auto_learning():
    source = inspect.getsource(Thalamus)
    for forbidden in (
        "from direct_response import",
        "relevance_score(",
        "answer_from_grounded_memories(",
        "prose_answer_to_structures(",
        "structures_from_grounded_memories(",
        "_attribute_asked(",
        "_fact_covers_attribute(",
        "response_provider.render(",
        "_auto_adapt_from_interaction(",
        "_learned_guidance_for_message(",
        "phase3_",
        "phase4_",
    ):
        assert forbidden not in source


def test_production_uses_only_native_cognitive_classes():
    import run_abin
    from run_abin import ConversationSystem as ProductionConversation
    from run_abin import DirectMaximumSophisticationAdapter as ProductionReasoning
    from run_abin import LanguageGenerator as ProductionLanguage
    from run_abin import SharedRepresentationSystem as ProductionShared
    from run_abin import Thalamus as ProductionThalamus

    assert ProductionThalamus is Thalamus
    assert ProductionConversation is ConversationSystem
    assert ProductionReasoning is DirectReasoningAdapter
    assert ProductionLanguage is LanguageGenerator
    assert ProductionShared is SharedRepresentationSystem
    source = inspect.getsource(run_abin)
    assert "phase3_thalamus" not in source
    assert "phase4_" not in source
    assert "shared_representation_phase2" not in source


def test_migration_bridge_modules_are_gone():
    root = Path(__file__).resolve().parent
    for name in (
        "phase3_thalamus.py",
        "phase4_thalamus.py",
        "phase4_conversation.py",
        "phase4_reasoning.py",
        "shared_representation_phase2.py",
    ):
        assert not (root / name).exists(), name
