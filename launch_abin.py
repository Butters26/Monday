#!/usr/bin/env python3
"""
ABIN Single-Launch System
Starts all lobes in background, launches GUI, manages shutdown
Like launching a game - one command does everything
"""

import subprocess
import sys
import os
import time
import signal
import atexit

class ABINLauncher:
    def __init__(self):
        self.brain_dir = os.path.dirname(os.path.abspath(__file__))
        self.lobe_processes = []
        self.gui_process = None
        
        # Register cleanup on exit
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
    def start_lobe_background(self, name: str, script: str) -> bool:
        """Start a lobe as detached background process"""
        script_path = os.path.join(self.brain_dir, script)
        
        # Start process completely detached
        process = subprocess.Popen(
            [sys.executable, script_path],
            cwd=self.brain_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True  # Detach from terminal
        )
        
        # Give it a moment
        time.sleep(0.3)
        
        # Check if it's still alive
        if process.poll() is None:
            self.lobe_processes.append((name, process))
            return True
        else:
            return False
    
    def check_lobe_online(self, socket_path: str, max_wait: float = 5.0) -> bool:
        """Wait for lobe socket to appear"""
        start = time.time()
        while time.time() - start < max_wait:
            if os.path.exists(socket_path):
                return True
            time.sleep(0.1)
        return False
    
    def launch(self):
        """Launch entire ABIN system"""
        print("\n" + "=" * 70)
        print("  🧠 ABIN LAUNCHER")
        print("=" * 70)
        
        # Clean up old sockets first
        print("\n🧹 Cleaning up old sockets...")
        sockets = [
            "/tmp/representation.sock",
            "/tmp/pattern.sock", 
            "/tmp/reasoning.sock",
            "/tmp/notus.sock",
            "/tmp/emotion.sock",
            "/tmp/perception.sock",
            "/tmp/output.sock",
            "/tmp/thalamus.sock"
        ]
        for sock in sockets:
            if os.path.exists(sock):
                os.remove(sock)
        
        # Start all lobes
        print("\n🚀 Starting brain lobes...")
        
        lobes = [
            ("Representation", "representation.py", "/tmp/representation.sock"),
            ("Pattern Recognition", "pattern_recognition.py", "/tmp/pattern.sock"),
            ("Reasoning", "reasoning.py", "/tmp/reasoning.sock"),
            ("Notus Memory", "notus.py", "/tmp/notus.sock"),
            ("Emotional Engine", "advanced_emotional_engine.py", "/tmp/emotion.sock"),
            ("Perception", "perception.py", "/tmp/perception.sock"),
            ("Output", "output.py", "/tmp/output.sock"),
            ("Thalamus", "thalamus.py", "/tmp/thalamus.sock"),
        ]
        
        failed = []
        
        for name, script, socket_path in lobes:
            if self.start_lobe_background(name, script):
                # Notus takes longer to load (big memory system)
                wait_time = 10.0 if 'notus' in script.lower() else 3.0
                if self.check_lobe_online(socket_path, max_wait=wait_time):
                    print(f"   ✅ {name}")
                else:
                    print(f"   ⚠️  {name} started but socket not ready")
            else:
                print(f"   ❌ {name} FAILED")
                failed.append(name)
        
        if failed:
            print(f"\n❌ Failed lobes: {', '.join(failed)}")
            print("   Shutting down...")
            self.cleanup()
            return False
        
        print(f"\n✅ All {len(lobes)} lobes online")
        
        # Verify sockets exist
        print("\n🔍 Verifying connections...")
        all_online = True
        for name, script, socket_path in lobes:
            if os.path.exists(socket_path):
                print(f"   ✅ {socket_path.split('/')[-1]}")
            else:
                print(f"   ❌ {socket_path.split('/')[-1]} missing")
                all_online = False
        
        if not all_online:
            print("\n❌ Some lobes not responding. Shutting down...")
            self.cleanup()
            return False
        
        # Launch GUI
        print("\n🎮 Launching interface...")
        print("=" * 70)
        
        gui_path = os.path.join(self.brain_dir, 'abin_interface.py')
        self.gui_process = subprocess.Popen(
            [sys.executable, gui_path],
            cwd=self.brain_dir
        )
        
        print("\n✨ ABIN is running!")
        print("   Close the interface window to shut down ABIN")
        print("=" * 70)
        
        # Wait for GUI to close
        try:
            self.gui_process.wait()
        except KeyboardInterrupt:
            pass
        
        # GUI closed - shut down lobes
        print("\n🛑 Interface closed. Shutting down brain lobes...")
        self.cleanup()
        print("✅ ABIN shutdown complete\n")
        
        return True
    
    def cleanup(self):
        """Shut down all lobes"""
        # Kill GUI if running
        if self.gui_process and self.gui_process.poll() is None:
            self.gui_process.terminate()
            try:
                self.gui_process.wait(timeout=2)
            except:
                self.gui_process.kill()
        
        # Kill all lobes
        for name, process in self.lobe_processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except:
                    process.kill()
        
        # Clean up sockets
        sockets = [
            "/tmp/representation.sock",
            "/tmp/pattern.sock",
            "/tmp/reasoning.sock", 
            "/tmp/notus.sock",
            "/tmp/emotion.sock",
            "/tmp/perception.sock",
            "/tmp/output.sock",
            "/tmp/thalamus.sock"
        ]
        for sock in sockets:
            try:
                if os.path.exists(sock):
                    os.remove(sock)
            except:
                pass
    
    def signal_handler(self, sig, frame):
        """Handle interrupt signals"""
        print("\n\n⚠️  Shutdown signal received...")
        self.cleanup()
        sys.exit(0)

if __name__ == "__main__":
    launcher = ABINLauncher()
    try:
        success = launcher.launch()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        launcher.cleanup()
        sys.exit(1)

