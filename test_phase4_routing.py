from __future__ import annotations

from phase4_conversation import Phase4ConversationSystem
from phase4_thalamus import Phase4Thalamus
from shared_representation_phase2 import (
    Phase2SharedRepresentationSystem,
    SharedRepresentationLanguageGenerator,
)


class NoRawTextSharedRepresentation(Phase2SharedRepresentationSystem):
    """Fail immediately if Thalamus regresses to SR raw-text interpretation."""

    def process_message(self, message):
        if message.get("type") == "resolve_from_text":
            raise AssertionError("Phase 4 forbids Thalamus -> SR resolve_from_text")
        return super().process_message(message)


def _phase4_stack(tmp_path):
    thalamus = Phase4Thalamus()
    shared = NoRawTextSharedRepresentation(
        thalamus=thalamus,
        store_path=tmp_path / "shared-phase4.json",
    )
    language = SharedRepresentationLanguageGenerator(thalamus=thalamus)
    conversation = Phase4ConversationSystem(thalamus=thalamus)

    assert thalamus.register_lobe("shared_representation", shared)["status"] == "success"
    assert thalamus.register_lobe("language", language)["status"] == "success"
    assert thalamus.register_lobe("conversation", conversation)["status"] == "success"
    return thalamus, shared, language, conversation


def test_phase4_thalamus_routes_raw_text_to_language_first(tmp_path):
    thalamus, shared, _, _ = _phase4_stack(tmp_path)
    perception = {"modality": "text", "concepts": [], "entities": [], "novelty_flags": []}

    result = thalamus._resolve_representation_live(
        "Steve gave the dog a ball yesterday.",
        perception_payload=perception,
        user_id="u1",
    )

    assert result["status"] == "success"
    assert result["phase4_language_first"] is True
    assert result["legacy_raw_text_parser_used"] is False
    assert result["phase3_language_comprehension"] is True
    assert len(result["proposition_ids"]) == 1
    assert result["language_understanding"]["contract"] == "language_understanding_v1"

    # The route starts with Thalamus -> Language comprehension.
    assert any(
        route.get("from") == "thalamus"
        and route.get("to") == "language"
        and route.get("type") == "comprehend"
        and route.get("status") == "success"
        for route in thalamus.message_routes
    )
    # Shared Representation may receive Language-owned lookup/register calls and
    # Thalamus-owned ID activation, but never raw text interpretation.
    assert not any(
        route.get("to") == "shared_representation"
        and route.get("type") == "resolve_from_text"
        for route in thalamus.message_routes
    )

    proposition = shared.get_proposition(result["proposition_ids"][0], user_id="u1")
    assert proposition is not None
    assert proposition.provenance.producer_lobe == "language"
    assert perception["proposition_ids"] == result["proposition_ids"]
    assert perception["representation_source"] == "language_via_shared_representation"
    thalamus.shutdown()


def test_phase4_thalamus_routes_activation_by_concept_id(tmp_path):
    thalamus, _, _, _ = _phase4_stack(tmp_path)
    result = thalamus._resolve_representation_live(
        "The dog chased the cat.", user_id="u1"
    )

    assert result["concept_ids"]
    activation_routes = [
        route
        for route in thalamus.message_routes
        if route.get("from") == "thalamus"
        and route.get("to") == "shared_representation"
        and route.get("type") == "activate"
    ]
    assert len(activation_routes) == len(result["concept_ids"])
    assert result["active_concepts"]
    thalamus.shutdown()


def test_phase4_conversation_receives_language_structure_without_reinterpreting(tmp_path):
    thalamus, _, _, conversation = _phase4_stack(tmp_path)
    perception = {"modality": "text", "concepts": [], "entities": [], "novelty_flags": []}
    representation = thalamus._resolve_representation_live(
        "Steve gave the dog a ball yesterday.",
        perception_payload=perception,
        user_id="u1",
    )

    response = conversation.process_message(
        {
            "type": "understand",
            "source": "thalamus",
            "message_id": "phase4-conversation-test",
            "content": {
                "user_input": "Steve gave the dog a ball yesterday.",
                "user_id": "u1",
                "perception": perception,
                "context": {"perception": perception},
            },
        }
    )

    assert response["status"] == "success"
    understanding = response["content"]["understanding"]
    assert understanding["language_understanding"] == representation["language_understanding"]
    assert understanding["representation_proposition_ids"] == representation["proposition_ids"]
    assert understanding["representation_referent_ids"] == representation["referent_ids"]
    assert understanding["representation_concept_ids"] == representation["concept_ids"]
    assert understanding["linguistic_context_source"] == "language_via_shared_representation"
    thalamus.shutdown()


def test_phase4_production_imports_use_phase4_adapters():
    from run_abin import ConversationSystem, Thalamus

    assert Thalamus is Phase4Thalamus
    assert ConversationSystem is Phase4ConversationSystem
