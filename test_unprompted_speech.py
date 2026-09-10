#!/usr/bin/env python3
"""
Test Unprompted Speech - Verify Monday can speak without prompting
"""

import sys
from thalamus import get_thalamus
from conversation import ConversationSystem
from autonomous_speech import AutonomousSpeechSystem


def test_unprompted_speech():
    """Test autonomous speech API returns structured, non-crashing results."""
    thalamus = get_thalamus()
    conversation = ConversationSystem(thalamus=thalamus)
    thalamus.register_lobe("conversation", conversation)
    speech = AutonomousSpeechSystem()

    context = {
        'emotion': 'curious',
        'curiosity': 0.8,  # High curiosity
        'recent_topic': 'pattern recognition in user behavior'
    }

    result = thalamus.send_message('speech', 'generate_unprompted', {'context': context})
    assert isinstance(result, dict)
    assert result.get("status") == "success"
    assert "generated" in result
    if result.get("generated"):
        assert isinstance(result.get("speech"), str)
        assert result.get("speech", "").strip()
    else:
        assert isinstance(result.get("reason"), str)
        assert result.get("reason", "").strip()

    speech_result = thalamus.send_message('speech', 'get_pending_speech', {})
    assert isinstance(speech_result, dict)
    assert speech_result.get("status") == "success"
    assert "speech" in speech_result

    conv_result = thalamus.send_message('conversation', 'check_unprompted_speech', {})
    assert isinstance(conv_result, dict)
    assert conv_result.get("status") == "success"
    assert "has_speech" in conv_result
    if conv_result.get("has_speech"):
        assert isinstance(conv_result.get("speech"), str)
        assert conv_result.get("speech", "").strip()

    speech.running = False


if __name__ == "__main__":
    try:
        test_unprompted_speech()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
