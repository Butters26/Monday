# Mercy Emotion Lobe — Hard Architecture Rules

## NON-NEGOTIABLE RULE: NO KEYWORD SEARCHING OR LANGUAGE MATCHING IN EMOTION

The Emotion lobe must NEVER determine emotional meaning by inspecting raw language for words, phrases, patterns, or textual similarities.

The Emotion lobe is strictly prohibited from using any of the following to determine emotional meaning:

- keyword searching
- trigger-word lists
- emotional word lists
- phrase matching
- phrase tables
- regex patterns used to infer emotional meaning
- substring matching
- hard-coded sentences or sentence fragments
- sentiment-word detection
- synonym lists used as emotional triggers
- semantic-similarity matching used to guess emotional meaning from raw text
- embedding similarity used as a replacement for keyword searching
- classifiers inside Emotion whose job is to interpret what raw language means
- any rule equivalent to: "if the user says X, Mercy should feel Y"

Renaming this behavior does not make it acceptable. A component named `SelfImpact`, `AppraisalEngine`, `EmotionUnderstanding`, `SemanticEmotion`, or anything else still violates this rule if it searches or analyzes raw language to determine what happened or what Mercy should feel.

## REQUIRED BOUNDARY

Emotion does not interpret language.

The appropriate upstream systems must first determine the meaning of an event and provide that meaning to Emotion in a structured form.

Emotion may then evaluate the already-understood event against Mercy's own internal state, including relevant goals, needs, attachment, relationships, memories, personality, expectations, current affect, and prior emotional state.

Emotion answers:

> What does this already-understood event mean to Mercy, and how should Mercy's internal emotional state change because of it?

Emotion does NOT answer:

> What do these words mean?

## BUILD / REBUILD ENFORCEMENT

This rule applies to every Emotion-lobe implementation, rebuild, rewrite, replacement, experiment, refactor, and recovery attempt.

Any Emotion implementation that introduces keyword matching, trigger words, regex emotional triggers, phrase tables, raw-text sentiment detection, semantic phrase matching, embedding-based language matching, or another language-search shortcut for determining emotional meaning is an ARCHITECTURE VIOLATION and must be rejected.

This restriction includes the current/legacy SelfImpact regex approach. If SelfImpact determines emotional meaning by matching raw text, it violates this rule and must not be carried into a compliant rebuild.
