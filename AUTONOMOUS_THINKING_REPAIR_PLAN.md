# Autonomous Thinking — Repair Plan and Acceptance Criteria

Status: **investigation completed; implementation not yet started**.
Scope: `autonomous_thinking.py`, `autonomous_selection.py`, and only the necessary integration surfaces. This is a working plan, **not** a claim of a fix.

## Source of truth

Follow `.github/instructions/autonomous-thinking.instructions.md` without weakening or redefining the lobe's job. Autonomous Thinking initiates and sustains internal thought, starts questions, reflection and exploration, and supplies ongoing thought to other lobes. Reasoning evaluates conclusions, Notus retrieves memory, Executive Control sets priorities, and Language expresses meaning. Do not make these lobes mandatory for thought initiation.

## Verified faults

- Live `run_abin.py` registers `AutonomousThinkingLoop`; `ContinuousThoughtGenerator` and `ControlledThinking` are explicitly unwired mock modules.
- The background loop sleeps for a randomly selected interval and calls `_generate_thought()`. The interval controls work rate; it does not implement continuation.
- `_generate_thought()` requests emotion, recent Notus memories, and values each cycle, whether needed or not.
- `_generate_mode_content()` builds thought text using predefined sentence formats. Candidate scoring, novelty, and satiation exist but do not independently develop the content of an idea.
- The live idle/post-message audit showed four generated thought records, but did not demonstrate an independently developing chain of ideas.
- The current chat daemon explicitly reports that unprompted speech delivery is unavailable; do not confuse internal thinking with speech.

## Implementation stages

### 1. Preserve the existing working boot and tracing path
- Establish a baseline boot and trace on this branch.
- Preserve Thalamus routing, Notus identity, Emotion, Reasoning, Language, Executive Control, and existing direct conversation.
- Keep all modifications on this branch until tested and approved.

### 2. Replace the content generator, not merely its wording
- Introduce a structured internal thought state: focus, proposition/question/hypothesis, source, uncertainty, explored alternatives, unresolved items, and next operations.
- Implement meaningful thought operations (for example: ask a follow-up question, relate two active concepts, propose a possibility, contrast alternatives, identify an inconsistency, revise a hypothesis, or conclude/park an idea).
- Require each operation to consume and transform a prior state or currently available concepts. Avoid using prewritten first-person monologue templates as the thinking mechanism.
- A language rendering step may express the resulting meaning, but its wording is not evidence that the idea was developed.

### 3. Support independent initiation and sustained development
- Seed new thoughts from active concepts, current unresolved questions, internally produced possibilities, or environmental events.
- Carry unfinished questions and their evolving state across steps.
- Let thoughts continue, branch, pause, or end for a reason visible in the trace.
- When idle, do not fabricate thoughts to satisfy a quota.

### 4. Make other lobes optional specialists
- Use current working context without requesting Notus on every step.
- Ask Notus only for missing historical information; ask Reasoning to evaluate conclusions when appropriate; let Executive Control prioritize conflicts.
- Keep ownership of initiation and continuation inside Autonomous Thinking.

### 5. Replace time-triggered thought generation with bounded work processing
- Wake for new information or a runnable continuation. Yield/sleep for CPU efficiency when idle; no arbitrary interval that requires a new thought.
- Bound individual processing bursts and allow user conversation to preempt background work.
- Record why a thought started or continued; do not treat elapsed time as its cause.

### 6. Live acceptance tests (not mocked success claims)
- Boot Monday normally and verify existing two-turn conversation still works.
- With no new user message, verify an internally initiated idea can develop through multiple distinct operations, without forced thought quotas.
- After one ordinary user message, verify a traceable evolving chain: initial concept/question, an actual change in content or hypothesis, and a reason for continuing/stopping.
- Verify memory requests occur when needed rather than once per thought cycle.
- Verify an unrelated stimulus can interrupt/resume a train of thought without losing its state.
- Check for repeated boilerplate, runaway loops, memory corruption, crashes, and routing failures.
- Report both successes and failures from real traces; do not mark complete because a unit test passed.

## Current decision

A genuine idea-generation mechanism is still required. Existing Shared Representation supplies concept and relationship storage, not general idea generation. Decide implementation mechanism explicitly before claiming Stage 2 complete; no model dependency or API expense has been approved.

## Completion rule

Only call this repaired when Monday can initiate and **develop** an internal thought in the live system without another user prompt, with evidence of substantive changes to the thought's meaning rather than templated sentence variation.
