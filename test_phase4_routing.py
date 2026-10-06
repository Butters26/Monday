from __future__ import annotations

import inspect

from phase4_conversation import Phase4ConversationSystem
from phase4_reasoning import Phase4ReasoningAdapter
from phase4_thalamus import Phase4Thalamus
from thalamus import Thalamus as NativeThalamus
from shared_representation_phase2 import Phase2SharedRepresentationSystem, SharedRepresentationLanguageGenerator


class NoRawTextSharedRepresentation(Phase2SharedRepresentationSystem):
    def process_message(self, message):
        if message.get("type") == "resolve_from_text":
            raise AssertionError("Thalamus must never ask SR to interpret raw text")
        return super().process_message(message)


def _stack(tmp_path):
    thalamus = NativeThalamus()
    shared = NoRawTextSharedRepresentation(thalamus=thalamus, store_path=tmp_path / "shared.json")
    language = SharedRepresentationLanguageGenerator(thalamus=thalamus)
    conversation = Phase4ConversationSystem(thalamus=thalamus)
    assert thalamus.register_lobe("shared_representation", shared)["status"] == "success"
    assert thalamus.register_lobe("language", language)["status"] == "success"
    assert thalamus.register_lobe("conversation", conversation)["status"] == "success"
    return thalamus, shared, conversation


def test_phase4_is_native_thalamus_not_wrapper():
    assert Phase4Thalamus is NativeThalamus
    assert NativeThalamus.__bases__ == (object,)


def test_language_first_then_sr_ids(tmp_path):
    thalamus, shared, _ = _stack(tmp_path)
    perception = {"modality": "text"}
    result = thalamus._resolve_representation_live(
        "Steve gave the dog a ball yesterday.", perception_payload=perception, user_id="u1"
    )
    assert result["status"] == "success"
    assert result["phase4_language_first"] is True
    assert result["legacy_raw_text_parser_used"] is False
    assert result["proposition_ids"]
    assert any(r.get("to") == "language" and r.get("type") == "comprehend" for r in thalamus.message_routes)
    assert not any(r.get("to") == "shared_representation" and r.get("type") == "resolve_from_text" for r in thalamus.message_routes)
    proposition = shared.get_proposition(result["proposition_ids"][0], user_id="u1")
    assert proposition.provenance.producer_lobe == "language"


def test_conversation_gets_language_structure(tmp_path):
    thalamus, _, conversation = _stack(tmp_path)
    perception = {"modality": "text"}
    representation = thalamus._resolve_representation_live(
        "Steve gave the dog a ball yesterday.", perception_payload=perception, user_id="u1"
    )
    response = conversation.process_message({
        "type": "understand",
        "source": "thalamus",
        "message_id": "p4",
        "content": {
            "user_input": "Steve gave the dog a ball yesterday.",
            "user_id": "u1",
            "perception": perception,
            "language_understanding": representation["language_understanding"],
            "concept_ids": representation["concept_ids"],
            "referent_ids": representation["referent_ids"],
            "proposition_ids": representation["proposition_ids"],
        },
    })
    understanding = response["content"]["understanding"]
    assert understanding["language_understanding"] == representation["language_understanding"]
    assert understanding["representation_proposition_ids"] == representation["proposition_ids"]


def test_native_thalamus_has_no_semantic_repair_or_auto_learning():
    source = inspect.getsource(NativeThalamus)
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
    ):
        assert forbidden not in source


def test_transport_does_not_inject_cognitive_guidance():
    class Echo:
        def process_message(self, message):
            self.message = message
            return {"status": "success", "content": {}}

    router = NativeThalamus()
    echo = Echo()
    router.register_lobe("echo", echo)
    router.send_message("echo", "test", {"value": 7}, source="unit")
    assert echo.message["content"] == {"value": 7}


def test_production_uses_native_clean_thalamus():
    from run_abin import Thalamus, ConversationSystem, DirectMaximumSophisticationAdapter
    assert Thalamus is NativeThalamus
    assert Phase4Thalamus is NativeThalamus
    assert ConversationSystem is Phase4ConversationSystem
    assert DirectMaximumSophisticationAdapter is Phase4ReasoningAdapter
