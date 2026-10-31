# Legacy code

Old code moved out of the live system so it can't be used by accident, kept
just in case. Nothing imports anything in this folder.

| File | What it was | Moved |
| --- | --- | --- |
| `language_generation_legacy.py` | Language's old grammar engine (163-word list, unused rulebook, fixed "I'm Monday" lines, fact templates, Mad Libs composers) and its old reply path | Oct 30, 2026 |

## test_thalamus_memory_queue_legacy.py (moved Oct 30, 2026)

Five tests for thalamus keeping a backup queue of his words when memory failed
to save them. Memory now saves each moment itself (it hears sensory
integration's `moment` announcement), so thalamus no longer saves or holds
anything. A failed save shows in the live trace instead.

## canned_lines_legacy.py (moved Oct 31, 2026)

Canned comfort lines Reasoning used to compute on emotional turns, a stock
curiosity follow-up question from Conversation, and the unused thalamus step
that glued it onto her reply. Language builds every reply from meaning now.
