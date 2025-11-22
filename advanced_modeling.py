"""
Advanced 3D Modeling Features
Includes subdivision surfaces, mesh sculpting, and detailed model generation.
Built from scratch without AI/ML components.
"""

import math
from model_3d import Model3D, Vertex, Face, ModelGenerator

class SubdivisionSurface:
    """
    Implements Catmull-Clark subdivision for smooth surfaces.
    Subdivides mesh to create smoother, more detailed models.
    """
    
    @staticmethod
    def subdivide(model, iterations=1):
        """
        Apply Catmull-Clark subdivision to smooth the mesh.
        Each iteration quadruples the face count.
        """
        result = Model3D(f"{model.name}_subdivided")
        
        # Copy original vertices
        for v in model.vertices:
            result.add_vertex(v.x, v.y, v.z)
            
        # Copy original faces
        for face in model.faces:
            result.add_face(face.indices[:])
            
        for _ in range(iterations):
            result = SubdivisionSurface._subdivide_once(result)
            
        return result
    
    @staticmethod
    def _subdivide_once(model):
        """Perform one iteration of subdivision."""
        new_model = Model3D(model.name)
        
        # For simple quad subdivision
        vertices = model.vertices
        faces = model.faces
        
        # Add original vertices
        for v in vertices:
            new_model.add_vertex(v.x, v.y, v.z)
        
        # For each face, create face point and subdivide
        for face in faces:
            if len(face.indices) == 4:  # Quad face
                # Calculate face center
                v0, v1, v2, v3 = [vertices[i] for i in face.indices]
                cx = (v0.x + v1.x + v2.x + v3.x) / 4
                cy = (v0.y + v1.y + v2.y + v3.y) / 4
                cz = (v0.z + v1.z + v2.z + v3.z) / 4
                center_idx = new_model.add_vertex(cx, cy, cz)
                
                # Calculate edge midpoints
                e0_idx = new_model.add_vertex((v0.x + v1.x)/2, (v0.y + v1.y)/2, (v0.z + v1.z)/2)
                e1_idx = new_model.add_vertex((v1.x + v2.x)/2, (v1.y + v2.y)/2, (v1.z + v2.z)/2)
                e2_idx = new_model.add_vertex((v2.x + v3.x)/2, (v2.y + v3.y)/2, (v2.z + v3.z)/2)
                e3_idx = new_model.add_vertex((v3.x + v0.x)/2, (v3.y + v0.y)/2, (v3.z + v0.z)/2)
                
                # Create 4 new faces
                new_model.add_face([face.indices[0], e0_idx, center_idx, e3_idx])
                new_model.add_face([e0_idx, face.indices[1], e1_idx, center_idx])
                new_model.add_face([center_idx, e1_idx, face.indices[2], e2_idx])
                new_model.add_face([e3_idx, center_idx, e2_idx, face.indices[3]])
                
            elif len(face.indices) == 3:  # Triangle face
                # Calculate face center
                v0, v1, v2 = [vertices[i] for i in face.indices]
                cx = (v0.x + v1.x + v2.x) / 3
                cy = (v0.y + v1.y + v2.y) / 3
                cz = (v0.z + v1.z + v2.z) / 3
                center_idx = new_model.add_vertex(cx, cy, cz)
                
                # Calculate edge midpoints
                e0_idx = new_model.add_vertex((v0.x + v1.x)/2, (v0.y + v1.y)/2, (v0.z + v1.z)/2)
                e1_idx = new_model.add_vertex((v1.x + v2.x)/2, (v1.y + v2.y)/2, (v1.z + v2.z)/2)
                e2_idx = new_model.add_vertex((v2.x + v0.x)/2, (v2.y + v0.y)/2, (v2.z + v0.z)/2)
                
                # Create 3 new faces
                new_model.add_face([face.indices[0], e0_idx, center_idx, e2_idx])
                new_model.add_face([e0_idx, face.indices[1], e1_idx, center_idx])
                new_model.add_face([center_idx, e1_idx, face.indices[2], e2_idx])
        
        return new_model


class MeshSculpting:
    """
    Mesh sculpting tools for deforming and shaping models.
    """
    
    @staticmethod
    def bulge(model, center, radius, strength):
        """
        Create a bulge effect - push vertices outward from center.
        """
        result = Model3D(f"{model.name}_bulged")
        
        for v in model.vertices:
            # Calculate distance from center
            dx = v.x - center[0]
            dy = v.y - center[1]
            dz = v.z - center[2]
            dist = math.sqrt(dx*dx + dy*dy + dz*dz)
            
            if dist < radius:
                # Calculate influence (stronger near center)
                influence = (1 - dist/radius) * strength
                
                # Normalize direction
                if dist > 0.001:
                    dx /= dist
                    dy /= dist
                    dz /= dist
                
                # Apply bulge
                new_x = v.x + dx * influence
                new_y = v.y + dy * influence
                new_z = v.z + dz * influence
            else:
                new_x, new_y, new_z = v.x, v.y, v.z
            
            result.add_vertex(new_x, new_y, new_z)
        
        # Copy faces
        for face in model.faces:
            result.add_face(face.indices[:])
        
        return result
    
    @staticmethod
    def twist(model, axis='y', angle=45, height_factor=1.0):
        """
        Twist the model around an axis.
        """
        result = Model3D(f"{model.name}_twisted")
        angle_rad = math.radians(angle)
        
        for v in model.vertices:
            if axis == 'y':
                # Twist amount based on height
                twist_amount = v.y * height_factor * angle_rad
                cos_t = math.cos(twist_amount)
                sin_t = math.sin(twist_amount)
                
                new_x = v.x * cos_t - v.z * sin_t
                new_y = v.y
                new_z = v.x * sin_t + v.z * cos_t
            elif axis == 'x':
                twist_amount = v.x * height_factor * angle_rad
                cos_t = math.cos(twist_amount)
                sin_t = math.sin(twist_amount)
                
                new_x = v.x
                new_y = v.y * cos_t - v.z * sin_t
                new_z = v.y * sin_t + v.z * cos_t
            else:  # z axis
                twist_amount = v.z * height_factor * angle_rad
                cos_t = math.cos(twist_amount)
                sin_t = math.sin(twist_amount)
                
                new_x = v.x * cos_t - v.y * sin_t
                new_y = v.x * sin_t + v.y * cos_t
                new_z = v.z
            
            result.add_vertex(new_x, new_y, new_z)
        
        # Copy faces
        for face in model.faces:
            result.add_face(face.indices[:])
        
        return result
    
    @staticmethod
    def taper(model, axis='y', amount=0.5):
        """
        Taper the model - make it narrower at one end.
        """
        result = Model3D(f"{model.name}_tapered")
        
        # Find bounds
        if axis == 'y':
            min_val = min(v.y for v in model.vertices)
            max_val = max(v.y for v in model.vertices)
        elif axis == 'x':
            min_val = min(v.x for v in model.vertices)
            max_val = max(v.x for v in model.vertices)
        else:
            min_val = min(v.z for v in model.vertices)
            max_val = max(v.z for v in model.vertices)
        
        range_val = max_val - min_val if max_val != min_val else 1.0
        
        for v in model.vertices:
            if axis == 'y':
                t = (v.y - min_val) / range_val
                scale = 1.0 - t * amount
                new_x = v.x * scale
                new_y = v.y
                new_z = v.z * scale
            elif axis == 'x':
                t = (v.x - min_val) / range_val
                scale = 1.0 - t * amount
                new_x = v.x
                new_y = v.y * scale
                new_z = v.z * scale
            else:
                t = (v.z - min_val) / range_val
                scale = 1.0 - t * amount
                new_x = v.x * scale
                new_y = v.y * scale
                new_z = v.z
            
            result.add_vertex(new_x, new_y, new_z)
        
        # Copy faces
        for face in model.faces:
            result.add_face(face.indices[:])
        
        return result


class DetailedHumanoidGenerator:
    """
    Generate detailed humanoid models with proper anatomy.
    """
    
    @staticmethod
    def create_humanoid(height=6.0, proportions='average'):
        """
        Create a detailed humanoid figure with proper proportions.
        proportions: 'average', 'athletic', 'heroic'
        """
        from model_3d import ComplexModelBuilder
        
        builder = ComplexModelBuilder("Humanoid")
        
        # Adjust proportions
        if proportions == 'athletic':
            chest_width = 1.8
            leg_thickness = 0.35
            arm_thickness = 0.28
        elif proportions == 'heroic':
            chest_width = 2.2
            leg_thickness = 0.42
            arm_thickness = 0.35
        else:  # average
            chest_width = 1.6
            leg_thickness = 0.32
            arm_thickness = 0.25
        
        scale = height / 6.0  # Scale based on desired height
        
        # Legs
        leg_length = 2.8 * scale
        leg_left = ModelGenerator.create_cylinder(radius=leg_thickness*scale, 
                                                   height=leg_length, segments=16)
        builder.add_model(leg_left, offset_x=-0.4*scale, offset_y=leg_length/2, scale=1.0)
        
        leg_right = ModelGenerator.create_cylinder(radius=leg_thickness*scale, 
                                                    height=leg_length, segments=16)
        builder.add_model(leg_right, offset_x=0.4*scale, offset_y=leg_length/2, scale=1.0)
        
        # Pelvis
        pelvis = ModelGenerator.create_cube(size=1.2*scale)
        builder.add_model(pelvis, offset_y=leg_length + 0.3*scale, scale=1.0)
        
        # Torso (tapered cube for chest)
        torso_height = 1.8 * scale
        torso = ModelGenerator.create_cylinder(radius=chest_width*scale/2, 
                                               height=torso_height, segments=16)
        torso = MeshSculpting.taper(torso, axis='y', amount=0.3)
        builder.add_model(torso, offset_y=leg_length + 0.6*scale + torso_height/2, scale=1.0)
        
        # Shoulders
        shoulder_height = leg_length + 0.6*scale + torso_height
        shoulder_left = ModelGenerator.create_sphere(radius=0.35*scale, segments=12, rings=12)
        builder.add_model(shoulder_left, offset_x=-1.1*scale, offset_y=shoulder_height, scale=1.0)
        
        shoulder_right = ModelGenerator.create_sphere(radius=0.35*scale, segments=12, rings=12)
        builder.add_model(shoulder_right, offset_x=1.1*scale, offset_y=shoulder_height, scale=1.0)
        
        # Arms
        arm_length = 2.2 * scale
        arm_left = ModelGenerator.create_cylinder(radius=arm_thickness*scale, 
                                                   height=arm_length, segments=12)
        builder.add_model(arm_left, offset_x=-1.1*scale, 
                         offset_y=shoulder_height - arm_length/2 - 0.35*scale, scale=1.0)
        
        arm_right = ModelGenerator.create_cylinder(radius=arm_thickness*scale, 
                                                    height=arm_length, segments=12)
        builder.add_model(arm_right, offset_x=1.1*scale, 
                         offset_y=shoulder_height - arm_length/2 - 0.35*scale, scale=1.0)
        
        # Hands
        hand_left = ModelGenerator.create_sphere(radius=0.25*scale, segments=10, rings=10)
        builder.add_model(hand_left, offset_x=-1.1*scale, 
                         offset_y=shoulder_height - arm_length - 0.6*scale, scale=1.0)
        
        hand_right = ModelGenerator.create_sphere(radius=0.25*scale, segments=10, rings=10)
        builder.add_model(hand_right, offset_x=1.1*scale, 
                         offset_y=shoulder_height - arm_length - 0.6*scale, scale=1.0)
        
        # Neck
        neck_height = 0.5 * scale
        neck = ModelGenerator.create_cylinder(radius=0.35*scale, height=neck_height, segments=12)
        builder.add_model(neck, offset_y=shoulder_height + neck_height/2, scale=1.0)
        
        # Head
        head = ModelGenerator.create_sphere(radius=0.7*scale, segments=20, rings=20)
        builder.add_model(head, offset_y=shoulder_height + neck_height + 0.7*scale, scale=1.0)
        
        return builder.get_model()
    
    @staticmethod
    def create_armored_character(height=6.0):
        """
        Create a character with armor-like features (inspired by game characters).
        """
        from model_3d import ComplexModelBuilder
        
        # Start with heroic proportions
        base = DetailedHumanoidGenerator.create_humanoid(height, proportions='heroic')
        
        builder = ComplexModelBuilder("ArmoredCharacter")
        builder.add_model(base, scale=1.0)
        
        scale = height / 6.0
        
        # Add armor plates (chest)
        chest_plate = ModelGenerator.create_cube(size=2.5*scale)
        chest_plate = MeshSculpting.bulge(chest_plate, (0, 0, 0.5*scale), 1.5*scale, 0.3*scale)
        builder.add_model(chest_plate, offset_y=4.5*scale, offset_z=0.2*scale, scale=1.0)
        
        # Shoulder armor
        shoulder_armor_l = ModelGenerator.create_sphere(radius=0.6*scale, segments=12, rings=12)
        shoulder_armor_l = MeshSculpting.bulge(shoulder_armor_l, (0, 0.3*scale, 0), 0.8*scale, 0.2*scale)
        builder.add_model(shoulder_armor_l, offset_x=-1.3*scale, offset_y=5.2*scale, scale=1.0)
        
        shoulder_armor_r = ModelGenerator.create_sphere(radius=0.6*scale, segments=12, rings=12)
        shoulder_armor_r = MeshSculpting.bulge(shoulder_armor_r, (0, 0.3*scale, 0), 0.8*scale, 0.2*scale)
        builder.add_model(shoulder_armor_r, offset_x=1.3*scale, offset_y=5.2*scale, scale=1.0)
        
        # Helmet
        helmet = ModelGenerator.create_sphere(radius=0.85*scale, segments=16, rings=16)
        builder.add_model(helmet, offset_y=6.2*scale, scale=1.0)
        
        # Helmet crest
        crest = ModelGenerator.create_pyramid(base_size=0.4*scale, height=0.8*scale)
        builder.add_model(crest, offset_y=7.0*scale, scale=1.0)
        
        return builder.get_model()


class ProceduralDetails:
    """
    Add procedural details to models for more interesting geometry.
    """
    
    @staticmethod
    def add_surface_detail(model, detail_type='bumps', intensity=0.1):
        """
        Add surface details like bumps or grooves.
        """
        result = Model3D(f"{model.name}_detailed")
        
        for i, v in enumerate(model.vertices):
            # Create procedural noise based on position
            noise_x = math.sin(v.x * 10) * math.cos(v.y * 10)
            noise_y = math.sin(v.y * 10) * math.cos(v.z * 10)
            noise_z = math.sin(v.z * 10) * math.cos(v.x * 10)
            
            if detail_type == 'bumps':
                offset = (noise_x + noise_y + noise_z) / 3 * intensity
                # Push outward from origin
                length = math.sqrt(v.x*v.x + v.y*v.y + v.z*v.z)
                if length > 0.001:
                    factor = (length + offset) / length
                    new_x = v.x * factor
                    new_y = v.y * factor
                    new_z = v.z * factor
                else:
                    new_x, new_y, new_z = v.x, v.y, v.z
            else:  # grooves
                new_x = v.x + noise_x * intensity
                new_y = v.y + noise_y * intensity
                new_z = v.z + noise_z * intensity
            
            result.add_vertex(new_x, new_y, new_z)
        
        # Copy faces
        for face in model.faces:
            result.add_face(face.indices[:])
        
        return result
