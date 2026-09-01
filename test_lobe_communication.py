#!/usr/bin/env python3
"""
Test: Can Reasoning and Notus actually communicate?
This test bypasses the full system and directly tests the Reasoning→Notus communication path.
"""

import sys
import os
import time
import json

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from thalamus import get_thalamus, Thalamus
from reasoning import MaximumSophisticationReasoning
from notus import NotusProcess

def test_communication():
    print("\n" + "="*70)
    print("🔬 LOBE COMMUNICATION TEST: Reasoning ↔ Notus")
    print("="*70)
    
    # Initialize Thalamus (message router)
    print("\n1️⃣  Initializing Thalamus...")
    thalamus = Thalamus()
    print("   ✅ Thalamus ready")
    
    # Initialize Notus (memory system)
    print("\n2️⃣  Initializing Notus (memory system)...")
    notus = NotusProcess()
    thalamus.register_lobe('notus', notus)
    print("   ✅ Notus registered with Thalamus")
    
    # Wait for Notus to initialize memory
    print("   ⏳ Waiting for Notus memory to initialize...")
    for i in range(30):  # Wait up to 30 seconds
        if notus.memory_ready.is_set():
            print(f"   ✅ Notus memory ready after {i+1} seconds")
            break
        time.sleep(1)
    else:
        print("   ⚠️  Notus memory did not initialize after 30 seconds")
    
    # Initialize Reasoning (gets Thalamus from global)
    print("\n3️⃣  Initializing Reasoning system...")
    reasoning = MaximumSophisticationReasoning()
    thalamus.register_lobe('reasoning', reasoning)
    print("   ✅ Reasoning registered with Thalamus")
    
    # TEST 1: Direct query call
    print("\n4️⃣  TEST 1: Reasoning queries Notus directly for user info...")
    print("-" * 70)
    
    try:
        user_info = reasoning.query_user_information_from_notus(user_id='test_user')
        print(f"   Status: {user_info.get('status')}")
        print(f"   Summary: {user_info.get('summary')}")
        print(f"   Facts about user: {len(user_info.get('facts_about_user', []))} found")
        print(f"   Past interactions: {len(user_info.get('past_interactions', []))} found")
        
        if user_info.get('status') == 'success':
            print("   ✅ COMMUNICATION SUCCESSFUL")
        else:
            print(f"   ❌ COMMUNICATION FAILED: {user_info.get('message')}")
    except Exception as e:
        print(f"   ❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    
    # TEST 2: Reasoning queries facts about a concept
    print("\n5️⃣  TEST 2: Reasoning queries Notus for facts about 'user'...")
    print("-" * 70)
    
    try:
        facts = reasoning.query_facts_from_notus(subject='user', limit=10)
        print(f"   Returned: {len(facts)} facts")
        if facts:
            for i, fact in enumerate(facts[:3], 1):
                print(f"   Fact {i}: {fact.get('subject')} {fact.get('predicate')} {fact.get('object')}")
        else:
            print("   (No facts stored yet)")
        print("   ✅ COMMUNICATION SUCCESSFUL")
    except Exception as e:
        print(f"   ❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    
    # TEST 3: Reasoning queries context
    print("\n6️⃣  TEST 3: Reasoning queries Notus for general context...")
    print("-" * 70)
    
    try:
        # Call Thalamus directly to see what it returns
        thalamus_response = thalamus.send_message(
            destination='notus',
            msg_type='query_context',
            content={'text': 'hello', 'user_id': 'default', 'max_results': 15},
            source='reasoning'
        )
        print(f"   Thalamus response: {thalamus_response}")
        
        context = reasoning.query_context_from_notus("hello")
        print(f"   Reasoning.query_context result: {context}")
        print(f"   Status: {context.get('status')}")
        print(f"   Summary: {context.get('summary')}")
        print(f"   Query: {context.get('query_text')}")
        
        if context.get('status') == 'success':
            print("   ✅ COMMUNICATION SUCCESSFUL")
        else:
            print(f"   ❌ COMMUNICATION FAILED")
    except Exception as e:
        print(f"   ❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    
    # TEST 4: Full think_about with automatic user info query
    print("\n7️⃣  TEST 4: Reasoning.think_about() - full workflow with user info...")
    print("-" * 70)
    
    try:
        input_data = {
            'user_input': 'hello',
            'user_id': 'test_user',
            'perception_result': {'status': 'error'},
            'emotion_result': {'status': 'error'},
            'memory_result': {'status': 'error'},
            'representation_result': {'status': 'error'},
            'pattern_result': {'status': 'error'}
        }
        
        result = reasoning.think_about(input_data)
        print(f"   Status: {result.get('status')}")
        response = result.get('composed_response', '')
        print(f"   Response: {response[:100] if response else 'None'}...")
        print("   ✅ THINKING COMPLETE")
    except Exception as e:
        print(f"   ❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*70)
    print("✅ COMMUNICATION TEST COMPLETE")
    print("="*70 + "\n")

if __name__ == '__main__':
    test_communication()
