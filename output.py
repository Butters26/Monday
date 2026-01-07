#!/usr/bin/env python3
"""
Output Lobe - Expression and Communication
Handles: Text-to-speech, text output, voice configuration
"""

import json
import os
import time
import sys
from typing import Dict, Any, Optional
from dataclasses import dataclass
from thalamus import get_thalamus

# ============================================================================
# VOICE PROFILES
# ============================================================================

@dataclass
class VoiceProfile:
    """Voice characteristics for TTS"""
    name: str
    pitch_base: float
    pitch_range: float
    formant_shift: float
    speed: float
    breathiness: float
    nasality: float
    warmth: float
    clarity: float
    resonance: float
    vibrato_depth: float
    vibrato_rate: float

# ============================================================================
# PREDEFINED VOICES
# ============================================================================

VOICE_PROFILES = {
    'shadowheart': VoiceProfile(
        name='Shadowheart',
        pitch_base=190,
        pitch_range=70,
        formant_shift=0.95,
        speed=0.95,
        breathiness=0.08,
        nasality=0.03,
        warmth=0.6,
        clarity=0.85,
        resonance=1.1,
        vibrato_depth=0.015,
        vibrato_rate=4.5
    ),
    
    'mealle': VoiceProfile(
        name='Mealle',
        pitch_base=220,
        pitch_range=95,
        formant_shift=1.05,
        speed=1.05,
        breathiness=0.15,
        nasality=0.08,
        warmth=0.85,
        clarity=0.75,
        resonance=0.9,
        vibrato_depth=0.025,
        vibrato_rate=5.5
    ),
    
    'people': VoiceProfile(
        name='People',
        pitch_base=210,
        pitch_range=85,
        formant_shift=1.0,
        speed=1.0,
        breathiness=0.12,
        nasality=0.05,
        warmth=0.7,
        clarity=0.8,
        resonance=1.0,
        vibrato_depth=0.02,
        vibrato_rate=5.0
    ),
    
    'monday': VoiceProfile(
        name='Monday',
        pitch_base=205,
        pitch_range=80,
        formant_shift=1.02,
        speed=0.98,
        breathiness=0.10,
        nasality=0.04,
        warmth=0.85,
        clarity=0.85,
        resonance=1.05,
        vibrato_depth=0.02,
        vibrato_rate=5.2
    )
}

# ============================================================================
# TEXT TO PHONEMES
# ============================================================================

TEXT_TO_PHONEMES = {
    'hello': ['h', 'eh', 'l', 'oh'],
    'hi': ['h', 'ay'],
    'monday': ['m', 'ah', 'n', 'd', 'ay'],
    'abin': ['ae', 'b', 'ih', 'n'],
    'matthew': ['m', 'ae', 'th', 'uw'],
    'shadowheart': ['sh', 'ae', 'd', 'oh', 'h', 'art'],
    'mealle': ['m', 'eh', 'ae', 'l'],
}

class OutputLobe:
    """Output system - handles all expression and communication"""
    
    def __init__(self):
        self.running = True
        # Removed: self.gui_socket_path - all communication through Thalamus
        self.last_sent_text = None  # Prevent duplicate sends
        self.last_sent_time = 0.0  # FIX: Initialize time tracking
        
        # Direct reference to Thalamus (NO SOCKETS)
        self.thalamus = get_thalamus()
        
        # Text-to-speech engine
        self.tts_engine = None
        self.tts_available = False
        
        # Voice configuration
        self.voice_config = {
            'enabled': False,
            'rate': 150,
            'volume': 1.0,
            'voice_id': None,
            'profile': 'monday'  # Default to Monday's voice
        }
        
        # Voice profiles
        self.voice_profiles = VOICE_PROFILES
        self.text_to_phonemes = TEXT_TO_PHONEMES
        
        self._initialize_tts()
        
    def _apply_voice_profile(self, profile_name: str = 'monday'):
        """Apply voice profile settings to TTS engine"""
        if not self.tts_engine or not self.tts_available:
            return
        
        if profile_name not in self.voice_profiles:
            profile_name = 'monday'  # Default fallback
        
        profile = self.voice_profiles[profile_name]
        
        # Apply profile settings (pyttsx3 has limited control, but we set what we can)
        # Rate is based on speed
        rate = int(150 * profile.speed)
        self.tts_engine.setProperty('rate', rate)
        
        # Volume stays at configured level
        self.tts_engine.setProperty('volume', self.voice_config['volume'])
        
        # Try to find a matching voice by pitch (limited in pyttsx3)
        try:
            voices = self.tts_engine.getProperty('voices')
            if voices:
                # Select voice based on pitch_base (higher pitch = typically female voices)
                if profile.pitch_base > 200:
                    # Prefer higher-pitched voices
                    for voice in voices:
                        if 'female' in voice.name.lower() or 'zira' in voice.name.lower():
                            self.tts_engine.setProperty('voice', voice.id)
                            break
                else:
                    # Prefer lower-pitched voices
                    for voice in voices:
                        if 'male' in voice.name.lower() or 'david' in voice.name.lower():
                            self.tts_engine.setProperty('voice', voice.id)
                            break
        except Exception:
            pass  # Voice selection is optional
    
    def _initialize_tts(self):
        """Initialize text-to-speech engine"""
        try:
            import pyttsx3
            self.tts_engine = pyttsx3.init()
            self.tts_available = True
            
            # Configure voice
            self.tts_engine.setProperty('rate', self.voice_config['rate'])
            self.tts_engine.setProperty('volume', self.voice_config['volume'])
            
            # Apply default voice profile (Monday)
            self._apply_voice_profile(self.voice_config.get('profile', 'monday'))
            
            print("✅ Text-to-speech engine initialized")
            
            # List available voices
            voices = self.tts_engine.getProperty('voices')
            print(f"   Available voices: {len(voices)}")
            print(f"   Active profile: {self.voice_config.get('profile', 'monday')}")
            
        except ImportError:
            print("⚠️  pyttsx3 not available - voice output disabled")
            print("   Install with: pip install pyttsx3")
            self.tts_available = False
        except Exception as e:
            print(f"⚠️  TTS initialization error: {e}")
            self.tts_available = False
    
    def speak(self, text: str, voice_prosody: Dict[str, float] = None) -> bool:
        """Speak text using TTS - with emotional prosody support"""
        if not self.tts_available or not self.voice_config['enabled']:
            # Voice disabled - just return text
            return False
        
        # Query emotional state if prosody not provided
        if not voice_prosody:
            try:
                emotion_result = self.thalamus.send_message(
                    destination='emotion',
                    msg_type='get_emotional_state',
                    content={},
                    source='output'
                )
                if emotion_result and emotion_result.get('status') == 'success':
                    voice_prosody = emotion_result.get('content', {}).get('voice_prosody', {})
            except Exception as e:
                print(f"⚠️  Could not get emotional prosody: {e}")
                voice_prosody = {}
        
        # Send text to Voice lobe with prosody
        try:
            result = self.thalamus.send_message(
                destination='voice',
                msg_type='play',
                content={
                    'text': text,
                    'emotion': 'neutral',
                    'intensity': 0.5,
                    'voice_prosody': voice_prosody or {}
                },
                source='output'
            )
            return result.get('status') == 'success'
        except Exception as e:
            print(f"❌ TTS error: {e}")
            # Fallback: try local TTS
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
                return True
            except Exception:
                return False
    
    def generate_text_output(self, content: Dict[str, Any]) -> str:
        """Generate formatted text output"""
        # Query Notus for context
        try:
            notus_context = self._send_to_thalamus({
                'type': 'route_message',
                'destination': 'notus',
                'msg_type': 'query',
                'content': {'type': 'get_context', 'content': content}
            })
            if notus_context and notus_context.get('status') == 'success':
                # Use context to inform output generation
                pass
        except Exception:
            pass
        
        output_type = content.get('type', 'response')
        text = content.get('text', '')
        
        if output_type == 'response':
            # Standard response - emotion is expressed through formatting, not labels
            return text
            
        elif output_type == 'thought':
            # Internal thought
            return f"💭 {text}"
            
        elif output_type == 'action':
            # Action description
            return f"*{text}*"
            
        else:
            return text
    
    def format_output(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Format output with emotion and personality"""
        # Query Notus for past output patterns
        try:
            notus_patterns = self._send_to_thalamus({
                'type': 'route_message',
                'destination': 'notus',
                'msg_type': 'query',
                'content': {'type': 'get_output_patterns'}
            })
            if notus_patterns and notus_patterns.get('status') == 'success':
                patterns = notus_patterns.get('patterns', [])
                # Use learned patterns if available
        except Exception:
            pass
        
        text = content.get('text', '')
        emotion = content.get('emotion')
        intensity = content.get('intensity', 0.5)
        
        # Handle None or empty text (Issue 3 fix)
        if text is None or not isinstance(text, str):
            return {
                'text': '',
                'emotion': emotion,
                'intensity': intensity,
                'formatted': False
            }
        
        # Clean up text first
        text = self._cleanup_text(text)
        
        # Apply emotional formatting
        if emotion and intensity > 0.6:
            # High intensity emotions
            if emotion in ['excited', 'happy', 'joy']:
                # Add excitement
                if intensity > 0.8:
                    # Very high intensity - add double exclamation if not already present
                    if not text.endswith('!'):
                        text = f"{text}!!"
                    elif text.endswith('!') and not text.endswith('!!'):
                        text = f"{text}!"
                elif not text.endswith('!'):
                    text = f"{text}!"
            
            elif emotion in ['worried', 'scared', 'anxious']:
                # Add uncertainty
                if not text.endswith('...'):
                    text = f"{text}..."
            
            elif emotion in ['angry', 'frustrated']:
                # Add intensity
                if intensity > 0.8:
                    text = text.upper()
                elif intensity > 0.6:
                    # Emphasize with punctuation (only if not already present)
                    if not text.endswith('!'):
                        text = f"{text}!"
            
            elif emotion in ['sad', 'depressed']:
                # Subdued tone
                if not text.endswith('.'):
                    text = f"{text}..."
            
            elif emotion in ['curious', 'interested']:
                # Add questioning tone if not already
                if '?' not in text and not text.endswith('?'):
                    # Don't force question mark, keep as is
                    pass
        
        # Ensure proper ending punctuation
        if not text.endswith(('.', '!', '?', '...')):
            text = f"{text}."
        
        return {
            'text': text,
            'emotion': emotion,
            'intensity': intensity,
            'formatted': True
        }
    
    def _cleanup_text(self, text: str) -> str:
        """Clean up and polish text"""
        if not text:
            return text
        
        # Remove redundant spaces
        import re
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        # Fix common issues
        text = text.replace(' .', '.')
        text = text.replace(' ,', ',')
        text = text.replace(' !', '!')
        text = text.replace(' ?', '?')
        
        # Fix double periods (but preserve ellipsis)
        text = re.sub(r'\.\.(?!\.)', '.', text)
        
        # Fix "i've" → "I've", "i'm" → "I'm"
        text = re.sub(r'\bi\b', 'I', text)
        text = re.sub(r'\bi\'', 'I\'', text)
        
        # Capitalize first letter
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        
        # Capitalize after periods
        sentences = text.split('. ')
        sentences = [s[0].upper() + s[1:] if s and s[0].islower() else s for s in sentences]
        text = '. '.join(sentences)
        
        return text
    
    def _register_with_thalamus(self):
        """Register with Thalamus - DIRECT FUNCTION CALL (NO SOCKETS)"""
        try:
            result = self.thalamus.register_lobe('output', self)
            if result.get('status') == 'success':
                print("✅ Output registered with Thalamus (direct function calls)")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register with Thalamus: {e}")
            return False
    
    def _send_to_thalamus(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send message to Thalamus - DIRECT FUNCTION CALL"""
        try:
            msg_type = message.get('type')
            if msg_type == 'route_message':
                destination = message.get('destination')
                route_msg_type = message.get('msg_type')
                content = message.get('content', {})
                return self.thalamus.send_message(destination, route_msg_type, content)
            else:
                return self.thalamus.handle_request(message)
        except Exception:
            return None
    
    def _send_to_gui(self, response: Dict[str, Any]):
        """Send response to GUI through Thalamus - NO DIRECT SOCKET"""
        # GUI communication goes through Thalamus now - no direct socket
        # Thalamus will route to GUI if needed
        pass  # Removed - GUI gets responses through Thalamus
    
    def start(self):
        """Start output - register with Thalamus (NO SOCKETS)"""
        print(f"🗣️  Output Lobe: Registering with Thalamus...")
        if self.tts_available:
            if self.voice_config['enabled']:
                print("   🔊 Voice output: enabled")
            else:
                print("   🔊 Voice output: disabled")
        else:
            print("   🔊 Voice output: not available")
        print("   📝 Text output: enabled")
        print("   Communication: Direct function calls (NO SOCKETS)")
        
        # Register with Thalamus
        if not self._register_with_thalamus():
            print("❌ Failed to register with Thalamus")
            return
        
        # Keep running (Thalamus calls us directly, no listening loop needed)
        while self.running:
            time.sleep(0.1)
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming message"""
        msg_type = message.get('type')
        
        # FIX: add health probe
        if msg_type == 'health':
            return {'status': 'success', 'healthy': True, 'pid': os.getpid()}
        
        if msg_type == 'generate_output':
            content = message.get('content', {})
            formatted = self.format_output(content)
            text_output = formatted.get('text', '')
            
            # Validate text before sending
            if not text_output or not isinstance(text_output, str) or not text_output.strip():
                text_output = "I'm thinking about that."
            
            spoke = False
            if self.voice_config['enabled']:
                spoke = self.speak(text_output)
            
            # Send response to GUI
            self._send_to_gui({
                'status': 'success',
                'response': text_output,
                'spoke': spoke,
                'formatted': formatted
            })
            
            # Store conversation to Notus if user_input is provided
            user_input = content.get('user_input', '') or message.get('user_input', '')
            if user_input and user_input.strip():
                try:
                    # Store full conversation to Notus memory
                    self._send_to_thalamus({
                        'type': 'route_message',
                        'destination': 'notus',
                        'msg_type': 'store',
                        'content': {
                            'role': 'system',
                            'content': f"User: {user_input}\nABIN: {text_output}",
                            'memory_type': 'conversation'
                        }
                    })
                except Exception as e:
                    # Don't break if memory storage fails
                    print(f"⚠️  Failed to store conversation to Notus: {e}")
            
            return {
                'status': 'success',
                'text': text_output,
                'spoke': spoke,
                'formatted': formatted
            }
        
        elif msg_type == 'text_response':
            # Direct text response from Language_generation
            text = message.get('text', '')
            if not text or not isinstance(text, str) or not text.strip():
                text = "I'm thinking about that."
            
            # FIX: Prevent duplicate sends (same text within 10 seconds)
            current_time = time.time()
            if text == self.last_sent_text and (current_time - self.last_sent_time) < 10.0:
                return {'status': 'success', 'sent_to_gui': False, 'duplicate': True}
            
            self.last_sent_text = text
            self.last_sent_time = current_time
            
            spoke = False
            if self.voice_config['enabled']:
                spoke = self.speak(text)
            
            # Send response to GUI
            self._send_to_gui({
                'status': 'success',
                'response': text,
                'spoke': spoke
            })
            
            # Store conversation to Notus if user_input is provided
            user_input = message.get('user_input', '')
            if user_input and user_input.strip():
                try:
                    # Store full conversation to Notus memory
                    self._send_to_thalamus({
                        'type': 'route_message',
                        'destination': 'notus',
                        'msg_type': 'store',
                        'content': {
                            'role': 'system',
                            'content': f"User: {user_input}\nABIN: {text}",
                            'memory_type': 'conversation'
                        }
                    })
                except Exception as e:
                    # Don't break if memory storage fails
                    print(f"⚠️  Failed to store conversation to Notus: {e}")
            
            return {'status': 'success', 'sent_to_gui': True}
            
        elif msg_type == 'speak':
            # Just speak the text
            text = message.get('text', '')
            spoke = self.speak(text)
            return {'status': 'success', 'spoke': spoke}
            
        elif msg_type == 'configure_voice':
            # Configure voice settings
            if 'enabled' in message:
                self.voice_config['enabled'] = message['enabled']
            if 'rate' in message:
                self.voice_config['rate'] = message['rate']
                if self.tts_engine:
                    self.tts_engine.setProperty('rate', message['rate'])
            if 'volume' in message:
                self.voice_config['volume'] = message['volume']
                if self.tts_engine:
                    self.tts_engine.setProperty('volume', message['volume'])
            if 'profile' in message:
                profile_name = message['profile']
                if profile_name in self.voice_profiles:
                    self.voice_config['profile'] = profile_name
                    self._apply_voice_profile(profile_name)
            
            return {'status': 'success', 'config': self.voice_config}
            
        elif msg_type == 'get_status':
            # Get output system status
            return {
                'status': 'success',
                'tts_available': self.tts_available,
                'voice_enabled': self.voice_config['enabled'],
                'text_output': True
            }
            
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        if self.tts_engine:
            try:
                self.tts_engine.stop()
            except Exception:
                pass
        # No sockets to close

if __name__ == "__main__":
    lobe = OutputLobe()
    try:
        lobe.start()
    except KeyboardInterrupt:
        print("\n🛑 Output lobe shutting down...")
        lobe.shutdown()

