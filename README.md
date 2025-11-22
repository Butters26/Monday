# Monday

## Project Structure

This repository contains two separate systems:

### 1. Brain System (Coming Soon)
The artificial brain - a computational brain architecture built from scratch without AI/ML components.

### 2. Body System (3D Model Generator)
**Location**: `model_3d.py`, `demo_3d.py`, `advanced_modeling.py`, `demo_advanced.py`

A standalone 3D model generation system for creating physical structures/bodies. This system is completely independent and NOT part of the brain - it creates the physical form that could house the brain.

**Basic Features**:
- Generate basic shapes: cubes, spheres, cylinders, toruses, pyramids
- Build complex models by combining shapes
- Export to OBJ and STL formats for 3D printing or visualization

**Advanced Features** ⭐:
- **Subdivision Surfaces**: Smooth meshes with Catmull-Clark subdivision
- **Mesh Sculpting**: Bulge, twist, taper effects for organic shapes
- **Detailed Humanoids**: Generate anatomically proportioned characters
- **Armored Characters**: Create game character-style models with armor
- **Procedural Details**: Add surface texture and complexity
- All procedurally generated - no AI/ML

**Usage**:
```bash
# Basic models
python demo_3d.py

# Advanced models (cool detailed characters!)
python demo_advanced.py

# Monday character model
python monday_character.py
```

This will create various 3D models in the `models_output/` directory.

**Example Models**:
- Monday character (2,412 vertices, 4,128 faces) - Female humanoid with feminine proportions, hair, glasses, earrings, and dress
- Armored hero character (1,737 vertices, 3,133 faces) - Master Chief style
- Detailed humanoids with proper anatomy
- Smooth subdivided spheres (2,504 vertices)
- Sculpted and textured shapes
