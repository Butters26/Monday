# Perception / Conversation / Language plan
Saved: 2026-10-06 (America/Denver)
Matthew asked: "Save that as a plan"
Status: plan only — do not implement until Matthew says to.

## Ownership (locked)
- **Perception:** Sense it. Convert raw text/audio/visual input into structured observations. Clean/normalize, extract basic observable features, pass onward. Does NOT decide meaning, intent, emotion, truth, or response.
- **Conversation:** Track what is happening between turns. Dialogue state, current topic, topic shifts, follow-ups, corrections, answers to Monday's questions, interruptions, unresolved questions, unfinished threads, recent references ("that", "the last one"). Pass conversational context onward.
- **Language:** Understand and express the words. Word meanings, grammar, sentence structure, relationships between words, ambiguity, unfamiliar words. Then turn internal meaning into natural sentences (wording, tense, pronouns, phrasing, tone). Does NOT retrieve memories, decide factual truth, perform reasoning, choose overall conversational intent, or invent facts.

## What's wrong now
- Perception mixes sensory intake with interpretation (sentiment, emotion keywords, grammar guesses, entity/name detection, novelty). Scene caption also crosses into interpretation.
- Conversation is mostly a turn-labeling classifier and steals language-analysis jobs (slots/entities/sentiment). Barely manages ongoing dialogue.
- Language is a response formatter + canned banks + retrieval/rescue, not real language. No word meaning.

## How to make them better (no keyword-matching as the brain)
1. Lock the ownership map above.
2. Cut stolen jobs out of each lobe so bleeding stops:
   - Perception: kill emotion keywords, sentiment lists, novelty flags, subject/verb/object guess.
   - Conversation: stop regex turn classification; no slots/entities/sentiment ownership here.
   - Language: no canned greeting/goodbye/check-in banks, no stock "not enough to go on" fake mouth, no Notus retrieval rescue inside Language.
3. Put meaning + grammar into Language first (offline linguistic base + parse into meaning packets + generate sentences from meaning). Conversation can't track referents and Perception shouldn't invent tags without Language.
4. Rebuild Conversation on top of Language's meaning packets (topic, open questions, threads, referents, corrections).
5. Prove each step with live turns that aren't on any keyword list — including off-script greetings and "that" / "the last one" follow-ups.

## On keyword matching
Wrong tool for these three jobs: fails on off-list phrasings (e.g. "Just saying hi" missing greeting), can't pick word sense, can't follow referents across turns, can't build sentences it hasn't templated.

## Do not
- Do not touch code until Matthew says to.
- Do not report PASS/done until the full bar holds.
