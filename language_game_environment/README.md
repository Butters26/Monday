# Mercy Language Game Environment

This directory is the **environment only** for future Language-lobe games.
It intentionally does **not** define the game, the correct answers, scoring,
rewards, mutation, selection, breeding, generations, or evolution.

## What the environment provides

- Isolated Language contestants.
- A separate state directory for every contestant.
- Access to Mercy Language's own current comprehension engine.
- Access to Mercy Language's own offline OEWN lexicon.
- Optional assistance adapters for other lobes.
- Hard ordering checks: Language works first, then may ask for help.
- Structured assistance only; helper lobes cannot submit the final answer.
- No grader or correct-answer object is exposed to contestants or helper lobes.
- Full traces of assistance use and whether a final submission was assisted.

## Enforced flow

1. A future game starts a problem with contestant-visible context.
2. Language uses/inspects one of its own resources.
3. Language records an independent candidate.
4. Language may submit immediately, or optionally request assistance.
5. Registered helper lobes may return structured observations/context only.
6. Language makes and submits the final decision.
7. The environment returns a `FinalSubmission` to whatever future game/grader the user creates.

## Important boundary

The environment has **no grading method**. It does not know the correct answer.
That separation is intentional so the Language contestant cannot reach through
the environment and inspect answer/scoring data.

## Hard rules

The canonical rules are encoded in `rules.py` and enforced by
`environment.py`. They include:

- Language owns the final answer.
- Language must try its own resources and make an independent attempt before help.
- Helper lobes stay inside their own role and cannot return answer-shaped fields.
- Language makes the final decision after assistance.
- Grader/solution/hidden-test fields are blocked from public problem context.
- Helpers receive no environment, grader, contestant-session, or helper-registry handle.
- Every help request/response is traced.
- Assisted and unassisted final submissions are distinguished.
- Environment rules are frozen for contestants.
- Contestant learning/runtime state is separated per contestant.

## Runtime location

By default contestant state is written under:

`~/.local/state/mercy/language_game/`

Set `MERCY_LANGUAGE_GAME_RUNTIME` to use a different runtime root.

Nothing in this environment writes learned state into Mercy's source files.
