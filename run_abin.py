#!/usr/bin/env python3
"""
Monday Single-Command Runner
Runs everything in one terminal - lobes in background, GUI in foreground
FIX: Added socket verification before launching GUI
"""

import subprocess
import sys
import os
import time
import signal
import atexit

def cleanup_sockets():
    """Clean up all socket files"""
    sockets = [
        "/tmp/representation.sock", "/tmp/pattern.sock", "/tmp/reasoning.sock",
        "/tmp/notus.sock", "/tmp/emotion.sock", "/tmp/perception.sock",
        "/tmp/output.sock", "/tmp/voice.sock", "/tmp/thalamus.sock", "/tmp/language.sock",
        "/tmp/conversation.sock"
    ]
    for sock in sockets:
        try:
            if os.path.exists(sock):
                os.remove(sock)
        except:
            pass

def start_lobe(script_path: str, wait_time: float = 0.5):
    """Start a lobe in background"""
    proc = subprocess.Popen(
        [sys.executable, script_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL
    )
    time.sleep(wait_time)
    return proc

def main():
    brain_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(brain_dir)
    
    processes = []
    
    # Cleanup handler
    def cleanup():
        print("\n🛑 Shutting down Monday...")
        for proc in processes:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except:
                try:
                    proc.kill()
                except:
                    pass
        cleanup_sockets()
        print("✅ Shutdown complete\n")
    
    atexit.register(cleanup)
    
    def signal_handler(sig, frame):
        cleanup()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("\n" + "=" * 70)
    print("  🧠 Monday - Maximum Sophistication AI")
    print("=" * 70)
    
    # Clean old sockets
    cleanup_sockets()
    
    print("\n🚀 Starting brain lobes in background...\n")
    
    # Start lobes
    lobes = [
        ("Representation", "representation.py", 0.5),
        ("Pattern Recognition", "pattern_recognition.py", 0.5),
        ("Reasoning (Self-Aware)", "reasoning.py", 1.0),
        ("Language Generation", "language_generation.py", 0.5),
        ("Notus Memory", "notus.py", 8.0),
        ("Emotional Engine", "advanced_emotional_engine.py", 1.0),
        ("Perception", "perception.py", 0.5),
        ("Output", "output.py", 0.5),
        ("Voice", "voice_lobe.py", 0.5),
        ("Conversation", "conversation.py", 0.5),
        ("Thalamus", "thalamus.py", 1.0)
    ]
    
    total_wait = sum(w for _, _, w in lobes)
    print(f"(This will take about {total_wait:.0f} seconds...)\n")
    
    for name, script, wait in lobes:
        print(f"  Starting {name}...", end='', flush=True)
        proc = start_lobe(script, wait)
        processes.append(proc)
        if proc.poll() is None:
            print(" ✅")
        else:
            print(" ❌")
    
    # FIX: Verify all sockets before launching GUI
    print("\n🔍 Verifying communication channels...\n")
    time.sleep(5)  # Give Notus more time to load ML models
    
    sockets = {
        "Representation": "/tmp/representation.sock",
        "Pattern": "/tmp/pattern.sock",
        "Reasoning": "/tmp/reasoning.sock",
        "Language Generation": "/tmp/language.sock",
        "Notus": "/tmp/notus.sock",
        "Emotion": "/tmp/emotion.sock",
        "Perception": "/tmp/perception.sock",
        "Output": "/tmp/output.sock",
        "Voice": "/tmp/voice.sock",
        "Conversation": "/tmp/conversation.sock",
        "Thalamus": "/tmp/thalamus.sock"
    }
    
    all_ready = True
    for name, sock_path in sockets.items():
        if os.path.exists(sock_path):
            print(f"  ✅ {name}")
        else:
            print(f"  ❌ {name} - not ready")
            all_ready = False
    
    if not all_ready:
        print("\n❌ Some lobes failed to start. Check logs.\n")
        cleanup()
        return 1
    
    print("\n✅ All 11 lobes online and connected!")
    print("\n🎮 Launching interface...")
    print("=" * 70)
    print()
    
    # Launch GUI in foreground
    try:
        gui_proc = subprocess.Popen([sys.executable, "abin_interface.py"])
        processes.append(gui_proc)
        
        # Wait for GUI to close
        gui_proc.wait()
        
    except KeyboardInterrupt:
        pass
    
    # GUI closed - cleanup happens automatically via atexit
    return 0

if __name__ == "__main__":
    sys.exit(main())

