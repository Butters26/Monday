#!/usr/bin/env python3
"""
Brain Connector - Thread-safe connection to Monday's brain systems
Handles communication with Thalamus, emotional engine, and thinking systems
"""

import threading
from queue import Queue
from typing import Dict, Any, Optional, Callable
import time
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from thalamus import get_thalamus


class BrainConnector:
    """Thread-safe connector to Monday's brain systems"""
    
    def __init__(self):
        self.thalamus = get_thalamus()
        self.running = True
        
        # Message queues
        self.input_queue = Queue()
        self.output_queue = Queue()
        
        # Callbacks
        self.on_response = None
        self.on_emotion_update = None
        self.on_thinking_update = None
        self.on_state_update = None
        
        # Current state
        self.current_emotion = 'neutral'
        self.emotion_intensity = 0.5
        self.is_thinking = False
        self.recent_thoughts = []
        
        # Processing thread
        self.process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.process_thread.start()
        
        # State monitoring thread
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def send_message(self, user_input: str):
        """Send a message to Monday (thread-safe)"""
        self.input_queue.put(user_input)
    
    def _process_loop(self):
        """Process messages from the input queue"""
        while self.running:
            try:
                # Get message from queue (blocks for up to 0.5 seconds)
                try:
                    user_input = self.input_queue.get(timeout=0.5)
                except:
                    continue
                
                # Set thinking state
                self.is_thinking = True
                if self.on_thinking_update:
                    self.on_thinking_update(True)
                
                # Process through Thalamus
                try:
                    result = self.thalamus.process_user_input(user_input)
                    response = (
                        result.get('response', result.get('message', 'Unable to process input.'))
                        if isinstance(result, dict)
                        else result
                    )
                    
                    # Send response via callback
                    if self.on_response:
                        self.on_response(response)
                    
                except Exception as e:
                    error_msg = f"Error processing: {str(e)}"
                    print(f"BrainConnector error: {error_msg}")
                    if self.on_response:
                        self.on_response(error_msg)
                
                finally:
                    # Clear thinking state
                    self.is_thinking = False
                    if self.on_thinking_update:
                        self.on_thinking_update(False)
                
            except Exception as e:
                print(f"Process loop error: {e}")
                time.sleep(0.1)
    
    def _monitor_loop(self):
        """Monitor brain state and emit updates"""
        while self.running:
            try:
                # Check emotional state
                self._update_emotion_state()
                
                # Check thinking state
                self._update_thinking_state()
                
                # Sleep to avoid busy-waiting
                time.sleep(0.5)
                
            except Exception as e:
                print(f"Monitor loop error: {e}")
                time.sleep(1.0)
    
    def _update_emotion_state(self):
        """Update emotional state from the engine"""
        try:
            result = self.thalamus.send_message(
                'emotion', 'get_emotional_state', {}, source='brain_connector', timeout=1
            )
            emotional_state = result.get('content', result)
            if result.get('status') == 'success':
                emotion_name = emotional_state.get('emotion', self.current_emotion)
                intensity = emotional_state.get('intensity', self.emotion_intensity)
                if emotion_name != self.current_emotion or abs(intensity - self.emotion_intensity) > 0.1:
                    self.current_emotion = emotion_name
                    self.emotion_intensity = intensity
                    if self.on_emotion_update:
                        self.on_emotion_update(emotion_name, intensity)
        except Exception as e:
            # Silent fail - emotion updates are non-critical
            pass
    
    def _update_thinking_state(self):
        """Update thinking/processing state"""
        try:
            result = self.thalamus.send_message(
                'reasoning', 'get_internal_state', {}, source='brain_connector', timeout=1
            )
            state = result.get('subjective_state', result.get('content', {}))
            recent = state.get('internal_monologue', []) if result.get('status') == 'success' else []
            if recent != self.recent_thoughts:
                self.recent_thoughts = recent
                if self.on_thinking_update:
                    self.on_thinking_update(self.is_thinking)
        except Exception as e:
            # Silent fail - thinking updates are non-critical
            pass
    
    def get_brain_state(self) -> Dict[str, Any]:
        """Get current brain state for debug panel"""
        try:
            state = {
                'lobes': {},
                'emotion': self.current_emotion,
                'intensity': self.emotion_intensity,
                'thinking': self.is_thinking,
                'recent_thoughts': self.recent_thoughts,
            }
            
            # Get lobe status from Thalamus
            if hasattr(self.thalamus, 'lobe_status'):
                state['lobes'] = dict(self.thalamus.lobe_status)
            
            # Get memory info
            if hasattr(self.thalamus, 'monday_memory'):
                memory = self.thalamus.monday_memory
                state['beliefs'] = memory.get('beliefs', [])
                state['learned_facts'] = memory.get('learned_facts', {})
                state['conversation_count'] = len(memory.get('past_conversations', []))
            
            return state
            
        except Exception as e:
            print(f"Error getting brain state: {e}")
            return {
                'lobes': {},
                'emotion': 'unknown',
                'intensity': 0.0,
                'thinking': False,
                'recent_thoughts': [],
            }
    
    def shutdown(self):
        """Shutdown the connector"""
        self.running = False
        if self.process_thread.is_alive():
            self.process_thread.join(timeout=2.0)
        if self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
