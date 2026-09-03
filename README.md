# Monday 3D Model Generator

This repository currently contains a standalone procedural 3D model generator
built from scratch with traditional geometry code.

## Files in this repository

- `model_3d.py` - core mesh types, primitive generators, model composition, OBJ/STL export
- `advanced_modeling.py` - subdivision, mesh sculpting, procedural detail, and humanoid generators
- `monday_character.py` - custom Monday character generator
- `demo_3d.py` - basic shape and combined-model demo
- `demo_advanced.py` - advanced modeling demo

## Features

- Basic shapes: cube, sphere, cylinder, torus, pyramid
- Complex model building by combining transformed shapes
- OBJ and STL export
- Face-center and edge-midpoint subdivision
- Mesh sculpting tools such as bulge, twist, and taper
- Detailed humanoid and armored character generators
- A custom Monday character base mesh

## Usage

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

## Demos

- `python demo_3d.py`
- `python demo_advanced.py`
- `python monday_character.py`
