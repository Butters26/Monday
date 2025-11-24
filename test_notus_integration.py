#!/usr/bin/env python3
"""
Unit tests for Notus integration fixes
Tests the fallback mechanism between Notus and dict-based storage
"""

import sys
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import the Thalamus class
sys.path.insert(0, '/home/runner/work/Monday/Monday')
from thalamus import Thalamus


def test_retrieve_relevant_memory_notus_success():
    """Test that retrieve_relevant_memory uses Notus when available"""
    print("\n=== Test 1: retrieve_relevant_memory with Notus success ===")
    
    thalamus = Thalamus()
    
    # Mock send_message to return success from Notus
    with patch.object(thalamus, 'send_message') as mock_send:
        mock_send.return_value = {
            'status': 'success',
            'context': 'This is context from Notus'
        }
        
        result = thalamus.retrieve_relevant_memory("Hello there")
        
        # Verify Notus was called
        mock_send.assert_called_once_with("notus", "context", {'user_input': 'Hello there'})
        
        # Verify result uses Notus context
        assert result['memory_source'] == 'notus', "Should use Notus as source"
        assert 'notus_context' in result, "Should have notus_context key"
        assert result['notus_context'] == 'This is context from Notus'
        print("✅ PASS: Notus context retrieved successfully")


def test_retrieve_relevant_memory_notus_failure():
    """Test that retrieve_relevant_memory falls back to dict when Notus fails"""
    print("\n=== Test 2: retrieve_relevant_memory with Notus failure ===")
    
    thalamus = Thalamus()
    
    # Add some test data to memory
    thalamus.monday_memory['past_conversations'].append({
        'user_said': 'test',
        'monday_said': 'response'
    })
    
    # Mock send_message to return failure from Notus
    with patch.object(thalamus, 'send_message') as mock_send:
        mock_send.return_value = {
            'status': 'error',
            'message': 'Notus unavailable'
        }
        
        result = thalamus.retrieve_relevant_memory("Hello there")
        
        # Verify result uses fallback
        assert result['memory_source'] == 'fallback', "Should use fallback as source"
        assert 'past_exchanges' in result, "Should have past_exchanges key"
        assert 'facts_about_user' in result, "Should have facts_about_user key"
        print("✅ PASS: Fallback to dict memory works correctly")


def test_retrieve_relevant_memory_notus_exception():
    """Test that retrieve_relevant_memory handles exceptions gracefully"""
    print("\n=== Test 3: retrieve_relevant_memory with Notus exception ===")
    
    thalamus = Thalamus()
    
    # Mock send_message to raise an exception
    with patch.object(thalamus, 'send_message') as mock_send:
        mock_send.side_effect = Exception("Connection error")
        
        result = thalamus.retrieve_relevant_memory("Hello there")
        
        # Verify result uses fallback after exception
        assert result['memory_source'] == 'fallback', "Should use fallback after exception"
        assert 'past_exchanges' in result, "Should have past_exchanges key"
        print("✅ PASS: Exception handling works correctly")


def test_sync_memory_to_notus():
    """Test sync_memory_to_notus syncs unsynced conversations"""
    print("\n=== Test 4: sync_memory_to_notus ===")
    
    thalamus = Thalamus()
    
    # Add unsynced conversations
    thalamus.monday_memory['past_conversations'] = [
        {
            'user_said': 'Hello',
            'monday_said': 'Hi there',
            'synced_to_notus': False
        },
        {
            'user_said': 'How are you?',
            'monday_said': 'I am fine',
            'synced_to_notus': False
        }
    ]
    
    # Mock send_message to return success
    with patch.object(thalamus, 'send_message') as mock_send:
        mock_send.return_value = {'status': 'stored'}
        
        thalamus.sync_memory_to_notus()
        
        # Verify all conversations are marked as synced
        for conv in thalamus.monday_memory['past_conversations']:
            assert conv['synced_to_notus'] == True, "All conversations should be synced"
        
        # Verify send_message was called correctly (2 messages per conversation)
        assert mock_send.call_count == 4, "Should call send_message 4 times (2 per conversation)"
        print("✅ PASS: Conversations synced to Notus successfully")


def test_sync_memory_to_notus_no_unsynced():
    """Test sync_memory_to_notus with no unsynced conversations"""
    print("\n=== Test 5: sync_memory_to_notus with no unsynced ===")
    
    thalamus = Thalamus()
    
    # Add already synced conversations
    thalamus.monday_memory['past_conversations'] = [
        {
            'user_said': 'Hello',
            'monday_said': 'Hi there',
            'synced_to_notus': True
        }
    ]
    
    # Mock send_message
    with patch.object(thalamus, 'send_message') as mock_send:
        thalamus.sync_memory_to_notus()
        
        # Verify send_message was not called
        mock_send.assert_not_called()
        print("✅ PASS: No sync needed when all conversations are synced")


def test_sync_memory_to_notus_failure():
    """Test sync_memory_to_notus stops on failure"""
    print("\n=== Test 6: sync_memory_to_notus with failure ===")
    
    thalamus = Thalamus()
    
    # Add unsynced conversations
    thalamus.monday_memory['past_conversations'] = [
        {
            'user_said': 'Hello',
            'monday_said': 'Hi there',
            'synced_to_notus': False
        },
        {
            'user_said': 'How are you?',
            'monday_said': 'I am fine',
            'synced_to_notus': False
        }
    ]
    
    # Mock send_message to raise exception on second call
    with patch.object(thalamus, 'send_message') as mock_send:
        mock_send.side_effect = Exception("Notus failed")
        
        thalamus.sync_memory_to_notus()
        
        # Verify only first conversation attempted (stopped after exception)
        synced_count = sum(1 for conv in thalamus.monday_memory['past_conversations'] 
                          if conv.get('synced_to_notus', False))
        assert synced_count == 0, "No conversations should be synced due to failure"
        print("✅ PASS: Sync stops on failure as expected")


if __name__ == '__main__':
    print("Running Notus Integration Tests...")
    print("=" * 60)
    
    try:
        test_retrieve_relevant_memory_notus_success()
        test_retrieve_relevant_memory_notus_failure()
        test_retrieve_relevant_memory_notus_exception()
        test_sync_memory_to_notus()
        test_sync_memory_to_notus_no_unsynced()
        test_sync_memory_to_notus_failure()
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
