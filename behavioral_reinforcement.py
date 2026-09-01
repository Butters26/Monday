#!/usr/bin/env python3
"""
Behavioral Reinforcement - Learns from your reactions
Tracks what you like/dislike and updates behavior accordingly.
"""

import json
import time
import threading
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from thalamus import get_thalamus
from runtime_paths import runtime_file

@dataclass
class BehaviorRecord:
    """Record of a behavior and its outcome"""
    id: str
    behavior_type: str  # "response_style", "topic", "timing", "tone", etc.
    behavior: str  # What Monday did
    user_reaction: str  # "positive", "negative", "neutral", "ignored"
    reaction_intensity: float  # 0-1 how strong the reaction
    context: Dict[str, Any]
    timestamp: float

@dataclass
class BehaviorWeight:
    """Weight for a behavior - determines likelihood of doing it"""
    behavior_type: str
    behavior: str
    weight: float  # -1 to 1 (avoid to prefer)
    confidence: float  # 0-1 based on sample size
    sample_count: int
    last_updated: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BehaviorWeight':
        return cls(**data)


class BehavioralReinforcement:
    """
    Tracks your reactions and learns what you like.
    Updates decision-making based on feedback.
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        self.thalamus = get_thalamus()
        self.storage_path = storage_path or runtime_file("monday_behavior_weights.json")
        self.running = True
        
        # Behavior tracking
        self.behavior_history: List[BehaviorRecord] = []
        self.behavior_weights: Dict[str, BehaviorWeight] = {}  # "type:behavior" -> weight
        
        # Load existing weights
        self._load_weights()
        
        # Register with Thalamus
        self._register_with_thalamus()
        
        # Lock
        self.lock = threading.Lock()
    
    def _register_with_thalamus(self):
        """Register with Thalamus"""
        try:
            result = self.thalamus.register_lobe('reinforcement', self)
            if result.get('status') == 'success':
                print("✅ Behavioral Reinforcement registered with Thalamus")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register Behavioral Reinforcement: {e}")
            return False
    
    def _load_weights(self):
        """Load behavior weights from disk"""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
            else:
                data = {}

            for weight_data in data.get('weights', []):
                weight = BehaviorWeight.from_dict(weight_data)
                key = f"{weight.behavior_type}:{weight.behavior}"
                self.behavior_weights[key] = weight

            print(f"📂 Loaded {len(self.behavior_weights)} behavior weights")
        except json.JSONDecodeError:
            # Attempt to recover from backup
            bak_path = f"{self.storage_path}.bak"
            try:
                if os.path.exists(bak_path):
                    with open(bak_path, 'r') as f:
                        data = json.load(f)
                    for weight_data in data.get('weights', []):
                        weight = BehaviorWeight.from_dict(weight_data)
                        key = f"{weight.behavior_type}:{weight.behavior}"
                        self.behavior_weights[key] = weight
                    # Restore backup
                    try:
                        os.replace(bak_path, self.storage_path)
                    except Exception:
                        pass
                    print(f"📂 Recovered behavior weights from backup ({bak_path})")
                else:
                    print(f"⚠️  Behavior weights file corrupted and no backup found: {self.storage_path}")
            except Exception as e:
                print(f"⚠️  Could not recover behavior weights: {e}")
        except Exception as e:
            print(f"⚠️  Could not load behavior weights: {e}")
        # No duplicate nested _load_weights - keeping only the primary implementation above
    
    def _save_weights(self):
        """Save behavior weights to disk"""
        try:
            data = {
                'weights': [w.to_dict() for w in self.behavior_weights.values()]
            }

            dirpath = os.path.dirname(self.storage_path) or '.'
            tmp_path = f"{self.storage_path}.tmp"
            bak_path = f"{self.storage_path}.bak"

            # Write to a temp file and fsync to ensure durability
            with open(tmp_path, 'w') as f:
                json.dump(data, f, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    # Not fatal on some platforms, continue
                    pass

            # Backup existing file if present
            try:
                if os.path.exists(self.storage_path):
                    os.replace(self.storage_path, bak_path)
            except Exception:
                pass

            # Atomically move tmp into place
            os.replace(tmp_path, self.storage_path)
        except Exception as e:
            print(f"⚠️  Could not save behavior weights atomically: {e}")
        # No duplicate nested _save_weights - keeping only the primary implementation above
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming messages"""
        msg_type = message.get('type')
        
        if msg_type == 'record_behavior':
            return self._record_behavior(message)
        
        elif msg_type == 'record_reaction':
            return self._record_reaction(message)
        
        elif msg_type == 'get_weight':
            return self._get_weight(message)
        
        elif msg_type == 'get_preferred_behaviors':
            return self._get_preferred_behaviors(message)
        
        elif msg_type == 'should_do':
            return self._should_do(message)
        
        elif msg_type == 'health':
            return {'status': 'success', 'healthy': True}
        
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def _record_behavior(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Record a behavior Monday performed"""
        with self.lock:
            record = BehaviorRecord(
                id=f"behavior_{int(time.time() * 1000)}",
                behavior_type=message.get('behavior_type', 'unknown'),
                behavior=message.get('behavior', ''),
                user_reaction='pending',
                reaction_intensity=0.0,
                context=message.get('context', {}),
                timestamp=time.time()
            )
            
            self.behavior_history.append(record)
            self.behavior_history = self.behavior_history[-500:]  # Keep last 500
            
            return {
                'status': 'success',
                'behavior_id': record.id
            }
    
    def _record_reaction(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Record user's reaction to a behavior.
        This is the learning signal.
        """
        behavior_id = message.get('behavior_id')
        reaction = message.get('reaction', 'neutral')  # positive, negative, neutral, ignored
        intensity = message.get('intensity', 0.5)
        
        with self.lock:
            # Find the behavior
            behavior_record = None
            for record in reversed(self.behavior_history):
                if record.id == behavior_id:
                    behavior_record = record
                    break
            
            if not behavior_record:
                # Try to match most recent behavior of same type
                behavior_type = message.get('behavior_type')
                if behavior_type:
                    for record in reversed(self.behavior_history):
                        if record.behavior_type == behavior_type and record.user_reaction == 'pending':
                            behavior_record = record
                            break
            
            if not behavior_record:
                return {'status': 'error', 'message': 'Behavior not found'}
            
            # Update record
            behavior_record.user_reaction = reaction
            behavior_record.reaction_intensity = intensity
            
            # Update weight
            self._update_weight(behavior_record)
            
            return {
                'status': 'success',
                'updated': True,
                'behavior_type': behavior_record.behavior_type,
                'behavior': behavior_record.behavior
            }
    
    def _update_weight(self, record: BehaviorRecord):
        """Update behavior weight based on reaction"""
        key = f"{record.behavior_type}:{record.behavior}"
        
        # Calculate reward signal
        reaction_values = {
            'positive': 1.0,
            'negative': -1.0,
            'neutral': 0.0,
            'ignored': -0.2  # Slight negative for being ignored
        }
        reward = reaction_values.get(record.user_reaction, 0.0) * record.reaction_intensity
        
        if key in self.behavior_weights:
            weight = self.behavior_weights[key]
            
            # Learning rate decreases with more samples
            learning_rate = 1.0 / (weight.sample_count + 1)
            
            # Update weight with exponential moving average
            weight.weight = weight.weight * (1 - learning_rate) + reward * learning_rate
            weight.weight = max(-1.0, min(1.0, weight.weight))  # Clamp
            weight.confidence = min(1.0, weight.sample_count / 10.0)  # Max confidence at 10 samples
            weight.sample_count += 1
            weight.last_updated = time.time()
        else:
            # Create new weight
            self.behavior_weights[key] = BehaviorWeight(
                behavior_type=record.behavior_type,
                behavior=record.behavior,
                weight=reward * 0.5,  # Start conservative
                confidence=0.1,
                sample_count=1,
                last_updated=time.time()
            )
        
        self._save_weights()
        
        print(f"📊 Behavior weight updated: {record.behavior_type}:{record.behavior} -> {self.behavior_weights[key].weight:.2f}")
    
    def _get_weight(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Get weight for a specific behavior"""
        behavior_type = message.get('behavior_type', '')
        behavior = message.get('behavior', '')
        key = f"{behavior_type}:{behavior}"
        
        with self.lock:
            if key in self.behavior_weights:
                return {
                    'status': 'success',
                    'weight': self.behavior_weights[key].to_dict(),
                    'found': True
                }
            
            return {
                'status': 'success',
                'weight': None,
                'found': False
            }
    
    def _get_preferred_behaviors(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Get behaviors with positive weights for a type"""
        behavior_type = message.get('behavior_type', '')
        
        with self.lock:
            preferred = []
            for key, weight in self.behavior_weights.items():
                if weight.behavior_type == behavior_type and weight.weight > 0:
                    preferred.append(weight.to_dict())
            
            # Sort by weight
            preferred.sort(key=lambda x: x['weight'], reverse=True)
            
            return {
                'status': 'success',
                'behaviors': preferred,
                'count': len(preferred)
            }
    
    def _should_do(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ask if Monday should do a behavior.
        Returns recommendation based on learned weights.
        """
        behavior_type = message.get('behavior_type', '')
        behavior = message.get('behavior', '')
        key = f"{behavior_type}:{behavior}"
        
        with self.lock:
            if key in self.behavior_weights:
                weight = self.behavior_weights[key]
                
                # Recommend based on weight and confidence
                if weight.confidence < 0.3:
                    recommendation = 'try'  # Not enough data, experiment
                    reason = "Not enough data, worth trying"
                elif weight.weight > 0.3:
                    recommendation = 'yes'
                    reason = f"User tends to like this (weight: {weight.weight:.2f})"
                elif weight.weight < -0.3:
                    recommendation = 'no'
                    reason = f"User tends to dislike this (weight: {weight.weight:.2f})"
                else:
                    recommendation = 'neutral'
                    reason = "No strong preference detected"
                
                return {
                    'status': 'success',
                    'recommendation': recommendation,
                    'reason': reason,
                    'weight': weight.weight,
                    'confidence': weight.confidence
                }
            
            # No data for this behavior
            return {
                'status': 'success',
                'recommendation': 'try',
                'reason': 'No data yet, worth trying',
                'weight': 0.0,
                'confidence': 0.0
            }
    
    def record_positive_reaction(self, behavior_type: str, behavior: str, intensity: float = 0.7):
        """Direct method to record positive reaction"""
        # First record the behavior
        self._record_behavior({
            'behavior_type': behavior_type,
            'behavior': behavior
        })
        
        # Then record positive reaction to most recent
        with self.lock:
            if self.behavior_history:
                record = self.behavior_history[-1]
                record.user_reaction = 'positive'
                record.reaction_intensity = intensity
                self._update_weight(record)
    
    def record_negative_reaction(self, behavior_type: str, behavior: str, intensity: float = 0.7):
        """Direct method to record negative reaction"""
        self._record_behavior({
            'behavior_type': behavior_type,
            'behavior': behavior
        })
        
        with self.lock:
            if self.behavior_history:
                record = self.behavior_history[-1]
                record.user_reaction = 'negative'
                record.reaction_intensity = intensity
                self._update_weight(record)
    
    def get_behavior_recommendation(self, behavior_type: str, behavior: str) -> str:
        """Direct method to get recommendation"""
        result = self._should_do({
            'behavior_type': behavior_type,
            'behavior': behavior
        })
        return result.get('recommendation', 'neutral')
    
    def start(self):
        """Start the reinforcement system"""
        print("🎯 Behavioral Reinforcement running...")
        while self.running:
            time.sleep(1)
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        self._save_weights()
        print("💾 Behavioral Reinforcement saved and shutdown")


if __name__ == "__main__":
    print("🎯 Behavioral Reinforcement starting...")
    system = BehavioralReinforcement()
    
    # Test recording
    system.record_positive_reaction('topic', 'music', 0.8)
    system.record_negative_reaction('topic', 'politics', 0.6)
    
    # Test recommendation
    rec = system.get_behavior_recommendation('topic', 'music')
    print(f"Music recommendation: {rec}")
    
    try:
        system.start()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down")
        system.shutdown()
