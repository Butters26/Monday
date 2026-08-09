#!/usr/bin/env python3
"""
Monday Single-Process Runner
Runs all lobes in ONE process as threads - they all share the same Thalamus instance
NO SOCKETS - All communication via direct function calls

SINGLE-PROCESS MODE ONLY: All lobes run as threads in one process, sharing the same Thalamus instance.
NO SOCKETS, NO SUBPROCESSES: All communication is via direct function calls.
Subprocess orchestration is not supported in this mode.
"""
import sys
import os
import time
import signal
import atexit
import threading

# SINGLE-PROCESS MODE ONLY
# Import all lobe classes so they run in the same process
from thalamus import get_thalamus, Thalamus
from reasoning import MaximumSophisticationReasoning
from perception import PerceptionLobe
from notus import NotusProcess
from representation import RepresentationLayer
from conversation import ConversationSystem
from voice_lobe import VoiceLobe
from pattern_recognition import AdvancedPatternRecognition
from language_generation import LanguageGenerator
from output import OutputLobe
from advanced_emotional_engine import EmotionalProcess
from novelty_lobe import NoveltyLobe

# New systems
from experience_processor import ExperienceProcessor
from self_reflection import SelfReflectionEngine
from value_evolution import ValueEvolutionSystem
from autonomous_speech import AutonomousSpeechSystem
from behavioral_reinforcement import BehavioralReinforcement
from value_system_learning import ValueSystemLearning
from dual_stream_thinking import DualStreamThinking

def cleanup_sockets():
    """Clean up old socket files - NO SOCKETS USED ANYMORE"""
    # No sockets to clean up - all communication is direct function calls
    pass

def test_lobe_registration(lobe_name: str) -> bool:
    """
    Test if a lobe is registered with Thalamus via DIRECT FUNCTION CALL (NO SOCKETS)
    """
    try:
        from thalamus import get_thalamus
        thalamus = get_thalamus()
        # Check if lobe is registered
        with thalamus.lobe_handlers_lock:
            return lobe_name in thalamus.lobe_handlers
    except Exception:
        return False

def check_syntax(script_path: str) -> tuple:
    """Check if Python file has syntax errors. Returns (is_valid, error_message)"""
    try:
        with open(script_path, 'r') as f:
            code = f.read()
        compile(code, script_path, 'exec')
        return True, ""
    except SyntaxError as e:
        error_msg = f"❌ SYNTAX ERROR in {script_path}:\n"
        error_msg += f"   Line {e.lineno}: {e.text}"
        if e.text:
            error_msg += f"   {e.msg}\n"
            if e.offset:
                error_msg += f"   {' ' * (e.offset - 1)}^\n"
        return False, error_msg
    except Exception as e:
        return False, f"❌ Error checking {script_path}: {e}"

## Subprocess orchestration removed: start_lobe and related logic are not supported in single-process mode.

def main():
    brain_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(brain_dir)
    
    lobe_instances = []
    thalamus = None
    
    # Cleanup handler
    def cleanup():
        print("\n🛑 Shutting down Monday...")
        # Shutdown all lobe instances
        for name, lobe in lobe_instances:
            try:
                lobe.shutdown()
            except Exception:
                pass
        # Shutdown Thalamus
        if thalamus:
            try:
                thalamus.shutdown()
            except Exception:
                pass
        cleanup_sockets()
        print("✅ Shutdown complete\n")
    
    # Don't auto-cleanup on exit - only on explicit shutdown
    # atexit.register(cleanup)  # REMOVED - only cleanup on Ctrl+C
    
    def signal_handler(sig, frame):
        cleanup()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("\n" + "=" * 70)
    print("  🧠 Monday - Maximum Sophistication AI")
    print("=" * 70)
    
    # Subprocess cleanup removed: all lobes run in-process as threads. No pkill or process cleanup needed.
    print("\n🧹 No process cleanup needed in single-process mode.")
    
    # Clean old sockets (noop)
    cleanup_sockets()
    
    print("\n🚀 Starting brain in SINGLE PROCESS (all lobes share Thalamus)...\n")
    
    # Initialize Thalamus FIRST (all lobes will share this instance)
    print("  Initializing Thalamus...", end='', flush=True)
    thalamus = get_thalamus()
    thalamus_thread = threading.Thread(target=thalamus.start, daemon=True)
    thalamus_thread.start()
    time.sleep(1)
    print(" ✅")
    
    # Create all lobe instances (they'll all use the same Thalamus via get_thalamus())
    lobe_instances = []
    lobe_threads = []
    
    lobes = [
        ("Representation", RepresentationLayer, 0.5),
        ("Pattern Recognition", AdvancedPatternRecognition, 0.5),
        ("Reasoning (Self-Aware)", MaximumSophisticationReasoning, 1.0),
        ("Language Generation", LanguageGenerator, 0.5),
        ("Notus Memory", NotusProcess, 3.5),  # Needs extra time for DB initialization to prevent race conditions
        ("Emotional Engine", EmotionalProcess, 1.0),
        ("Novelty Lobe", NoveltyLobe, 0.5),  # Curiosity detection
        ("Perception", PerceptionLobe, 0.5),
        ("Output", OutputLobe, 0.5),
        ("Voice", VoiceLobe, 0.5),
        ("Conversation", ConversationSystem, 0.5),
        # New systems - wire them in
        ("Dual Stream Thinking", DualStreamThinking, 0.5),  # Conscious experience
        ("Experience Processor", ExperienceProcessor, 0.5),
        ("Self Reflection", SelfReflectionEngine, 0.5),
        ("Value Evolution", ValueEvolutionSystem, 0.5),
        ("Autonomous Speech", AutonomousSpeechSystem, 0.5),
        ("Behavioral Reinforcement", BehavioralReinforcement, 0.5),
        ("Value System Learning", ValueSystemLearning, 0.5),
    ]
    
    print(f"\n  Creating lobe instances...")
    for name, lobe_class, wait in lobes:
        print(f"    Creating {name}...", end='', flush=True)
        try:
            lobe = lobe_class()
            lobe_instances.append((name, lobe))
            time.sleep(wait)
            print(" ✅")
        except Exception as e:
            print(f" ❌ (Error: {e})")
            cleanup()
            return 1
    
    print(f"\n  Starting lobe threads...")
    for name, lobe in lobe_instances:
        print(f"    Starting {name} thread...", end='', flush=True)
        try:
            thread = threading.Thread(target=lobe.start, daemon=True)
            thread.start()
            lobe_threads.append((name, thread))
            time.sleep(0.5)
            print(" ✅")
        except Exception as e:
            print(f" ❌ (Error: {e})")
    
    # Instantiate and register new lobes with Thalamus
    from attention_lobe import AttentionLobe
    from motor_action_lobe import MotorActionLobe
    from executive_control_lobe import ExecutiveControlLobe
    from meta_cognition_lobe import MetaCognitionLobe
    from social_context_lobe import SocialContextLobe
    from sensory_integration_lobe import SensoryIntegrationLobe
    from value_goal_management_lobe import ValueGoalManagementLobe

    new_lobes = [
        ("attention", AttentionLobe),
        ("motor_action", MotorActionLobe),
        ("executive_control", ExecutiveControlLobe),
        ("meta_cognition", MetaCognitionLobe),
        ("social_context", SocialContextLobe),
        ("sensory_integration", SensoryIntegrationLobe),
        ("value_goal_management", ValueGoalManagementLobe)
    ]

    print(f"\n  Creating and registering new lobes...")
    for lobe_name, lobe_class in new_lobes:
        print(f"    Creating {lobe_name}...", end='', flush=True)
        try:
            lobe_instance = lobe_class(thalamus=thalamus)
            thalamus.register_lobe(lobe_name, lobe_instance)
            lobe_instances.append((lobe_name, lobe_instance))
            print(" ✅")
        except Exception as e:
            print(f" ❌ (Error: {e})")
            cleanup()
            return 1
    
    # Wait for all lobes to register with Thalamus
    print("\n🔍 Verifying lobe registration...\n")
    time.sleep(3)  # Give all lobes time to register
    
    lobes_to_test = [
        "representation",
        "pattern", 
        "reasoning",
        "language",
        "notus",
        "emotion",
        "perception",
        "output",
        "voice",
        "conversation",
        "novelty",
        "experience",
        "reflection",
        "value_evolution",
        "autonomous",
        "speech",
        "reinforcement",
        "value_learning",
        "dual_stream",
        "attention",
        "motor_action",
        "executive_control",
        "meta_cognition",
        "social_context",
        "sensory_integration",
        "value_goal_management"
    ]
    
    print(f"  Checking registered lobes...")
    all_registered = True
    failed_lobes = []
    
    for lobe_name in lobes_to_test:
        print(f"    Checking {lobe_name}...", end='', flush=True)
        try:
            if test_lobe_registration(lobe_name):
                print(" ✅")
            else:
                print(" ❌")
                all_registered = False
                failed_lobes.append(lobe_name)
        except Exception as e:
            print(f" ⚠️ (error: {e})")
            failed_lobes.append(lobe_name)
    
    # Retry failed registrations once
    if failed_lobes:
        print(f"\n⚠️  Some lobes not registered yet: {', '.join(failed_lobes)}")
        print("   Retrying in 2 seconds...\n")
        time.sleep(2)
        
        still_failed = []
        for lobe_name in failed_lobes:
            print(f"    Retrying {lobe_name}...", end='', flush=True)
            try:
                if test_lobe_registration(lobe_name):
                    print(" ✅")
                else:
                    print(" ❌")
                    still_failed.append(lobe_name)
            except Exception as e:
                print(f" ⚠️ (error: {e})")
                still_failed.append(lobe_name)
        
        if still_failed:
            print(f"\n⚠️  Some lobes still not registered: {', '.join(still_failed)}")
            print("   Continuing anyway - they may register later...\n")
    
    print(f"\n✅ Verification complete!")
    
    print("\n🎮 Launching interface...")
    print("=" * 70)
    print()
    
    # Launch GUI in SAME PROCESS (so it shares the same Thalamus instance)
    try:
        from PyQt5.QtWidgets import QApplication
        from abin_interface import MondayInterface
        import sys
        
        # Create QApplication in this process
        app = QApplication(sys.argv)
        window = MondayInterface()
        window.show()
        
        # Run GUI event loop (this blocks until GUI closes)
        app.exec_()
        
        # GUI closed - but keep system running
        print("\n💡 GUI closed, but brain lobes are still running in background")
        print("   You can reopen the GUI anytime")
        print("   Press Ctrl+C to fully shutdown\n")
        
        # Keep running until user presses Ctrl+C
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        
    except KeyboardInterrupt:
        pass
    
    # Only cleanup on explicit shutdown (Ctrl+C)
    cleanup()
    return 0

if __name__ == "__main__":
    sys.exit(main())
