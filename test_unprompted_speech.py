#!/usr/bin/env python3
"""
Test Unprompted Speech - Verify Monday can speak without prompting
"""

import time
import sys
from thalamus import get_thalamus


def test_unprompted_speech():
    """Test that Monday can speak on her own"""
    print("🧪 Testing Unprompted Speech System\n")
    
    thalamus = get_thalamus()
    
    print("📋 Test Scenario: Checking if Monday will speak unprompted")
    print("   - Simulating high curiosity emotional state")
    print("   - Requesting speech generation")
    print("   - Checking speech queue\n")
    
    # Simulate emotional state that triggers speech
    print("1️⃣ Setting up emotional context...")
    context = {
        'emotion': 'curious',
        'curiosity': 0.8,  # High curiosity
        'recent_topic': 'pattern recognition in user behavior'
    }
    
    # Ask speech system to evaluate if it should speak
    print("2️⃣ Requesting unprompted speech generation...")
    result = thalamus.send_message('speech', 'generate_unprompted', {'context': context})
    
    if result:
        print(f"   Status: {result.get('status')}")
        if result.get('generated'):
            print(f"   ✅ Speech generated: {result.get('speech')}")
        else:
            print(f"   ℹ️  No speech generated: {result.get('reason')}")
    
    # Check if there's pending speech
    print("\n3️⃣ Checking for pending speech...")
    speech_result = thalamus.send_message('speech', 'get_pending_speech', {})
    
    if speech_result and speech_result.get('status') == 'success':
        speech_item = speech_result.get('speech')
        if speech_item:
            print(f"   ✅ PENDING SPEECH FOUND:")
            print(f"      Content: \"{speech_item.get('content')}\"")
            print(f"      Priority: {speech_item.get('priority'):.2f}")
            print(f"      Timing: {speech_item.get('timing')}")
        else:
            reason = speech_result.get('reason', 'No speech queued')
            print(f"   ℹ️  No pending speech: {reason}")
    
    # Test conversation system integration
    print("\n4️⃣ Testing conversation system integration...")
    conv_result = thalamus.send_message('conversation', 'check_unprompted_speech', {})
    
    if conv_result and conv_result.get('status') == 'success':
        if conv_result.get('has_speech'):
            print(f"   ✅ Conversation system found speech:")
            print(f"      \"{conv_result.get('speech')}\"")
        else:
            print("   ℹ️  No speech ready for delivery")
    
    print("\n📊 Test Complete")
    print("\n💡 In the GUI:")
    print("   - Monday will check for unprompted speech every 5 seconds")
    print("   - Thinking loop generates speech opportunities every 30 seconds")
    print("   - Speech appears with 💭 emoji prefix")
    print("   - Natural timing based on emotional state\n")
    
    return True


if __name__ == "__main__":
    try:
        success = test_unprompted_speech()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
