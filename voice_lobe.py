#!/usr/bin/env python3
"""
Voice Lobe - Speech Synthesis and Audio Output
Integrated with other lobes through central hub
"""

import socket
import struct
import json
import os
import time
import threading
import subprocess
import platform
import numpy as np
import wave
from typing import Dict, Any, Optional
from dataclasses import dataclass
import random

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

# ============================================================================
# VOICE PROFILES
# ============================================================================

@dataclass
class VoiceProfile:
    """Voice characteristics"""
    name: str
    pitch_base: float
    pitch_range: float
    formant_shift: float = 1.0
    speed: float = 1.0
    breathiness: float = 0.1
    nasality: float = 0.05
    warmth: float = 0.5
    clarity: float = 0.7
    resonance: float = 1.0
    vibrato_depth: float = 0.02
    vibrato_rate: float = 5.0

VOICE_PROFILES = {
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
    ),
    'shadowheart': VoiceProfile(
        name='Shadowheart',
        pitch_base=308.2,
        pitch_range=28.8,
        formant_shift=1.90,
        speed=0.78,
        breathiness=0.581,
        nasality=0.05,
        warmth=1.10,
        clarity=0.42,
        resonance=1.0,
        vibrato_depth=0.02,
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
}

# ============================================================================
# PHONEME DATABASE
# ============================================================================

PHONEME_FREQUENCIES = {
    'aa': {'f1': 700, 'f2': 1220, 'f3': 2600},
    'ae': {'f1': 660, 'f2': 1770, 'f3': 2540},
    'ah': {'f1': 640, 'f2': 1190, 'f3': 2540},
    'ao': {'f1': 570, 'f2': 840, 'f3': 2250},
    'aw': {'f1': 590, 'f2': 920, 'f3': 2250},
    'ay': {'f1': 650, 'f2': 1780, 'f3': 2540},
    'eh': {'f1': 530, 'f2': 1840, 'f3': 2480},
    'er': {'f1': 490, 'f2': 1350, 'f3': 1690},
    'ey': {'f1': 500, 'f2': 1900, 'f3': 2550},
    'ih': {'f1': 400, 'f2': 1920, 'f3': 2560},
    'iy': {'f1': 270, 'f2': 2360, 'f3': 3100},
    'oh': {'f1': 570, 'f2': 840, 'f3': 2250},
    'oy': {'f1': 620, 'f2': 1100, 'f3': 2250},
    'uh': {'f1': 370, 'f2': 990, 'f3': 2250},
    'uw': {'f1': 300, 'f2': 870, 'f3': 2250},
}

TEXT_TO_PHONEMES = {
    'hello': ['h', 'eh', 'l', 'oh'],
    'hi': ['h', 'ay'],
    'monday': ['m', 'ah', 'n', 'd', 'ay'],
    'matthew': ['m', 'ae', 'th', 'uw'],
    'i': ['ay'],
    'am': ['ae', 'm'],
    'the': ['th', 'ah'],
    'think': ['th', 'ih', 'ng', 'k'],
    'understand': ['ah', 'n', 'd', 'er', 's', 't', 'ae', 'n', 'd'],
    'you': ['y', 'uw'],
    'what': ['w', 'ah', 't'],
    'why': ['w', 'ay'],
}

# ============================================================================
# VOICE SYNTHESIZER
# ============================================================================

class VoiceSynthesizer:
    """Synthesize speech from text"""
    
    def __init__(self, voice_profile: VoiceProfile, sample_rate: int = 22050):
        self.voice = voice_profile
        self.sample_rate = sample_rate
        self.output_dir = "monday_audio"
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
    
    def text_to_phonemes(self, text: str) -> list:
        """Convert text to phoneme sequence"""
        text = text.lower()
        words = text.split()
        phonemes = []
        
        for word in words:
            word = ''.join(c for c in word if c.isalpha())
            
            if word in TEXT_TO_PHONEMES:
                phonemes.extend(TEXT_TO_PHONEMES[word])
            else:
                phonemes.extend(self._simple_phonemize(word))
            
            phonemes.append('sil')
        
        return phonemes
    
    def _simple_phonemize(self, word: str) -> list:
        """Fallback phonemization"""
        phonemes = []
        vowels = 'aeiou'
        for char in word:
            if char in vowels:
                phonemes.append('ah')
            else:
                phonemes.append(char)
        return phonemes
    
    def generate_sine_wave(self, frequency: float, duration_ms: float, amplitude: float = 1.0) -> np.ndarray:
        """Generate sine wave"""
        duration_s = duration_ms / 1000.0
        t = np.linspace(0, duration_s, int(self.sample_rate * duration_s))
        wave = amplitude * np.sin(2 * np.pi * frequency * t)
        return wave
    
    def apply_envelope(self, wave: np.ndarray, attack_ms: float = 10, decay_ms: float = 50) -> np.ndarray:
        """Apply ADSR envelope"""
        n_samples = len(wave)
        n_attack = int(self.sample_rate * attack_ms / 1000)
        n_decay = int(self.sample_rate * decay_ms / 1000)
        
        envelope = np.ones(n_samples)
        
        if n_attack > 0:
            envelope[:n_attack] = np.linspace(0, 1, n_attack)
        if n_decay > 0:
            envelope[-n_decay:] = np.linspace(1, 0, n_decay)
        
        return wave * envelope
    
    def generate_formant_vowel(self, phoneme: str, duration_ms: float) -> np.ndarray:
        """Generate vowel using formants"""
        if phoneme not in PHONEME_FREQUENCIES:
            return self.generate_sine_wave(200, duration_ms)
        
        freq_data = PHONEME_FREQUENCIES[phoneme]
        f1 = freq_data.get('f1', 500) * self.voice.formant_shift
        f2 = freq_data.get('f2', 1500) * self.voice.formant_shift
        f3 = freq_data.get('f3', 2500) * self.voice.formant_shift
        
        duration_s = duration_ms / 1000.0
        t = np.linspace(0, duration_s, int(self.sample_rate * duration_s))
        
        f1_amp = 0.5 + (self.voice.warmth * 0.2)
        f2_amp = 0.3 + (self.voice.clarity * 0.15)
        f3_amp = 0.2
        
        wave = (f1_amp * np.sin(2 * np.pi * f1 * t) +
                f2_amp * np.sin(2 * np.pi * f2 * t) +
                f3_amp * np.sin(2 * np.pi * f3 * t))
        
        noise = np.random.randn(len(wave)) * self.voice.breathiness * 0.1
        wave = wave + noise
        wave = wave * self.voice.resonance
        wave = wave / (np.max(np.abs(wave)) + 1e-6)
        
        return self.apply_envelope(wave, attack_ms=5, decay_ms=30)
    
    def generate_consonant(self, phoneme: str) -> np.ndarray:
        """Generate consonant sound"""
        if phoneme not in PHONEME_FREQUENCIES:
            return self.generate_sine_wave(200, 50)
        
        freq_data = PHONEME_FREQUENCIES[phoneme]
        duration = freq_data.get('duration', 60) / self.voice.speed
        
        if phoneme in ['s', 'sh', 'f', 'th', 'z', 'zh']:
            duration_s = duration / 1000.0
            noise = np.random.randn(int(self.sample_rate * duration_s)) * 0.3
            return self.apply_envelope(noise, attack_ms=2, decay_ms=10)
        else:
            frequency = self.voice.pitch_base * 0.8
            wave = self.generate_sine_wave(frequency, duration)
            return self.apply_envelope(wave, attack_ms=2, decay_ms=5)
    
    def synthesize_phoneme(self, phoneme: str) -> np.ndarray:
        """Generate waveform for a phoneme"""
        if phoneme == 'sil':
            return np.zeros(int(self.sample_rate * 0.1))
        
        if phoneme in ['aa', 'ae', 'ah', 'ao', 'aw', 'ay', 'eh', 'er', 'ey', 'ih', 'iy', 'oh', 'oy', 'uh', 'uw']:
            return self.generate_formant_vowel(phoneme, 100)
        else:
            return self.generate_consonant(phoneme)
    
    def synthesize_speech(self, text: str, emotion: str = "neutral", intensity: float = 0.5) -> np.ndarray:
        """Synthesize full speech"""
        phonemes = self.text_to_phonemes(text)
        
        # Adjust for emotion
        if emotion == "excited":
            self.voice.pitch_base *= 1.2
            self.voice.speed *= 1.1
            intensity = 1.0
        elif emotion == "sad":
            self.voice.pitch_base *= 0.8
            self.voice.speed *= 0.9
        
        audio = []
        for phoneme in phonemes:
            audio.append(self.synthesize_phoneme(phoneme))
        
        if audio:
            speech = np.concatenate(audio)
        else:
            speech = np.array([])
        
        speech = speech * intensity * 0.8
        
        return speech
    
    def save_to_file(self, audio: np.ndarray, filename: str = None) -> str:
        """Save audio to WAV file"""
        if filename is None:
            filename = f"{self.output_dir}/monday_{int(random.random() * 10000)}.wav"
        
        if not filename.startswith(self.output_dir):
            filename = os.path.join(self.output_dir, filename)
        
        audio = np.clip(audio, -1, 1)
        audio_int16 = np.int16(audio * 32767)
        
        with wave.open(filename, 'w') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_int16.tobytes())
        
        return filename
    
    def speak(self, text: str, emotion: str = "neutral", intensity: float = 0.5) -> str:
        """Synthesize and save speech"""
        audio = self.synthesize_speech(text, emotion, intensity)
        filename = self.save_to_file(audio)
        return filename

# ============================================================================
# VOICE LOBE
# ============================================================================

class VoiceLobe:
    """Voice synthesis and audio output lobe"""
    
    def __init__(self, socket_path="/tmp/voice.sock", voice_name: str = "shadowheart"):
        self.socket_path = socket_path
        self.running = True
        self.user = "Butters26"
        
        # Voice synthesis
        self.voice_profile = VOICE_PROFILES.get(voice_name, VOICE_PROFILES['monday'])
        self.synthesizer = VoiceSynthesizer(self.voice_profile)
        
        self.voice_config = {
            'enabled': True,
            'voice_name': voice_name,
            'auto_play': True
        }
    
    def synthesize_and_play(self, text: str, emotion: str = "neutral", intensity: float = 0.5) -> bool:
        """Synthesize speech and play it"""
        try:
            filename = self.synthesizer.speak(text, emotion=emotion, intensity=intensity)
            
            if self.voice_config['auto_play']:
                self._play_audio(filename)
            
            return True
        except Exception as e:
            print(f"❌ Voice error: {e}")
            return False
    
    def _play_audio(self, filename: str):
        """Play audio file"""
        try:
            if platform.system() == "Darwin":  # macOS
                subprocess.Popen(["afplay", filename])
            elif platform.system() == "Linux":
                subprocess.Popen(["paplay", filename])
            elif platform.system() == "Windows":
                os.startfile(filename)
        except Exception as e:
            print(f"Could not play audio: {e}")
    
    def set_voice(self, voice_name: str) -> bool:
        """Switch voice"""
        if voice_name in VOICE_PROFILES:
            self.voice_profile = VOICE_PROFILES[voice_name]
            self.synthesizer = VoiceSynthesizer(self.voice_profile)
            self.voice_config['voice_name'] = voice_name
            return True
        return False
    
    def handle_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming requests"""
        msg_type = message.get('type')
        
        if msg_type == 'health':
            return {'status': 'success', 'healthy': True}
        
        elif msg_type == 'synthesize':
            text = message.get('text', '')
            emotion = message.get('emotion', 'neutral')
            intensity = message.get('intensity', 0.5)
            
            filename = self.synthesizer.speak(text, emotion=emotion, intensity=intensity)
            
            return {
                'status': 'success',
                'text': text,
                'audio_file': filename,
                'emotion': emotion,
                'intensity': intensity
            }
        
        elif msg_type == 'play':
            text = message.get('text', '')
            emotion = message.get('emotion', 'neutral')
            intensity = message.get('intensity', 0.5)
            
            success = self.synthesize_and_play(text, emotion=emotion, intensity=intensity)
            
            return {
                'status': 'success' if success else 'error',
                'played': success,
                'text': text
            }
        
        elif msg_type == 'set_voice':
            voice_name = message.get('voice_name', 'monday')
            success = self.set_voice(voice_name)
            
            return {
                'status': 'success' if success else 'error',
                'voice_changed': success,
                'current_voice': self.voice_config['voice_name']
            }
        
        elif msg_type == 'get_status':
            return {
                'status': 'success',
                'voice_enabled': self.voice_config['enabled'],
                'current_voice': self.voice_config['voice_name'],
                'auto_play': self.voice_config['auto_play']
            }
        
        else:
            return {'status': 'error', 'message': f'Unknown type: {msg_type}'}
    
    def start(self):
        """Start voice lobe"""
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        sock.settimeout(1.0)
        
        print(f"🎤 Voice Lobe: Online at {self.socket_path}")
        print(f"   Voice: {self.voice_config['voice_name']}")
        print(f"   Auto-play: {self.voice_config['auto_play']}\n")
        
        while self.running:
            try:
                try:
                    conn, _ = sock.accept()
                except socket.timeout:
                    continue
                
                try:
                    conn.settimeout(5)
                    
                    length_data = _recv_all(conn, 4, timeout=5)
                    msg_length = struct.unpack('!I', length_data)[0]
                    
                    if msg_length <= 0 or msg_length > 10_000_000:
                        raise ValueError(f"Invalid length: {msg_length}")
                    
                    data = _recv_all(conn, msg_length, timeout=5)
                    message = json.loads(data.decode('utf-8'))
                    
                    result = self.handle_request(message)
                    
                    response_data = json.dumps(result).encode('utf-8')
                    response_length = struct.pack('!I', len(response_data))
                    conn.sendall(response_length + response_data)
                    
                except Exception as e:
                    try:
                        err = {'status': 'error', 'message': str(e)}
                        resp = json.dumps(err).encode('utf-8')
                        conn.sendall(struct.pack('!I', len(resp)) + resp)
                    except:
                        pass
                finally:
                    try:
                        conn.close()
                    except:
                        pass
                
            except Exception as e:
                print(f"❌ Error: {e}")
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

if __name__ == "__main__":
    lobe = VoiceLobe()
    try:
        lobe.start()
    except KeyboardInterrupt:
        print("\n🛑 Voice lobe shutting down...")
        lobe.shutdown()
