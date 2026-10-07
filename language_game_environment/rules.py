"""Non-negotiable rules for Mercy's Language game environment.

This module contains environment rules only. It does not define a game,
scoring, lessons, answers, mutation, selection, or evolution.
"""

from __future__ import annotations

from dataclasses import dataclass


RULE_TEXT = (
    "Language owns the final answer.",
    "Language must make an independent attempt before requesting help.",
    "Language must use or inspect its own permitted resources before requesting help.",
    "Other lobes may only provide information that belongs to their own responsibility.",
    "Other lobes may not submit, select, or directly provide the final answer.",
    "Language must make the final decision after any assistance.",
    "Contestants and helper lobes may not access grader state, correct answers, hidden tests, or scoring internals.",
    "A helper lobe may not chain through the environment to another helper lobe.",
    "Every assistance request and response must be recorded.",
    "The environment must record whether a final answer was assisted or unassisted.",
    "Contestants may not change environment rules, permissions, or architecture boundaries.",
    "Language learning state must remain Language-owned and contestant-specific.",
)


# Helpers must return structured support, never an answer-shaped field.
ALLOWED_ASSISTANCE_FIELDS = frozenset(
    {
        "observations",
        "context",
        "confidence",
        "metadata",
    }
)

FORBIDDEN_ASSISTANCE_FIELDS = frozenset(
    {
        "answer",
        "correct_answer",
        "expected_answer",
        "final_answer",
        "choice",
        "correct_choice",
        "selected",
        "selected_answer",
        "selected_sense",
        "target_sense",
        "sense_id",
        "score",
        "reward",
        "grader",
        "hidden_test",
    }
)

# Problem context is visible to the contestant. These names are reserved so a
# future game cannot accidentally leak grading data through the public context.
FORBIDDEN_PUBLIC_PROBLEM_FIELDS = frozenset(
    {
        "answer",
        "correct_answer",
        "expected_answer",
        "target_sense",
        "score",
        "reward",
        "grader",
        "hidden_test",
        "hidden_tests",
        "solution",
    }
)


@dataclass(frozen=True)
class EnvironmentRules:
    """Frozen rule configuration. Contestants receive no mutation API for this."""

    language_owns_final_answer: bool = True
    independent_attempt_before_help: bool = True
    own_resources_before_help: bool = True
    helpers_must_stay_in_lobe_scope: bool = True
    helpers_cannot_answer: bool = True
    language_makes_final_decision: bool = True
    hidden_grader_data_blocked: bool = True
    helper_chaining_blocked: bool = True
    assistance_trace_required: bool = True
    assisted_status_recorded: bool = True
    architecture_rules_immutable: bool = True
    learning_state_isolated_per_contestant: bool = True


DEFAULT_RULES = EnvironmentRules()
