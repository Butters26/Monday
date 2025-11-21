#!/usr/bin/env python3
"""
Brain Startup Script
Launches all brain lobes as independent processes
"""

import subprocess
import time
import os
import signal
import sys

class BrainStarter:
    def __init__(self):
        self.processes = []
        self.brain_dir = os.path.dirname(os.path.abspath(__file__))
        
    def start_lobe(self, name: str, script: str):
        """Start a brain lobe as subprocess"""
        print(f"🚀 Starting {name}...")
        script_path = os.path.join(self.brain_dir, script)
        process = subprocess.Popen(
            [sys.executable, script_path],
            cwd=self.brain_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.processes.append((name, process))
        time.sleep(0.5)  # Give it time to start
        
        # Check if it started successfully
        if process.poll() is None:
            print(f"   ✅ {name} started (PID: {process.pid})")
            return True
        else:
            print(f"   ❌ {name} failed to start")
            return False
    
    def start_all(self):
        """Start all brain lobes"""
        print("🧠 Starting Brain System...")
        print("=" * 60)
        
        # Start lobes in order
        lobes = [
            ("Representation Layer", "representation.py"),
            ("Pattern Recognition", "pattern_recognition.py"),
            ("Reasoning (Thinking)", "reasoning.py"),
            ("Notus (Memory)", "notus.py"),
            ("Emotional Engine", "advanced_emotional_engine.py"),
            ("Perception (Ears/Eyes)", "perception.py"),
            ("Output (Voice/Text)", "output.py"),
            ("Thalamus (Coordinator)", "thalamus.py"),
        ]
        
        for name, script in lobes:
            if not self.start_lobe(name, script):
                print(f"\n❌ Failed to start {name}. Shutting down...")
                self.shutdown_all()
                return False
        
        print("\n✅ All lobes started successfully!")
        print("\n🎯 ABIN is online and ready")
        print("   Launch interface with: python3 abin_interface.py")
        
        # Keep running until interrupted
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n⚠️  Shutdown signal received")
        
        return True
    
    def shutdown_all(self):
        """Shutdown all lobes"""
        print("\n🛑 Shutting down all lobes...")
        for name, process in self.processes:
            try:
                print(f"   Stopping {name}...")
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"   Force killing {name}...")
                process.kill()
        
        # Clean up socket files
        socket_files = [
            "/tmp/notus.sock",
            "/tmp/emotion.sock",
            "/tmp/perception.sock",
            "/tmp/reasoning.sock",
            "/tmp/output.sock",
            "/tmp/pattern.sock",
            "/tmp/representation.sock",
            "/tmp/thalamus.sock"
        ]
        
        for sock_file in socket_files:
            try:
                if os.path.exists(sock_file):
                    os.remove(sock_file)
            except:
                pass
        
        print("✅ All lobes stopped")

def signal_handler(sig, frame):
    """Handle Ctrl+C"""
    print("\n\n⚠️  Interrupt received...")
    starter.shutdown_all()
    sys.exit(0)

if __name__ == "__main__":
    starter = BrainStarter()
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        starter.start_all()
    finally:
        starter.shutdown_all()

