"""
Demonstration of the 3D model generation system.
Creates various high-quality 3D models without AI/ML.
"""

from model_3d import ModelGenerator, ComplexModelBuilder
import os

def main():
    print("=" * 70)
    print("3D MODEL GENERATOR DEMONSTRATION")
    print("Creating high-quality 3D models from scratch - No AI/ML")
    print("=" * 70)
    print()
    
    # Create output directory
    output_dir = "models_output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}/")
        print()
    
    # Generate basic shapes
    print("Generating basic 3D shapes...")
    print()
    
    # 1. Cube
    print("1. Creating a cube...")
    cube = ModelGenerator.create_cube(size=2.0)
    cube_obj = os.path.join(output_dir, "cube.obj")
    cube_stl = os.path.join(output_dir, "cube.stl")
    cube.export_obj(cube_obj)
    cube.export_stl(cube_stl)
    print(f"   {cube}")
    print(f"   Exported: {cube_obj}")
    print(f"   Exported: {cube_stl}")
    print()
    
    # 2. Sphere
    print("2. Creating a high-resolution sphere...")
    sphere = ModelGenerator.create_sphere(radius=1.5, segments=32, rings=32)
    sphere_obj = os.path.join(output_dir, "sphere.obj")
    sphere_stl = os.path.join(output_dir, "sphere.stl")
    sphere.export_obj(sphere_obj)
    sphere.export_stl(sphere_stl)
    print(f"   {sphere}")
    print(f"   Exported: {sphere_obj}")
    print(f"   Exported: {sphere_stl}")
    print()
    
    # 3. Cylinder
    print("3. Creating a cylinder...")
    cylinder = ModelGenerator.create_cylinder(radius=1.0, height=3.0, segments=24)
    cylinder_obj = os.path.join(output_dir, "cylinder.obj")
    cylinder_stl = os.path.join(output_dir, "cylinder.stl")
    cylinder.export_obj(cylinder_obj)
    cylinder.export_stl(cylinder_stl)
    print(f"   {cylinder}")
    print(f"   Exported: {cylinder_obj}")
    print(f"   Exported: {cylinder_stl}")
    print()
    
    # 4. Torus
    print("4. Creating a torus (donut)...")
    torus = ModelGenerator.create_torus(major_radius=1.5, minor_radius=0.4, 
                                        major_segments=32, minor_segments=16)
    torus_obj = os.path.join(output_dir, "torus.obj")
    torus_stl = os.path.join(output_dir, "torus.stl")
    torus.export_obj(torus_obj)
    torus.export_stl(torus_stl)
    print(f"   {torus}")
    print(f"   Exported: {torus_obj}")
    print(f"   Exported: {torus_stl}")
    print()
    
    # 5. Pyramid
    print("5. Creating a pyramid...")
    pyramid = ModelGenerator.create_pyramid(base_size=2.0, height=2.5)
    pyramid_obj = os.path.join(output_dir, "pyramid.obj")
    pyramid_stl = os.path.join(output_dir, "pyramid.stl")
    pyramid.export_obj(pyramid_obj)
    pyramid.export_stl(pyramid_stl)
    print(f"   {pyramid}")
    print(f"   Exported: {pyramid_obj}")
    print(f"   Exported: {pyramid_stl}")
    print()
    
    # Create complex model
    print("6. Creating a complex model (snowman)...")
    builder = ComplexModelBuilder("Snowman")
    
    # Bottom sphere (body)
    bottom_sphere = ModelGenerator.create_sphere(radius=1.5, segments=24, rings=24)
    builder.add_model(bottom_sphere, offset_y=0, scale=1.0)
    
    # Middle sphere
    middle_sphere = ModelGenerator.create_sphere(radius=1.0, segments=24, rings=24)
    builder.add_model(middle_sphere, offset_y=2.5, scale=1.0)
    
    # Top sphere (head)
    top_sphere = ModelGenerator.create_sphere(radius=0.7, segments=24, rings=24)
    builder.add_model(top_sphere, offset_y=4.2, scale=1.0)
    
    # Hat (cylinder + cone)
    hat_base = ModelGenerator.create_cylinder(radius=0.8, height=0.2, segments=16)
    builder.add_model(hat_base, offset_y=4.9, scale=1.0)
    
    hat_top = ModelGenerator.create_cylinder(radius=0.5, height=0.8, segments=16)
    builder.add_model(hat_top, offset_y=5.5, scale=1.0)
    
    snowman = builder.get_model()
    snowman_obj = os.path.join(output_dir, "snowman.obj")
    snowman_stl = os.path.join(output_dir, "snowman.stl")
    snowman.export_obj(snowman_obj)
    snowman.export_stl(snowman_stl)
    print(f"   {snowman}")
    print(f"   Exported: {snowman_obj}")
    print(f"   Exported: {snowman_stl}")
    print()
    
    # Create another complex model
    print("7. Creating a complex model (robot)...")
    robot_builder = ComplexModelBuilder("Robot")
    
    # Body (cube)
    body = ModelGenerator.create_cube(size=2.0)
    robot_builder.add_model(body, offset_y=2.0, scale=1.0)
    
    # Head (cube)
    head = ModelGenerator.create_cube(size=1.2)
    robot_builder.add_model(head, offset_y=4.0, scale=1.0)
    
    # Arms (cylinders)
    arm_left = ModelGenerator.create_cylinder(radius=0.3, height=2.0, segments=12)
    robot_builder.add_model(arm_left, offset_x=-1.5, offset_y=2.0, scale=1.0)
    
    arm_right = ModelGenerator.create_cylinder(radius=0.3, height=2.0, segments=12)
    robot_builder.add_model(arm_right, offset_x=1.5, offset_y=2.0, scale=1.0)
    
    # Legs (cylinders)
    leg_left = ModelGenerator.create_cylinder(radius=0.4, height=2.5, segments=12)
    robot_builder.add_model(leg_left, offset_x=-0.6, offset_y=-0.25, scale=1.0)
    
    leg_right = ModelGenerator.create_cylinder(radius=0.4, height=2.5, segments=12)
    robot_builder.add_model(leg_right, offset_x=0.6, offset_y=-0.25, scale=1.0)
    
    # Antenna (small cylinder)
    antenna = ModelGenerator.create_cylinder(radius=0.1, height=0.8, segments=8)
    robot_builder.add_model(antenna, offset_y=5.2, scale=1.0)
    
    robot = robot_builder.get_model()
    robot_obj = os.path.join(output_dir, "robot.obj")
    robot_stl = os.path.join(output_dir, "robot.stl")
    robot.export_obj(robot_obj)
    robot.export_stl(robot_stl)
    print(f"   {robot}")
    print(f"   Exported: {robot_obj}")
    print(f"   Exported: {robot_stl}")
    print()
    
    print("=" * 70)
    print("GENERATION COMPLETE!")
    print("=" * 70)
    print(f"\nAll models have been exported to the '{output_dir}/' directory.")
    print("\nSupported formats:")
    print("  - OBJ: Universal format, can be opened in Blender, Maya, 3ds Max, etc.")
    print("  - STL: Standard for 3D printing")
    print("\nTo view the models:")
    print("  - Open .obj files in any 3D software (Blender is free)")
    print("  - Use online viewers like: https://3dviewer.net/")
    print("  - Import into 3D printing software for STL files")
    print("\nAll models are procedurally generated - NO AI/ML USED!")
    print("=" * 70)

if __name__ == "__main__":
    main()
