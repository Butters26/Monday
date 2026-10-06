from __future__ import annotations

import inspect

from phase4_conversation import Phase4ConversationSystem
from phase4_reasoning import Phase4ReasoningAdapter
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


class _QuietReasoner:
    """Minimal legacy-reasoner surface; DirectReasoning owns the useful answer."""

    def __init__(self, thalamus=None):
        self.thalamus = thalamus
        self.facts = {}
        self._direct_core = True

    def think_about(self, input_data):
        return {"composed_response": None, "theories": []}

    def shutdown(self):
        return None


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
                "language_understanding": representation["language_understanding"],
                "concept_ids": representation["concept_ids"],
                "referent_ids": representation["referent_ids"],
                "proposition_ids": representation["proposition_ids"],
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


def test_phase4_reasoning_owns_semantic_finalization_and_routes_all_representation_ids(tmp_path):
    thalamus, _, _, _ = _phase4_stack(tmp_path)
    reasoning = Phase4ReasoningAdapter(
        thalamus=thalamus,
        reasoner_factory=_QuietReasoner,
    )
    assert thalamus.register_lobe("reasoning", reasoning)["status"] == "success"

    result = reasoning.process_message(
        {
            "type": "think",
            "source": "thalamus",
            "message_id": "phase4-reasoning-test",
            "content": {
                "input": {
                    "user_input": "What is my favorite color?",
                    "user_id": "u1",
                    "understanding": {"intent": "question", "confidence": 0.95},
                    "memory_context": {
                        "memories": [
                            {"role": "fact", "content": "Your favorite color is teal."}
                        ],
                        "facts": [],
                    },
                    "emotion_result": {
                        "current_emotion": "neutral",
                        "emotional_tone": "neutral",
                        "intensity": 0.4,
                    },
                    "representation_result": {
                        "status": "success",
                        "concept_ids": ["c_input"],
                        "referent_ids": ["i_input"],
                        "proposition_ids": ["p_input"],
                        "language_understanding": {"contract": "language_understanding_v1"},
                        "highly_active_concepts": [],
                    },
                    "social_context": {"continuity": "active"},
                }
            },
        }
    )

    assert result["status"] == "success"
    semantic = result["content"]["semantic_input"]
    assert semantic["phase4_semantics_finalized"] is True
    assert semantic["semantic_owner"] == "reasoning"
    assert semantic["user_input"] == "What is my favorite color?"
    assert semantic["representation_concept_ids"] == ["c_input"]
    assert semantic["representation_referent_ids"] == ["i_input"]
    assert semantic["input_representation_proposition_ids"] == ["p_input"]
    assert semantic["language_understanding"]["contract"] == "language_understanding_v1"
    assert semantic["grounded_structures"]
    # Reasoning-created grounded meaning is published to SR as a new proposition.
    assert semantic["representation_proposition_ids"]
    thalamus.shutdown()


def test_phase4_thalamus_contains_no_old_semantic_salvage_or_relevance_logic():
    source = inspect.getsource(Phase4Thalamus.process_user_input)
    forbidden = (
        "relevance_score(",
        "content_tokens(",
        "answer_from_grounded_memories(",
        "prose_answer_to_structures(",
        "structures_from_grounded_memories(",
        "_attribute_asked(",
        "_fact_covers_attribute(",
        "_asks_about_monday_own_speech(",
        "response_provider.render(",
    )
    for marker in forbidden:
        assert marker not in source

    curiosity_source = inspect.getsource(Phase4Thalamus._maybe_attach_curiosity_follow_up)
    assert "honest_curiosity_question(" not in curiosity_source
    assert "maybe_curiosity_follow_up" in curiosity_source


def test_phase4_production_imports_use_phase4_adapters():
    from run_abin import ConversationSystem, DirectMaximumSophisticationAdapter, Thalamus

    assert Thalamus is Phase4Thalamus
    assert ConversationSystem is Phase4ConversationSystem
    assert DirectMaximumSophisticationAdapter is Phase4ReasoningAdapter
