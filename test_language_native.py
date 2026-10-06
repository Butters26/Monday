from __future__ import annotations

from thalamus import Thalamus
from shared_representation import SharedRepresentationSystem
from language_generation import LanguageGenerator


class _Router:
    def __init__(self, shared, language=None):
        self.shared = shared
        self.language = language

    def send_message(self, destination, msg_type, content=None, source="test"):
        target = self.shared if destination == "shared_representation" else self.language if destination == "language" else None
        assert target is not None, destination
        return target.process_message(
            {
                "type": msg_type,
                "content": content or {},
                "source": source,
                "message_id": "phase3-test-turn",
            }
        )


def _systems(tmp_path):
    shared = SharedRepresentationSystem(store_path=tmp_path / "shared.json")
    router = _Router(shared)
    language = LanguageGenerator(thalamus=router)
    router.language = language
    shared.thalamus = router
    return shared, language, router


def _concept_name(shared, reference_id, user_id="u1"):
    instance = shared.get_instance(reference_id, user_id=user_id)
    if instance is not None:
        concept = shared.get_concept(instance.concept_id)
        return concept.canonical_name if concept else None
    concept = shared.get_concept(reference_id)
    return concept.canonical_name if concept else None


def _one_clause(result):
    understanding = result["language_understanding"]
    assert len(understanding["clauses"]) == 1
    return understanding, understanding["clauses"][0]


def test_native_ditransitive_registers_roles_time_and_referents(tmp_path):
    shared, language, _ = _systems(tmp_path)
    result = language.comprehend(
        "Steve gave the dog a ball yesterday.", user_id="u1", turn_id="turn-1"
    )
    understanding, clause = _one_clause(result)

    assert clause["predicate_surface"] == "give"
    assert clause["qualifiers"]["temporal_relation"] == "before_now"
    assert clause["qualifiers"]["event_time_text"] == "yesterday"
    assert clause["proposition_id"] in result["proposition_ids"]

    proposition = shared.get_proposition(clause["proposition_id"], user_id="u1")
    assert proposition is not None
    assert set(proposition.roles) == {"agent", "recipient", "theme"}
    assert _concept_name(shared, proposition.roles["agent"]) == "steve"
    assert _concept_name(shared, proposition.roles["recipient"]) == "dog"
    assert _concept_name(shared, proposition.roles["theme"]) == "ball"
    assert len(understanding["referent_ids"]) == 3
    assert proposition.provenance.producer_lobe == "language"
    assert proposition.provenance.source_type == "user_utterance_linguistic_interpretation"


def test_native_active_and_passive_preserve_semantic_roles(tmp_path):
    shared, language, _ = _systems(tmp_path)

    active = language.comprehend("The dog chased the cat.", user_id="u1")
    _, active_clause = _one_clause(active)
    active_prop = shared.get_proposition(active_clause["proposition_id"], user_id="u1")
    assert active_prop is not None

    passive = language.comprehend("The cat was chased by the dog.", user_id="u1")
    _, passive_clause = _one_clause(passive)
    passive_prop = shared.get_proposition(passive_clause["proposition_id"], user_id="u1")
    assert passive_prop is not None

    assert _concept_name(shared, active_prop.roles["agent"]) == "dog"
    assert _concept_name(shared, active_prop.roles["patient"]) == "cat"
    assert _concept_name(shared, passive_prop.roles["agent"]) == "dog"
    assert _concept_name(shared, passive_prop.roles["patient"]) == "cat"
    assert active_clause["voice"] == "active"
    assert passive_clause["voice"] == "passive"


def test_native_preserves_negation_modality_time_and_quantity(tmp_path):
    shared, language, _ = _systems(tmp_path)
    result = language.comprehend(
        "Steve might not give the dog three balls tomorrow.", user_id="u1"
    )
    _, clause = _one_clause(result)
    q = clause["qualifiers"]

    assert q["polarity"] == "negative"
    assert q["modality"] == "possibility"
    assert q["modality_text"] == "might"
    assert q["temporal_relation"] == "after_now"
    assert q["event_time_text"] == "tomorrow"
    assert q["quantities"]["theme"] == 3.0

    proposition = shared.get_proposition(clause["proposition_id"], user_id="u1")
    assert proposition is not None
    assert proposition.qualifiers["polarity"] == "negative"
    assert proposition.qualifiers["modality"] == "possibility"
    assert proposition.qualifiers["quantities"]["theme"] == 3.0


def test_native_keeps_multiword_noun_phrase_as_one_concept(tmp_path):
    shared, language, _ = _systems(tmp_path)
    result = language.comprehend("The control panel failed.", user_id="u1")
    _, clause = _one_clause(result)
    proposition = shared.get_proposition(clause["proposition_id"], user_id="u1")

    assert proposition is not None
    assert _concept_name(shared, proposition.roles["theme"]) == "control panel"
    matches = shared.get_candidate_concepts("control panel")
    assert len(matches) == 1
    assert shared.get_candidate_concepts("the control panel") == []


def test_native_ambiguity_returns_candidates_and_does_not_guess(tmp_path):
    shared, language, _ = _systems(tmp_path)
    first = shared.resolve_concept("bank", concept_type="financial_institution")
    second = shared.create_concept_sense("bank", concept_type="river_edge")
    assert first is not None and second is not None

    result = language.comprehend("Steve likes the bank.", user_id="u1")
    understanding, clause = _one_clause(result)
    bank_mentions = [m for m in understanding["mentions"] if m.get("concept_surface") == "bank"]

    assert len(bank_mentions) == 1
    bank = bank_mentions[0]
    assert set(bank["candidate_concept_ids"]) == {first.concept_id, second.concept_id}
    assert bank["selected_concept_id"] is None
    assert bank["instance_id"] is None
    assert clause["proposition_id"] is None
    assert "theme" in clause["unresolved_roles"]
    assert understanding["unresolved_ambiguities"]


def test_native_unknown_predicate_is_explicit_and_not_registered(tmp_path):
    _, language, _ = _systems(tmp_path)
    result = language.comprehend("Steve florbed the dog.", user_id="u1")
    understanding, clause = _one_clause(result)

    assert clause["predicate_surface"] == "florbed"
    assert clause["predicate_known"] is False
    assert clause["predicate_id"] is None
    assert clause["proposition_id"] is None
    assert "florbed" in understanding["unknown_words"]


def test_shared_representation_rejects_raw_text_interpretation(tmp_path):
    shared, _, router = _systems(tmp_path)
    response = router.send_message(
        "shared_representation",
        "resolve_from_text",
        {"text": "Steve gave the dog a ball yesterday.", "user_id": "u1"},
        source="thalamus",
    )
    assert response["status"] == "error"
    assert "belongs to language" in response["message"]



def test_native_real_thalamus_live_representation_path_uses_language(tmp_path):
    thalamus = Thalamus()
    shared = SharedRepresentationSystem(
        thalamus=thalamus,
        store_path=tmp_path / "shared-live.json",
    )
    language = LanguageGenerator(thalamus=thalamus)
    assert thalamus.register_lobe("language", language)["status"] == "success"
    assert thalamus.register_lobe("shared_representation", shared)["status"] == "success"

    perception = {"modality": "text", "concepts": [], "entities": [], "novelty_flags": []}
    result = thalamus._resolve_representation_live(
        "Steve gave the dog a ball yesterday.",
        perception_payload=perception,
        user_id="u1",
    )

    assert result["language_comprehension_available"] is True
    assert result["raw_text_parser_used"] is False
    assert len(result["proposition_ids"]) == 1
    assert result["language_understanding"]["contract"] == "language_understanding_v1"
    assert perception["concept_ids"] == result["concept_ids"]
    assert perception["resolved_concepts"] == result["resolved"]
    assert perception["proposition_ids"] == result["proposition_ids"]
    assert perception["language_understanding"]["contract"] == "language_understanding_v1"
    thalamus.shutdown()
