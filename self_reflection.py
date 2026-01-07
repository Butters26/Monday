#!/usr/bin/env python3
"""
Self-Reflection Engine - Questions own beliefs and updates confidence
Makes Monday examine WHY she believes things, not just WHAT she believes.
"""

import json
import time
import threading
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from thalamus import get_thalamus
import os
import random

@dataclass
class Belief:
    """A belief Monday holds"""
    id: str
    content: str  # What she believes
    category: str  # "value", "fact", "preference", "identity", "about_matthew"
    confidence: float  # 0-1 how sure she is
    source: str  # Where this belief came from: "matthew_told_me", "experience", "inference", "default"
    reason: str  # Why she believes this
    created_at: float
    last_examined: float
    examination_count: int = 0
    contradictions_found: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Belief':
        return cls(**data)


@dataclass
class ReflectionResult:
    """Result of examining a belief"""
    belief_id: str
    original_confidence: float
    new_confidence: float
    reason_for_change: str
    contradictions: List[str]
    supporting_evidence: List[str]
    timestamp: float


class SelfReflectionEngine:
    """
    Makes Monday question her own beliefs.
    Not just storing beliefs - actively examining them.
    """
    
    def __init__(self, storage_path: str = "monday_beliefs.json"):
        self.thalamus = get_thalamus()
        self.storage_path = storage_path
        self.running = True
        
        # Belief storage
        self.beliefs: Dict[str, Belief] = {}  # id -> Belief
        self.reflection_history: List[ReflectionResult] = []
        
        # Load existing beliefs
        self._load_beliefs()
        
        # Register with Thalamus
        self._register_with_thalamus()
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
        # Reflection state
        self.last_reflection_time = 0.0
        self.reflection_interval = 60.0  # Reflect every 60 seconds of activity
    
    def _register_with_thalamus(self):
        """Register with Thalamus"""
        try:
            result = self.thalamus.register_lobe('reflection', self)
            if result.get('status') == 'success':
                print("✅ Self-Reflection Engine registered with Thalamus")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register Self-Reflection Engine: {e}")
            return False
    
    def _load_beliefs(self):
        """Load beliefs from disk"""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                
                for belief_data in data.get('beliefs', []):
                    belief = Belief.from_dict(belief_data)
                    self.beliefs[belief.id] = belief
                
                for result_data in data.get('reflection_history', []):
                    self.reflection_history.append(ReflectionResult(**result_data))
                
                print(f"📂 Loaded {len(self.beliefs)} beliefs")
        except Exception as e:
            print(f"⚠️  Could not load beliefs: {e}")
    
    def _save_beliefs(self):
        """Save beliefs to disk"""
        try:
            data = {
                'beliefs': [b.to_dict() for b in self.beliefs.values()],
                'reflection_history': [asdict(r) for r in self.reflection_history[-100:]]
            }
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️  Could not save beliefs: {e}")
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming messages"""
        msg_type = message.get('type')
        
        if msg_type == 'add_belief':
            return self._handle_add_belief(message)
        
        elif msg_type == 'examine_belief':
            return self._handle_examine_belief(message)
        
        elif msg_type == 'check_contradiction':
            return self._handle_check_contradiction(message)
        
        elif msg_type == 'get_beliefs':
            return self._handle_get_beliefs(message)
        
        elif msg_type == 'trigger_reflection':
            return self._handle_trigger_reflection(message)
        
        elif msg_type == 'health':
            return {'status': 'success', 'healthy': True}
        
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def _handle_add_belief(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new belief"""
        with self.lock:
            belief_id = f"belief_{int(time.time() * 1000)}"
            
            belief = Belief(
                id=belief_id,
                content=message.get('content', ''),
                category=message.get('category', 'fact'),
                confidence=message.get('confidence', 0.5),
                source=message.get('source', 'inference'),
                reason=message.get('reason', 'No reason given'),
                created_at=time.time(),
                last_examined=time.time(),
                examination_count=0,
                contradictions_found=0
            )
            
            # Check for contradictions with existing beliefs
            contradictions = self._find_contradictions(belief)
            if contradictions:
                belief.contradictions_found = len(contradictions)
                belief.confidence *= 0.8  # Lower confidence if contradictions found
            
            self.beliefs[belief_id] = belief
            self._save_beliefs()
            
            print(f"💭 New belief: {belief.content[:50]}... (conf: {belief.confidence:.2f})")
            
            return {
                'status': 'success',
                'belief_id': belief_id,
                'contradictions_found': len(contradictions),
                'contradictions': contradictions
            }
    
    def _handle_examine_belief(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Examine a specific belief - the core of self-reflection.
        Ask: "Why do I believe this? Is it still valid?"
        """
        belief_id = message.get('belief_id')
        
        with self.lock:
            if belief_id not in self.beliefs:
                return {'status': 'error', 'message': 'Belief not found'}
            
            belief = self.beliefs[belief_id]
            result = self._examine_belief_internal(belief)
            
            return {
                'status': 'success',
                'result': asdict(result),
                'belief': belief.to_dict()
            }
    
    def _examine_belief_internal(self, belief: Belief) -> ReflectionResult:
        """
        Internal method to examine a belief.
        This is where the actual reflection happens.
        """
        original_confidence = belief.confidence
        contradictions = self._find_contradictions(belief)
        supporting = self._find_supporting_evidence(belief)
        
        # Calculate new confidence based on evidence
        contradiction_penalty = len(contradictions) * 0.1
        support_bonus = len(supporting) * 0.05
        
        # Source credibility affects confidence
        source_weights = {
            'matthew_told_me': 0.9,  # High trust in Matthew
            'experience': 0.7,       # Direct experience is reliable
            'inference': 0.5,        # Inferences are less certain
            'default': 0.3           # Default beliefs are lowest
        }
        source_weight = source_weights.get(belief.source, 0.5)
        
        # Age decay - older unexamined beliefs lose confidence
        days_since_examined = (time.time() - belief.last_examined) / 86400
        age_decay = min(0.2, days_since_examined * 0.01)
        
        # Calculate new confidence
        new_confidence = belief.confidence
        new_confidence -= contradiction_penalty
        new_confidence += support_bonus
        new_confidence *= source_weight
        new_confidence -= age_decay
        new_confidence = max(0.1, min(1.0, new_confidence))
        
        # Determine reason for change
        if new_confidence < original_confidence:
            if contradictions:
                reason = f"Found {len(contradictions)} contradicting beliefs"
            elif age_decay > 0.1:
                reason = "Belief hasn't been examined in a while"
            else:
                reason = "Source is not highly reliable"
        elif new_confidence > original_confidence:
            reason = f"Found {len(supporting)} supporting pieces of evidence"
        else:
            reason = "No significant change in evidence"
        
        # Update belief
        belief.confidence = new_confidence
        belief.last_examined = time.time()
        belief.examination_count += 1
        belief.contradictions_found = len(contradictions)
        
        # Create result
        result = ReflectionResult(
            belief_id=belief.id,
            original_confidence=original_confidence,
            new_confidence=new_confidence,
            reason_for_change=reason,
            contradictions=[c.content for c in contradictions],
            supporting_evidence=[s.content for s in supporting],
            timestamp=time.time()
        )
        
        self.reflection_history.append(result)
        self._save_beliefs()
        
        print(f"🔍 Examined belief: {belief.content[:30]}... ({original_confidence:.2f} → {new_confidence:.2f})")
        
        return result
    
    def _find_contradictions(self, belief: Belief) -> List[Belief]:
        """Find beliefs that might contradict this one"""
        contradictions = []
        
        # Simple keyword-based contradiction detection
        belief_words = set(belief.content.lower().split())
        negation_words = {'not', 'dont', 'doesnt', 'never', 'no', 'hate', 'dislike'}
        
        for other_id, other in self.beliefs.items():
            if other_id == belief.id:
                continue
            
            other_words = set(other.content.lower().split())
            overlap = belief_words & other_words
            
            # Check if one has negation and other doesn't
            belief_has_negation = bool(belief_words & negation_words)
            other_has_negation = bool(other_words & negation_words)
            
            if len(overlap) >= 3 and belief_has_negation != other_has_negation:
                contradictions.append(other)
        
        return contradictions
    
    def _find_supporting_evidence(self, belief: Belief) -> List[Belief]:
        """Find beliefs that support this one"""
        supporting = []
        
        belief_words = set(belief.content.lower().split())
        
        for other_id, other in self.beliefs.items():
            if other_id == belief.id:
                continue
            
            other_words = set(other.content.lower().split())
            overlap = belief_words & other_words
            
            # Similar content without contradiction = support
            if len(overlap) >= 3:
                # Check they're not contradicting
                negation_words = {'not', 'dont', 'doesnt', 'never', 'no'}
                belief_has_negation = bool(belief_words & negation_words)
                other_has_negation = bool(other_words & negation_words)
                
                if belief_has_negation == other_has_negation:
                    supporting.append(other)
        
        return supporting
    
    def _handle_check_contradiction(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Check if a new statement contradicts existing beliefs"""
        statement = message.get('statement', '')
        
        # Create temporary belief to check
        temp_belief = Belief(
            id='temp',
            content=statement,
            category='fact',
            confidence=0.5,
            source='test',
            reason='Testing for contradiction',
            created_at=time.time(),
            last_examined=time.time()
        )
        
        contradictions = self._find_contradictions(temp_belief)
        
        return {
            'status': 'success',
            'has_contradiction': len(contradictions) > 0,
            'contradictions': [c.to_dict() for c in contradictions],
            'count': len(contradictions)
        }
    
    def _handle_get_beliefs(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Get beliefs, optionally filtered"""
        category = message.get('category', None)
        min_confidence = message.get('min_confidence', 0.0)
        
        with self.lock:
            beliefs = list(self.beliefs.values())
            
            if category:
                beliefs = [b for b in beliefs if b.category == category]
            
            beliefs = [b for b in beliefs if b.confidence >= min_confidence]
            
            # Sort by confidence
            beliefs.sort(key=lambda b: b.confidence, reverse=True)
            
            return {
                'status': 'success',
                'beliefs': [b.to_dict() for b in beliefs],
                'count': len(beliefs)
            }
    
    def _handle_trigger_reflection(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger a reflection session - examine multiple beliefs"""
        num_to_examine = message.get('count', 3)
        
        with self.lock:
            # Pick beliefs to examine
            # Prioritize: low confidence, old, never examined, has contradictions
            candidates = list(self.beliefs.values())
            
            def examination_priority(b: Belief) -> float:
                score = 0.0
                score += (1.0 - b.confidence) * 2  # Low confidence = high priority
                score += (time.time() - b.last_examined) / 86400 * 0.5  # Days since examined
                score += (5 - b.examination_count) * 0.3 if b.examination_count < 5 else 0  # Never examined
                score += b.contradictions_found * 0.5  # Has contradictions
                return score
            
            candidates.sort(key=examination_priority, reverse=True)
            to_examine = candidates[:num_to_examine]
            
            results = []
            for belief in to_examine:
                result = self._examine_belief_internal(belief)
                results.append(asdict(result))
            
            return {
                'status': 'success',
                'examined_count': len(results),
                'results': results
            }
    
    def add_belief_direct(self, content: str, category: str, confidence: float,
                         source: str, reason: str) -> str:
        """Direct method to add belief without going through Thalamus"""
        result = self._handle_add_belief({
            'content': content,
            'category': category,
            'confidence': confidence,
            'source': source,
            'reason': reason
        })
        return result.get('belief_id', '')
    
    def reflect(self) -> List[ReflectionResult]:
        """Public method to trigger reflection"""
        result = self._handle_trigger_reflection({'count': 3})
        return result.get('results', [])
    
    def start(self):
        """Start the reflection engine with periodic reflection"""
        print("🪞 Self-Reflection Engine running...")
        
        while self.running:
            time.sleep(self.reflection_interval)
            
            # Periodic reflection
            if time.time() - self.last_reflection_time > self.reflection_interval:
                with self.lock:
                    if self.beliefs:
                        self._handle_trigger_reflection({'count': 1})
                        self.last_reflection_time = time.time()
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        self._save_beliefs()
        print("💾 Self-Reflection Engine saved and shutdown")


if __name__ == "__main__":
    print("🪞 Self-Reflection Engine starting...")
    engine = SelfReflectionEngine()
    
    # Add some test beliefs
    engine.add_belief_direct(
        content="I care about Matthew",
        category="value",
        confidence=0.9,
        source="experience",
        reason="Many positive interactions"
    )
    
    engine.add_belief_direct(
        content="Music is interesting",
        category="preference",
        confidence=0.6,
        source="inference",
        reason="Haven't experienced much music yet"
    )
    
    # Trigger reflection
    results = engine.reflect()
    for r in results:
        print(f"  Reflected on: {r}")
    
    try:
        engine.start()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down")
        engine.shutdown()
