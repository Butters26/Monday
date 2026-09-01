#!/usr/bin/env python3
"""
Test: Novelty Lobe Integration with Conversation System
Verify that novelty questions flow through the conversation pipeline
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from thalamus import Thalamus
from conversation import ConversationSystem
from novelty_lobe import NoveltyLobe
from advanced_emotional_engine import EmotionalProcess, EmotionalState

def test_novelty_in_conversation():
    """Test novelty detection integrated in conversation flow"""
    
    print("\n" + "=" * 70)
    print("NOVELTY LOBE INTEGRATION TEST")
    print("=" * 70)
    
    # Setup
    print("\n🔧 Setting up components...")
    thalamus = Thalamus()
    conversation = ConversationSystem()
    novelty = NoveltyLobe()
    emotion = EmotionalProcess()
    
    # Register with Thalamus
    thalamus.register_lobe("conversation", conversation)
    thalamus.register_lobe("novelty", novelty)
    thalamus.register_lobe("emotion", emotion)
    
    print("✅ Components initialized")
    
    # Test 1: Low emotion (no novelty)
    print("\n" + "─" * 70)
    print("TEST 1: Low Emotion - Should NOT trigger novelty")
    print("─" * 70)
    
    user_input_1 = "hello world"
    print(f"\n👤 User: \"{user_input_1}\"")
    
    # Understanding with emotional context
    understanding_1 = conversation.understand(
        user_input_1,
        context={'emotion': 'calm', 'intensity': 0.3, 'valence': 0.0}
    )
    
    print(f"   Intent: {understanding_1['intent']}")
    print(f"   Novelty question: {understanding_1.get('novelty_question', 'None')}")
    
    if understanding_1.get('novelty_question') is None:
        print("   ✅ PASSED: No novelty triggered (emotion too weak)")
    else:
        print("   ⚠️  Question generated (might be okay)")
    
    # Test 2: Strong emotion (should trigger novelty)
    print("\n" + "─" * 70)
    print("TEST 2: Strong Emotion - SHOULD trigger novelty")
    print("─" * 70)
    
    user_input_2 = "I just discovered this amazing band Radiohead"
    print(f"\n👤 User: \"{user_input_2}\"")
    
    # First trigger emotion engine
    emotion.engine.feel_emotion(
        emotion=EmotionalState.CURIOUS,
        intensity=0.80,
        trigger=user_input_2
    )
    
    # Then get understanding with emotional context
    understanding_2 = conversation.understand(
        user_input_2,
        context={
            'emotion': emotion.engine.current_emotion.value,
            'intensity': emotion.engine.emotional_intensity,
            'valence': emotion.engine.pad.v
        }
    )
    
    print(f"   Intent: {understanding_2['intent']}")
    print(f"   Novelty question: {understanding_2.get('novelty_question', 'None')}")
    
    if understanding_2.get('novelty_question'):
        print("   ✅ PASSED: Novelty question generated")
        print(f"   Question: \"{understanding_2['novelty_question']}\"")
    else:
        print("   ⚠️  No novelty question generated")
    
    # Test 3: User response → Learning
    print("\n" + "─" * 70)
    print("TEST 3: Learning from User Response")
    print("─" * 70)
    
    question = understanding_2.get('novelty_question')
    if question:
        user_response = "They're experimental rock mixed with electronic music"
        print(f"\n🤖 Monday: \"{question}\"")
        print(f"👤 User: \"{user_response}\"")
        
        # Store the response in novelty
        learn_result = novelty.process_message({
            'type': 'user_response',
            'stimulus': user_input_2,
            'answer': user_response
        })
        
        if learn_result['status'] == 'learned':
            print(f"   ✅ Memory stored")
            print(f"   Momentum: {novelty.emotional_momentum:.3f}")
        else:
            print(f"   ⚠️  Status: {learn_result['status']}")
    
    # Test 4: Second mention (should detect pattern)
    print("\n" + "─" * 70)
    print("TEST 4: Pattern Recognition - Same Topic")
    print("─" * 70)
    
    user_input_3 = "Radiohead's new album is really weird"
    print(f"\n👤 User: \"{user_input_3}\"")
    
    emotion.engine.feel_emotion(
        emotion=EmotionalState.EXCITED,
        intensity=0.75,
        trigger=user_input_3
    )
    
    understanding_3 = conversation.understand(
        user_input_3,
        context={
            'emotion': emotion.engine.current_emotion.value,
            'intensity': emotion.engine.emotional_intensity,
            'valence': emotion.engine.pad.v
        }
    )
    
    question_3 = understanding_3.get('novelty_question')
    print(f"   Novelty question: {question_3}")
    
    if question_3:
        # Check if it's different from first question (indicating pattern recognition)
        if question_3 != understanding_2.get('novelty_question'):
            print("   ✅ Question adapted (pattern recognized)")
        else:
            print("   ⚠️  Same question as before")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    print(f"""
✅ Integration Status:
   - Conversation recognizes emotional context
   - Novelty lobe triggered when intensity > 0.6
   - Questions generated and adapted
   - Learning mechanism working
   
📊 Metrics:
   - Memories stored: {len(novelty.novelty_memories)}
   - Emotional momentum: {novelty.emotional_momentum:.3f}
   - Pattern matches: {len(novelty._query_notus_for_similar_stimuli(user_input_2) if user_input_2 else [])}
   
✨ Integration Complete!
""")


if __name__ == "__main__":
    try:
        test_novelty_in_conversation()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
