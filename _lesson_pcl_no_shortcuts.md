# Lesson: Perception → Conversation → Language (no shortcuts)

Saved: 2026-10-07 (America/Denver)
Matthew said: make a lesson, follow the list, no fucking shortcuts.
Condition: no shortcuts when this is executed.

This is the ordered lesson. Each step must finish for real before the next starts. A step is done only when the full bar holds on the live path (`_monday_say` / chat daemon → `thalamus.process_user_input`), not when a flag is set or a test only inspects a wrapper.

---

## Locked jobs (memorize these)

1. **Perception** — Sense only. Raw input → clean/normalize → basic observables → handoff. No meaning, intent, emotion, truth, or response.
2. **Conversation** — Dialogue state across turns. Topic, shifts, follow-ups, corrections, answers to her questions, interruptions, open threads, referents (“that”, “the last one”). Not a turn-label classifier.
3. **Language** — Word meaning + grammar + expression. Understand the sentence into a meaning packet; speak from meaning. No memory retrieval, no truth decisions, no inventing facts, no canned banks as the brain.

Keyword matching is the wrong tool for all three.

---

## The list (exact order)

### Step 0 — Ownership lock
Already locked. Do not reopen. If a change steals another lobe’s job, it fails this lesson.

### Step 1 — Cut stolen jobs (bleeding stops)

| Lobe | Must kill | Status |
|---|---|---|
| Perception | Emotion keywords, sentiment, novelty-as-interpretation, S-V-O guess, interpretive captions | Done on disk + GitHub (`d010c9c` sense-only). Re-verify before calling Language done. |
| Conversation | Regex turn classifier, slots, entities, sentiment ownership | Regex ownership removed; dialogue from Language packets. Correction = OEWN same-kind replace (`_correction_change_note.txt`). Banks ripped Step 4. |
| Language | Canned greeting/goodbye/check-in banks as mouth, stock fillers, Notus retrieval rescue inside Language | Stock fillers ripped (`63946c0`). **Greeting/goodbye/check-in banks ripped Step 4** (silence / meaning-only; see `_step4_change_note.txt`). Notus rescue / bank-as-brain still fail if present. |

No shortcut: deleting a flag or wrapping a call while the old classifier still runs = fail.

### Step 2 — Language meaning + grammar first (offline base)

Put real understanding in Language before Conversation can track referents and before anyone invents tags.

Required (all of them):

1. **Offline linguistic base on disk** — downloaded once, stored under the Monday tree (or a fixed local path she already owns), read with no internet at runtime. OEWN via `wn` (or equivalent offline wordnet) + any local trim allowed. Runtime network = fail.
2. **Open vocabulary** — unknown words marked unknown, not forced into a 30-verb toy list.
3. **Parse packet** — full-sentence structure Language owns: words/senses, roles, speech-act/clause shape, referents hooks, ambiguity, confidence. Consumable by Conversation and Reasoning.
4. **Generate from meaning** — expression builds sentences from grounded meaning packets / structures, not banks.
5. **Kill dead Phase 3/4 theater** — remove or replace the closed-set `LanguageComprehensionEngine` lists as the meaning source; delete the shadowed ~538-line dead `Phase4Thalamus.process_user_input`; live path must run one real orchestration, not a 33-line wrapper over legacy salvage.

No shortcut: keeping the toy verb/noun sets and calling it “Phase 3 language” = fail. Packet shape without a real lexicon = fail. Tests that only `inspect.getsource` the wrapper = fail.

### Step 3 — Rebuild Conversation on Language packets

After Language emits real packets:

- Topic / topic shift from meaning, not keyword labels
- Open questions and unfinished threads
- Corrections and answers to her questions
- Cross-turn referents (“that”, “the last one”) resolved via Language + dialogue state
- Stop owning slots/entities/sentiment

No shortcut: attaching `language_understanding` onto the old regex result without driving decisions = fail (that is today’s Phase4Conversation).

### Step 4 — Prove with off-list live turns

Prove on the live path, not keyword lists:

- Off-script greetings (“Just saying hi”) — not bank-matched theater
- Sentences with words outside any hard-coded set
- “that” / “the last one” follow-ups across turns
- When nothing grounded: silence (already required), not a stock line

Write before/after proof files. Change note: Matthew’s exact words + exactly what was done.

No shortcut: grepping for a flag, unit tests that mock the packet, or talking to the sidebar Monday agent as “proof” = fail.

---

## What ChatGPT’s Phase 3/4 already did (honest)

- Real packet shape + SR ID registration on live chat: yes.
- Offline lexicon / open vocabulary: **yes (Step 2)**. Conversation driven by meaning packets: **yes (correction = OEWN same-kind replace; see `_correction_change_note.txt`)**. Social greeting/goodbye/check-in banks: **ripped Step 4**. Dead Phase3/4 path: **removed by Phase 5**.
- Full bar for listed PCL items: **FAIL — listed proofs** after Matty 11:25 fix (depth-from-entity triviality, plastic primary-sense nominal, null-synset affect bridge killed; brass→plastic + long/heavy + off-list). Not whole-mind done; Matty may still audit.

---

## Execution rules (no shortcuts)

1. Open the actual lobe code before naming which files a change touches.
2. One list step at a time. Do not “also clean” Conversation while claiming Language.
3. Full bar every time: designed job on live path AND claims match mechanism AND no dead fancy APIs AND no keyword theater sold as understanding.
4. Partial progress = FAIL for that step. Say FAIL, not almost.
5. When she has nothing real to say: silence.
6. Never connect Mercy to the internet at runtime.
7. Change note every time you change something.
8. Push to GitHub when a step actually holds — local-only is not done for Matthew.

---

## Current pointer

- Step 1 Perception: done (re-check).
- Step 2 Language OEWN: done (`1f789ff`).
- Step 3 Conversation on Language packets: **FAIL — listed proofs** — correction = OEWN same-kind replace with depth-from-entity triviality (no hand lemma bag); brass→plastic True; long/heavy not affect_share; Matty negatives False; off-list hold. See `_correction_after_live.txt` / `_correction_change_note.txt`.
- Step 4 bank rip (greeting/goodbye/check-in): **done on live mouth** — social cue alone → silence; proofs in `_step4_*.txt`.
- **Listed PCL items: FAIL — listed proofs** — bag gone; brass/plastic + long/heavy + off-list hold; banks ripped; silence when empty. Not claiming whole mind done. Matty may still audit.
