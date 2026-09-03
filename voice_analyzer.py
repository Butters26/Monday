#!/usr/bin/env python3
"""
Voice Analyzer - Extract vocal characteristics from audio samples
Measures pitch, formants, breathiness, speed to clone a voice
"""

import numpy as np
import librosa
import soundfile as sf
from typing import Dict, Any, Tuple
import matplotlib.pyplot as plt
import sys

class VoiceAnalyzer:
    """Analyze audio to extract voice characteristics"""
    
    def __init__(self, audio_file: str, sr: int = 22050):
        self.audio_file = audio_file
        self.sr = sr
        self.y, self.sr = librosa.load(audio_file, sr=sr)
    
    def get_pitch_characteristics(self) -> Dict[str, float]:
        """Extract pitch info"""
        # Use pyin for pitch tracking
        f0, voiced_flag, voiced_probs = librosa.pyin(self.y, fmin=50, fmax=400, sr=self.sr)
        
        # Remove NaN values
        f0_clean = f0[~np.isnan(f0)]
        
        if len(f0_clean) == 0:
            return {'base_pitch': 0, 'pitch_range': 0}
        
        return {
            'base_pitch': float(np.median(f0_clean)),
            'pitch_range': float(np.std(f0_clean)),
            'min_pitch': float(np.min(f0_clean)),
            'max_pitch': float(np.max(f0_clean))
        }
    
    def get_formants(self) -> Dict[str, float]:
        """Extract formant frequencies"""
        # Simple formant estimation using LPC
        order = 10
        
        # Split into frames
        frame_length = int(0.025 * self.sr)  # 25ms frames
        hop_length = int(0.010 * self.sr)    # 10ms hop
        
        frames = librosa.util.frame(self.y, frame_length=frame_length, hop_length=hop_length)
        
        formants_f1 = []
        formants_f2 = []
        formants_f3 = []
        
        for frame in frames[:100]:  # Sample first 100 frames
            if np.sum(np.abs(frame)) == 0:
                continue
            
            # Apply window
            frame = frame * np.hanning(len(frame))
            
            # LPC analysis
            try:
                a = librosa.lpc(frame, order=order)
                
                # Find formants from LPC coefficients
                roots = np.roots(a)
                angles = np.angle(roots)
                freqs = np.abs(angles * self.sr / (2 * np.pi))
                
                # Filter for valid formant range (200-4000 Hz) and positive
                freqs = freqs[(freqs > 200) & (freqs < 4000)]
                freqs = np.sort(freqs)
                
                if len(freqs) >= 3:
                    formants_f1.append(freqs[0])
                    formants_f2.append(freqs[1])
                    formants_f3.append(freqs[2])
            except:
                continue
        
        return {
            'f1_mean': float(np.mean(formants_f1)) if formants_f1 else 0,
            'f2_mean': float(np.mean(formants_f2)) if formants_f2 else 0,
            'f3_mean': float(np.mean(formants_f3)) if formants_f3 else 0,
            'f1_std': float(np.std(formants_f1)) if formants_f1 else 0,
        }
    
    def get_spectral_characteristics(self) -> Dict[str, float]:
        """Extract spectral properties"""
        # Spectral centroid
        spectral_centroids = librosa.feature.spectral_centroid(y=self.y, sr=self.sr)[0]
        
        # Spectral rolloff
        spectral_rolloff = librosa.feature.spectral_rolloff(y=self.y, sr=self.sr)[0]
        
        # MFCC for overall timbral quality
        mfcc = librosa.feature.mfcc(y=self.y, sr=self.sr, n_mfcc=13)
        
        return {
            'spectral_centroid': float(np.mean(spectral_centroids)),
            'spectral_rolloff': float(np.mean(spectral_rolloff)),
            'brightness': float(np.mean(spectral_centroids) / 4000),  # Normalized
            'mfcc_mean': float(np.mean(mfcc[1:]))  # Skip energy
        }
    
    def get_breathiness(self) -> float:
        """Estimate breathiness (noise content)"""
        # High-frequency energy ratio
        stft = np.abs(librosa.stft(self.y))
        
        # Convert frequency bins to Hz
        freqs = librosa.fft_frequencies(sr=self.sr)
        high_freq_bin = np.where(freqs >= 3000)[0]
        
        if len(high_freq_bin) == 0:
            return 0.1  # Default low breathiness
        
        # Separate into frequency bands
        high_freq = stft[high_freq_bin[0]:, :].mean()
        total = stft.mean()
        
        if total == 0 or np.isnan(total):
            return 0.1
        
        breathiness = high_freq / (total + 1e-8)
        
        return float(np.clip(breathiness, 0.0, 1.0))
    
    def get_speech_rate(self) -> float:
        """Estimate speech rate"""
        # Use onset detection
        onset_env = librosa.onset.onset_strength(y=self.y, sr=self.sr)
        onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=self.sr)
        
        # Phoneme rate estimate
        duration = len(self.y) / self.sr
        phoneme_rate = len(onsets) / duration
        
        # Convert to speed multiplier (1.0 = normal)
        speed = phoneme_rate / 5.0  # Assume 5 phonemes/sec is normal
        
        return float(np.clip(speed, 0.7, 1.3))
    
    def analyze_full(self) -> Dict[str, Any]:
        """Full voice analysis"""
        print(f"Analyzing {self.audio_file}...")
        
        pitch = self.get_pitch_characteristics()
        formants = self.get_formants()
        spectral = self.get_spectral_characteristics()
        breathiness = self.get_breathiness()
        speed = self.get_speech_rate()
        
        # Estimate voice characteristics
        characteristics = {
            'pitch_base': pitch['base_pitch'],
            'pitch_range': pitch['pitch_range'],
            'formant_shift': max(formants['f1_mean'] / 700.0, 0.5) if formants['f1_mean'] > 0 else 1.0,
            'speed': speed,
            'breathiness': breathiness,
            'warmth': (spectral['brightness'] - 0.3) * 2,  # Normalize
            'clarity': 1.0 - breathiness,
        }
        
        return {
            'file': self.audio_file,
            'pitch': pitch,
            'formants': formants,
            'spectral': spectral,
            'breathiness': breathiness,
            'speech_rate': speed,
            'voice_profile': characteristics
        }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 voice_analyzer.py <audio_file>")
        print("\nExample:")
        print("  python3 voice_analyzer.py shadowheart_voice.wav")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    
    analyzer = VoiceAnalyzer(audio_file)
    result = analyzer.analyze_full()
    
    print("\n" + "="*60)
    print(f"VOICE ANALYSIS: {result['file']}")
    print("="*60)
    
    print("\nPitch Characteristics:")
    for k, v in result['pitch'].items():
        print(f"  {k}: {v:.2f}")
    
    print("\nFormants:")
    for k, v in result['formants'].items():
        print(f"  {k}: {v:.2f}")
    
    print("\nVoice Profile (for voice_lobe.py):")
    profile = result['voice_profile']
    print(f"""
VoiceProfile(
    name='NewVoice',
    pitch_base={profile['pitch_base']:.1f},
    pitch_range={profile['pitch_range']:.1f},
    formant_shift={profile['formant_shift']:.2f},
    speed={profile['speed']:.2f},
    breathiness={profile['breathiness']:.3f},
    warmth={profile['warmth']:.2f},
    clarity={profile['clarity']:.2f}
)""")

