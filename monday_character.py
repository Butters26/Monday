"""
Monday Character Model Generator
Creates a female humanoid character model for the Monday project.
Built from scratch without AI/ML components.

Note: This generates the geometric structure. Advanced features like detailed
facial features, hair strands, clothing textures would require additional
texture mapping and detail sculpting beyond procedural geometry.
"""

from model_3d import ModelGenerator, ComplexModelBuilder
from advanced_modeling import MeshSculpting
import os

def create_monday_character(height=5.6):
    """
    Create the Monday character - a female humanoid figure.
    
    Based on description: mature female with feminine proportions,
    long hair, glasses, elegant dress.
    
    Args:
        height: Character height in units (5.6 for average female)
    
    Returns:
        Model3D object
    """
    builder = ComplexModelBuilder("Monday")
    scale = height / 6.0
    
    # Feminine proportions
    chest_width = 1.4 * scale
    waist_width = 1.0 * scale
    hip_width = 1.5 * scale
    leg_thickness = 0.30 * scale
    arm_thickness = 0.22 * scale
    
    print("Building Monday character model...")
    print(f"Height: {height} units")
    print(f"Proportions: feminine (chest {chest_width:.2f}, waist {waist_width:.2f}, hips {hip_width:.2f})")
    print()
    
    # === LOWER BODY ===
    
    # Legs (with slight taper for feminine shape)
    leg_length = 2.9 * scale
    leg_left = ModelGenerator.create_cylinder(radius=leg_thickness, 
                                               height=leg_length, segments=16)
    leg_left = MeshSculpting.taper(leg_left, axis='y', amount=0.15)
    builder.add_model(leg_left, offset_x=-0.35*scale, offset_y=leg_length/2, scale=1.0)
    
    leg_right = ModelGenerator.create_cylinder(radius=leg_thickness, 
                                                height=leg_length, segments=16)
    leg_right = MeshSculpting.taper(leg_right, axis='y', amount=0.15)
    builder.add_model(leg_right, offset_x=0.35*scale, offset_y=leg_length/2, scale=1.0)
    
    # Hips (wider for feminine shape)
    hip_height = leg_length + 0.25*scale
    hips = ModelGenerator.create_sphere(radius=hip_width/2, segments=16, rings=12)
    # Flatten vertically to create hip shape
    builder.add_model(hips, offset_y=hip_height, scale=1.0)
    
    # === TORSO ===
    
    # Waist (narrow)
    waist_height = 0.4 * scale
    waist = ModelGenerator.create_cylinder(radius=waist_width/2, 
                                           height=waist_height, segments=16)
    builder.add_model(waist, offset_y=hip_height + 0.4*scale, scale=1.0)
    
    # Chest/torso (tapered from chest to waist for feminine silhouette)
    torso_height = 1.5 * scale
    torso = ModelGenerator.create_cylinder(radius=chest_width/2, 
                                           height=torso_height, segments=20)
    # Taper to create hourglass shape
    torso = MeshSculpting.taper(torso, axis='y', amount=0.35)
    # Add subtle curves
    torso = MeshSculpting.bulge(torso, center=(0, torso_height/3, 0), 
                                radius=1.2*scale, strength=0.15*scale)
    builder.add_model(torso, offset_y=hip_height + 0.6*scale + torso_height/2, scale=1.0)
    
    # === UPPER BODY ===
    
    shoulder_height = hip_height + 0.6*scale + torso_height
    
    # Shoulders (smaller, more delicate)
    shoulder_left = ModelGenerator.create_sphere(radius=0.28*scale, segments=12, rings=10)
    builder.add_model(shoulder_left, offset_x=-0.9*scale, offset_y=shoulder_height, scale=1.0)
    
    shoulder_right = ModelGenerator.create_sphere(radius=0.28*scale, segments=12, rings=10)
    builder.add_model(shoulder_right, offset_x=0.9*scale, offset_y=shoulder_height, scale=1.0)
    
    # Arms (slender, tapered)
    arm_length = 2.0 * scale
    arm_left = ModelGenerator.create_cylinder(radius=arm_thickness, 
                                               height=arm_length, segments=12)
    arm_left = MeshSculpting.taper(arm_left, axis='y', amount=0.2)
    builder.add_model(arm_left, offset_x=-0.9*scale, 
                     offset_y=shoulder_height - arm_length/2 - 0.28*scale, scale=1.0)
    
    arm_right = ModelGenerator.create_cylinder(radius=arm_thickness, 
                                                height=arm_length, segments=12)
    arm_right = MeshSculpting.taper(arm_right, axis='y', amount=0.2)
    builder.add_model(arm_right, offset_x=0.9*scale, 
                     offset_y=shoulder_height - arm_length/2 - 0.28*scale, scale=1.0)
    
    # Hands (delicate)
    hand_left = ModelGenerator.create_sphere(radius=0.20*scale, segments=10, rings=8)
    builder.add_model(hand_left, offset_x=-0.9*scale, 
                     offset_y=shoulder_height - arm_length - 0.48*scale, scale=1.0)
    
    hand_right = ModelGenerator.create_sphere(radius=0.20*scale, segments=10, rings=8)
    builder.add_model(hand_right, offset_x=0.9*scale, 
                     offset_y=shoulder_height - arm_length - 0.48*scale, scale=1.0)
    
    # === HEAD ===
    
    # Neck (slender)
    neck_height = 0.4 * scale
    neck = ModelGenerator.create_cylinder(radius=0.28*scale, height=neck_height, segments=12)
    builder.add_model(neck, offset_y=shoulder_height + neck_height/2, scale=1.0)
    
    # Head (slightly smaller, oval shape for feminine features)
    head = ModelGenerator.create_sphere(radius=0.65*scale, segments=24, rings=24)
    # Slightly elongate vertically for more realistic head shape
    builder.add_model(head, offset_y=shoulder_height + neck_height + 0.65*scale, scale=1.0)
    
    # Hair volume (represented as larger sphere around head)
    # Long flowing hair approximated by extended volume
    hair_volume = ModelGenerator.create_sphere(radius=0.75*scale, segments=20, rings=20)
    # Elongate downward for long hair
    hair_volume = MeshSculpting.taper(hair_volume, axis='y', amount=-0.3)
    builder.add_model(hair_volume, offset_y=shoulder_height + neck_height + 0.7*scale, 
                     offset_z=0.1*scale, scale=1.0)
    
    # Glasses (simple representation with geometric shapes)
    # Left lens
    lens_left = ModelGenerator.create_torus(major_radius=0.15*scale, minor_radius=0.02*scale,
                                            major_segments=16, minor_segments=8)
    builder.add_model(lens_left, offset_x=-0.25*scale, 
                     offset_y=shoulder_height + neck_height + 0.65*scale,
                     offset_z=0.68*scale, scale=1.0)
    
    # Right lens
    lens_right = ModelGenerator.create_torus(major_radius=0.15*scale, minor_radius=0.02*scale,
                                             major_segments=16, minor_segments=8)
    builder.add_model(lens_right, offset_x=0.25*scale, 
                     offset_y=shoulder_height + neck_height + 0.65*scale,
                     offset_z=0.68*scale, scale=1.0)
    
    # Glasses bridge (small cylinder connecting lenses)
    bridge = ModelGenerator.create_cylinder(radius=0.02*scale, height=0.5*scale, segments=8)
    # Rotate to horizontal would require rotation matrix, so approximate position
    builder.add_model(bridge, offset_y=shoulder_height + neck_height + 0.65*scale,
                     offset_z=0.68*scale, scale=1.0)
    
    # Earrings (small spheres as dangling ornaments)
    earring_left = ModelGenerator.create_sphere(radius=0.08*scale, segments=8, rings=8)
    builder.add_model(earring_left, offset_x=-0.72*scale,
                     offset_y=shoulder_height + neck_height + 0.5*scale, scale=1.0)
    
    earring_right = ModelGenerator.create_sphere(radius=0.08*scale, segments=8, rings=8)
    builder.add_model(earring_right, offset_x=0.72*scale,
                     offset_y=shoulder_height + neck_height + 0.5*scale, scale=1.0)
    
    # Dress representation (flowing shape around torso)
    # Upper dress (slip dress with spaghetti straps)
    dress_top = ModelGenerator.create_cylinder(radius=chest_width/2 + 0.1*scale,
                                               height=torso_height * 0.6, segments=24)
    dress_top = MeshSculpting.taper(dress_top, axis='y', amount=0.25)
    builder.add_model(dress_top, 
                     offset_y=hip_height + 0.8*scale + torso_height * 0.3,
                     offset_z=-0.08*scale, scale=1.0)
    
    # Lower dress (flowing)
    dress_bottom = ModelGenerator.create_cylinder(radius=hip_width/2 + 0.2*scale,
                                                  height=leg_length * 0.6, segments=24)
    dress_bottom = MeshSculpting.taper(dress_bottom, axis='y', amount=-0.3)
    # Add flow/movement with twist
    dress_bottom = MeshSculpting.twist(dress_bottom, axis='y', angle=15, height_factor=0.2)
    builder.add_model(dress_bottom,
                     offset_y=hip_height + leg_length * 0.3,
                     offset_z=-0.05*scale, scale=1.0)
    
    model = builder.get_model()
    print(f"✓ Model created: {model}")
    print()
    
    return model


def main():
    print("=" * 70)
    print("MONDAY CHARACTER MODEL GENERATOR")
    print("Creating female humanoid character with specified features")
    print("=" * 70)
    print()
    
    # Create output directory
    output_dir = "models_output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Generate the Monday character
    monday = create_monday_character(height=5.6)
    
    # Export to files
    obj_file = os.path.join(output_dir, "monday_character.obj")
    stl_file = os.path.join(output_dir, "monday_character.stl")
    
    print("Exporting model files...")
    monday.export_obj(obj_file)
    monday.export_stl(stl_file)
    
    print(f"✓ OBJ file: {obj_file}")
    print(f"✓ STL file: {stl_file}")
    print()
    
    print("=" * 70)
    print("CHARACTER MODEL COMPLETE!")
    print("=" * 70)
    print()
    print("📝 MODEL FEATURES:")
    print("  • Feminine proportions (hourglass silhouette)")
    print("  • Long hair volume representation")
    print("  • Glasses (geometric frames)")
    print("  • Earrings (dangling ornaments)")
    print("  • Dress (slip style with flowing bottom)")
    print("  • Proper anatomical structure")
    print()
    print("⚠️  LIMITATIONS:")
    print("  This is a geometric/structural model. For production-quality")
    print("  character models, you would need:")
    print("  • Texture mapping for clothing patterns and skin")
    print("  • Detailed facial features (eyes, nose, mouth sculpting)")
    print("  • Hair strand modeling or hair cards")
    print("  • UV unwrapping for texture application")
    print("  • Normal/bump maps for fine surface details")
    print("  • Rigging for animation")
    print()
    print("  The current model provides the geometric foundation that")
    print("  can be imported into 3D software (Blender, Maya, etc.) for")
    print("  further detailed work.")
    print("=" * 70)

if __name__ == "__main__":
    main()
