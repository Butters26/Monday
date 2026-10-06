import json

from shared_representation_phase2 import (
    Phase2SharedRepresentationSystem,
    SharedRepresentationLanguageGenerator,
    SharedRepresentationReasoningAdapter,
)


class _Router:
    def __init__(self, shared):
        self.shared = shared

    def send_message(self, destination, msg_type, content=None, source="test"):
        assert destination == "shared_representation"
        return self.shared.process_message(
            {"type": msg_type, "content": content or {}, "source": source, "message_id": "test-msg"}
        )


def test_phase2_reasoning_publishes_and_language_hydrates(tmp_path):
    shared = Phase2SharedRepresentationSystem(store_path=tmp_path / "shared.json")
    router = _Router(shared)

    reasoning = object.__new__(SharedRepresentationReasoningAdapter)
    reasoning.thalamus = router
    registered = reasoning._register_grounded_structures(
        [
            {
                "subject": "user",
                "relation": "favorite_color",
                "predicate": "favorite_color",
                "value": "teal",
                "object": "teal",
                "certainty": 0.95,
            }
        ],
        turn_id="turn-7",
    )

    assert len(registered) == 1
    proposition_id = registered[0]["proposition_id"]
    proposition = shared.get_proposition(proposition_id)
    assert proposition is not None
    assert proposition.provenance.producer_lobe == "reasoning"
    assert proposition.provenance.source_type == "reasoning_grounded_structure"
    assert proposition.provenance.turn_id == "turn-7"
    assert proposition.qualifiers["certainty"] == 0.95

    language = object.__new__(SharedRepresentationLanguageGenerator)
    language.thalamus = router
    hydrated = language._hydrate_shared_propositions(
        {"representation_proposition_ids": [proposition_id]}
    )

    assert hydrated["representation_hydrated"] is True
    assert hydrated["grounded_structures"] == [
        {
            "subject": "user",
            "relation": "favorite_color",
            "predicate": "favorite_color",
            "value": "teal",
            "object": "teal",
            "certainty": 0.95,
            "proposition_id": proposition_id,
        }
    ]


def test_phase2_propositions_remain_transient(tmp_path):
    path = tmp_path / "shared.json"
    shared = Phase2SharedRepresentationSystem(store_path=path)

    subject = shared.resolve_concept("user")
    predicate = shared.resolve_concept("lives_in")
    obj = shared.resolve_concept("fort collins")
    proposition = shared.register_proposition(
        predicate.concept_id,
        {"subject": subject.concept_id, "object": obj.concept_id},
        qualifiers={"certainty": 1.0},
        provenance={"producer_lobe": "reasoning", "source_type": "test"},
    )
    assert proposition is not None

    shared._persist()
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert "propositions" not in persisted
    assert "instances" not in persisted
    assert proposition.proposition_id not in path.read_text(encoding="utf-8")
