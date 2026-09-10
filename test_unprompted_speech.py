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

    result = speech.process_message({'type': 'generate_unprompted', 'context': context})
    assert isinstance(result, dict)
    assert result.get("status") == "success"
    result_content = result.get("content", {})
    generated = result.get("generated")
    if generated is None and isinstance(result_content, dict):
        generated = result_content.get("generated")
    if isinstance(generated, bool) and generated:
        speech_text = result.get("speech")
        if speech_text is None and isinstance(result_content, dict):
            speech_text = result_content.get("speech")
        assert isinstance(speech_text, str)
        assert speech_text.strip()
    elif isinstance(generated, bool):
        reason = result.get("reason")
        if reason is None and isinstance(result_content, dict):
            reason = result_content.get("reason")
        assert isinstance(reason, str)
        assert reason.strip()
    else:
        assert "message" not in result

    speech_result = speech.process_message({'type': 'get_pending_speech'})
    assert isinstance(speech_result, dict)
    assert speech_result.get("status") == "success"
    assert "speech" in speech_result or "reason" in speech_result

    conv_result = conversation.process_message({'type': 'check_unprompted_speech'})
    assert isinstance(conv_result, dict)
    assert conv_result.get("status") == "success"
    conv_content = conv_result.get("content", {})
    has_speech = conv_result.get("has_speech")
    if has_speech is None and isinstance(conv_content, dict):
        has_speech = conv_content.get("has_speech")
    assert isinstance(has_speech, bool)
    if has_speech:
        speech_text = conv_result.get("speech")
        if speech_text is None and isinstance(conv_content, dict):
            speech_text = conv_content.get("speech")
        assert isinstance(speech_text, str)
        assert speech_text.strip()

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
