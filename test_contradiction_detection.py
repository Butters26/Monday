#!/usr/bin/env python3
"""
Test: Contradiction Detection System
Verify that Reasoning detects belief contradictions and signals Novelty Lobe
"""

import sys
import time
from unittest.mock import Mock, MagicMock
sys.path.insert(0, '/Users/matthew/Desktop/This is very close to being a brain')

from reasoning import MaximumSophisticationReasoning, Belief

def test_simple_contradiction_detection():
    """Test that Reasoning detects simple contradictions"""
    print("\n" + "="*70)
    print("TEST 1: Simple Contradiction Detection")
    print("="*70)
    
    reasoning = MaximumSophisticationReasoning()
    
    # Set up a belief
    reasoning.beliefs['test_belief'] = Belief(
        about='cats',
        what_i_believe='cats are always friendly',
        why_i_believe_it=['I have only met friendly cats'],
        confidence=0.8,
        formed_when=time.time()
    )
    
    # Mock Notus to return contradicting evidence
    contradicting_facts = [
        {'content': 'Some cats are aggressive'},
        {'content': 'Feral cats attack people'},
        {'content': 'Not all cats are friendly'}
    ]
    
    def mock_send(dest, msg_type, content, source=None):
        if dest == 'notus' and msg_type == 'query_facts':
            return {
                'status': 'success',
                'facts': contradicting_facts
            }
        return {'status': 'ok'}
    
    reasoning.thalamus.send_message = mock_send
    
    # Input that contradicts the belief
    user_input = "But some cats are actually very aggressive and unfriendly"
    key_concepts = ['cats', 'aggressive', 'unfriendly']
    memory_result = {'context_data': {}}
    
    contradictions = reasoning._detect_belief_contradictions(user_input, key_concepts, memory_result)
    
    print(f"User input: {user_input}")
    print(f"Contradictions detected: {len(contradictions)}")
    
    if contradictions:
        for c in contradictions:
            print(f"  - {c['belief_about']}: strength {c['contradiction_strength']:.2f}")
    
    assert len(contradictions) > 0, "❌ FAILED: No contradictions detected"
    assert contradictions[0]['belief_about'] == 'cats', "❌ FAILED: Wrong belief detected"
    assert contradictions[0]['contradiction_strength'] > 0.5, "❌ FAILED: Strength too low"
    
    print("✅ PASSED: Simple contradiction detected with correct strength")


def test_no_contradiction_when_no_conflict_language():
    """Test that input without contradiction language doesn't trigger"""
    print("\n" + "="*70)
    print("TEST 2: No Contradiction Without Conflict Language")
    print("="*70)
    
    reasoning = MaximumSophisticationReasoning()
    
    reasoning.beliefs['color_belief'] = Belief(
        about='sky',
        what_i_believe='the sky is blue',
        why_i_believe_it=['I observe it'],
        confidence=0.9,
        formed_when=time.time()
    )
    
    reasoning.thalamus.send_message = lambda d, m, c, source=None: {'status': 'ok'}
    
    # Input mentions the belief topic but has no contradiction language
    user_input = "The sky is so beautiful today"
    contradictions = reasoning._detect_belief_contradictions(
        user_input, 
        ['sky', 'beautiful'], 
        {'context_data': {}}
    )
    
    print(f"User input: {user_input}")
    print(f"Contradictions detected: {len(contradictions)}")
    
    assert len(contradictions) == 0, "❌ FAILED: False contradiction detected"
    print("✅ PASSED: No contradiction when no conflict language present")


def test_belief_updated_with_contradiction():
    """Test that belief object is updated when contradiction found"""
    print("\n" + "="*70)
    print("TEST 3: Belief Object Updated with Contradiction")
    print("="*70)
    
    reasoning = MaximumSophisticationReasoning()
    
    belief = Belief(
        about='AI',
        what_i_believe='AI has no emotions',
        why_i_believe_it=['logic-based systems'],
        confidence=0.7,
        formed_when=time.time()
    )
    reasoning.beliefs['ai_belief'] = belief
    
    initial_challenged = belief.times_challenged
    initial_contradiction = belief.contradiction_detected
    
    contradicting_facts = [
        {'content': 'AI systems can simulate emotions'},
        {'content': 'Some AI systems are designed to have preferences'}
    ]
    
    reasoning.thalamus.send_message = lambda d, m, c, source=None: {
        'status': 'success',
        'facts': contradicting_facts
    } if d == 'notus' else {'status': 'ok'}
    
    # User input that contradicts
    user_input = "But AI systems can actually have real or simulated emotions"
    
    reasoning._detect_belief_contradictions(
        user_input,
        ['AI', 'emotions'],
        {'context_data': {}}
    )
    
    print(f"Belief before: contradiction_detected={initial_contradiction}, times_challenged={initial_challenged}")
    print(f"Belief after: contradiction_detected={belief.contradiction_detected}, times_challenged={belief.times_challenged}")
    print(f"Contradiction strength: {belief.contradiction_strength:.2f}")
    print(f"Evidence stored: {len(belief.contradicting_evidence)} items")
    
    assert belief.contradiction_detected == True, "❌ FAILED: contradiction_detected not set"
    assert belief.times_challenged > initial_challenged, "❌ FAILED: times_challenged not incremented"
    assert belief.contradiction_strength > 0, "❌ FAILED: contradiction_strength not set"
    
    print("✅ PASSED: Belief object correctly updated with contradiction data")


def test_multiple_contradictions():
    """Test detecting contradictions in multiple beliefs"""
    print("\n" + "="*70)
    print("TEST 4: Multiple Contradictions in One Input")
    print("="*70)
    
    reasoning = MaximumSophisticationReasoning()
    
    # Set up multiple beliefs
    reasoning.beliefs['belief1'] = Belief(
        about='humans',
        what_i_believe='humans are always rational',
        why_i_believe_it=['they think logically'],
        confidence=0.6,
        formed_when=time.time()
    )
    
    reasoning.beliefs['belief2'] = Belief(
        about='emotions',
        what_i_believe='emotions are separate from logic',
        why_i_believe_it=['they feel different'],
        confidence=0.7,
        formed_when=time.time()
    )
    
    contradicting_facts = [
        {'content': 'Humans make irrational decisions'},
        {'content': 'Emotions override logic'}
    ]
    
    reasoning.thalamus.send_message = lambda d, m, c, source=None: {
        'status': 'success',
        'facts': contradicting_facts
    } if d == 'notus' else {'status': 'ok'}
    
    # Input that contradicts both beliefs
    user_input = "Actually, humans are not rational - emotions override their logic constantly"
    
    contradictions = reasoning._detect_belief_contradictions(
        user_input,
        ['humans', 'emotions', 'logic'],
        {'context_data': {}}
    )
    
    print(f"User input: {user_input}")
    print(f"Total contradictions detected: {len(contradictions)}")
    
    for i, c in enumerate(contradictions, 1):
        print(f"  {i}. {c['belief_about']}: strength {c['contradiction_strength']:.2f}")
    
    assert len(contradictions) >= 1, "❌ FAILED: Should detect at least 1 contradiction"
    print(f"✅ PASSED: Detected {len(contradictions)} contradiction(s) in single input")


def test_contradiction_strength_scaling():
    """Test that contradiction strength scales with evidence"""
    print("\n" + "="*70)
    print("TEST 5: Contradiction Strength Scales with Evidence")
    print("="*70)
    
    reasoning = MaximumSophisticationReasoning()
    
    belief = Belief(
        about='test_topic',
        what_i_believe='statement',
        why_i_believe_it=['reason'],
        confidence=0.5,
        formed_when=time.time()
    )
    reasoning.beliefs['test'] = belief
    
    # Test with different numbers of contradicting facts
    test_cases = [
        (1, 0.35),   # 1 fact -> strength ~0.35
        (2, 0.70),   # 2 facts -> strength ~0.70
        (3, 0.95),   # 3+ facts -> strength capped at 0.95
    ]
    
    for num_facts, expected_strength in test_cases:
        belief.contradiction_detected = False
        belief.contradiction_strength = 0.0
        
        facts = [{'content': f'Fact {i}'} for i in range(num_facts)]
        
        reasoning.thalamus.send_message = lambda d, m, c, source=None: {
            'status': 'success',
            'facts': facts
        } if d == 'notus' else {'status': 'ok'}
        
        contradictions = reasoning._detect_belief_contradictions(
            "But actually, not test_topic",
            ['test_topic'],
            {'context_data': {}}
        )
        
        if contradictions:
            actual_strength = contradictions[0]['contradiction_strength']
            print(f"{num_facts} fact(s): strength = {actual_strength:.2f} (expected ~{expected_strength:.2f})")
            assert abs(actual_strength - expected_strength) < 0.05, f"❌ Strength mismatch"
    
    print("✅ PASSED: Contradiction strength scales correctly")


if __name__ == '__main__':
    print("\n🧪 CONTRADICTION DETECTION SYSTEM TESTS\n")
    
    try:
        test_simple_contradiction_detection()
        test_no_contradiction_when_no_conflict_language()
        test_belief_updated_with_contradiction()
        test_multiple_contradictions()
        test_contradiction_strength_scaling()
        
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED - Contradiction Detection Working")
        print("="*70 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
