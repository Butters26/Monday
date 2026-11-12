# Notus (Memory) — Functional Spec — DRAFT for Matthew to approve

Status: DRAFT. Nothing here is law until Matthew approves it.
Source: built only from the Notus contract (`.github/instructions/notus-memory.instructions.md`).
Each function says which contract sentence authorizes it.

Contract, quoted:
> (A) It preserves experiences and knowledge so they remain available beyond the moment they were encountered.
> (B) It retrieves relevant stored information when another lobe needs to remember something.
> (C) Memory must preserve the distinction between what was experienced, what someone reported, and what was concluded.
> (D) Retrieving a stored statement establishes that it was remembered, not that it is necessarily true. Notus supplies remembered information; other lobes interpret and evaluate it.

---

## What one memory looks like

Every memory Notus stores has these fields. No memory is stored without all of the required ones.

| Field | Required | What it is | Example |
|---|---|---|---|
| `id` | yes | Notus gives every memory its own number | `57` |
| `kind` | yes | **experienced**, **reported**, or **concluded** (C) | `reported` |
| `content` | yes | what is remembered, as it was given to Notus | `Matthew's dog is Pixel` |
| `about` | yes | who/what it is about | `Matthew`, `Matthew's dog` |
| `source` | yes | who told her, which sense, or which lobe concluded it (C) | `told by Matthew (typed)` / `seen (camera)` / `concluded by reasoning` |
| `based_on` | concluded only | the ids of the memories the conclusion came from | `[57, 58]` |
| `stored_at` | yes | when Notus stored it | `2026-11-12 13:05` |
| `when_it_happened` | if given | the time the memory is about, if any | `tomorrow`, `when I was a kid` |
| `recalled_count` | yes | how many times it has been given back | `3` |
| `structure` | if given | the who / relation / what, if the lobe that sent it gave one | `Matthew — dog — Pixel` |

Notus never changes `kind` or `source` after storing. A report never becomes an experience. A conclusion never becomes a report. (C)

---

## Functions (messages other lobes send Notus through the thalamus)

### 1. `remember` — store a memory  (authorized by A, C)

**In:**
```
kind:              experienced | reported | concluded      (required)
content:           what to remember                        (required)
about:             who/what it is about                    (required)
source:            who told her / which sense / which lobe (required)
based_on:          [ids]       (required when kind = concluded)
when_it_happened:  optional
structure:         optional (who — relation — what)
```
**Out:** `{ id, stored: true }`, or `{ stored: false, missing: [fields] }` if a required field is missing.

**Rules:**
- Stores it exactly as given. Notus does not reword it, decide what it means, or decide whether it is true. (D)
- The same thing from the same source again → not a second copy; that memory's `recalled_count`/strength goes up.
- The same thing from a *different* source (Matthew said it, then Reasoning concluded it) → kept as **separate** memories, because they are different kinds. (C)
- Something new that disagrees with something old ("I live in Boulder" after "I live in Denver") → **both are kept.** Notus deletes nothing and marks nothing wrong. Deciding which is current is another lobe's job. (D)

**Checked live by:** boot her, say something, and the raw trace shows the `remember` message arriving, the memory stored with all required fields, and the `id` sent back.

### 2. `remember_moment` — store an experience as it happened  (authorized by A, C)

Sent by Sensory Integration for every moment: something heard, seen, or felt.

**In:** `{ modality: heard | seen | felt, what_happened, who_was_there, time }`
**Out:** `{ id }`

**Rules:**
- The moment itself is stored as **experienced** (e.g. "Matthew said 'my dog is Pixel' at 13:05").
- What was *said* inside it is not stored as experienced. If it is stored as knowledge, it goes through `remember` as **reported**, with Matthew as source.

**Checked live by:** every turn in the raw trace shows one experienced memory for that moment.

### 3. `recall` — give back relevant memories  (authorized by B, C, D)

**In:**
```
looking_for:   the words / question / thing the lobe needs to remember (required)
about:         optional — only memories about this
kind:          optional — only experienced / reported / concluded
source:        optional — only from this source
time:          optional — only memories about this time
limit:         optional — how many at most
```
**Out:** a list, most relevant first. Each entry has **all** the memory fields (kind, source, stored_at, etc.).
If nothing relevant is stored: `{ memories: [], nothing_remembered: true }`.

**Rules:**
- Gives back only memories relevant to what was asked. Never fills the list with unrelated ones to have something to return.
- If stored memories disagree, gives back **all** of them, each with its kind, source and time. Does not pick a winner. (D)
- Every memory it gives back gets `recalled_count + 1`.
- Never says or implies a memory is true. (D)

**Checked live by:** ask her something she was told; the raw trace shows the lobe's `recall` message, and Notus's answer lists the right memories with their kind and source.

### 4. `history` — everything ever stored about one thing, in order  (authorized by A, B)

**In:** `{ about }`
**Out:** every memory about it, oldest to newest, each with kind/source/time.
(Lets Reasoning see "Denver (told 13:01), then Boulder (told 13:06)" and decide for itself.)

**Checked live by:** after changing something, the raw trace shows `history` returning both versions in order.

### 5. `still_have_it` — survives shutdown  (authorized by A)

Not a message — a requirement: everything stored is on disk. Shut her down, boot her again: `recall` gives back the same memories with the same ids, kinds and sources.

**Checked live by:** tell her something, shut her down, boot her, ask; raw trace from the second boot shows the memory recalled.

### 6. `health`  (support)

**In:** nothing. **Out:** `{ running, storage_path, memory_count }`.

---

## What Notus does NOT do (D, and the contract's rules)

- Does not decide what something means ("moved to Boulder" → "lives in Boulder"). That's another lobe's call.
- Does not decide which of two memories is true or current, and does not mark memories wrong.
- Does not announce contradictions or judge them.
- Does not read Matthew's sentences to work out the facts in them. The lobe that understands language sends Notus the structured memory.
- Does not remind, bring things up, or speak on its own unless Matthew says that is Notus's job.
- Does not delete anything.

---

## Current code that conflicts with this spec (would be moved to `legacy/` or to another lobe — Matthew decides)

1. Notus reads sentences itself to find facts (`_learn_reading`, `_file`, `_who`...) → conflicts with "does not read sentences".
2. Notus replaces old facts / marks them contradicted (`single_valued`, `is_contradicted`, `mark_wrong`, one-at-a-time file) → conflicts with D.
3. `memory_what_it_means.txt` ("move to → live in") → interpretation, conflicts with D.
4. Announces `contradicts` → evaluation, conflicts with D.
5. Reminder / bring-up-while-quiet thread → not in the contract.
6. Beliefs (`store_belief`, `adjust_belief`) — Notus adjusting how sure a belief is → evaluation; needs Matthew's call.
7. Emotional memory, behavioral patterns, meta patterns, contradictions queries (`get_*`) → need checking against this spec one by one.

---

## Decisions Matthew needs to make

1. Who turns his sentence into a structured memory to send Notus — Language?
2. Who decides an old memory is no longer current (Denver → Boulder) — Reasoning?
3. Do reminders / bringing things up on her own belong to some lobe, and which one?
4. Code in the conflict list: move to `legacy/`, or move into the lobe that owns it?
5. Anything in this spec to change, add or remove.
