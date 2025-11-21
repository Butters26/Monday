#!/usr/bin/env python3
"""
Pattern Recognition Lobe - Sees patterns in everything
Watches for co-occurrences, sequences, repetitions
Like how humans see faces in walls and patterns everywhere
"""

import socket
import struct
import json
import os
import time
from typing import Dict, Any, List, Tuple, Set, Optional
from collections import defaultdict, deque
from dataclasses import dataclass, field

@dataclass
class CoOccurrence:
    """Two things that appear together"""
    item_a: str
    item_b: str
    count: int = 0
    strength: float = 0.0
    last_seen: float = 0.0

@dataclass
class Sequence:
    """Pattern where A happens then B happens"""
    trigger: str
    follows: str
    count: int = 0
    confidence: float = 0.0
    last_seen: float = 0.0

@dataclass
class Cluster:
    """Group of things that keep appearing together"""
    items: Set[str]
    frequency: int = 0
    last_seen: float = 0.0

class PatternRecognitionLobe:
    """Watches everything and sees patterns"""
    
    def __init__(self, socket_path="/tmp/pattern.sock"):
        self.socket_path = socket_path
        self.running = True
        
        # Pattern storage
        self.co_occurrences: Dict[Tuple[str, str], CoOccurrence] = {}
        self.sequences: Dict[Tuple[str, str], Sequence] = {}
        self.clusters: List[Cluster] = []
        
        # Recent history for sequence detection
        self.recent_items = deque(maxlen=10)
        self.recent_concepts = deque(maxlen=20)
        
        # Thresholds
        self.co_occurrence_threshold = 3  # Need to see together 3+ times
        self.sequence_threshold = 2  # Need to see sequence 2+ times
        self.cluster_threshold = 4  # Need 4+ co-occurrences to form cluster
        
        # Decay - patterns fade if not reinforced
        self.decay_rate = 0.1
        self.last_decay = time.time()
        
    def observe(self, items: List[str], item_type: str = "concept") -> Dict[str, Any]:
        """
        Watch items and detect patterns
        items: list of concepts, words, or events
        item_type: what kind of items these are
        """
        current_time = time.time()
        patterns_found = {
            'co_occurrences': [],
            'sequences': [],
            'clusters': [],
            'new_patterns': False
        }
        
        # Add to recent history
        for item in items:
            self.recent_items.append((item, current_time))
            if item_type == "concept":
                self.recent_concepts.append((item, current_time))
        
        # Detect co-occurrences (things appearing together right now)
        for i, item_a in enumerate(items):
            for item_b in items[i+1:]:
                pattern = self._record_co_occurrence(item_a, item_b, current_time)
                if pattern and pattern.count >= self.co_occurrence_threshold:
                    patterns_found['co_occurrences'].append({
                        'items': [pattern.item_a, pattern.item_b],
                        'count': pattern.count,
                        'strength': pattern.strength
                    })
                    if pattern.count == self.co_occurrence_threshold:
                        patterns_found['new_patterns'] = True
        
        # Detect sequences (A happened, now B happened)
        if len(self.recent_items) >= 2:
            recent_list = list(self.recent_items)
            for i in range(len(recent_list) - 1):
                prev_item, prev_time = recent_list[i]
                curr_item, curr_time = recent_list[i + 1]
                
                # Only connect if they're close in time (within 30 seconds)
                if curr_time - prev_time < 30:
                    sequence = self._record_sequence(prev_item, curr_item, current_time)
                    if sequence and sequence.count >= self.sequence_threshold:
                        patterns_found['sequences'].append({
                            'trigger': sequence.trigger,
                            'follows': sequence.follows,
                            'count': sequence.count,
                            'confidence': sequence.confidence
                        })
                        if sequence.count == self.sequence_threshold:
                            patterns_found['new_patterns'] = True
        
        # Detect clusters (groups that keep appearing together)
        if len(items) >= 3:
            cluster = self._detect_cluster(items, current_time)
            if cluster:
                patterns_found['clusters'].append({
                    'items': list(cluster.items),
                    'frequency': cluster.frequency
                })
                patterns_found['new_patterns'] = True
        
        # Decay old patterns periodically
        if current_time - self.last_decay > 60:  # Every minute
            self._decay_patterns()
            self.last_decay = current_time
        
        return patterns_found
    
    def _record_co_occurrence(self, item_a: str, item_b: str, timestamp: float) -> Optional[CoOccurrence]:
        """Record that two items appeared together"""
        # Sort so (a,b) and (b,a) are treated the same
        pair = tuple(sorted([item_a, item_b]))
        
        if pair in self.co_occurrences:
            pattern = self.co_occurrences[pair]
            pattern.count += 1
            pattern.last_seen = timestamp
            # Strength increases with count but caps at 1.0
            pattern.strength = min(1.0, pattern.count / 10.0)
        else:
            pattern = CoOccurrence(
                item_a=pair[0],
                item_b=pair[1],
                count=1,
                strength=0.1,
                last_seen=timestamp
            )
            self.co_occurrences[pair] = pattern
        
        return pattern
    
    def _record_sequence(self, trigger: str, follows: str, timestamp: float) -> Optional[Sequence]:
        """Record that B tends to follow A"""
        key = (trigger, follows)
        
        if key in self.sequences:
            seq = self.sequences[key]
            seq.count += 1
            seq.last_seen = timestamp
            # Confidence increases with count
            seq.confidence = min(1.0, seq.count / 5.0)
        else:
            seq = Sequence(
                trigger=trigger,
                follows=follows,
                count=1,
                confidence=0.2,
                last_seen=timestamp
            )
            self.sequences[key] = seq
        
        return seq
    
    def _detect_cluster(self, items: List[str], timestamp: float) -> Optional[Cluster]:
        """Detect if a group of items forms a cluster"""
        items_set = set(items)
        
        # Check if this cluster already exists
        for cluster in self.clusters:
            if cluster.items == items_set:
                cluster.frequency += 1
                cluster.last_seen = timestamp
                return cluster
        
        # Check if these items have strong co-occurrences
        strong_pairs = 0
        for i, item_a in enumerate(items):
            for item_b in items[i+1:]:
                pair = tuple(sorted([item_a, item_b]))
                if pair in self.co_occurrences:
                    if self.co_occurrences[pair].count >= self.cluster_threshold:
                        strong_pairs += 1
        
        # If enough pairs are strong, create cluster
        if strong_pairs >= len(items) - 1:  # Most items connected
            cluster = Cluster(
                items=items_set,
                frequency=1,
                last_seen=timestamp
            )
            self.clusters.append(cluster)
            return cluster
        
        return None
    
    def _decay_patterns(self):
        """Fade patterns that haven't been seen recently"""
        current_time = time.time()
        
        # Decay co-occurrences
        to_remove = []
        for key, pattern in self.co_occurrences.items():
            time_since = current_time - pattern.last_seen
            if time_since > 300:  # 5 minutes
                pattern.count = max(0, pattern.count - 1)
                pattern.strength *= (1.0 - self.decay_rate)
                if pattern.count == 0 or pattern.strength < 0.01:
                    to_remove.append(key)
        
        for key in to_remove:
            del self.co_occurrences[key]
        
        # Decay sequences
        to_remove = []
        for key, seq in self.sequences.items():
            time_since = current_time - seq.last_seen
            if time_since > 300:
                seq.count = max(0, seq.count - 1)
                seq.confidence *= (1.0 - self.decay_rate)
                if seq.count == 0 or seq.confidence < 0.01:
                    to_remove.append(key)
        
        for key in to_remove:
            del self.sequences[key]
        
        # Decay clusters
        self.clusters = [c for c in self.clusters 
                        if current_time - c.last_seen < 600]  # 10 minutes
    
    def get_patterns_for(self, item: str) -> Dict[str, Any]:
        """Get all known patterns involving this item"""
        patterns = {
            'related_items': [],
            'triggers': [],  # What does this item trigger?
            'triggered_by': [],  # What triggers this item?
            'clusters': []
        }
        
        # Find co-occurrences
        for pair, pattern in self.co_occurrences.items():
            if item in pair and pattern.count >= self.co_occurrence_threshold:
                other = pair[0] if pair[1] == item else pair[1]
                patterns['related_items'].append({
                    'item': other,
                    'strength': pattern.strength,
                    'count': pattern.count
                })
        
        # Find sequences where this triggers something
        for (trigger, follows), seq in self.sequences.items():
            if trigger == item and seq.count >= self.sequence_threshold:
                patterns['triggers'].append({
                    'item': follows,
                    'confidence': seq.confidence,
                    'count': seq.count
                })
            elif follows == item and seq.count >= self.sequence_threshold:
                patterns['triggered_by'].append({
                    'item': trigger,
                    'confidence': seq.confidence,
                    'count': seq.count
                })
        
        # Find clusters containing this item
        for cluster in self.clusters:
            if item in cluster.items:
                patterns['clusters'].append({
                    'items': list(cluster.items),
                    'frequency': cluster.frequency
                })
        
        return patterns
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get overall pattern statistics"""
        return {
            'total_co_occurrences': len(self.co_occurrences),
            'strong_co_occurrences': sum(1 for p in self.co_occurrences.values() 
                                        if p.count >= self.co_occurrence_threshold),
            'total_sequences': len(self.sequences),
            'reliable_sequences': sum(1 for s in self.sequences.values() 
                                     if s.count >= self.sequence_threshold),
            'clusters': len(self.clusters),
            'recent_items': len(self.recent_items)
        }
    
    def get_significant_patterns_only(self) -> Dict[str, Any]:
        """Filter and return only significant patterns for reasoning"""
        # Only send strong patterns, not noise
        significant = {
            'strong_co_occurrences': [],
            'reliable_sequences': [],
            'active_clusters': []
        }
        
        # Strong co-occurrences only
        for pair, pattern in self.co_occurrences.items():
            if pattern.count >= self.co_occurrence_threshold and pattern.strength >= 0.5:
                significant['strong_co_occurrences'].append({
                    'items': list(pair),
                    'strength': pattern.strength,
                    'count': pattern.count
                })
        
        # Reliable sequences only
        for (trigger, follows), seq in self.sequences.items():
            if seq.count >= self.sequence_threshold and seq.confidence >= 0.6:
                significant['reliable_sequences'].append({
                    'trigger': trigger,
                    'follows': follows,
                    'confidence': seq.confidence
                })
        
        # Active clusters only
        current_time = time.time()
        for cluster in self.clusters:
            if current_time - cluster.last_seen < 120:  # Active in last 2 minutes
                significant['active_clusters'].append({
                    'items': list(cluster.items),
                    'frequency': cluster.frequency
                })
        
        return significant
    
    def start(self):
        """Start pattern recognition lobe as independent process"""
        # Remove old socket if exists
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
            
        # Create Unix socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        
        print(f"🔍 Pattern Recognition Lobe: Online at {self.socket_path}")
        print(f"   Watching for co-occurrences, sequences, clusters")
        print(f"   Thresholds: co-occur={self.co_occurrence_threshold}, "
              f"sequence={self.sequence_threshold}, cluster={self.cluster_threshold}")
        
        while self.running:
            try:
                # Accept connection from Thalamus
                conn, _ = sock.accept()
                
                # Read message length (4 bytes)
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
                
                # Process based on message type
                result = self.process_message(message)
                
                # Send response
                response_data = json.dumps(result).encode('utf-8')
                response_length = struct.pack('!I', len(response_data))
                conn.send(response_length + response_data)
                conn.close()
                
            except Exception as e:
                print(f"❌ Pattern recognition error: {e}")
                try:
                    conn.close()
                except:
                    pass
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming message"""
        msg_type = message.get('type')
        
        if msg_type == 'observe':
            # Watch items and detect patterns
            items = message.get('items', [])
            item_type = message.get('item_type', 'concept')
            patterns = self.observe(items, item_type)
            return {'status': 'success', 'patterns': patterns}
            
        elif msg_type == 'get_patterns':
            # Get patterns for specific item
            item = message.get('item')
            patterns = self.get_patterns_for(item)
            return {'status': 'success', 'patterns': patterns}
            
        elif msg_type == 'get_statistics':
            # Get overall statistics
            stats = self.get_statistics()
            return {'status': 'success', 'statistics': stats}
            
        elif msg_type == 'get_significant':
            # Get only significant patterns (filtered for reasoning)
            significant = self.get_significant_patterns_only()
            return {'status': 'success', 'significant_patterns': significant}
            
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

if __name__ == "__main__":
    lobe = PatternRecognitionLobe()
    try:
        lobe.start()
    except KeyboardInterrupt:
        print("\n🛑 Pattern recognition lobe shutting down...")
        lobe.shutdown()

