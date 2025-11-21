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
import time
from typing import Dict, Any, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

# FIX: robust recv helper
def _recv_all(conn, n, timeout=5.0):
    """Read exactly n bytes or raise IOError on EOF/timeout"""
    conn.settimeout(timeout)
    data = b''
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise IOError("Unexpected EOF while reading")
        data += chunk
    return data

@dataclass
class Concept:
    """A concept in the shared representation space"""
    concept_id: str
    name: str
    concept_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    relationships: List[Tuple[str, str, float]] = field(default_factory=list)
    activation_level: float = 0.0
    created_at: float = 0.0
    last_activated: float = 0.0

class RepresentationLayer:
    """Shared concept space for all brain lobes"""
    
    def __init__(self, socket_path="/tmp/representation.sock"):
        self.socket_path = socket_path
        self.running = True
        
        # Concept storage
        self.concepts: Dict[str, Concept] = {}
        self.concept_counter = 0
        
        # Active concepts
        self.active_concepts: Set[str] = set()
        
        # Spreading activation parameters
        self.activation_decay = 0.1
        self.activation_threshold = 0.3
        self.spread_strength = 0.7
        
        self._initialize_basic_concepts()
        
    def _initialize_basic_concepts(self):
        """Initialize comprehensive concept network"""
        # Create basic emotion concepts
        emotions = ['happy', 'sad', 'angry', 'excited', 'calm', 'worried', 'curious']
        for emotion in emotions:
            self.create_concept(emotion, 'emotion', {'intensity_range': (0.0, 1.0)})
        
        # Create basic action concepts
        actions = ['think', 'feel', 'speak', 'learn', 'understand']
        for action in actions:
            self.create_concept(action, 'action', {})
    
    def create_concept(self, name: str, concept_type: str, properties: Dict[str, Any]) -> str:
        """Create a new concept"""
        concept_id = f"concept_{self.concept_counter}"
        self.concept_counter += 1
        
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
    
    def activate_concept(self, concept_id: str, activation_level: float = 1.0):
        """Activate a concept and spread activation to related concepts"""
        if concept_id not in self.concepts:
            return
        
        concept = self.concepts[concept_id]
        concept.activation_level = min(1.0, concept.activation_level + activation_level)
        concept.last_activated = time.time()
        self.active_concepts.add(concept_id)
        
        for relation_type, target_id, strength in concept.relationships:
            if target_id in self.concepts:
                spread_amount = activation_level * strength * self.spread_strength
                self.activate_concept(target_id, spread_amount)
    
    def get_active_concepts(self) -> List[Concept]:
        """Get currently active concepts"""
        return [self.concepts[cid] for cid in self.active_concepts if cid in self.concepts]
    
    def start(self):
        """Start representation layer with FIX: per-connection timeout"""
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
            
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        sock.settimeout(1.0)  # FIX: accept timeout
        
        print(f"🔗 Representation Layer: Online at {self.socket_path}")
        print(f"   Concepts: {len(self.concepts)}")
        
        while self.running:
            try:
                try:
                    conn, _ = sock.accept()
                except socket.timeout:
                    continue  # FIX: allow check of self.running
                
                # FIX: per-connection timeout + recv_all
                try:
                    conn.settimeout(5)
                    
                    length_data = _recv_all(conn, 4, timeout=5)
                    msg_length = struct.unpack('!I', length_data)[0]
                    
                    # FIX: validate message length
                    if msg_length <= 0 or msg_length > 10_000_000:
                        raise ValueError(f"Invalid message length: {msg_length}")
                    
                    data = _recv_all(conn, msg_length, timeout=5)
                    message = json.loads(data.decode('utf-8'))
                    
                    result = self.process_message(message)
                    
                    response_data = json.dumps(result).encode('utf-8')
                    response_length = struct.pack('!I', len(response_data))
                    conn.sendall(response_length + response_data)
                    
                except Exception as e:
                    # FIX: try to send error
                    try:
                        err = {'status': 'error', 'message': str(e)}
                        conn.sendall(struct.pack('!I', len(json.dumps(err).encode('utf-8'))) + json.dumps(err).encode('utf-8'))
                    except Exception:
                        pass
                finally:
                    # FIX: always close
                    try:
                        conn.close()
                    except Exception:
                        pass
                
            except Exception as e:
                print(f"❌ Representation error: {e}")
                try:
                    conn.close()
                except:
                    pass
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming message"""
        msg_type = message.get('type')
        
        # FIX: add health probe
        if msg_type == 'health':
            return {'status': 'success', 'healthy': True, 'pid': os.getpid()}
        
        if msg_type == 'translate_from':
            lobe_name = message.get('lobe')
            data = message.get('data', {})
            # Placeholder - activate concepts from data
            return {'status': 'success', 'activated_concepts': []}
            
        elif msg_type == 'translate_to':
            concept_ids = message.get('concept_ids', [])
            translated = {
                'concepts': [
                    {'id': c.concept_id, 'name': c.name, 'activation': c.activation_level}
                    for c in [self.concepts.get(cid) for cid in concept_ids] if c
                ]
            }
            return {'status': 'success', 'translated': translated}
            
        elif msg_type == 'get_active':
            active = self.get_active_concepts()
            return {
                'status': 'success',
                'active_concepts': [
                    {'id': c.concept_id, 'name': c.name, 'activation': c.activation_level}
                    for c in active
                ]
            }
            
        elif msg_type == 'get_highly_active':
            threshold = message.get('threshold', 0.6)
            highly_active = [c for c in self.get_active_concepts() if c.activation_level >= threshold]
            return {
                'status': 'success',
                'highly_active_concepts': [
                    {'id': c.concept_id, 'name': c.name, 'activation': c.activation_level}
                    for c in highly_active
                ]
            }
            
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
