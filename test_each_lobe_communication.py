#!/usr/bin/env python3
"""
Test each lobe's communication one at a time
Test lobes that need memory, then lobes that just talk to Reasoning
"""

import sys
import os
import time
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from thalamus import get_thalamus, Thalamus
from reasoning import MaximumSophisticationReasoning
from notus import NotusProcess
from advanced_emotional_engine import EmotionalProcess
from perception import PerceptionLobe
from pattern_recognition import AdvancedPatternRecognition

def test_emotional_engine():
    """TEST 1: Emotional Engine → Notus → Reasoning"""
    print("\n" + "="*70)
    print("🧪 TEST 1: EMOTIONAL ENGINE")
    print("="*70)
    
    try:
        thalamus = Thalamus()
        
        # Start Notus
        print("\n[1] Starting Notus...")
        notus = NotusProcess()
        thalamus.register_lobe('notus', notus)
        time.sleep(5)  # Wait for initialization
        
        # Start Emotional Engine
        print("[2] Starting Emotional Engine...")
        emotion = EmotionalProcess()
        thalamus.register_lobe('emotion', emotion)
        
        # Start Reasoning
        print("[3] Starting Reasoning...")
        reasoning = MaximumSophisticationReasoning()
        thalamus.register_lobe('reasoning', reasoning)
        
        # Test: Emotion generates state and sends to Reasoning
        print("\n[4] Emotion Engine generating emotional state...")
        emotion_msg = {
            'type': 'process_input',
            'user_input': 'user praised my work'
        }
        
        emotion_result = emotion.process_message_safe(emotion_msg)
        print(f"   Emotion response: {emotion_result}")
        
        if emotion_result.get('status') == 'success':
            print("   ✅ Emotion state generated")
        else:
            print(f"   ❌ FAILED: {emotion_result.get('message')}")
        
        # Test: Emotion sends to Reasoning
        print("\n[5] Emotion sending state to Reasoning through Thalamus...")
        print(f"   Message type being sent: 'emotional_state'")
        print(f"   Source: emotion → Destination: reasoning")
        
        thalamus_result = thalamus.send_message(
            source='emotion',
            destination='reasoning',
            msg_type='emotional_state',
            content=emotion_result.get('content', {})
        )
        print(f"   Thalamus returned: {thalamus_result}")
        print(f"   Status: {thalamus_result.get('status')}")
        print(f"   Message: {thalamus_result.get('message')}")
        
        if thalamus_result.get('status') == 'success':
            print("   ✅ Emotion → Reasoning communication SUCCESS")
        else:
            print(f"   ❌ FAILED")
            print(f"   REASON: Reasoning doesn't recognize message type 'emotional_state'")
        
    except Exception as e:
        print(f"   ❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()

def test_perception():
    """TEST 2: Perception → Reasoning"""
    print("\n" + "="*70)
    print("🧪 TEST 2: PERCEPTION LOBE")
    print("="*70)
    
    try:
        thalamus = Thalamus()
        
        # Start Reasoning
        print("\n[1] Starting Reasoning...")
        reasoning = MaximumSophisticationReasoning()
        thalamus.register_lobe('reasoning', reasoning)
        
        # Start Perception
        print("[2] Starting Perception...")
        perception = PerceptionLobe()
        thalamus.register_lobe('perception', perception)
        
        # Test: Perception processes user input
        print("\n[3] Perception processing user input: 'hello'...")
        perception_msg = {
            'type': 'process_text',
            'text': 'hello'
        }
        
        perception_result = perception.process_message(perception_msg)
        print(f"   Perception response: {perception_result}")
        
        if perception_result.get('status') == 'success':
            print("   ✅ Perception processed input")
        else:
            print(f"   ❌ FAILED: {perception_result.get('message')}")
        
        # Test: Perception sends to Reasoning
        print("\n[4] Perception sending to Reasoning through Thalamus...")
        print(f"   Message type being sent: 'perception_input'")
        print(f"   Source: perception → Destination: reasoning")
        
        thalamus_result = thalamus.send_message(
            source='perception',
            destination='reasoning',
            msg_type='perception_input',
            content=perception_result.get('content', {})
        )
        print(f"   Thalamus returned: {thalamus_result}")
        print(f"   Status: {thalamus_result.get('status')}")
        print(f"   Message: {thalamus_result.get('message')}")
        
        if thalamus_result.get('status') == 'success':
            print("   ✅ Perception → Reasoning communication SUCCESS")
        else:
            print(f"   ❌ FAILED")
            print(f"   REASON: Reasoning might not recognize message type or path not allowed")
        
    except Exception as e:
        print(f"   ❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()

def test_pattern_recognition():
    """TEST 3: Pattern Recognition → Reasoning"""
    print("\n" + "="*70)
    print("🧪 TEST 3: PATTERN RECOGNITION LOBE")
    print("="*70)
    
    try:
        thalamus = Thalamus()
        
        # Start Reasoning
        print("\n[1] Starting Reasoning...")
        reasoning = MaximumSophisticationReasoning()
        thalamus.register_lobe('reasoning', reasoning)
        
        # Start Pattern Recognition
        print("[2] Starting Pattern Recognition...")
        pattern = AdvancedPatternRecognition()
        thalamus.register_lobe('pattern', pattern)
        
        # Test: Pattern Recognition analyzes behavior
        print("\n[3] Pattern Recognition analyzing behavior...")
        pattern_msg = {
            'type': 'process_input',
            'data': {'recent_events': ['user coded for 2 hours', 'user took break', 'user coded again']}
        }
        
        pattern_result = pattern.process_message(pattern_msg)
        print(f"   Pattern response: {pattern_result}")
        
        if pattern_result.get('status') == 'success':
            print("   ✅ Pattern Recognition analyzed")
        else:
            print(f"   ❌ FAILED: {pattern_result.get('message')}")
        
        # Test: Pattern sends to Reasoning
        print("\n[4] Pattern Recognition sending to Reasoning through Thalamus...")
        print(f"   Message type being sent: 'pattern_analysis'")
        print(f"   Source: pattern → Destination: reasoning")
        
        thalamus_result = thalamus.send_message(
            source='pattern',
            destination='reasoning',
            msg_type='pattern_analysis',
            content=pattern_result.get('content', {})
        )
        print(f"   Thalamus returned: {thalamus_result}")
        print(f"   Status: {thalamus_result.get('status')}")
        print(f"   Message: {thalamus_result.get('message')}")
        
        if thalamus_result.get('status') == 'success':
            print("   ✅ Pattern Recognition → Reasoning communication SUCCESS")
        else:
            print(f"   ❌ FAILED")
            print(f"   REASON: Reasoning doesn't recognize message type 'pattern_analysis'")
        
    except Exception as e:
        print(f"   ❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🧠 LOBE COMMUNICATION TESTS - ONE AT A TIME")
    print("="*70)
    
    test_emotional_engine()
    test_perception()
    test_pattern_recognition()
    
    print("\n" + "="*70)
    print("✅ ALL TESTS COMPLETE")
    print("="*70 + "\n")
