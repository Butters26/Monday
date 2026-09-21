#!/usr/bin/env python3
"""
Output Lobe - Expression and Communication

Designed purpose: turn language text + emotion ExpressionState into a reply
envelope the live path uses (spoken/written delivery metadata).

Inputs: language text, emotion (ExpressionState tears/voice_shake/withdraw),
        voice_prosody, emotional_tone, intensity/PAD, emphasis.
Outputs: reply envelope {text, expression, delivery, voice_prosody, tone, ...}.
TTS speaker hardware may be unavailable — honest text-buffer / metadata path.
"""

import json
import os
import time
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict, field
from thalamus import get_thalamus

try:
    from runtime_paths import runtime_dir
except Exception:  # pragma: no cover
    def runtime_dir():
        return Path(os.environ.get("MONDAY_RUNTIME_DIR") or (Path.home() / ".local/state/monday"))

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


@dataclass
class OutputEnvelope:
    """Reply envelope consumed by the live path (text + expression delivery)."""
    text: str
    emotion: Optional[str] = None
    intensity: float = 0.5
    expression: Dict[str, bool] = field(default_factory=lambda: {
        "tears": False, "voice_shake": False, "withdraw": False
    })
    emotional_tone: Optional[str] = None
    emphasis: List[str] = field(default_factory=list)
    voice_prosody: Dict[str, float] = field(default_factory=dict)
    pleasure: Optional[float] = None
    arousal: Optional[float] = None
    dominance: Optional[float] = None
    delivery: Dict[str, Any] = field(default_factory=dict)
    spoke: bool = False
    buffered: bool = False
    buffer_path: Optional[str] = None
    channel: str = "text"
    formatted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OutputLobe:
    """Output system - handles all expression and communication"""
    
    def __init__(self, thalamus=None, enable_tts: bool = True):
        self.running = True
        # Removed: self.gui_socket_path - all communication through Thalamus
        self.last_sent_text = None  # Prevent duplicate sends
        self.last_sent_time = 0.0  # FIX: Initialize time tracking
        
        # Direct reference to Thalamus (NO SOCKETS)
        self.thalamus = thalamus or get_thalamus()
        
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
        
        self.last_emotion_meta = {}
        self.last_output = None
        self.last_envelope: Optional[Dict[str, Any]] = None
        self.last_motor_action: Optional[Dict[str, Any]] = None
        self.last_voice: Optional[Dict[str, Any]] = None
        # Honest TTS stub: write spoken lines to a runtime buffer when no speaker.
        try:
            self._speech_buffer_path = Path(runtime_dir()) / "output_speech_buffer.txt"
        except Exception:
            self._speech_buffer_path = Path("/tmp/monday_output_speech_buffer.txt")
        self._speech_buffer: List[str] = []
        if enable_tts:
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
        """Hand text to Voice for synthesis when registered; else local TTS.

        Honest: returns True when Voice reports a successful synthesis attempt
        (synthesized / play_unavailable / played). Does NOT claim audio played
        unless Voice envelope.played is True — callers should read last_voice.
        Local pyttsx3 is optional fallback only.
        """
        # Prefer Voice lobe (owns speech synthesis) when registered.
        th = self.thalamus
        voice_registered = False
        if th is not None:
            try:
                lock = getattr(th, "lobe_handlers_lock", None)
                handlers = getattr(th, "lobe_handlers", {})
                if lock is not None:
                    with lock:
                        voice_registered = "voice" in handlers
                else:
                    voice_registered = "voice" in handlers
            except Exception:
                voice_registered = False

        if voice_registered:
            if not voice_prosody:
                try:
                    emotion_result = th.send_message(
                        "emotion",
                        "get_emotional_state",
                        {},
                        source="output",
                    )
                    if emotion_result and emotion_result.get("status") == "success":
                        voice_prosody = (
                            emotion_result.get("content", {}) or {}
                        ).get("voice_prosody", {})
                except Exception as e:
                    print(f"⚠️  Could not get emotional prosody: {e}")
                    voice_prosody = {}
            try:
                result = th.send_message(
                    "voice",
                    "speak_for_output",
                    {
                        "text": text,
                        "emotion": "neutral",
                        "intensity": 0.5,
                        "voice_prosody": voice_prosody or {},
                        "try_play": False,
                    },
                    source="output",
                )
                voice = None
                if isinstance(result, dict):
                    content = result.get("content") if isinstance(result.get("content"), dict) else {}
                    voice = content.get("voice") or result.get("voice")
                if isinstance(voice, dict):
                    self.last_voice = dict(voice)
                    if isinstance(self.last_envelope, dict):
                        env = dict(self.last_envelope)
                        env["voice"] = dict(voice)
                        self.last_envelope = env
                    return voice.get("status") in (
                        "synthesized",
                        "play_unavailable",
                        "played",
                    )
                return result.get("status") == "success"
            except Exception as e:
                print(f"❌ Voice handoff error: {e}")

        if not self.tts_available or not self.voice_config["enabled"]:
            return False

        # Fallback: local pyttsx3 only when Voice absent and TTS enabled.
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
        
        # ExpressionState delivery shaping (non-preserve path).
        expression = self.normalize_expression(content.get('expression') or {})
        if expression.get('tears'):
            # Soften terminal punctuation toward ellipsis when tearful.
            if text.endswith('.'):
                text = text[:-1] + '...'
            elif not text.endswith(('...', '!', '?')):
                text = f"{text}..."
        if expression.get('voice_shake') and '...' not in text:
            words = text.split()
            if len(words) > 4:
                text = f"{' '.join(words[:3])} ... {' '.join(words[3:])}"
        if expression.get('withdraw'):
            # Withdrawn delivery: avoid shouty transforms already applied.
            if text.isupper() and len(text) > 4:
                text = text[0] + text[1:].lower()

        return {
            'text': text,
            'emotion': emotion,
            'intensity': intensity,
            'expression': expression,
            'voice_prosody': content.get('voice_prosody') or {},
            'emotional_tone': content.get('emotional_tone'),
            'emphasis': content.get('emphasis') or [],
            'pleasure': content.get('pleasure'),
            'arousal': content.get('arousal'),
            'dominance': content.get('dominance'),
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
    
    @staticmethod
    def normalize_expression(expression: Any) -> Dict[str, bool]:
        """Normalize ExpressionState (dict or object) to tears/voice_shake/withdraw."""
        if expression is None:
            expression = {}
        if hasattr(expression, "tears") and not isinstance(expression, dict):
            return {
                "tears": bool(getattr(expression, "tears", False)),
                "voice_shake": bool(getattr(expression, "voice_shake", False)),
                "withdraw": bool(getattr(expression, "withdraw", False)),
            }
        if not isinstance(expression, dict):
            return {"tears": False, "voice_shake": False, "withdraw": False}
        return {
            "tears": bool(expression.get("tears", False)),
            "voice_shake": bool(expression.get("voice_shake", False)),
            "withdraw": bool(expression.get("withdraw", False)),
        }

    def derive_delivery(
        self,
        expression: Dict[str, bool],
        voice_prosody: Optional[Dict[str, float]] = None,
        emotional_tone: Optional[str] = None,
        intensity: float = 0.5,
    ) -> Dict[str, Any]:
        """Derive delivery metadata/behavior from ExpressionState + prosody."""
        prosody = dict(voice_prosody or {})
        markers: List[str] = []
        # Expression → delivery behavior (metadata; hardware TTS may be stubbed).
        if expression.get("tears"):
            markers.append("tearful")
            prosody["warmth"] = float(prosody.get("warmth", 0.5)) * 0.85
            prosody["speed"] = float(prosody.get("speed", 1.0)) * 0.92
            prosody["pitch"] = float(prosody.get("pitch", 1.0)) * 0.95
        if expression.get("voice_shake"):
            markers.append("voice_shake")
            prosody["clarity"] = float(prosody.get("clarity", 1.0)) * 0.82
            prosody["pitch_jitter"] = 0.12 + 0.1 * float(intensity or 0.5)
            prosody["speed"] = float(prosody.get("speed", 1.0)) * 0.9
        if expression.get("withdraw"):
            markers.append("withdraw")
            prosody["volume"] = min(float(prosody.get("volume", 1.0)), 0.55)
            prosody["confidence"] = float(prosody.get("confidence", 0.7)) * 0.7
            prosody["speed"] = float(prosody.get("speed", 1.0)) * 0.88
        if not markers:
            markers.append("calm_delivery")

        channel = "text"
        tts_reason = None
        if self.voice_config.get("enabled") and self.tts_available:
            channel = "tts"
        else:
            channel = "text_buffer"
            if not self.tts_available:
                tts_reason = "tts_engine_unavailable"
            elif not self.voice_config.get("enabled"):
                tts_reason = "voice_disabled"

        return {
            "markers": markers,
            "channel": channel,
            "tts_reason": tts_reason,
            "prosody": prosody,
            "emotional_tone": emotional_tone,
            "intensity": float(intensity if intensity is not None else 0.5),
            "expression_active": bool(
                expression.get("tears")
                or expression.get("voice_shake")
                or expression.get("withdraw")
            ),
        }

    def build_envelope(self, content: Dict[str, Any], text: str, spoke: bool = False) -> OutputEnvelope:
        """Build the reply envelope from language text + emotion expression fields."""
        expression = self.normalize_expression(content.get("expression") or {})
        try:
            intensity = float(content.get("intensity", 0.5) if content.get("intensity") is not None else 0.5)
        except (TypeError, ValueError):
            intensity = 0.5
        voice_prosody = content.get("voice_prosody") or {}
        if not isinstance(voice_prosody, dict):
            voice_prosody = {}
        emotional_tone = content.get("emotional_tone")
        delivery = self.derive_delivery(
            expression,
            voice_prosody=voice_prosody,
            emotional_tone=emotional_tone if isinstance(emotional_tone, str) else None,
            intensity=intensity,
        )
        buffered = False
        buffer_path = None
        # Always record delivery to the text buffer (honest stub when no speaker).
        try:
            buffered, buffer_path = self._buffer_delivery(text, delivery)
            delivery["buffered"] = buffered
            delivery["buffer_path"] = buffer_path
        except Exception as exc:
            delivery["buffer_error"] = str(exc)

        emphasis = content.get("emphasis") or []
        if not isinstance(emphasis, list):
            emphasis = []

        return OutputEnvelope(
            text=text,
            emotion=content.get("emotion"),
            intensity=intensity,
            expression=expression,
            emotional_tone=emotional_tone if isinstance(emotional_tone, str) else None,
            emphasis=list(emphasis),
            voice_prosody=dict(delivery.get("prosody") or voice_prosody),
            pleasure=content.get("pleasure"),
            arousal=content.get("arousal"),
            dominance=content.get("dominance"),
            delivery=delivery,
            spoke=bool(spoke),
            buffered=buffered,
            buffer_path=buffer_path,
            channel=str(delivery.get("channel") or "text"),
            formatted=bool(content.get("formatted", False)),
        )

    def _buffer_delivery(self, text: str, delivery: Dict[str, Any]) -> tuple:
        """Write spoken/written line to runtime buffer (TTS-speaker stand-in)."""
        if not text or not str(text).strip():
            return False, None
        path = self._speech_buffer_path
        path.parent.mkdir(parents=True, exist_ok=True)
        markers = ",".join(delivery.get("markers") or [])
        line = (
            f"{time.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"markers={markers} | tone={delivery.get('emotional_tone')} | "
            f"{str(text).strip()}\n"
        )
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)
        self._speech_buffer.append(str(text).strip())
        if len(self._speech_buffer) > 50:
            self._speech_buffer = self._speech_buffer[-50:]
        return True, str(path)

    def get_last_envelope(self) -> Optional[Dict[str, Any]]:
        return dict(self.last_envelope) if isinstance(self.last_envelope, dict) else None

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
        payload = message.get('content', message)
        
        # FIX: add health probe
        if msg_type == 'health':
            return {'status': 'success', 'healthy': True, 'pid': os.getpid()}
        
        if msg_type == 'generate_output':
            content = payload if isinstance(payload, dict) else {}
            preserve = bool(content.get('preserve_text')) and isinstance(content.get('text'), str)
            if preserve:
                # Live path: keep language text intact; expression drives delivery envelope.
                expression = self.normalize_expression(content.get('expression') or {})
                formatted = {
                    'text': content['text'],
                    'emotion': content.get('emotion'),
                    'intensity': content.get('intensity', 0.5),
                    'voice_prosody': content.get('voice_prosody') or {},
                    'emotional_tone': content.get('emotional_tone'),
                    'emphasis': content.get('emphasis') or [],
                    'expression': expression,
                    'pleasure': content.get('pleasure'),
                    'arousal': content.get('arousal'),
                    'dominance': content.get('dominance'),
                    'formatted': False,
                }
            else:
                formatted = self.format_output(content)
                # Ensure expression survives format_output for envelope build.
                if 'expression' not in formatted or not formatted.get('expression'):
                    formatted['expression'] = self.normalize_expression(
                        content.get('expression') or {}
                    )
                for key in (
                    'voice_prosody', 'emotional_tone', 'emphasis',
                    'pleasure', 'arousal', 'dominance',
                ):
                    if key not in formatted and key in content:
                        formatted[key] = content.get(key)

            text_output = formatted.get('text', '')
            if not text_output or not isinstance(text_output, str) or not text_output.strip():
                text_output = "I'm thinking about that."
            formatted['text'] = text_output

            self.last_emotion_meta = {
                'emotion': formatted.get('emotion'),
                'intensity': formatted.get('intensity'),
                'voice_prosody': formatted.get('voice_prosody') or {},
                'emotional_tone': formatted.get('emotional_tone'),
                'emphasis': formatted.get('emphasis') or [],
                'expression': self.normalize_expression(formatted.get('expression') or {}),
            }

            spoke = False
            if self.voice_config['enabled']:
                spoke = self.speak(
                    text_output,
                    voice_prosody=formatted.get('voice_prosody') or {},
                )

            envelope_obj = self.build_envelope(formatted, text_output, spoke=spoke)
            envelope = envelope_obj.to_dict()
            self.last_envelope = envelope
            self.last_output = text_output

            self._send_to_gui({
                'status': 'success',
                'response': text_output,
                'spoke': spoke,
                'formatted': formatted,
                'envelope': envelope,
            })

            user_input = content.get('user_input', '') or message.get('user_input', '')
            if content.get('store_user_input') and user_input and user_input.strip():
                try:
                    self._send_to_thalamus({
                        'type': 'route_message',
                        'destination': 'notus',
                        'msg_type': 'store',
                        'content': {
                            'role': 'user',
                            'content': user_input,
                            'memory_type': 'conversation',
                            'user_id': content.get('user_id', 'default'),
                        }
                    })
                except Exception as e:
                    print(f"⚠️  Failed to store conversation to Notus: {e}")

            return {
                'status': 'success',
                'content': {
                    'text': text_output,
                    'spoke': spoke,
                    'formatted': formatted,
                    'envelope': envelope,
                    'expression': envelope.get('expression'),
                    'delivery': envelope.get('delivery'),
                    'emotional_tone': envelope.get('emotional_tone'),
                    'voice_prosody': envelope.get('voice_prosody'),
                    'channel': envelope.get('channel'),
                    'buffered': envelope.get('buffered'),
                    'buffer_path': envelope.get('buffer_path'),
                },
                'text': text_output,
                'spoke': spoke,
                'formatted': formatted,
                'envelope': envelope,
            }
        
        elif msg_type == 'text_response':
            # Direct text response from Language_generation
            text = payload.get('text', '')
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
            
            # Store only explicit, structured user input; never a transcript.
            user_input = payload.get('user_input', '')
            if payload.get('store_user_input') and user_input and user_input.strip():
                try:
                    self._send_to_thalamus({
                        'type': 'route_message',
                        'destination': 'notus',
                        'msg_type': 'store',
                        'content': {
                            'role': 'user',
                            'content': user_input,
                            'memory_type': 'conversation',
                            'user_id': payload.get('user_id', 'default'),
                        }
                    })
                except Exception as e:
                    # Don't break if memory storage fails
                    print(f"⚠️  Failed to store conversation to Notus: {e}")
            
            self.last_output = text
            # Minimal envelope so text_response path still exposes delivery metadata.
            mini = self.build_envelope(
                {
                    'emotion': payload.get('emotion'),
                    'intensity': payload.get('intensity', 0.5),
                    'expression': payload.get('expression') or {},
                    'voice_prosody': payload.get('voice_prosody') or {},
                    'emotional_tone': payload.get('emotional_tone'),
                    'emphasis': payload.get('emphasis') or [],
                },
                text,
                spoke=spoke,
            )
            self.last_envelope = mini.to_dict()
            return {
                'status': 'success',
                'content': {
                    'text': text,
                    'sent_to_gui': True,
                    'envelope': self.last_envelope,
                    'expression': self.last_envelope.get('expression'),
                    'delivery': self.last_envelope.get('delivery'),
                },
                'sent_to_gui': True,
            }
            
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
            env = self.last_envelope or {}
            delivery = env.get('delivery') or {}
            return {
                'status': 'success',
                'tts_available': self.tts_available,
                'voice_enabled': self.voice_config['enabled'],
                'text_output': True,
                'channel': env.get('channel') or (
                    'tts' if (self.tts_available and self.voice_config['enabled']) else 'text_buffer'
                ),
                'speech_buffer_path': str(self._speech_buffer_path),
                'last_envelope_present': bool(self.last_envelope),
                'last_expression': (env.get('expression') if env else None),
                'last_delivery_markers': list(delivery.get('markers') or []),
                'last_motor_action': dict(self.last_motor_action) if self.last_motor_action else None,
                'last_voice': dict(self.last_voice) if self.last_voice else None,
                'content': {
                    'tts_available': self.tts_available,
                    'voice_enabled': self.voice_config['enabled'],
                    'text_output': True,
                    'channel': env.get('channel'),
                    'last_envelope_present': bool(self.last_envelope),
                },
            }


        elif msg_type == 'motor_output':
            # MotorActionLobe surfaces a planned/queued action envelope (no actuators).
            action = payload.get('action') if isinstance(payload, dict) else None
            if action is None and isinstance(message.get('action'), dict):
                action = message.get('action')
            if not isinstance(action, dict):
                return {'status': 'error', 'message': 'motor_output requires action dict'}
            action = dict(action)
            self.last_motor_action = action
            # Attach onto last reply envelope when one exists this turn.
            if isinstance(self.last_envelope, dict):
                env = dict(self.last_envelope)
                env['motor_action'] = action
                self.last_envelope = env
            return {
                'status': 'success',
                'content': {
                    'action': action,
                    'envelope_attached': bool(
                        isinstance(self.last_envelope, dict)
                        and self.last_envelope.get('motor_action')
                    ),
                },
                'action': action,
            }


        elif msg_type == 'voice_output':
            # VoiceLobe surfaces a speech envelope (synth file / honest play status).
            voice = payload.get('voice') if isinstance(payload, dict) else None
            if voice is None and isinstance(message.get('voice'), dict):
                voice = message.get('voice')
            if not isinstance(voice, dict):
                return {'status': 'error', 'message': 'voice_output requires voice dict'}
            voice = dict(voice)
            self.last_voice = voice
            if isinstance(self.last_envelope, dict):
                env = dict(self.last_envelope)
                env['voice'] = voice
                self.last_envelope = env
            return {
                'status': 'success',
                'content': {
                    'voice': voice,
                    'envelope_attached': bool(
                        isinstance(self.last_envelope, dict)
                        and self.last_envelope.get('voice')
                    ),
                },
                'voice': voice,
            }

        elif msg_type == 'get_last_envelope':
            env = self.get_last_envelope()
            if not env:
                return {'status': 'success', 'content': {'envelope': None}, 'envelope': None}
            return {'status': 'success', 'content': {'envelope': env}, 'envelope': env}
            
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
