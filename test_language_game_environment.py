from __future__ import annotations

import pytest

from language_game_environment import GameRuleViolation, LanguageGameEnvironment


class FakeLanguage:
    def analyze(self, text: str):
        return {"text": text, "source": "fake_language"}


def make_env(tmp_path):
    return LanguageGameEnvironment(
        runtime_root=tmp_path,
        language_factory=FakeLanguage,
    )


def prepare_own_attempt(session, problem_id="p1"):
    session.start_problem(problem_id, visible_context={"prompt": "visible only"})
    session.mark_own_resource_use(problem_id, resource="language_internal_state")
    session.record_independent_attempt(problem_id, {"candidate": "first guess"})


def test_language_must_use_own_resource_before_independent_attempt(tmp_path):
    env = make_env(tmp_path)
    session = env.create_contestant("c1")
    session.start_problem("p1", visible_context={"prompt": "x"})

    with pytest.raises(GameRuleViolation):
        session.record_independent_attempt("p1", "guess")


def test_language_must_attempt_before_help(tmp_path):
    env = make_env(tmp_path)
    env.register_helper("reasoning", lambda request: {"observations": ["support"]})
    session = env.create_contestant("c1")
    session.start_problem("p1", visible_context={"prompt": "x"})
    session.mark_own_resource_use("p1", resource="language_internal_state")

    with pytest.raises(GameRuleViolation):
        session.request_assistance("p1", "reasoning", "help")


def test_helper_cannot_return_direct_prose_answer(tmp_path):
    env = make_env(tmp_path)
    env.register_helper("reasoning", lambda request: "the answer")
    session = env.create_contestant("c1")
    prepare_own_attempt(session)

    with pytest.raises(GameRuleViolation):
        session.request_assistance("p1", "reasoning", "help")


def test_helper_cannot_return_answer_shaped_field(tmp_path):
    env = make_env(tmp_path)
    env.register_helper(
        "reasoning",
        lambda request: {
            "observations": ["support"],
            "metadata": {"selected_sense": "hidden-answer"},
        },
    )
    session = env.create_contestant("c1")
    prepare_own_attempt(session)

    with pytest.raises(GameRuleViolation):
        session.request_assistance("p1", "reasoning", "help")


def test_valid_help_is_traced_and_final_is_marked_assisted(tmp_path):
    env = make_env(tmp_path)
    env.register_helper(
        "reasoning",
        lambda request: {
            "observations": ["one supporting observation"],
            "context": {"source": "reasoning"},
            "confidence": 0.5,
            "metadata": {},
        },
    )
    session = env.create_contestant("c1")
    prepare_own_attempt(session)

    packet = session.request_assistance("p1", "reasoning", "help")
    submission = session.submit_final("p1", "language's own final decision")

    assert packet.source_lobe == "reasoning"
    assert submission.assisted is True
    assert submission.assistance_count == 1
    assert len(session.assistance_trace("p1")) == 1


def test_unassisted_final_is_recorded_as_unassisted(tmp_path):
    env = make_env(tmp_path)
    session = env.create_contestant("c1")
    prepare_own_attempt(session)

    submission = session.submit_final("p1", "language answer")

    assert submission.assisted is False
    assert submission.assistance_count == 0


def test_hidden_answer_fields_are_blocked_from_visible_problem_context(tmp_path):
    env = make_env(tmp_path)
    session = env.create_contestant("c1")

    with pytest.raises(GameRuleViolation):
        session.start_problem(
            "p1",
            visible_context={"prompt": "x", "correct_answer": "do not leak"},
        )


def test_reserved_answer_or_grader_helpers_cannot_be_registered(tmp_path):
    env = make_env(tmp_path)

    with pytest.raises(GameRuleViolation):
        env.register_helper("grader", lambda request: {"observations": []})

    with pytest.raises(GameRuleViolation):
        env.register_helper("language", lambda request: {"observations": []})


def test_population_has_separate_state_directories(tmp_path):
    env = make_env(tmp_path)
    population = env.create_population(3)

    paths = {contestant.state_dir for contestant in population}
    assert len(population) == 3
    assert len(paths) == 3
