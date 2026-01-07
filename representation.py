#!/usr/bin/env python3
"""
Representation Layer - Shared Concept Language
The "corpus callosum" - translates between all brain lobes
Provides a common language for concepts, relationships, and meaning
"""

import json
import os
import time
import sys
from typing import Dict, Any, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from thalamus import get_thalamus

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
    
    def __init__(self):
        self.running = True
        # Direct reference to Thalamus (NO SOCKETS)
        self.thalamus = get_thalamus()
        
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
        # Query Notus to check if concept already exists
        try:
            notus_check = self._query_lobe('notus', {'type': 'concept_exists', 'name': name})
            if notus_check and notus_check.get('status') == 'success' and notus_check.get('exists', False):
                # Concept exists in Notus, use that one
                existing = notus_check.get('concept', {})
                if existing.get('concept_id'):
                    return existing['concept_id']
        except Exception:
            pass
        
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
        
        # Query Notus for concept if not found locally
        try:
            notus_concept = self._query_lobe('notus', {'type': 'get_concept', 'name': name})
            if notus_concept and notus_concept.get('status') == 'success':
                concept_data = notus_concept.get('concept', {})
                if concept_data:
                    # Create concept from Notus data
                    concept = Concept(
                        concept_id=concept_data.get('concept_id', f"concept_{self.concept_counter}"),
                        name=concept_data.get('name', name),
                        concept_type=concept_data.get('type', 'unknown'),
                        properties=concept_data.get('properties', {}),
                        created_at=concept_data.get('created_at', time.time())
                    )
                    self.concepts[concept.concept_id] = concept
                    return concept
        except Exception:
            pass
        
        return None
    
    def activate_concept(self, concept_id: str, activation_level: float = 1.0):
        """Activate a concept and spread activation to related concepts"""
        if concept_id not in self.concepts:
            return
        
        concept = self.concepts[concept_id]
        concept.activation_level = min(1.0, concept.activation_level + activation_level)
        concept.last_activated = time.time()
        self.active_concepts.add(concept_id)
        
        # Query Notus for related concepts to activate
        try:
            notus_related = self._query_lobe('notus', {'type': 'get_related_concepts', 'concept_id': concept_id})
            if notus_related and notus_related.get('status') == 'success':
                related = notus_related.get('related', [])
                for rel_data in related:
                    if isinstance(rel_data, dict):
                        rel_id = rel_data.get('concept_id', '')
                        strength = rel_data.get('strength', 0.5)
                        if rel_id and rel_id in self.concepts:
                            spread_amount = activation_level * strength * self.spread_strength
                            self.activate_concept(rel_id, spread_amount)
        except Exception:
            pass
        
        for relation_type, target_id, strength in concept.relationships:
            if target_id in self.concepts:
                spread_amount = activation_level * strength * self.spread_strength
                self.activate_concept(target_id, spread_amount)
    
    def get_active_concepts(self) -> List[Concept]:
        """Get currently active concepts"""
        local_active = [self.concepts[cid] for cid in self.active_concepts if cid in self.concepts]
        
        # Query Notus for related active concepts
        try:
            notus_related = self._query_lobe('notus', {'type': 'get_related_active', 'concepts': [c.concept_id for c in local_active]})
            if notus_related and notus_related.get('status') == 'success':
                related = notus_related.get('related', [])
                for rel_data in related:
                    if isinstance(rel_data, dict):
                        rel_id = rel_data.get('concept_id', '')
                        if rel_id and rel_id in self.concepts:
                            if rel_id not in self.active_concepts:
                                local_active.append(self.concepts[rel_id])
        except Exception:
            pass
        
        return local_active
    
    def _register_with_thalamus(self):
        """Register with Thalamus - DIRECT FUNCTION CALL (NO SOCKETS)"""
        try:
            result = self.thalamus.register_lobe('representation', self)
            if result.get('status') == 'success':
                print("✅ Representation registered with Thalamus (direct function calls)")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register with Thalamus: {e}")
            return False
    
    def start(self):
        """Start representation - register with Thalamus (NO SOCKETS)"""
        print(f"🔗 Representation Layer: Registering with Thalamus...")
        print(f"   Shared concept space for all lobes")
        print(f"   Communication: Direct function calls (NO SOCKETS)")
        
        # Register with Thalamus
        if not self._register_with_thalamus():
            print("❌ Failed to register with Thalamus")
            return
        
        # Keep running (Thalamus calls us directly, no listening loop needed)
        while self.running:
            time.sleep(0.1)
    
    def _query_lobe(self, lobe_name: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Query a lobe through Thalamus - DIRECT FUNCTION CALL"""
        try:
            msg_type = message.get('type', 'query')
            return self.thalamus.send_message(lobe_name, msg_type, message)
        except Exception:
            return None
    
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
        # No sockets to close

if __name__ == "__main__":
    layer = RepresentationLayer()
    try:
        layer.start()
    except KeyboardInterrupt:
        print("\n🛑 Representation layer shutting down...")
        layer.shutdown()
