from __future__ import annotations

import json

from shared_representation import SharedRepresentationSystem


def _sr(tmp_path):
    return SharedRepresentationSystem(store_path=tmp_path / "shared_representation.json")


def test_transient_instances_and_propositions_do_not_persist(tmp_path):
    sr = _sr(tmp_path)
    steve = sr.resolve_concept("steve")
    give = sr.resolve_concept("give")
    dog = sr.resolve_concept("dog")
    ball = sr.resolve_concept("ball")

    dog_ref = sr.register_instance(
        dog.concept_id,
        label="the dog",
        provenance={"producer_lobe": "language", "source_type": "user_assertion"},
        expires_after_turn=4,
    )
    ball_ref = sr.register_instance(
        ball.concept_id,
        label="a ball",
        provenance={"producer_lobe": "language", "source_type": "user_assertion"},
        expires_after_turn=4,
    )
    proposition = sr.register_proposition(
        give.concept_id,
        {
            "agent": steve.concept_id,
            "recipient": dog_ref.instance_id,
            "theme": ball_ref.instance_id,
        },
        qualifiers={"event_time": "yesterday", "polarity": "positive"},
        provenance={"producer_lobe": "language", "source_type": "user_assertion"},
        expires_after_turn=4,
    )

    assert proposition is not None
    assert sr.get_proposition(proposition.proposition_id) is proposition
    assert proposition.roles["recipient"] == dog_ref.instance_id
    assert proposition.qualifiers["event_time"] == "yesterday"

    stored = json.loads((tmp_path / "shared_representation.json").read_text())
    assert "instances" not in stored
    assert "propositions" not in stored

    expired = sr.expire_turn(4)
    assert expired == {"instances": 2, "propositions": 1}
    assert sr.get_proposition(proposition.proposition_id) is None


def test_polysemy_returns_candidates_without_breaking_legacy_resolution(tmp_path):
    sr = _sr(tmp_path)
    financial = sr.resolve_concept("bank", concept_type="financial_institution")
    river = sr.create_concept_sense("bank", concept_type="river_edge")

    assert financial is not None and river is not None
    assert financial.concept_id != river.concept_id
    assert sr.resolve_concept("bank").concept_id == financial.concept_id
    assert {c.concept_id for c in sr.get_candidate_concepts("bank")} == {
        financial.concept_id,
        river.concept_id,
    }


def test_multiword_surface_lookup_is_exact_and_does_not_discover_phrases(tmp_path):
    sr = _sr(tmp_path)
    panel = sr.resolve_concept("control panel", concept_type="equipment")

    matches = sr.lookup_surface("control panel")
    assert [c.concept_id for c in matches] == [panel.concept_id]
    assert sr.lookup_surface("control") == []


def test_new_contract_is_available_through_process_message(tmp_path):
    sr = _sr(tmp_path)
    give = sr.resolve_concept("give")
    steve = sr.resolve_concept("steve")
    ball = sr.resolve_concept("ball")

    instance_response = sr.process_message(
        {
            "type": "register_instance",
            "content": {
                "concept_id": ball.concept_id,
                "label": "the ball",
                "provenance": {
                    "producer_lobe": "language",
                    "source_type": "user_assertion",
                },
            },
        }
    )
    assert instance_response["status"] == "success"

    proposition_response = sr.process_message(
        {
            "type": "register_proposition",
            "content": {
                "predicate_id": give.concept_id,
                "roles": {
                    "agent": steve.concept_id,
                    "theme": instance_response["instance"]["instance_id"],
                },
                "qualifiers": {"modality": "possibility"},
                "provenance": {
                    "producer_lobe": "language",
                    "source_type": "user_assertion",
                },
            },
        }
    )
    assert proposition_response["status"] == "success"

    lookup = sr.process_message(
        {"type": "lookup_surface", "content": {"surface": "give"}}
    )
    assert lookup["status"] == "success"
    assert give.concept_id in lookup["concept_ids"]
