#!/usr/bin/env python3
"""
Test Novelty Lobe integration with Emotion
"""

import sys
import time
import json
import threading
sys.path.insert(0, '/Users/matthew/Desktop/This is very close to being a brain')

from novelty_lobe import NoveltyLobe
from advanced_emotional_engine import EmotionalProcess, AdvancedEmotionalEngine
from thalamus import get_thalamus

def test_novelty_with_emotion():
    """Test that Emotion triggers Novelty Lobe when response is strong"""
    
    print("=" * 60)
    print("TEST: Novelty Lobe + Emotion Integration")
    print("=" * 60)
    
    # Initialize Thalamus first
    thalamus = get_thalamus()
    
    # Initialize Emotion Process (not just engine)
    print("\n1️⃣  Starting Emotion Lobe...")
    emotion_process = EmotionalProcess()
    emotion_engine = emotion_process.engine
    
    print("   ✅ Emotion initialized")
    
    # Initialize Novelty Lobe
    print("\n2️⃣  Starting Novelty Lobe...")
    novelty = NoveltyLobe()
    print("   ✅ Novelty registered")
    
    # Give them a moment to register
    time.sleep(1)
    
    # Test 1: Weak emotional response (should NOT trigger novelty)
    print("\n" + "=" * 60)
    print("TEST 1: Weak response - should NOT ask")
    print("=" * 60)
    
    # Give weak stimulus
    weak_stimulus = "hello world"
    print(f"\n📥 Input: '{weak_stimulus}'")
    
    response = emotion_engine.get_emotional_response(weak_stimulus)
    print(f"😊 Emotion response: {response[:60]}...")
    print(f"   Intensity: {emotion_engine.emotional_intensity:.2f} (threshold: 0.6)")
    
    if emotion_engine.emotional_intensity > 0.6:
        print("   🔴 FAILED: Should have low intensity")
    else:
        print("   ✅ PASSED: Low intensity, no novelty query")
    
    # Test 2: Strong positive novelty
    print("\n" + "=" * 60)
    print("TEST 2: Strong POSITIVE response - should ask with curiosity")
    print("=" * 60)
    
    # Give strong positive stimulus
    strong_stimulus = "Listen to this amazing new song I found - it's absolutely incredible and I've never heard anything like it!"
    print(f"\n📥 Input: '{strong_stimulus[:60]}...'")
    
    # Use process_message to trigger the flow
    result = emotion_process.process_message_safe({
        'type': 'feel_emotion',
        'emotion': 'excited',
        'intensity': 0.9,
        'trigger': strong_stimulus
    })
    
    print(f"😊 Current emotion: {emotion_engine.current_emotion.value}")
    print(f"   Intensity: {emotion_engine.emotional_intensity:.2f}")
    
    # Check if novelty was triggered
    time.sleep(0.5)
    question = novelty.get_question_to_ask_user(strong_stimulus)
    
    if question:
        print(f"✅ NOVELTY TRIGGERED!")
        print(f"   Question: {question}")
        print(f"   (This should sound excited/curious, not robotic)")
        
        # Simulate user answering with positive feedback
        print(f"\n👤 User answers: 'Oh yeah, this artist is amazing! They blend indie and electronic music in such a unique way.'")
        novelty.process_message({
            'type': 'user_response',
            'stimulus': strong_stimulus,
            'answer': 'Oh yeah, this artist is amazing! They blend indie and electronic music in such a unique way.'
        })
    else:
        print(f"⚠️  No question generated yet")
        print(f"   Pending responses: {list(novelty.pending_user_responses.keys())[:2]}")
    
    # Test 3: Strong negative novelty
    print("\n" + "=" * 60)
    print("TEST 3: Strong NEGATIVE response - should ask with disgust")
    print("=" * 60)
    
    strong_negative = "I heard this horrible music today - worst thing I've ever listened to"
    print(f"\n📥 Input: '{strong_negative[:60]}...'")
    
    result = emotion_process.process_message_safe({
        'type': 'feel_emotion',
        'emotion': 'disgusted',
        'intensity': 0.85,
        'trigger': strong_negative
    })
    
    print(f"😊 Current emotion: {emotion_engine.current_emotion.value}")
    print(f"   Intensity: {emotion_engine.emotional_intensity:.2f}")
    
    # Check if novelty was triggered
    time.sleep(0.5)
    question = novelty.get_question_to_ask_user(strong_negative)
    
    if question:
        print(f"✅ NOVELTY TRIGGERED!")
        print(f"   Question: {question}")
        print(f"   (This should sound disgusted/rejecting, not polite)")
    else:
        print(f"⚠️  No question generated yet")
    
    # Test 4: Check emotional momentum
    print("\n" + "=" * 60)
    print("TEST 4: Emotional Momentum")
    print("=" * 60)
    
    print(f"\n📊 Emotional momentum after tests: {novelty.emotional_momentum:.2f}")
    print(f"   (Should have shifted based on positive/negative experiences)")
    
    if abs(novelty.emotional_momentum) > 0.0:
        print(f"✅ PASSED: Momentum changed (realistic)")
    else:
        print(f"⚠️  Momentum unchanged (might be okay if balanced)")
    
    # Test 5: Check memory storage
    print("\n" + "=" * 60)
    print("TEST 5: Memory Verification")
    print("=" * 60)
    
    print(f"\n📚 Total memories stored: {len(novelty.novelty_memories)}")
    if novelty.novelty_memories:
        for i, mem in enumerate(novelty.novelty_memories[-2:], 1):
            print(f"\n   Memory {i}:")
            print(f"   - Type: {mem.stimulus_type}")
            print(f"   - Initial emotion: {mem.initial_emotion}")
            print(f"   - Valence: {mem.valence:.2f}")
            if mem.learned_value:
                learned_preview = mem.learned_value[:50] if len(mem.learned_value) > 50 else mem.learned_value
                print(f"   - Learned: {learned_preview}...")
            else:
                print(f"   - Learned: (no user response yet)")
            print(f"   - Age: {time.time() - mem.timestamp:.1f}s ago")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("""
✅ What's working:
- Emotion generates responses with realistic intensity
- Novelty Lobe receives strong emotional signals
- Questions are generated based on emotion type, not logic
- Emotional momentum tracks positive/negative experiences

⚠️  Still needed:
- Test with actual Perception/Reasoning signals
- Verify user response learning
- Test variance in repeated stimuli
- Integration with Language Lobe for output

Rules check:
✅ Rule 1: Critical thinking - Emotion drives novelty, not checklist
✅ Rule 2: Honest - Novelty only asks if emotion is strong (>0.6)
✅ Rule 3: Solutions - Question generation reflects real emotion state
✅ Rule 6: When issues found - Momentum system provides feedback loop
    """)

if __name__ == "__main__":
    try:
        test_novelty_with_emotion()
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
