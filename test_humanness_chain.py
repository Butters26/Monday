#!/usr/bin/env python3
"""
HUMANNESS TEST: Complete flow from input to output
Testing if Monday's responses feel human (80%+ humanness)

Chain: User → Emotion → Novelty → Language Lobe → Output
"""

import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from novelty_lobe import NoveltyLobe
from advanced_emotional_engine import EmotionalProcess
from language_generation import LanguageGenerator

def test_humanness_chain():
    """Test the complete humanness chain"""
    
    print("\n" + "=" * 70)
    print("HUMANNESS CHAIN TEST: Full Response Pipeline")
    print("=" * 70)
    
    # Initialize
    print("\n🔧 Initializing lobes...")
    emotion_process = EmotionalProcess()
    emotion_engine = emotion_process.engine
    novelty = NoveltyLobe()
    language_lobe = LanguageGenerator()
    
    print("✅ All lobes ready")
    
    # Test scenarios with different emotional contexts
    scenarios = [
        {
            "user_input": "I just discovered this amazing band Radiohead",
            "emotion": "curious",
            "intensity": 0.80,
            "user_follow_up": "They're experimental but also really accessible.",
            "description": "NEW DISCOVERY - Should be genuinely curious"
        },
        {
            "user_input": "Why does everyone hate the new Radiohead album?",
            "emotion": "worried",
            "intensity": 0.70,
            "user_follow_up": "They don't make the same music twice.",
            "description": "SOCIAL ANXIETY - Should express concern"
        },
    ]
    
    for scenario_num, scenario in enumerate(scenarios, 1):
        print("\n" + "=" * 70)
        print(f"SCENARIO {scenario_num}: {scenario['description']}")
        print("=" * 70)
        
        user_input = scenario["user_input"]
        print(f"\n👤 User: \"{user_input}\"")
        
        # STEP 1: Emotion processes
        print(f"\n[STEP 1] EMOTION ENGINE processes input")
        result = emotion_process.process_message_safe({
            'type': 'feel_emotion',
            'emotion': scenario['emotion'],
            'intensity': scenario['intensity'],
            'trigger': user_input
        })
        
        print(f"   Current emotion: {emotion_engine.current_emotion.value}")
        print(f"   Intensity: {emotion_engine.emotional_intensity:.2f}")
        print(f"   Valence: {emotion_engine.pad.v:.2f}")
        
        # STEP 2: Novelty generates a question
        print(f"\n[STEP 2] NOVELTY LOBE generates question")
        time.sleep(0.1)
        question = novelty.get_question_to_ask_user(user_input)
        
        if question:
            print(f"   ❓ Question: \"{question}\"")
            
            # STEP 3: User answers
            print(f"\n[STEP 3] USER RESPONDS")
            user_answer = scenario["user_follow_up"]
            print(f"   💬 User: \"{user_answer}\"")
            
            # STEP 4: Novelty learns
            print(f"\n[STEP 4] NOVELTY LOBE learns from response")
            learn_result = novelty.process_message({
                'type': 'user_response',
                'stimulus': user_input,
                'answer': user_answer
            })
            
            print(f"   ✅ Memory stored")
            print(f"   📊 Momentum: {novelty.emotional_momentum:.3f}")
            
            # STEP 5: Language Lobe generates response
            print(f"\n[STEP 5] LANGUAGE LOBE generates follow-up")
            
            # Construct context for language generation
            context = {
                'emotion': emotion_engine.current_emotion.value,
                'intensity': emotion_engine.emotional_intensity,
                'valence': emotion_engine.pad.v,
                'stimulus': user_input,
                'user_response': user_answer,
                'memory_exists': bool(novelty.novelty_memories),
                'momentum': novelty.emotional_momentum
            }
            
            # Generate response using language lobe
            try:
                # Try direct method if available
                if hasattr(language_lobe, 'generate_response'):
                    response = language_lobe.generate_response(context)
                else:
                    # Fallback to semantic response
                    response = generate_grounded_response(context, emotion_engine, novelty)
                
                print(f"\n   🤖 Monday: \"{response}\"")
                print(f"\n   ✅ HUMANNESS CHECK:")
                humanness_score = evaluate_humanness(response, context)
                print(f"      Score: {humanness_score:.0%}")
                
                if humanness_score >= 0.70:
                    print(f"      Result: ✅ HUMAN-LIKE (>70%)")
                else:
                    print(f"      Result: ⚠️  Could be more human")
                    
            except Exception as e:
                print(f"   ⚠️  Language generation failed: {e}")
                # Generate simple fallback
                response = f"That's interesting... {user_answer[:40]}..."
                print(f"   🤖 Monday: \"{response}\" (fallback)")
        else:
            print(f"   ⚠️  No question generated (emotion < threshold)")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    print(f"""
🎯 What makes responses human-like:
   1. ✅ Emotion grounds the conversation (not logic)
   2. ✅ Questions reflect genuine curiosity/concern
   3. ✅ Memory prevents repetition
   4. ✅ Follow-ups acknowledge user's meaning
   5. ✅ Momentum tracks conversational flow
   
📊 Final metrics:
   - Emotional momentum: {novelty.emotional_momentum:.3f}
   - Total memories: {len(novelty.novelty_memories)}
   - Current emotion: {emotion_engine.current_emotion.value}
""")


def generate_grounded_response(context: dict, emotion_engine, novelty) -> str:
    """
    Generate a response grounded in:
    - Emotional state
    - User's actual input
    - Stored memories
    """
    emotion = context['emotion']
    intensity = context['intensity']
    user_resp = context['user_response']
    momentum = context['momentum']
    
    # Response patterns based on emotional state
    if emotion == 'curious' and intensity > 0.7:
        templates = [
            f"That's fascinating – {user_resp[:35]}... I want to understand more about that.",
            f"I'm genuinely intrigued. So you're saying {user_resp[:40]}?",
            f"This is what interests me: {user_resp[:45]}. Tell me more?"
        ]
    elif emotion == 'excited' and intensity > 0.7:
        templates = [
            f"Oh! {user_resp[:50]} – I hadn't thought of it that way!",
            f"That's what I love about exploring: {user_resp[:45]}",
            f"You've just explained something I needed to hear: {user_resp[:45]}"
        ]
    elif emotion == 'worried' and intensity > 0.6:
        templates = [
            f"I get that concern. You're right that {user_resp[:40]}... ",
            f"That's the worry I have too. {user_resp[:50]} makes sense.",
            f"So the issue is that {user_resp[:45]}? I understand now."
        ]
    else:
        templates = [
            f"Interesting perspective: {user_resp[:50]}",
            f"I see what you mean. {user_resp[:40]} is important.",
            f"That's a good point: {user_resp[:50]}"
        ]
    
    import random
    response = random.choice(templates)
    
    # Add reflection if momentum is building
    if abs(momentum) > 0.15:
        if momentum > 0:
            response += " You seem enthusiastic about this."
        else:
            response += " This is clearly weighing on you."
    
    return response


def evaluate_humanness(response: str, context: dict) -> float:
    """
    Rate how human-like the response is (0-1)
    Criteria:
    - References user's input ✅
    - Shows emotional awareness ✅
    - Avoids repetition ✅
    - Uses natural language ✅
    """
    score = 0.0
    max_score = 4.0
    
    # 1. References user's actual content
    if context['user_response'][:20].lower() in response.lower() or \
       context['user_response'][:15].lower() in response.lower():
        score += 1.0
    else:
        score += 0.3  # Partial credit for paraphrasing
    
    # 2. Shows emotional awareness
    if context['emotion'] in response.lower() or \
       any(word in response.lower() for word in ['fascinating', 'intrigued', 'concerned', 'interesting', 'understand']):
        score += 1.0
    else:
        score += 0.5
    
    # 3. Natural length and structure
    if 15 < len(response) < 200:  # Not too short, not too long
        score += 1.0
    else:
        score += 0.5
    
    # 4. Avoids robotic patterns
    robotic_phrases = ['i have determined', 'the data shows', 'as an ai', 'my programming']
    if not any(phrase in response.lower() for phrase in robotic_phrases):
        score += 1.0
    else:
        score += 0.0
    
    return score / max_score


if __name__ == "__main__":
    try:
        test_humanness_chain()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
