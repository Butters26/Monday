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

Lobes communicate through direct function calls via `thalamus.py`. There is no
socket code between lobes. (The chat daemon uses a Unix socket only as the
transport between client and daemon.)

`run_abin.create_core_systems()` builds the live system. The prompted path is:

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
