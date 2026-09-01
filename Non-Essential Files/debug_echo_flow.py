#!/usr/bin/env python3
"""
Debug the exact flow to find where echo happens
"""

import socket
import struct
import json
import sys

def send_to_reasoning(user_input):
    """Send directly to Reasoning and see what it returns"""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect("/tmp/reasoning.sock")
        
        message = {
            'type': 'think',
            'input': {
                'user_input': user_input,
                'emotion': {'type': 'neutral', 'intensity': 0.5},
                'memories': [],
                'concepts': [],
                'patterns': {},
                'highly_active_concepts': []
            }
        }
        
        msg_data = json.dumps(message).encode('utf-8')
        sock.send(struct.pack('!I', len(msg_data)) + msg_data)
        
        length_data = sock.recv(4)
        if length_data:
            resp_len = struct.unpack('!I', length_data)[0]
            resp_data = b''
            while len(resp_data) < resp_len:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                resp_data += chunk
            
            result = json.loads(resp_data.decode('utf-8'))
            sock.close()
            return result
    except Exception as e:
        return {'status': 'error', 'message': str(e)}
    
    return {'status': 'error', 'message': 'No response'}

def send_to_thalamus(user_input):
    """Send to Thalamus and see what it returns"""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect("/tmp/thalamus.sock")
        
        message = {
            'type': 'process_input',
            'user_input': user_input
        }
        
        msg_data = json.dumps(message).encode('utf-8')
        sock.send(struct.pack('!I', len(msg_data)) + msg_data)
        
        length_data = sock.recv(4)
        if length_data:
            resp_len = struct.unpack('!I', length_data)[0]
            resp_data = b''
            while len(resp_data) < resp_len:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                resp_data += chunk
            
            result = json.loads(resp_data.decode('utf-8'))
            sock.close()
            return result
    except Exception as e:
        return {'status': 'error', 'message': str(e)}
    
    return {'status': 'error', 'message': 'No response'}

def main():
    if len(sys.argv) < 2:
        test_input = "Hello"
    else:
        test_input = sys.argv[1]
    
    print("=" * 70)
    print(f"DEBUGGING ECHO FLOW")
    print(f"Test input: '{test_input}'")
    print("=" * 70)
    
    # Test 1: Direct to Reasoning
    print("\n1. Testing Reasoning directly:")
    reasoning_result = send_to_reasoning(test_input)
    print(f"   Status: {reasoning_result.get('status')}")
    
    if reasoning_result.get('status') == 'success':
        thinking = reasoning_result.get('thinking', {})
        composed = thinking.get('composed_response', 'MISSING')
        print(f"   composed_response: '{composed}'")
        print(f"   Type: {type(composed)}")
        print(f"   Length: {len(composed) if composed else 0}")
        
        if composed == test_input:
            print("   ⚠️  ECHO DETECTED - Response matches input!")
        elif composed == '':
            print("   ⚠️  EMPTY RESPONSE - composed_response is empty string")
        elif composed == 'MISSING':
            print("   ⚠️  MISSING KEY - composed_response key doesn't exist")
        else:
            print(f"   ✅ Valid response: '{composed[:100]}...'")
    else:
        print(f"   ❌ Error: {reasoning_result.get('message')}")
    
    # Test 2: Through Thalamus
    print("\n2. Testing through Thalamus:")
    thalamus_result = send_to_thalamus(test_input)
    print(f"   Status: {thalamus_result.get('status')}")
    
    if thalamus_result.get('status') == 'success':
        response = thalamus_result.get('response', 'MISSING')
        print(f"   response: '{response}'")
        print(f"   Type: {type(response)}")
        print(f"   Length: {len(response) if response else 0}")
        
        if response == test_input:
            print("   ⚠️  ECHO DETECTED - Response matches input!")
        elif response == '':
            print("   ⚠️  EMPTY RESPONSE")
        elif response == 'MISSING':
            print("   ⚠️  MISSING KEY")
        else:
            print(f"   ✅ Valid response: '{response[:100]}...'")
    else:
        print(f"   ❌ Error: {thalamus_result.get('message')}")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()

