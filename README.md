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

`run_abin.create_core_systems()` creates the prompted path:
conversation → Notus → emotion → reasoning → language → output. Each lobe
receives `{"type", "content", "source", "message_id"}` and `content` holds the
message payload.

The direct core intentionally excludes the legacy/experimental launcher,
PostgreSQL-backed `notus.py`, GUI, socket integrations, and autonomous loops.
They remain in the repository for compatibility work but are not imported by
`run_abin.py`.

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
