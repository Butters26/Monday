"""Sentence builder: grammar from meaning, learning from feedback, persistence.

No option is favored up front, so grammar tests accept any valid choice and the
learning test checks that feedback, not a built-in default, decides the output.
"""

import random
import re

import pytest

from language_builder import Built, Lexicon, SentenceBuilder, indefinite_article, regular_past, third_person_s


def N(name):
    return {"name": name}


class NoSynonyms(Lexicon):
    """Real dictionary forms, but no synonym swaps, so grammar is tested alone."""

    def synonyms(self, lemma, pos):
        return []


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("MONDAY_RUNTIME_DIR", str(tmp_path))
    return tmp_path


def steady(learner="t", seed=0, explore=0.0):
    return SentenceBuilder(learner=learner, rng=random.Random(seed), explore_rate=explore,
                           lexicon=NoSynonyms())


def say(meaning, learner="t"):
    return steady(learner).build(meaning).sentence


GREETING = re.compile(r"^(Hello|Hullo|Hi|Howdy|How-do-you-do)(, Matthew)?!$")


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
        in {"Ariana is Matthew's wife.", "Ariana is the wife of Matthew."}
    assert say({"subject": N("Malrik"), "verb": "devour", "modal": "can",
                "object": {"noun": "fire", "count": "mass"}}) == "Malrik can devour fire."
    assert say({"subject": N("The Black Witch"), "verb": "give", "tense": "past",
                "object": N("Jester"), "recipient": N("Matthew")}) \
        in {"The Black Witch gave Jester to Matthew.", "The Black Witch gave Matthew Jester."}
    assert say({"subject": N("Gehrman"), "verb": "carry",
                "object": {"noun": "claymore", "adjectives": ["enormous"]}}) == "Gehrman carries an enormous claymore."
    assert say({"subject": N("Cleo"), "verb": "have",
                "object": {"noun": "hair", "count": "mass", "adjectives": ["white"]}}) == "Cleo has white hair."
    assert say({"subject": {"noun": "child", "count": "many", "definite": True}, "verb": "play",
                "tense": "past"}) == "The children played."


def test_negation_questions_greeting(runtime):
    assert say({"subject": N("Malrik"), "verb": "fear", "negated": True, "object": N("Matthew")}) \
        in {"Malrik does not fear Matthew.", "Malrik doesn't fear Matthew."}
    assert say({"act": "ask", "subject": N("Malrik"), "verb": "devour", "modal": "can",
                "object": {"noun": "fire", "count": "mass"}}) == "Can Malrik devour fire?"
    assert say({"act": "ask", "subject": {"ref": "addressee"}, "verb": "be",
                "complement": {"adjectives": ["stressed"]}}) == "Are you stressed?"
    assert say({"act": "ask", "ask_about": "object", "subject": N("Malrik"), "verb": "devour",
                "modal": "can", "object": {"noun": "fire", "count": "mass"}}) == "What can Malrik devour?"
    assert GREETING.match(say({"act": "greet", "addressee": N("Matthew")}))


def test_joining_same_subject(runtime):
    built = steady().build_many([
        {"subject": N("Cleo"), "verb": "have", "object": {"noun": "hair", "count": "mass", "adjectives": ["white"]}},
        {"subject": N("Cleo"), "verb": "use", "object": {"noun": "magic", "count": "mass", "adjectives": ["gravity"]}},
    ])
    assert built.sentence in {"Cleo has white hair and uses gravity magic.",
                              "Cleo has white hair. Cleo uses gravity magic."}


def test_feedback_decides_and_persists(runtime):
    meaning = {"act": "greet", "addressee": N("Matthew")}
    learner = steady("learner_a", seed=1, explore=0.5)
    for _ in range(80):
        built = learner.build(meaning)
        learner.feedback(built, good=(built.sentence == "Howdy, Matthew!"))
    assert steady("learner_a", seed=2).build(meaning).sentence == "Howdy, Matthew!"
    # A different learner has learned nothing and keeps no scores.
    assert steady("learner_b").memory._scores() == {}


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
