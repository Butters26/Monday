# Monday

This repository currently contains two separate systems built with traditional
programming rather than AI/ML frameworks:

- a direct-call brain/reasoning system
- a standalone procedural 3D model generator

## Runtime data

Monday stores mutable data outside the repository. By default, the directory is
`~/.local/state/monday`; set `MONDAY_RUNTIME_DIR` to use another private
directory. This includes learned memory, emotional state, snapshots, logs, and
local recovery files. Do not add runtime data to Git.

## Direct-call core

All socket code has been removed. Lobes communicate through direct function
calls via Thalamus.

`run_abin.create_core_systems()` builds the live prompted path (plus optional
Perception / Attention / Novelty / AutonomousThinkingLoop). The memory→reply
core order remains:

conversation → Notus → emotion → reasoning → language → output

Each lobe receives `{"type", "content", "source", "message_id"}` and `content`
holds the message payload.

### Notus memory

- **Primary path:** PostgreSQL `ActiveNotusMemorySystem` (`notus_memory_core.py`)
  when `create_core_systems()` is called without a custom `notus_factory`.
- **Outage fallback:** if a Notus store/query returns an error or raises (caught
  by Thalamus), the prompted path continues. Failed writes go into a bounded
  per-user in-memory queue (`notus_outage_fallback.py`, max 64 records/user,
  FIFO eviction). Each queued record gets its own stable `event_id` — identical
  content is kept as separate events; retry idempotency is per event_id, not
  per content. Query failures serve that per-user buffer. When QUERY succeeds
  but pending rows remain (STORE still failing), pending memories for the same
  user are merged into the returned context before Reasoning (ordered, no
  cross-user leak, not claimed durable until synced). Recovery flush is strict
  FIFO: on the first sync failure, later records are not attempted.
  `Thalamus.retry_unsaved_notus_records()` uses event_ids so a double retry
  cannot double-store the same queued record. This does **not** restore the
  legacy `monday_memory` / `retrieve_relevant_memory` / `sync_memory_to_notus`
  APIs.
- **Tests / CI:** inject SQLite `DirectNotusProcess` via `notus_factory` and set
  `enable_autonomous=False` so acceptance stays PostgreSQL-free, socket-free,
  and without autonomous background loops. See
  `test_direct_core_pipeline.py` and `test_notus_integration.py`.

Live `create_core_systems()` still starts AutonomousThinkingLoop by default;
pass `enable_autonomous=False` for a loop-free boot. GUI and legacy socket
launchers remain in the tree but are not required for the direct-call path.

## Learning system (easy to find)

- `learning/api.py` — simple entry points (`teach_monday`, `learning_overview`,
  `teach_lobe_skill`, `list_lobe_skills`)
- `learning/__init__.py` — exports the learning API helpers
- `learning/lobe_learning_store.py` — per-lobe adaptive persistence (one file per
  lobe under runtime data)
- `thalamus.py` — learning router and global `teach_monday`/`learning_overview`
  handlers
- `direct_notus.py` — SQLite conversation memory adapter (injectable for tests)
- `notus_outage_fallback.py` — bounded per-user Notus outage queue
- `test_direct_core_pipeline.py` / `test_notus_integration.py` — direct-core +
  Notus fallback acceptance

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
