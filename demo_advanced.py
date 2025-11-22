"""
Demonstration of advanced 3D modeling features.
Creates cool, detailed models with mesh sculpting and subdivision.
"""

from model_3d import ModelGenerator
from advanced_modeling import (SubdivisionSurface, MeshSculpting, 
                                DetailedHumanoidGenerator, ProceduralDetails)
import os

def main():
    print("=" * 70)
    print("ADVANCED 3D MODEL GENERATOR - COOL DETAILED MODELS")
    print("Mesh sculpting, subdivision surfaces, and detailed characters")
    print("=" * 70)
    print()
    
    # Create output directory
    output_dir = "models_output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    print("Creating advanced models with cool details...\n")
    
    # 1. Smooth sphere using subdivision
    print("1. Creating ultra-smooth sphere with subdivision surfaces...")
    base_sphere = ModelGenerator.create_sphere(radius=1.5, segments=8, rings=8)
    print(f"   Base sphere: {base_sphere}")
    
    smooth_sphere = SubdivisionSurface.subdivide(base_sphere, iterations=2)
    print(f"   After 2 subdivisions: {smooth_sphere}")
    
    smooth_sphere_obj = os.path.join(output_dir, "smooth_sphere.obj")
    smooth_sphere_stl = os.path.join(output_dir, "smooth_sphere.stl")
    smooth_sphere.export_obj(smooth_sphere_obj)
    smooth_sphere.export_stl(smooth_sphere_stl)
    print(f"   Exported: {smooth_sphere_obj}")
    print()
    
    # 2. Bulged sphere (muscle-like)
    print("2. Creating bulged sphere with sculpting (muscle effect)...")
    sphere = ModelGenerator.create_sphere(radius=1.0, segments=16, rings=16)
    bulged = MeshSculpting.bulge(sphere, center=(0, 0, 0), radius=1.5, strength=0.4)
    print(f"   {bulged}")
    
    bulged_obj = os.path.join(output_dir, "bulged_sphere.obj")
    bulged.export_obj(bulged_obj)
    print(f"   Exported: {bulged_obj}")
    print()
    
    # 3. Twisted cylinder (cool effect)
    print("3. Creating twisted cylinder...")
    cylinder = ModelGenerator.create_cylinder(radius=0.5, height=3.0, segments=32)
    twisted = MeshSculpting.twist(cylinder, axis='y', angle=180, height_factor=0.3)
    print(f"   {twisted}")
    
    twisted_obj = os.path.join(output_dir, "twisted_cylinder.obj")
    twisted.export_obj(twisted_obj)
    print(f"   Exported: {twisted_obj}")
    print()
    
    # 4. Tapered cone
    print("4. Creating tapered cylinder (organic shape)...")
    cyl = ModelGenerator.create_cylinder(radius=0.8, height=2.5, segments=24)
    tapered = MeshSculpting.taper(cyl, axis='y', amount=0.8)
    print(f"   {tapered}")
    
    tapered_obj = os.path.join(output_dir, "tapered_cone.obj")
    tapered.export_obj(tapered_obj)
    print(f"   Exported: {tapered_obj}")
    print()
    
    # 5. Detailed humanoid - Average proportions
    print("5. Creating detailed humanoid character (average proportions)...")
    humanoid = DetailedHumanoidGenerator.create_humanoid(height=6.0, proportions='average')
    print(f"   {humanoid}")
    
    humanoid_obj = os.path.join(output_dir, "humanoid_average.obj")
    humanoid_stl = os.path.join(output_dir, "humanoid_average.stl")
    humanoid.export_obj(humanoid_obj)
    humanoid.export_stl(humanoid_stl)
    print(f"   Exported: {humanoid_obj}")
    print()
    
    # 6. Athletic humanoid
    print("6. Creating athletic humanoid character...")
    athletic = DetailedHumanoidGenerator.create_humanoid(height=6.5, proportions='athletic')
    print(f"   {athletic}")
    
    athletic_obj = os.path.join(output_dir, "humanoid_athletic.obj")
    athletic.export_obj(athletic_obj)
    print(f"   Exported: {athletic_obj}")
    print()
    
    # 7. Heroic humanoid
    print("7. Creating heroic humanoid character (game character proportions)...")
    heroic = DetailedHumanoidGenerator.create_humanoid(height=7.0, proportions='heroic')
    print(f"   {heroic}")
    
    heroic_obj = os.path.join(output_dir, "humanoid_heroic.obj")
    heroic_stl = os.path.join(output_dir, "humanoid_heroic.stl")
    heroic.export_obj(heroic_obj)
    heroic.export_stl(heroic_stl)
    print(f"   Exported: {heroic_obj}")
    print()
    
    # 8. Armored character (like Master Chief / game heroes)
    print("8. Creating ARMORED CHARACTER (Master Chief / game hero style)...")
    print("   This is the COOL ONE with armor plates and helmet!")
    armored = DetailedHumanoidGenerator.create_armored_character(height=7.5)
    print(f"   {armored}")
    
    armored_obj = os.path.join(output_dir, "armored_hero.obj")
    armored_stl = os.path.join(output_dir, "armored_hero.stl")
    armored.export_obj(armored_obj)
    armored.export_stl(armored_stl)
    print(f"   Exported: {armored_obj}")
    print(f"   Exported: {armored_stl}")
    print()
    
    # 9. Detailed sphere with surface bumps
    print("9. Creating sphere with procedural surface detail (bumpy texture)...")
    sphere_base = ModelGenerator.create_sphere(radius=1.2, segments=24, rings=24)
    detailed_sphere = ProceduralDetails.add_surface_detail(sphere_base, 
                                                           detail_type='bumps', 
                                                           intensity=0.15)
    print(f"   {detailed_sphere}")
    
    detailed_obj = os.path.join(output_dir, "detailed_sphere.obj")
    detailed_sphere.export_obj(detailed_obj)
    print(f"   Exported: {detailed_obj}")
    print()
    
    # 10. Complex sculpted model
    print("10. Creating complex sculpted model (combined effects)...")
    base = ModelGenerator.create_torus(major_radius=1.5, minor_radius=0.4, 
                                       major_segments=32, minor_segments=16)
    # Apply multiple effects
    sculpted = MeshSculpting.twist(base, axis='y', angle=90, height_factor=0.2)
    sculpted = MeshSculpting.bulge(sculpted, center=(0, 0, 0), radius=2.0, strength=0.3)
    sculpted = ProceduralDetails.add_surface_detail(sculpted, detail_type='bumps', intensity=0.1)
    print(f"   {sculpted}")
    
    sculpted_obj = os.path.join(output_dir, "sculpted_torus.obj")
    sculpted.export_obj(sculpted_obj)
    print(f"   Exported: {sculpted_obj}")
    print()
    
    print("=" * 70)
    print("ADVANCED GENERATION COMPLETE!")
    print("=" * 70)
    print(f"\nAll advanced models saved to '{output_dir}/' directory.\n")
    print("✨ COOL MODELS CREATED:")
    print("  • Smooth sphere (subdivision surfaces)")
    print("  • Bulged/muscular sphere")
    print("  • Twisted cylinder")
    print("  • Organic tapered cone")
    print("  • Detailed humanoid characters (3 body types)")
    print("  • ⭐ ARMORED HERO (Master Chief style) - THE COOLEST!")
    print("  • Procedurally detailed sphere")
    print("  • Complex sculpted torus")
    print("\n🎮 The armored character is the closest to game characters like")
    print("   Master Chief, with armor plates, shoulder pads, and helmet!")
    print("\n📦 All models are procedurally generated - NO AI/ML!")
    print("=" * 70)

if __name__ == "__main__":
    main()
