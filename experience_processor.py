#!/usr/bin/env python3
"""
Experience Processor - Stores experiences with emotions, forms preferences
Every experience has an emotional tag. Accumulated emotions form preferences.
"""

import json
import time
import threading
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from thalamus import get_thalamus
import os
from runtime_paths import runtime_file

@dataclass
class Experience:
    """A single experience with emotional context"""
    id: str
    stimulus: str  # What happened
    stimulus_type: str  # "conversation", "music", "concept", "person", etc.
    emotion: str  # Primary emotion felt
    intensity: float  # 0-1 how strong
    valence: float  # -1 to 1 (negative to positive)
    timestamp: float
    context: Dict[str, Any] = field(default_factory=dict)  # Additional context
    user_involved: bool = True  # Was Matthew involved?
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Experience':
        return cls(**data)


@dataclass
class Preference:
    """A preference formed from accumulated experiences"""
    subject: str  # What the preference is about
    subject_type: str  # "music", "topic", "behavior", "person", etc.
    valence: float  # -1 (hate) to 1 (love)
    strength: float  # 0-1 how strong the preference is
    confidence: float  # 0-1 how confident (based on experience count)
    experience_count: int  # How many experiences formed this
    last_updated: float
    emotion_history: List[str] = field(default_factory=list)  # Emotions that formed this
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Preference':
        return cls(**data)


class ExperienceProcessor:
    """
    Processes and stores experiences with emotional context.
    Forms preferences from accumulated emotional experiences.
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        self.thalamus = get_thalamus()
        self.storage_path = storage_path or runtime_file("monday_experiences.json")
        self.running = True
        
        # Experience storage
        self.experiences: List[Experience] = []
        self.preferences: Dict[str, Preference] = {}  # subject -> Preference
        
        # Load existing data
        self._load_data()
        
        # Register with Thalamus
        self._register_with_thalamus()
        
        # Lock for thread safety
        self.lock = threading.Lock()
    
    def _register_with_thalamus(self):
        """Register with Thalamus"""
        try:
            result = self.thalamus.register_lobe('experience', self)
            if result.get('status') == 'success':
                print("✅ Experience Processor registered with Thalamus")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register Experience Processor: {e}")
            return False
    
    def _load_data(self):
        """Load experiences and preferences from disk"""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    
                # Load experiences
                for exp_data in data.get('experiences', []):
                    self.experiences.append(Experience.from_dict(exp_data))
                
                # Load preferences
                for pref_data in data.get('preferences', []):
                    pref = Preference.from_dict(pref_data)
                    self.preferences[pref.subject] = pref
                
                print(f"📂 Loaded {len(self.experiences)} experiences, {len(self.preferences)} preferences")
        except Exception as e:
            print(f"⚠️  Could not load experience data: {e}")
    
    def _save_data(self):
        """Save experiences and preferences to disk"""
        try:
            data = {
                'experiences': [exp.to_dict() for exp in self.experiences[-1000:]],  # Keep last 1000
                'preferences': [pref.to_dict() for pref in self.preferences.values()]
            }
            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️  Could not save experience data: {e}")
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming messages"""
        msg_type = message.get('type')
        
        if msg_type == 'store_experience':
            return self._handle_store_experience(message)
        
        elif msg_type == 'get_preference':
            return self._handle_get_preference(message)
        
        elif msg_type == 'get_preferences_by_type':
            return self._handle_get_preferences_by_type(message)
        
        elif msg_type == 'get_recent_experiences':
            return self._handle_get_recent_experiences(message)
        
        elif msg_type == 'health':
            return {'status': 'success', 'healthy': True}
        
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def _handle_store_experience(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Store an experience and update preferences.
        This is the main entry point for the system.
        """
        with self.lock:
            # Create experience
            experience = Experience(
                id=f"exp_{int(time.time() * 1000)}",
                stimulus=message.get('stimulus', ''),
                stimulus_type=message.get('stimulus_type', 'unknown'),
                emotion=message.get('emotion', 'neutral'),
                intensity=message.get('intensity', 0.5),
                valence=message.get('valence', 0.0),
                timestamp=time.time(),
                context=message.get('context', {}),
                user_involved=message.get('user_involved', True)
            )
            
            # Store experience
            self.experiences.append(experience)
            
            # Update preference based on this experience
            self._update_preference_from_experience(experience)
            
            # Save periodically (every 10 experiences)
            if len(self.experiences) % 10 == 0:
                self._save_data()
            
            print(f"📝 Stored experience: {experience.stimulus[:50]}... ({experience.emotion}, {experience.valence:.2f})")
            
            return {
                'status': 'success',
                'experience_id': experience.id,
                'preference_updated': True
            }
    
    def _update_preference_from_experience(self, experience: Experience):
        """
        Update or create preference based on new experience.
        Preferences are formed by accumulating emotional responses.
        """
        subject = experience.stimulus_type  # Preference is about the TYPE of thing
        
        # Also create subject-specific preference if we can identify one
        # e.g., if stimulus is "jazz music", create preference for "jazz"
        specific_subject = self._extract_specific_subject(experience.stimulus)
        
        subjects_to_update = [subject]
        if specific_subject:
            subjects_to_update.append(specific_subject)
        
        for subj in subjects_to_update:
            if subj in self.preferences:
                pref = self.preferences[subj]
                
                # Weighted average of existing preference and new experience
                # More experiences = less influence from new data
                weight = 1.0 / (pref.experience_count + 1)
                
                pref.valence = pref.valence * (1 - weight) + experience.valence * weight
                pref.strength = min(1.0, pref.strength + (experience.intensity * 0.1))
                pref.confidence = min(1.0, pref.experience_count / 20.0)  # Max confidence at 20 experiences
                pref.experience_count += 1
                pref.last_updated = time.time()
                pref.emotion_history.append(experience.emotion)
                pref.emotion_history = pref.emotion_history[-20:]  # Keep last 20
                
            else:
                # Create new preference
                self.preferences[subj] = Preference(
                    subject=subj,
                    subject_type=experience.stimulus_type,
                    valence=experience.valence,
                    strength=experience.intensity,
                    confidence=0.1,  # Low confidence with single experience
                    experience_count=1,
                    last_updated=time.time(),
                    emotion_history=[experience.emotion]
                )
        
        print(f"   → Updated preference for '{subject}': valence={self.preferences[subject].valence:.2f}")
    
    def _extract_specific_subject(self, stimulus: str) -> Optional[str]:
        """
        Try to extract a specific subject from the stimulus.
        e.g., "I love jazz music" -> "jazz"
        """
        # Simple keyword extraction - could be made smarter
        stimulus_lower = stimulus.lower()
        
        # Music genres
        genres = ['jazz', 'rock', 'pop', 'classical', 'electronic', 'hip hop', 'country', 'metal']
        for genre in genres:
            if genre in stimulus_lower:
                return genre
        
        # Could add more extraction patterns here
        return None
    
    def _handle_get_preference(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Get preference for a specific subject"""
        subject = message.get('subject', '')
        
        with self.lock:
            if subject in self.preferences:
                pref = self.preferences[subject]
                return {
                    'status': 'success',
                    'preference': pref.to_dict(),
                    'has_preference': True
                }
            else:
                return {
                    'status': 'success',
                    'preference': None,
                    'has_preference': False
                }
    
    def _handle_get_preferences_by_type(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Get all preferences of a certain type"""
        pref_type = message.get('preference_type', '')
        
        with self.lock:
            matching = [
                pref.to_dict() for pref in self.preferences.values()
                if pref.subject_type == pref_type
            ]
            
            return {
                'status': 'success',
                'preferences': matching,
                'count': len(matching)
            }
    
    def _handle_get_recent_experiences(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Get recent experiences, optionally filtered"""
        limit = message.get('limit', 10)
        stimulus_type = message.get('stimulus_type', None)
        
        with self.lock:
            experiences = self.experiences
            
            if stimulus_type:
                experiences = [e for e in experiences if e.stimulus_type == stimulus_type]
            
            recent = experiences[-limit:]
            
            return {
                'status': 'success',
                'experiences': [e.to_dict() for e in recent],
                'count': len(recent)
            }
    
    def get_preference_for_reasoning(self, subject: str) -> Dict[str, Any]:
        """
        Public method for Reasoning lobe to quickly check preferences.
        Returns simplified preference info.
        """
        with self.lock:
            if subject in self.preferences:
                pref = self.preferences[subject]
                return {
                    'likes': pref.valence > 0.2,
                    'dislikes': pref.valence < -0.2,
                    'valence': pref.valence,
                    'strength': pref.strength,
                    'confident': pref.confidence > 0.5
                }
            
            # Check for partial matches
            for key, pref in self.preferences.items():
                if key in subject.lower() or subject.lower() in key:
                    return {
                        'likes': pref.valence > 0.2,
                        'dislikes': pref.valence < -0.2,
                        'valence': pref.valence,
                        'strength': pref.strength,
                        'confident': pref.confidence > 0.5
                    }
        
        return {
            'likes': None,
            'dislikes': None,
            'valence': 0.0,
            'strength': 0.0,
            'confident': False
        }
    
    def store_experience_direct(self, stimulus: str, stimulus_type: str, 
                                emotion: str, intensity: float, valence: float,
                                context: Dict[str, Any] = None) -> str:
        """
        Direct method to store experience without going through Thalamus.
        Returns experience ID.
        """
        result = self._handle_store_experience({
            'stimulus': stimulus,
            'stimulus_type': stimulus_type,
            'emotion': emotion,
            'intensity': intensity,
            'valence': valence,
            'context': context or {},
            'user_involved': True
        })
        return result.get('experience_id', '')
    
    def start(self):
        """Start the experience processor"""
        print("🧠 Experience Processor running...")
        while self.running:
            time.sleep(1)
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        self._save_data()
        print("💾 Experience Processor saved and shutdown")


if __name__ == "__main__":
    print("🧠 Experience Processor starting...")
    processor = ExperienceProcessor()
    
    try:
        processor.start()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down")
        processor.shutdown()
