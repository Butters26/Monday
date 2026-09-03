#!/usr/bin/env python3
"""
Test: Full flow of Novelty Lobe in a conversation
- User says something new/interesting
- Emotion responds
- Novelty asks a question based on emotion  
- User answers
- Novelty learns and updates momentum
- Next time similar topic comes up, asks differently
"""

import sys
import time
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from novelty_lobe import NoveltyLobe
from advanced_emotional_engine import AdvancedEmotionalEngine, EmotionalState, EmotionalProcess

def test_full_novelty_conversation():
    """Test a realistic conversation flow with novelty"""
    
    print("\n" + "=" * 70)
    print("FULL NOVELTY CONVERSATION FLOW TEST")
    print("=" * 70)
    
    # Initialize components
    print("\n🔧 Initializing components...")
    emotion_process = EmotionalProcess()
    emotion_engine = emotion_process.engine
    novelty = NoveltyLobe()
    
    print("✅ Ready")
    
    # Conversation scenario
    conversation_turns = [
        {
            "user_input": "I just discovered this band called Radiohead - have you heard of them?",
            "emotion": EmotionalState.CURIOUS,
            "intensity": 0.75,
            "user_response": "They're like... experimental rock but also electronic sometimes. The album OK Computer changed everything.",
            "description": "First mention of band - should be curious"
        },
        {
            "user_input": "Radiohead's new album is weird but I kind of love it",
            "emotion": EmotionalState.EXCITED,
            "intensity": 0.80,
            "user_response": "Yeah, they don't do what people expect. That's what makes them interesting.",
            "description": "Second mention - should remember or ask differently"
        },
        {
            "user_input": "Why does everyone hate the new Radiohead album?",
            "emotion": EmotionalState.WORRIED,
            "intensity": 0.70,
            "user_response": "I think people expect them to sound like OK Computer. But they keep evolving.",
            "description": "Negative social response - should pick up concern"
        },
    ]
    
    # Run conversation
    for turn_num, turn in enumerate(conversation_turns, 1):
        print("\n" + "=" * 70)
        print(f"TURN {turn_num}: {turn['description']}")
        print("=" * 70)
        
        # User input
        user_input = turn["user_input"]
        print(f"\n👤 User: {user_input}")
        
        # Emotion+Novelty processes together via EmotionalProcess
        print(f"\n1️⃣  Emotion processes...")
        result = emotion_process.process_message_safe({
            'type': 'feel_emotion',
            'emotion': turn["emotion"].value,
            'intensity': turn["intensity"],
            'trigger': user_input
        })
        
        print(f"   😊 Emotion: {emotion_engine.current_emotion.value}")
        print(f"   - Intensity: {emotion_engine.emotional_intensity:.2f}")
        
        # Check if novelty question was asked
        print(f"\n2️⃣  Novelty Lobe processes...")
        time.sleep(0.2)
        question = novelty.get_question_to_ask_user(user_input)
        
        if question:
            print(f"   ❓ Question: {question}")
            
            # Simulate user answering
            user_answer = turn["user_response"]
            print(f"\n👤 User answers: {user_answer}")
            
            # Novelty learns from response
            result = novelty.process_message({
                'type': 'user_response',
                'stimulus': user_input,
                'answer': user_answer
            })
            
            print(f"   ✅ {result['status'].upper()}: Memory stored")
            print(f"   📊 Emotional momentum: {novelty.emotional_momentum:.3f}")
        else:
            print(f"   ⚠️  No question generated")
        
        # Show learned patterns
        print(f"\n3️⃣  Pattern check...")
        similar = novelty._query_notus_for_similar_stimuli(user_input)
        if similar:
            print(f"   📚 Found {len(similar)} similar past experience(s)")
            for i, mem in enumerate(similar[:1], 1):
                print(f"      - Learned: {mem.learned_value[:60] if mem.learned_value else 'no response'}...")
        else:
            print(f"   📚 No similar patterns yet")
        
        time.sleep(0.3)
    
    # Summary
    print("\n" + "=" * 70)
    print("CONVERSATION SUMMARY")
    print("=" * 70)
    
    print(f"\n📊 Final emotional momentum: {novelty.emotional_momentum:.3f}")
    print(f"📚 Memories formed: {len(novelty.novelty_memories)}")
    
    if novelty.novelty_memories:
        print(f"\n   Memories:")
        for i, mem in enumerate(novelty.novelty_memories, 1):
            stim_preview = mem.stimulus[:40] + "..." if len(mem.stimulus) > 40 else mem.stimulus
            learned_preview = mem.learned_value[:40] + "..." if mem.learned_value and len(mem.learned_value) > 40 else (mem.learned_value or "no response")
            print(f"   {i}. Stimulus: {stim_preview}")
            print(f"      Learned: {learned_preview}")
            print(f"      Emotion: {mem.initial_emotion} (valence: {mem.valence:.2f})")
            print()
    
    print("\n✅ Test complete!")
    print("\n🎯 What this demonstrates:")
    print("   1. Emotion drives what Novelty finds interesting")
    print("   2. Novelty asks questions shaped by emotional tone")
    print("   3. User responses create real memories")
    print("   4. Pattern recognition learns from repeated topics")
    print("   5. Emotional momentum tracks overall tendency")


if __name__ == "__main__":
    try:
        test_full_novelty_conversation()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
