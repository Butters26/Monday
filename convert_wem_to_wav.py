#!/usr/bin/env python3
"""
Convert WEM files to WAV for voice analysis
WEM files are from games like Baldur's Gate 3
"""

import os
import sys
import subprocess
from pathlib import Path

def convert_wem_to_wav(wem_file: str, output_file: str = None) -> str:
    """Convert WEM file to WAV using vgmstream (for game audio)"""
    
    if output_file is None:
        output_file = wem_file.replace('.wem', '.wav').replace('.WEM', '.wav')
    
    # Try vgmstream first (best for game audio WEM files)
    try:
        subprocess.run([
            'vgmstream-cli', '-o', output_file, wem_file
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print(f"✅ Converted: {os.path.basename(wem_file)} -> {os.path.basename(output_file)}")
        return output_file
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fall through to ffmpeg
        pass
    
    # Fallback to ffmpeg (may not work for all WEM files)
    try:
        subprocess.run(['ffmpeg', '-version'], 
                      stdout=subprocess.DEVNULL, 
                      stderr=subprocess.DEVNULL, 
                      check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"❌ Neither vgmstream nor ffmpeg found. Install vgmstream: brew install vgmstream")
        return None
    
    try:
        subprocess.run([
            'ffmpeg', '-i', wem_file,
            '-acodec', 'pcm_s16le',
            '-ar', '22050',
            '-ac', '1',
            output_file
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print(f"✅ Converted: {os.path.basename(wem_file)} -> {os.path.basename(output_file)}")
        return output_file
    except subprocess.CalledProcessError as e:
        print(f"❌ Conversion failed for {os.path.basename(wem_file)}: {e}")
        return None

def find_wem_files(directory: str) -> list:
    """Find all WEM files in directory"""
    wem_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.lower().endswith('.wem'):
                wem_files.append(os.path.join(root, file))
    return wem_files

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 convert_wem_to_wav.py <wem_file>")
        print("  python3 convert_wem_to_wav.py <directory>  # Convert all WEM files in directory")
        print("\nExample:")
        print("  python3 convert_wem_to_wav.py shadowheart_voice.wem")
        print("  python3 convert_wem_to_wav.py ./audio_files/")
        sys.exit(1)
    
    input_path = sys.argv[1]
    
    if os.path.isfile(input_path):
        # Single file
        if input_path.lower().endswith('.wem'):
            convert_wem_to_wav(input_path)
        else:
            print("❌ File must be a .wem file")
    elif os.path.isdir(input_path):
        # Directory - convert all WEM files
        wem_files = find_wem_files(input_path)
        print(f"Found {len(wem_files)} WEM files")
        
        for wem_file in wem_files:
            convert_wem_to_wav(wem_file)
        
        print(f"\n✅ Converted {len(wem_files)} files")
    else:
        print(f"❌ Path not found: {input_path}")

