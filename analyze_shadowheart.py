#!/usr/bin/env python3
"""
Analyze multiple Shadowheart voice files and create averaged voice profile
"""

import os
import sys
import numpy as np
from voice_analyzer import VoiceAnalyzer
from pathlib import Path

def analyze_multiple_files(wav_dir: str, max_files: int = 20) -> dict:
    """Analyze multiple WAV files and average the results"""
    
    # Find all WAV files
    wav_files = []
    for root, dirs, files in os.walk(wav_dir):
        for file in files:
            if file.lower().endswith('.wav'):
                wav_files.append(os.path.join(root, file))
    
    if len(wav_files) == 0:
        print(f"❌ No WAV files found in {wav_dir}")
        return None
    
    # Sample files (don't analyze all 198)
    if len(wav_files) > max_files:
        import random
        wav_files = random.sample(wav_files, max_files)
        print(f"📊 Analyzing {max_files} random samples from {len(wav_files)} total files...")
    else:
        print(f"📊 Analyzing {len(wav_files)} files...")
    
    all_profiles = []
    successful = 0
    
    for i, wav_file in enumerate(wav_files, 1):
        try:
            print(f"[{i}/{len(wav_files)}] Analyzing {os.path.basename(wav_file)}...", end=" ")
            analyzer = VoiceAnalyzer(wav_file)
            result = analyzer.analyze_full()
            
            profile = result['voice_profile']
            # Only include valid profiles
            if not np.isnan(profile['pitch_base']) and profile['pitch_base'] > 0:
                all_profiles.append(profile)
                successful += 1
                print("✅")
            else:
                print("❌ (invalid)")
        except Exception as e:
            print(f"❌ Error: {e}")
            continue
    
    if len(all_profiles) == 0:
        print("❌ No valid profiles extracted")
        return None
    
    # Average the profiles
    avg_profile = {
        'pitch_base': np.mean([p['pitch_base'] for p in all_profiles]),
        'pitch_range': np.mean([p['pitch_range'] for p in all_profiles]),
        'formant_shift': np.mean([p['formant_shift'] for p in all_profiles]),
        'speed': np.mean([p['speed'] for p in all_profiles]),
        'breathiness': np.mean([p['breathiness'] for p in all_profiles]),
        'warmth': np.mean([p['warmth'] for p in all_profiles]),
        'clarity': np.mean([p['clarity'] for p in all_profiles]),
    }
    
    print(f"\n✅ Successfully analyzed {successful}/{len(wav_files)} files")
    
    return avg_profile

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_shadowheart.py <wav_directory> [max_files]")
        print("\nExample:")
        print("  python3 analyze_shadowheart.py '/Users/matthew/Desktop/baldur gate sounds' 20")
        sys.exit(1)
    
    wav_dir = sys.argv[1]
    max_files = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    
    if not os.path.isdir(wav_dir):
        print(f"❌ Directory not found: {wav_dir}")
        sys.exit(1)
    
    profile = analyze_multiple_files(wav_dir, max_files)
    
    if profile:
        print("\n" + "="*60)
        print("SHADOWHEART VOICE PROFILE (Averaged)")
        print("="*60)
        print(f"""
VoiceProfile(
    name='Shadowheart',
    pitch_base={profile['pitch_base']:.1f},
    pitch_range={profile['pitch_range']:.1f},
    formant_shift={profile['formant_shift']:.2f},
    speed={profile['speed']:.2f},
    breathiness={profile['breathiness']:.3f},
    warmth={profile['warmth']:.2f},
    clarity={profile['clarity']:.2f}
)""")
        print("\nAdd this to voice_lobe.py VOICE_PROFILES dictionary!")

