"""Sentence builder: grammar from meaning, learning from feedback, persistence."""

import random

import pytest

from language_builder import Built, SentenceBuilder, indefinite_article, regular_past, third_person_s


def N(name):
    return {"name": name}


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("MONDAY_RUNTIME_DIR", str(tmp_path))
    return tmp_path


def steady(learner="t"):
    return SentenceBuilder(learner=learner, rng=random.Random(0), explore_rate=0.0)


def say(meaning, learner="t"):
    return steady(learner).build(meaning).sentence


def test_morphology_rules():
    assert third_person_s("carry") == "carries"
    assert third_person_s("watch") == "watches"
    assert regular_past("stop") == "stopped"
    assert regular_past("create") == "created"
    assert indefinite_article("enormous claymore") == "an"
    assert indefinite_article("powerful wizard") == "a"
    assert indefinite_article("hour") == "an"


def test_statements(runtime):
    assert say({"subject": N("Ariana"), "verb": "be", "complement": {"noun": "wife", "of": N("Matthew")}}) \
        == "Ariana is Matthew's wife."
    assert say({"subject": N("Malrik"), "verb": "devour", "modal": "can",
                "object": {"noun": "fire", "count": "mass"}}) == "Malrik can devour fire."
    assert say({"subject": N("The Black Witch"), "verb": "give", "tense": "past",
                "object": N("Jester"), "recipient": N("Matthew")}) == "The Black Witch gave Jester to Matthew."
    assert say({"subject": N("Gehrman"), "verb": "carry",
                "object": {"noun": "claymore", "adjectives": ["enormous"]}}) == "Gehrman carries an enormous claymore."
    assert say({"subject": N("Cleo"), "verb": "have",
                "object": {"noun": "hair", "count": "mass", "adjectives": ["white"]}}) == "Cleo has white hair."
    assert say({"subject": {"noun": "child", "count": "many", "definite": True}, "verb": "play",
                "tense": "past"}) == "The children played."


def test_negation_questions_greeting(runtime):
    assert say({"subject": N("Malrik"), "verb": "fear", "negated": True, "object": N("Matthew")}) \
        == "Malrik does not fear Matthew."
    assert say({"act": "ask", "subject": N("Malrik"), "verb": "devour", "modal": "can",
                "object": {"noun": "fire", "count": "mass"}}) == "Can Malrik devour fire?"
    assert say({"act": "ask", "subject": {"ref": "addressee"}, "verb": "be",
                "complement": {"adjectives": ["stressed"]}}) == "Are you stressed?"
    assert say({"act": "ask", "ask_about": "object", "subject": N("Malrik"), "verb": "devour",
                "modal": "can", "object": {"noun": "fire", "count": "mass"}}) == "What can Malrik devour?"
    assert say({"act": "greet", "addressee": N("Matthew")}) == "Hello, Matthew!"


def test_joining_same_subject(runtime):
    built = steady().build_many([
        {"subject": N("Cleo"), "verb": "have", "object": {"noun": "hair", "count": "mass", "adjectives": ["white"]}},
        {"subject": N("Cleo"), "verb": "use", "object": {"noun": "magic", "count": "mass", "adjectives": ["gravity"]}},
    ])
    assert built.sentence == "Cleo has white hair and uses gravity magic."


def test_feedback_changes_choice_and_persists(runtime):
    meaning = {"act": "greet", "addressee": N("Matthew")}
    builder = steady("learner_a")
    first = builder.build(meaning)
    assert first.sentence == "Hello, Matthew!"
    for _ in range(4):
        builder.feedback(builder.build(meaning), good=False, reason="too formal")
    changed = builder.build(meaning).sentence
    assert changed != "Hello, Matthew!"
    # A brand-new builder for the same learner reads the learned scores from disk.
    assert steady("learner_a").build(meaning).sentence != "Hello, Matthew!"
    # Another learner is unaffected.
    assert steady("learner_b").build(meaning).sentence == "Hello, Matthew!"


def test_record_round_trip_and_language_lobe(runtime):
    from thalamus import Thalamus
    from language_generation import LanguageGenerator

    lang = LanguageGenerator(thalamus=Thalamus())
    out = lang.process_message({"type": "express", "content": {
        "meaning": {"subject": N("Ariana"), "verb": "be", "complement": {"noun": "wife", "of": N("Matthew")}},
        "learner": "lobe_test"}})
    assert out["status"] == "success"
    record = out["content"]
    assert record["sentence"].startswith("Ariana is")
    assert Built.from_dict(record).choices
    fb = lang.process_message({"type": "express_feedback", "content": {
        "record": record, "good": True, "reason": "clear"}})
    assert fb["status"] == "success" and fb["content"]["changes"]
