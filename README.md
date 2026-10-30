# Monday

This repository contains two separate systems built with traditional
programming rather than AI/ML frameworks:

- **Monday** — a direct-call brain/reasoning system
- a standalone procedural 3D model generator (unrelated to the brain)

## Running Monday

Requires Python 3.11. Install dependencies with `pip install -r requirements.txt`.

- `python run_abin.py` — interactive REPL
- `python _monday_chat_daemon.py` — persistent chat daemon (keeps Monday running
  between messages and lets her speak unprompted)
- `python _monday_say.py "<message>"` — send one message to the daemon and print
  the reply; `--poll` collects anything she said unprompted
- `python _monday_web_chat.py` — local web chat UI at http://127.0.0.1:8765
  (talks to the daemon)

The REPL and the daemon share the same memory.

## Runtime data

Monday stores mutable data outside the repository. Do not add runtime data to Git.

| Variable | Default | Holds |
| --- | --- | --- |
| `MONDAY_RUNTIME_DIR` | `~/.local/state/monday` (`~/.local/state/monday-chat` for the daemon's socket/pid) | emotional state, shared representation, lobe learning, snapshots, logs |
| `MONDAY_NOTUS_SQLITE` | `~/.local/state/monday/notus_memory.sqlite3` | Notus conversation memory |

## Architecture

Thalamus is the message boy (contract: `.github/instructions/thalamus.instructions.md`):
it reads only the address on a message and delivers it. Every registered lobe
runs on its own thread with its own inbox (`lobe_inbox.py`); Thalamus puts each
message in the destination's inbox and carries the answer back. Lobes can:

- `send_message` / `send_and_wait`: ask another lobe and get its answer;
- `tell`: deliver without waiting;
- `listen` + `announce`: receive / send announcements on a topic;
- `broadcast_message`: ask several lobes at once.

A lobe waiting for an answer keeps handling messages from the same
back-and-forth, so two lobes asking each other never lock up; unrelated messages
wait their turn. No answer within `MONDAY_LOBE_ANSWER_TIMEOUT` seconds (default
60) is reported to the sender as a failure. Everything runs in one process; there
is no socket code between lobes. (The chat daemon uses a Unix socket only as the
transport between client and daemon.)

The offline dictionary keeps one SQLite connection per thread
(`lexicon/oewn_offline.py`), since a connection only works on the thread that
opened it.

`run_abin.create_core_systems()` builds the live system. For now a turn is still
run by a temporary script in `Thalamus.process_user_input` (being removed lobe by
lobe, see the Monday Build Plan). The prompted path is:

conversation → Notus → emotion → reasoning → language → output

Also registered on the live system: perception, sensory integration, attention,
novelty, pattern recognition, meta-cognition, executive control, social context,
motor action, voice, autonomous speech, meta-awareness, and shared
representation. When `enable_autonomous=True` (the default), an
`AutonomousThinkingLoop` runs in the background.

Each lobe receives `{"type", "content", "source", "message_id"}`; `content`
holds the message payload.

**Not wired into the live system:** `continuous_thought_generator.py` and
`controlled_thinking.py` (mock/toy modules) and `dual_stream_thinking.py`
(standalone demo). Legacy launcher, GUI (`monday_interface/`), and socket
integrations remain in the tree for compatibility work but are not the live
path.

### Notus memory

- **One memory store:** unless a custom `notus_factory` is passed,
  `open_primary_notus()` opens a SQLite `DirectNotusProcess` at
  `shared_direct_notus_path()`. The REPL and chat daemon use the same file.
  There is no PostgreSQL memory; it was removed. Fact extraction and
  matching helpers live in `notus_fact_text.py`.
- **Outage fallback:** if a Notus store/query errors or raises (caught by
  `Thalamus.send_message`), the prompted path keeps going using a bounded
  per-user in-memory queue (`notus_outage_fallback.py`, max 64 records per user,
  oldest dropped first). Queued records carry stable `event_id`s. Recovery is
  strict FIFO and stops on the first sync failure.
  `Thalamus.retry_unsaved_notus_records()` uses the event_ids so a double retry
  doesn't re-store the same event.

### Learning

- `learning/api.py` — entry points: `teach_monday`, `learning_overview`,
  `teach_lobe_skill`, `list_lobe_skills`
- `learning/lobe_learning_store.py` — per-lobe persistence (one file per lobe
  under runtime data)
- `thalamus.py` — routes learning requests to lobes

Lobe-local learning is separate from Notus conversation memory.

### How she replies (Language builds, Reasoning reviews)

`language_builder.py` is Language's expression half: it takes a meaning (who,
what, to whom; telling, asking, or greeting) and builds the sentence with
general grammar rules and words from the offline dictionary — no canned replies.
Every point where more than one correct option exists is a learned choice.
No option gets a head start and there are no example lists; each option keeps
a success record (used / judged good) in Language's learning store, the builder
leans toward better records, and records persist per learner. Reach it with
`LanguageGenerator.express()` / `express_feedback()` or the `express` /
`express_feedback` messages.

This is how she replies live: Language gathers the pieces in front of her (the
words she heard, what memory holds, how she feels, herself and the person),
picks a grammar form (say, ask, greet, or stay quiet) and puts pieces together;
every choice is learned, none is preset. Reasoning reviews each draft
(`review_reply`) and says what's wrong; Language learns from the verdict and
tries again, up to 7 times. Staying quiet is reviewed too. A failure is
reported as a failure, never passed off as silence.

## Live tracing

Set `MONDAY_TRACE=1` (or a file path) before starting her (`run_abin.py` or the
chat daemon) and `trace_monitor.py` records, while she is actually being used:
every Thalamus message with its real sender and what the receiver did with it,
which lobe's own thread handled it and how long it sat in the inbox, which lobes
are running on their own (at boot),
every turn with her reply and why a reply was blank, lobe-reported events,
uncaught errors in any thread, and printed warnings. It does not change her
behavior. `python trace_report.py [trace.jsonl]` summarizes it.

## Tests

Tests inject a SQLite `DirectNotusProcess` via `notus_factory=` and pass
`enable_autonomous=False` so they run without a background loop.

```
python -m pytest -q test_direct_core_pipeline.py test_notus_integration.py
python -m pytest -q test_shared_representation_semantics.py test_shared_representation_native.py test_language_native.py test_native_routing.py
python live_notus_memory_check.py
```

CI (`.github/workflows/direct-core.yml`) runs these on Python 3.11.

`_prove_*.py` scripts and the `_*_before.txt` / `_*_after.txt` files are
proof runs and logs from lobe-by-lobe development work.

## 3D model generator

The standalone 3D generator is independent from the brain system and provides:

- basic shapes: cube, sphere, cylinder, torus, pyramid
- complex model building by combining transformed shapes
- OBJ and STL export
- face-center and edge-midpoint subdivision
- mesh sculpting tools such as bulge, twist, and taper
- detailed humanoid and armored character generators
- a custom Monday character base mesh

### 3D generator files

- `model_3d.py` - core mesh types, primitive generators, model composition, OBJ/STL export
- `advanced_modeling.py` - subdivision, mesh sculpting, procedural detail, and humanoid generators
- `monday_character.py` - custom Monday character generator
- `demo_3d.py` - basic shape and combined-model demo
- `demo_advanced.py` - advanced modeling demo

### 3D usage

```python
from model_3d import ModelGenerator, ComplexModelBuilder
from advanced_modeling import SubdivisionSurface, MeshSculpting, DetailedHumanoidGenerator
from monday_character import create_monday_character

# Basic shape
sphere = ModelGenerator.create_sphere(radius=1.5, segments=32, rings=32)
sphere.export_obj("sphere.obj")
sphere.export_stl("sphere.stl")

# Combined model
builder = ComplexModelBuilder("MyModel")
builder.add_model(ModelGenerator.create_cube(size=2.0), offset_y=0)
builder.add_model(ModelGenerator.create_sphere(radius=1.0), offset_y=2.5)
model = builder.get_model()

# Subdivision and sculpting
base = ModelGenerator.create_sphere(radius=1.5, segments=8, rings=8)
smooth = SubdivisionSurface.subdivide(base, iterations=2)

cylinder = ModelGenerator.create_cylinder(radius=0.5, height=3.0, segments=32)
twisted = MeshSculpting.twist(cylinder, axis='y', angle=180)

# Character generators
hero = DetailedHumanoidGenerator.create_armored_character(height=7.5)
monday = create_monday_character(height=5.6)
```

### 3D demos

- `python demo_3d.py`
- `python demo_advanced.py`
- `python monday_character.py`
