#!/usr/bin/env python3
"""
Representation Layer - Shared Concept Language
The "corpus callosum" - translates between all brain lobes
Provides a common language for concepts, relationships, and meaning
"""

import socket
import struct
import json
import os
from typing import Dict, Any, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

@dataclass
class Concept:
    """A concept in the shared representation space"""
    concept_id: str
    name: str
    concept_type: str  # 'object', 'action', 'emotion', 'abstract', 'relation'
    properties: Dict[str, Any] = field(default_factory=dict)
    relationships: List[Tuple[str, str, float]] = field(default_factory=list)  # (relation_type, target_id, strength)
    activation_level: float = 0.0
    created_at: float = 0.0
    last_activated: float = 0.0

@dataclass
class ConceptRelation:
    """Relationship between concepts"""
    source_id: str
    target_id: str
    relation_type: str  # 'is_a', 'has_property', 'causes', 'similar_to', 'opposite_of', etc.
    strength: float
    bidirectional: bool = False

class RepresentationLayer:
    """Shared concept space for all brain lobes"""
    
    def __init__(self, socket_path="/tmp/representation.sock"):
        self.socket_path = socket_path
        self.running = True
        
        # Concept storage
        self.concepts: Dict[str, Concept] = {}
        self.concept_counter = 0
        
        # Active concepts (currently being processed)
        self.active_concepts: Set[str] = set()
        
        # Spreading activation parameters
        self.activation_decay = 0.1
        self.activation_threshold = 0.3
        self.spread_strength = 0.7
        
        # Initialize basic concepts
        self._initialize_basic_concepts()
        
    def _initialize_basic_concepts(self):
        """Initialize comprehensive concept network"""
        import json
        
        # Load concept data
        try:
            concept_file = os.path.join(os.path.dirname(__file__), 'concept_data.json')
            with open(concept_file, 'r') as f:
                data = json.load(f)
            
            # Create emotion concepts
            for emotion in data.get('emotions', []):
                self.create_concept(emotion, 'emotion', {'intensity_range': (0.0, 1.0)})
            
            # Create object concepts
            for obj in data.get('objects', []):
                self.create_concept(obj, 'object', {})
            
            # Create action concepts
            for action in data.get('actions', []):
                self.create_concept(action, 'action', {})
            
            # Create abstract concepts
            for abstract in data.get('abstract', []):
                self.create_concept(abstract, 'abstract', {})
            
            print(f"✅ Loaded {len(self.concepts)} concepts from dataset")
            
            # Create relationships
            relations_data = data.get('relations', [])
            relationship_count = 0
            
            for relation_type_data in relations_data:
                rel_type = relation_type_data.get('type')
                pairs = relation_type_data.get('pairs', [])
                
                for pair in pairs:
                    if len(pair) == 2:
                        concept_a = self.find_concept_by_name(pair[0])
                        concept_b = self.find_concept_by_name(pair[1])
                        
                        if concept_a and concept_b:
                            self.add_relationship(
                                concept_a.concept_id,
                                concept_b.concept_id,
                                rel_type,
                                strength=1.0,
                                bidirectional=(rel_type in ['similar_to', 'opposite_of'])
                            )
                            relationship_count += 1
            
            print(f"✅ Created {relationship_count} concept relationships")
            
        except FileNotFoundError:
            print("⚠️  concept_data.json not found - loading minimal concepts")
            # Fallback to minimal set
            for emotion in ['happy', 'sad', 'angry', 'excited']:
                self.create_concept(emotion, 'emotion', {})
            for action in ['think', 'feel', 'speak']:
                self.create_concept(action, 'action', {})
    
    def create_concept(self, name: str, concept_type: str, properties: Dict[str, Any]) -> str:
        """Create a new concept"""
        concept_id = f"concept_{self.concept_counter}"
        self.concept_counter += 1
        
        import time
        concept = Concept(
            concept_id=concept_id,
            name=name,
            concept_type=concept_type,
            properties=properties,
            created_at=time.time()
        )
        
        self.concepts[concept_id] = concept
        return concept_id
    
    def get_concept(self, concept_id: str) -> Optional[Concept]:
        """Get a concept by ID"""
        return self.concepts.get(concept_id)
    
    def find_concept_by_name(self, name: str) -> Optional[Concept]:
        """Find a concept by name"""
        name_lower = name.lower()
        for concept in self.concepts.values():
            if concept.name.lower() == name_lower:
                return concept
        return None
    
    def add_relationship(self, source_id: str, target_id: str, relation_type: str, strength: float = 1.0, bidirectional: bool = False):
        """Add a relationship between concepts"""
        if source_id not in self.concepts or target_id not in self.concepts:
            return False
        
        # Add relationship to source concept
        self.concepts[source_id].relationships.append((relation_type, target_id, strength))
        
        # Add reverse relationship if bidirectional
        if bidirectional:
            self.concepts[target_id].relationships.append((relation_type, source_id, strength))
        
        return True
    
    def activate_concept(self, concept_id: str, activation_level: float = 1.0):
        """Activate a concept and spread activation to related concepts"""
        if concept_id not in self.concepts:
            return
        
        import time
        concept = self.concepts[concept_id]
        concept.activation_level = min(1.0, concept.activation_level + activation_level)
        concept.last_activated = time.time()
        self.active_concepts.add(concept_id)
        
        # Spread activation to related concepts
        for relation_type, target_id, strength in concept.relationships:
            if target_id in self.concepts:
                spread_amount = activation_level * strength * self.spread_strength
                self.activate_concept(target_id, spread_amount)
    
    def decay_activation(self):
        """Decay activation levels over time"""
        to_remove = []
        for concept_id in self.active_concepts:
            concept = self.concepts[concept_id]
            concept.activation_level *= (1.0 - self.activation_decay)
            
            if concept.activation_level < self.activation_threshold:
                concept.activation_level = 0.0
                to_remove.append(concept_id)
        
        for concept_id in to_remove:
            self.active_concepts.remove(concept_id)
    
    def get_active_concepts(self) -> List[Concept]:
        """Get currently active concepts"""
        return [self.concepts[cid] for cid in self.active_concepts if cid in self.concepts]
    
    def get_highly_active_concepts(self, threshold: float = 0.6) -> List[Concept]:
        """Filter: only return highly activated concepts for reasoning"""
        highly_active = []
        for cid in self.active_concepts:
            if cid in self.concepts:
                concept = self.concepts[cid]
                if concept.activation_level >= threshold:
                    highly_active.append(concept)
        return highly_active
    
    def translate_from_lobe(self, lobe_name: str, data: Dict[str, Any]) -> List[str]:
        """Translate lobe-specific data into shared concept space"""
        activated_concepts = []
        
        if lobe_name == "perception":
            # Translate perception data to concepts
            words = data.get('words', [])
            emotions = data.get('emotions', [])
            
            # Activate word concepts
            for word in words:
                concept = self.find_concept_by_name(word)
                if concept:
                    self.activate_concept(concept.concept_id)
                    activated_concepts.append(concept.concept_id)
                else:
                    # Create new concept for unknown word
                    concept_id = self.create_concept(word, 'unknown', {})
                    self.activate_concept(concept_id)
                    activated_concepts.append(concept_id)
            
            # Activate emotion concepts
            for emotion in emotions:
                concept = self.find_concept_by_name(emotion)
                if concept:
                    self.activate_concept(concept.concept_id, 0.8)
                    activated_concepts.append(concept.concept_id)
        
        elif lobe_name == "emotion":
            # Translate emotional state to concepts
            emotion = data.get('emotion')
            intensity = data.get('intensity', 0.5)
            
            if emotion:
                concept = self.find_concept_by_name(emotion)
                if concept:
                    self.activate_concept(concept.concept_id, intensity)
                    activated_concepts.append(concept.concept_id)
        
        elif lobe_name == "notus":
            # Translate memory data to concepts
            memories = data.get('memories', [])
            for memory in memories:
                # Extract concepts from memory content
                content = memory.get('content', '')
                words = content.split()
                for word in words[:10]:  # Limit to first 10 words
                    concept = self.find_concept_by_name(word)
                    if concept:
                        self.activate_concept(concept.concept_id, 0.5)
                        activated_concepts.append(concept.concept_id)
        
        return activated_concepts
    
    def translate_to_lobe(self, lobe_name: str, concept_ids: List[str]) -> Dict[str, Any]:
        """Translate shared concepts into lobe-specific format"""
        concepts_data = []
        
        for concept_id in concept_ids:
            concept = self.get_concept(concept_id)
            if concept:
                concepts_data.append({
                    'id': concept.concept_id,
                    'name': concept.name,
                    'type': concept.concept_type,
                    'activation': concept.activation_level,
                    'properties': concept.properties
                })
        
        return {
            'concepts': concepts_data,
            'active_count': len(self.active_concepts)
        }
    
    def get_concept_network(self, concept_id: str, depth: int = 2) -> Dict[str, Any]:
        """Get network of related concepts"""
        if concept_id not in self.concepts:
            return {}
        
        visited = set()
        network = {'nodes': [], 'edges': []}
        
        def explore(cid: str, current_depth: int):
            if current_depth > depth or cid in visited:
                return
            
            visited.add(cid)
            concept = self.concepts[cid]
            
            network['nodes'].append({
                'id': cid,
                'name': concept.name,
                'type': concept.concept_type,
                'activation': concept.activation_level
            })
            
            for relation_type, target_id, strength in concept.relationships:
                if target_id in self.concepts:
                    network['edges'].append({
                        'source': cid,
                        'target': target_id,
                        'relation': relation_type,
                        'strength': strength
                    })
                    explore(target_id, current_depth + 1)
        
        explore(concept_id, 0)
        return network
    
    def start(self):
        """Start representation layer as independent process"""
        # Remove old socket if exists
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
            
        # Create Unix socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        
        print(f"🔗 Representation Layer: Online at {self.socket_path}")
        print(f"   Concepts: {len(self.concepts)}")
        print(f"   Active concepts: {len(self.active_concepts)}")
        
        while self.running:
            try:
                # Accept connection
                conn, _ = sock.accept()
                
                # Read message length
                length_data = conn.recv(4)
                if not length_data:
                    conn.close()
                    continue
                    
                msg_length = struct.unpack('!I', length_data)[0]
                
                # Read full message
                data = b''
                while len(data) < msg_length:
                    chunk = conn.recv(min(msg_length - len(data), 4096))
                    if not chunk:
                        break
                    data += chunk
                
                # Parse message
                message = json.loads(data.decode('utf-8'))
                
                # Process message
                result = self.process_message(message)
                
                # Send response
                response_data = json.dumps(result).encode('utf-8')
                response_length = struct.pack('!I', len(response_data))
                conn.send(response_length + response_data)
                conn.close()
                
                # Decay activation periodically
                self.decay_activation()
                
            except Exception as e:
                print(f"❌ Representation error: {e}")
                try:
                    conn.close()
                except:
                    pass
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming message"""
        msg_type = message.get('type')
        
        if msg_type == 'translate_from':
            # Translate from lobe to shared space
            lobe_name = message.get('lobe')
            data = message.get('data', {})
            activated = self.translate_from_lobe(lobe_name, data)
            return {'status': 'success', 'activated_concepts': activated}
            
        elif msg_type == 'translate_to':
            # Translate from shared space to lobe
            lobe_name = message.get('lobe')
            concept_ids = message.get('concept_ids', [])
            translated = self.translate_to_lobe(lobe_name, concept_ids)
            return {'status': 'success', 'translated': translated}
            
        elif msg_type == 'get_active':
            # Get active concepts
            active = self.get_active_concepts()
            return {
                'status': 'success',
                'active_concepts': [
                    {'id': c.concept_id, 'name': c.name, 'activation': c.activation_level}
                    for c in active
                ]
            }
            
        elif msg_type == 'get_highly_active':
            # Get only highly activated concepts (filtered for reasoning)
            threshold = message.get('threshold', 0.6)
            highly_active = self.get_highly_active_concepts(threshold)
            return {
                'status': 'success',
                'highly_active_concepts': [
                    {'id': c.concept_id, 'name': c.name, 'activation': c.activation_level}
                    for c in highly_active
                ]
            }
            
        elif msg_type == 'create_concept':
            # Create new concept
            name = message.get('name')
            concept_type = message.get('concept_type', 'unknown')
            properties = message.get('properties', {})
            concept_id = self.create_concept(name, concept_type, properties)
            return {'status': 'success', 'concept_id': concept_id}
            
        elif msg_type == 'add_relationship':
            # Add relationship between concepts
            source_id = message.get('source_id')
            target_id = message.get('target_id')
            relation_type = message.get('relation_type')
            strength = message.get('strength', 1.0)
            success = self.add_relationship(source_id, target_id, relation_type, strength)
            return {'status': 'success' if success else 'error'}
            
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

if __name__ == "__main__":
    layer = RepresentationLayer()
    try:
        layer.start()
    except KeyboardInterrupt:
        print("\n🛑 Representation layer shutting down...")
        layer.shutdown()

