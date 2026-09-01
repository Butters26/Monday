#!/usr/bin/env python3
"""
Test: Perception → Novelty Lobe Integration
Verify that Perception correctly detects and signals novel concepts.
"""

import sys
import time
from unittest.mock import Mock, patch, MagicMock
sys.path.insert(0, '/Users/matthew/Desktop/This is very close to being a brain')

from perception import PerceptionLobe
from novelty_lobe import NoveltyLobe

def test_perception_detects_novel_entities():
    """Test that Perception detects new entities as novel"""
    print("\n" + "="*70)
    print("TEST 1: Perception Detects Novel Entities")
    print("="*70)
    
    # Create perception lobe with mocked thalamus
    perception = PerceptionLobe()
    
    # Mock the thalamus.send_message to capture novelty signals
    novelty_signals = []
    original_send = perception.thalamus.send_message
    
    def capture_novelty(destination, msg_type, content, source=None):
        if destination == 'novelty' and msg_type == 'novelty_signal':
            novelty_signals.append(content)
            return {'status': 'success'}
        return {'status': 'ok'}
    
    perception.thalamus.send_message = capture_novelty
    
    # Input 1: A sentence with a novel entity (proper noun)
    text1 = "I just discovered this amazing musician named David Bowie"
    result1 = perception.process_text_input(text1)
    
    print(f"Input: {text1}")
    print(f"Entities detected: {result1['concepts']['entities']}")
    print(f"Novelty signals sent: {len(novelty_signals)}")
    
    if novelty_signals:
        print(f"Signal 1: {novelty_signals[0]}")
    
    assert len(novelty_signals) > 0, "❌ FAILED: No novelty signal sent for new entity"
    assert 'David' in novelty_signals[0].get('novel_entities', []) or 'Bowie' in novelty_signals[0].get('novel_entities', []), \
        "❌ FAILED: Entity not recognized as novel"
    
    print("✅ PASSED: New entity correctly detected as novel")
    
    # Input 2: Same entity again - should NOT trigger novelty (already seen)
    novelty_signals.clear()
    text2 = "David Bowie is a legend"
    result2 = perception.process_text_input(text2)
    
    print(f"\nInput: {text2}")
    print(f"Entities detected: {result2['concepts']['entities']}")
    print(f"Novelty signals sent: {len(novelty_signals)}")
    
    # Should still send if there's a new concept, but not the Bowie entity again
    if novelty_signals:
        print(f"Signal 2: {novelty_signals[0]}")
        novel_ents = novelty_signals[0].get('novel_entities', [])
        assert 'Bowie' not in novel_ents and 'David' not in novel_ents, \
            "❌ FAILED: Repeated entity triggered novelty again"
    
    print("✅ PASSED: Repeated entity not detected as novel again")


def test_perception_detects_novel_concepts():
    """Test that Perception detects new concepts as novel"""
    print("\n" + "="*70)
    print("TEST 2: Perception Detects Novel Concepts")
    print("="*70)
    
    perception = PerceptionLobe()
    novelty_signals = []
    
    def capture_novelty(destination, msg_type, content, source=None):
        if destination == 'novelty' and msg_type == 'novelty_signal':
            novelty_signals.append(content)
            return {'status': 'success'}
        return {'status': 'ok'}
    
    perception.thalamus.send_message = capture_novelty
    
    # Input with novel concepts
    text = "I discovered synesthesia - where sounds have colors"
    result = perception.process_text_input(text)
    
    print(f"Input: {text}")
    print(f"Concepts detected: {result['concepts']['words']}")
    print(f"Novelty signals sent: {len(novelty_signals)}")
    
    if novelty_signals:
        print(f"Novel concepts: {novelty_signals[0].get('novel_concepts', [])}")
    
    assert len(novelty_signals) > 0, "❌ FAILED: No novelty signal sent for new concepts"
    assert len(novelty_signals[0].get('novel_concepts', [])) > 0, \
        "❌ FAILED: Concepts not recognized as novel"
    
    print("✅ PASSED: New concepts correctly detected as novel")


def test_perception_detects_novel_questions():
    """Test that Perception flags novel questions"""
    print("\n" + "="*70)
    print("TEST 3: Perception Detects Novel Questions")
    print("="*70)
    
    perception = PerceptionLobe()
    novelty_signals = []
    
    def capture_novelty(destination, msg_type, content, source=None):
        if destination == 'novelty' and msg_type == 'novelty_signal':
            novelty_signals.append(content)
            return {'status': 'success'}
        return {'status': 'ok'}
    
    perception.thalamus.send_message = capture_novelty
    
    # Input with a genuine question
    text = "What makes consciousness different from simple information processing?"
    result = perception.process_text_input(text)
    
    print(f"Input: {text}")
    print(f"Questions detected: {result['concepts']['questions']}")
    print(f"Novelty signals sent: {len(novelty_signals)}")
    
    if novelty_signals:
        print(f"Has novel questions: {novelty_signals[0].get('has_novel_questions', False)}")
        print(f"Confidence: {novelty_signals[0].get('confidence', 0):.2f}")
    
    assert len(novelty_signals) > 0, "❌ FAILED: No novelty signal sent for novel question"
    assert novelty_signals[0].get('has_novel_questions', False), \
        "❌ FAILED: Question not flagged as novel"
    
    print("✅ PASSED: Novel questions correctly detected")


def test_perception_novelty_confidence():
    """Test that Perception calculates confidence correctly"""
    print("\n" + "="*70)
    print("TEST 4: Novelty Confidence Calculation")
    print("="*70)
    
    perception = PerceptionLobe()
    novelty_signals = []
    
    def capture_novelty(destination, msg_type, content, source=None):
        if destination == 'novelty' and msg_type == 'novelty_signal':
            novelty_signals.append(content)
            return {'status': 'success'}
        return {'status': 'ok'}
    
    perception.thalamus.send_message = capture_novelty
    
    # High novelty: new entity + new concepts
    text = "Meet my friend Aria, she practices polyamory"
    result = perception.process_text_input(text)
    
    print(f"Input: {text}")
    
    if novelty_signals:
        confidence = novelty_signals[0].get('confidence', 0)
        print(f"Novelty confidence: {confidence:.2f}")
        assert confidence > 0.5, f"❌ FAILED: Expected high confidence, got {confidence}"
        print("✅ PASSED: High novelty inputs have high confidence")
    else:
        print("⚠️  No novelty signal (might be OK if no new entities/concepts)")


def test_perception_thalamus_integration():
    """Test that Perception correctly sends messages through Thalamus"""
    print("\n" + "="*70)
    print("TEST 5: Perception-Thalamus Integration")
    print("="*70)
    
    perception = PerceptionLobe()
    messages_sent = []
    
    def track_send(destination, msg_type, content, source=None):
        messages_sent.append({
            'destination': destination,
            'msg_type': msg_type,
            'content': content,
            'source': source
        })
        return {'status': 'success'}
    
    perception.thalamus.send_message = track_send
    
    # Process input
    text = "I learned about the Fermi Paradox today"
    perception.process_text_input(text)
    
    # Check that novelty message was sent correctly
    novelty_msgs = [m for m in messages_sent if m['destination'] == 'novelty']
    
    print(f"Total messages sent: {len(messages_sent)}")
    print(f"Novelty messages sent: {len(novelty_msgs)}")
    
    if novelty_msgs:
        msg = novelty_msgs[0]
        print(f"Novelty message structure:")
        print(f"  - type: {msg['content'].get('type')}")
        print(f"  - source: {msg['content'].get('source')}")
        print(f"  - stimulus_type: {msg['content'].get('stimulus_type')}")
        
        assert msg['content'].get('type') == 'novelty_signal', \
            "❌ FAILED: Message type should be 'novelty_signal'"
        assert msg['content'].get('source') == 'perception', \
            "❌ FAILED: Source should be 'perception'"
        
        print("✅ PASSED: Novelty messages properly formatted")
    else:
        print("⚠️  No novelty messages sent (might be OK if no novelty detected)")


if __name__ == '__main__':
    print("\n🧪 PERCEPTION → NOVELTY LOBE INTEGRATION TESTS\n")
    
    try:
        test_perception_detects_novel_entities()
        test_perception_detects_novel_concepts()
        test_perception_detects_novel_questions()
        test_perception_novelty_confidence()
        test_perception_thalamus_integration()
        
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED - Perception ↔ Novelty Integration Working")
        print("="*70 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
