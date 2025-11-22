"""
3D Model Generator - Creates 3D models programmatically.
Built from scratch without AI/ML components.
"""

import math

class Vertex:
    """A point in 3D space."""
    
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z
        
    def __repr__(self):
        return f"Vertex({self.x:.2f}, {self.y:.2f}, {self.z:.2f})"
        
    def to_tuple(self):
        return (self.x, self.y, self.z)


class Face:
    """A face defined by vertex indices."""
    
    def __init__(self, vertex_indices):
        self.indices = vertex_indices
        
    def __repr__(self):
        return f"Face({self.indices})"


class Model3D:
    """
    A 3D model consisting of vertices and faces.
    Can export to various formats like OBJ, STL.
    """
    
    def __init__(self, name="Model"):
        self.name = name
        self.vertices = []
        self.faces = []
        self.normals = []
        
    def add_vertex(self, x, y, z):
        """Add a vertex to the model."""
        vertex = Vertex(x, y, z)
        self.vertices.append(vertex)
        return len(self.vertices) - 1
        
    def add_face(self, vertex_indices):
        """Add a face defined by vertex indices."""
        face = Face(vertex_indices)
        self.faces.append(face)
        return len(self.faces) - 1
        
    def calculate_normals(self):
        """Calculate face normals for lighting."""
        self.normals = []
        for face in self.faces:
            if len(face.indices) >= 3:
                # Get three vertices
                v0 = self.vertices[face.indices[0]]
                v1 = self.vertices[face.indices[1]]
                v2 = self.vertices[face.indices[2]]
                
                # Calculate two edges
                edge1_x = v1.x - v0.x
                edge1_y = v1.y - v0.y
                edge1_z = v1.z - v0.z
                
                edge2_x = v2.x - v0.x
                edge2_y = v2.y - v0.y
                edge2_z = v2.z - v0.z
                
                # Cross product for normal
                nx = edge1_y * edge2_z - edge1_z * edge2_y
                ny = edge1_z * edge2_x - edge1_x * edge2_z
                nz = edge1_x * edge2_y - edge1_y * edge2_x
                
                # Normalize
                length = math.sqrt(nx*nx + ny*ny + nz*nz)
                if length > 0:
                    nx /= length
                    ny /= length
                    nz /= length
                    
                self.normals.append((nx, ny, nz))
            else:
                self.normals.append((0, 0, 1))
                
    def export_obj(self, filename):
        """Export model to OBJ format."""
        with open(filename, 'w') as f:
            f.write(f"# {self.name}\n")
            f.write(f"# Vertices: {len(self.vertices)}\n")
            f.write(f"# Faces: {len(self.faces)}\n\n")
            
            # Write vertices
            for v in self.vertices:
                f.write(f"v {v.x} {v.y} {v.z}\n")
            f.write("\n")
            
            # Write faces (OBJ uses 1-based indexing)
            for face in self.faces:
                indices_str = " ".join(str(i + 1) for i in face.indices)
                f.write(f"f {indices_str}\n")
                
    def export_stl(self, filename):
        """Export model to STL format (ASCII)."""
        self.calculate_normals()
        
        with open(filename, 'w') as f:
            f.write(f"solid {self.name}\n")
            
            for i, face in enumerate(self.faces):
                if len(face.indices) < 3:
                    continue
                    
                normal = self.normals[i] if i < len(self.normals) else (0, 0, 1)
                f.write(f"  facet normal {normal[0]} {normal[1]} {normal[2]}\n")
                f.write(f"    outer loop\n")
                
                for idx in face.indices[:3]:  # STL only supports triangles
                    v = self.vertices[idx]
                    f.write(f"      vertex {v.x} {v.y} {v.z}\n")
                    
                f.write(f"    endloop\n")
                f.write(f"  endfacet\n")
                
            f.write(f"endsolid {self.name}\n")
            
    def __repr__(self):
        return f"Model3D(name='{self.name}', vertices={len(self.vertices)}, faces={len(self.faces)})"


class ModelGenerator:
    """
    Generates various 3D model shapes procedurally.
    """
    
    @staticmethod
    def create_cube(size=1.0):
        """Create a cube model."""
        model = Model3D("Cube")
        half = size / 2
        
        # 8 vertices of a cube
        vertices = [
            (-half, -half, -half),  # 0
            ( half, -half, -half),  # 1
            ( half,  half, -half),  # 2
            (-half,  half, -half),  # 3
            (-half, -half,  half),  # 4
            ( half, -half,  half),  # 5
            ( half,  half,  half),  # 6
            (-half,  half,  half),  # 7
        ]
        
        for v in vertices:
            model.add_vertex(v[0], v[1], v[2])
            
        # 6 faces (quads)
        faces = [
            [0, 1, 2, 3],  # front
            [4, 7, 6, 5],  # back
            [0, 4, 5, 1],  # bottom
            [2, 6, 7, 3],  # top
            [0, 3, 7, 4],  # left
            [1, 5, 6, 2],  # right
        ]
        
        for face in faces:
            model.add_face(face)
            
        return model
        
    @staticmethod
    def create_sphere(radius=1.0, segments=16, rings=16):
        """Create a sphere model using UV sphere algorithm."""
        model = Model3D("Sphere")
        
        # Generate vertices
        for ring in range(rings + 1):
            theta = ring * math.pi / rings
            sin_theta = math.sin(theta)
            cos_theta = math.cos(theta)
            
            for seg in range(segments):
                phi = seg * 2 * math.pi / segments
                sin_phi = math.sin(phi)
                cos_phi = math.cos(phi)
                
                x = radius * sin_theta * cos_phi
                y = radius * cos_theta
                z = radius * sin_theta * sin_phi
                
                model.add_vertex(x, y, z)
                
        # Generate faces
        for ring in range(rings):
            for seg in range(segments):
                current = ring * segments + seg
                next_seg = ring * segments + (seg + 1) % segments
                next_ring = (ring + 1) * segments + seg
                next_both = (ring + 1) * segments + (seg + 1) % segments
                
                # Create two triangles for each quad
                model.add_face([current, next_ring, next_both])
                model.add_face([current, next_both, next_seg])
                
        return model
        
    @staticmethod
    def create_cylinder(radius=1.0, height=2.0, segments=16):
        """Create a cylinder model."""
        model = Model3D("Cylinder")
        half_height = height / 2
        
        # Bottom center
        bottom_center = model.add_vertex(0, -half_height, 0)
        
        # Bottom ring
        bottom_ring = []
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            x = radius * math.cos(angle)
            z = radius * math.sin(angle)
            idx = model.add_vertex(x, -half_height, z)
            bottom_ring.append(idx)
            
        # Top ring
        top_ring = []
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            x = radius * math.cos(angle)
            z = radius * math.sin(angle)
            idx = model.add_vertex(x, half_height, z)
            top_ring.append(idx)
            
        # Top center
        top_center = model.add_vertex(0, half_height, 0)
        
        # Bottom cap
        for i in range(segments):
            next_i = (i + 1) % segments
            model.add_face([bottom_center, bottom_ring[next_i], bottom_ring[i]])
            
        # Side faces
        for i in range(segments):
            next_i = (i + 1) % segments
            model.add_face([bottom_ring[i], bottom_ring[next_i], top_ring[next_i], top_ring[i]])
            
        # Top cap
        for i in range(segments):
            next_i = (i + 1) % segments
            model.add_face([top_center, top_ring[i], top_ring[next_i]])
            
        return model
        
    @staticmethod
    def create_torus(major_radius=1.0, minor_radius=0.3, major_segments=24, minor_segments=12):
        """Create a torus (donut) model."""
        model = Model3D("Torus")
        
        # Generate vertices
        for i in range(major_segments):
            theta = 2 * math.pi * i / major_segments
            cos_theta = math.cos(theta)
            sin_theta = math.sin(theta)
            
            for j in range(minor_segments):
                phi = 2 * math.pi * j / minor_segments
                cos_phi = math.cos(phi)
                sin_phi = math.sin(phi)
                
                x = (major_radius + minor_radius * cos_phi) * cos_theta
                y = minor_radius * sin_phi
                z = (major_radius + minor_radius * cos_phi) * sin_theta
                
                model.add_vertex(x, y, z)
                
        # Generate faces
        for i in range(major_segments):
            next_i = (i + 1) % major_segments
            
            for j in range(minor_segments):
                next_j = (j + 1) % minor_segments
                
                v1 = i * minor_segments + j
                v2 = next_i * minor_segments + j
                v3 = next_i * minor_segments + next_j
                v4 = i * minor_segments + next_j
                
                model.add_face([v1, v2, v3, v4])
                
        return model
        
    @staticmethod
    def create_pyramid(base_size=1.0, height=1.5):
        """Create a pyramid with square base."""
        model = Model3D("Pyramid")
        half = base_size / 2
        
        # Base vertices
        model.add_vertex(-half, 0, -half)  # 0
        model.add_vertex( half, 0, -half)  # 1
        model.add_vertex( half, 0,  half)  # 2
        model.add_vertex(-half, 0,  half)  # 3
        
        # Apex
        model.add_vertex(0, height, 0)  # 4
        
        # Base face
        model.add_face([0, 1, 2, 3])
        
        # Side faces
        model.add_face([0, 1, 4])
        model.add_face([1, 2, 4])
        model.add_face([2, 3, 4])
        model.add_face([3, 0, 4])
        
        return model


class ComplexModelBuilder:
    """
    Build complex models by combining and transforming basic shapes.
    """
    
    def __init__(self, name="Complex Model"):
        self.model = Model3D(name)
        
    def add_model(self, source_model, offset_x=0, offset_y=0, offset_z=0, scale=1.0):
        """Add another model to this one with transformations."""
        vertex_offset = len(self.model.vertices)
        
        # Add vertices with transformations
        for v in source_model.vertices:
            x = v.x * scale + offset_x
            y = v.y * scale + offset_y
            z = v.z * scale + offset_z
            self.model.add_vertex(x, y, z)
            
        # Add faces with adjusted indices
        for face in source_model.faces:
            new_indices = [idx + vertex_offset for idx in face.indices]
            self.model.add_face(new_indices)
            
        return self
        
    def get_model(self):
        """Get the built model."""
        return self.model
