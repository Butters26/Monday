# Monday

## Project Structure

This repository contains two separate systems:

### 1. Brain System (Coming Soon)
The artificial brain - a computational brain architecture built from scratch without AI/ML components.

### 2. Body System (3D Model Generator)
**Location**: `model_3d.py`, `demo_3d.py`

A standalone 3D model generation system for creating physical structures/bodies. This system is completely independent and NOT part of the brain - it creates the physical form that could house the brain.

**Features**:
- Generate basic shapes: cubes, spheres, cylinders, toruses, pyramids
- Build complex models by combining shapes
- Export to OBJ and STL formats for 3D printing or visualization
- All procedurally generated - no AI/ML

**Usage**:
```bash
python demo_3d.py
```

This will create various 3D models in the `models_output/` directory.
