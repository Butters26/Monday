#!/usr/bin/env python3
"""
Deep debugger to trace conversation flow
Shows exactly what each lobe is doing
"""

import socket
import struct
import json
import sys

def _recv_all(conn, n, timeout=5.0):
    """Read exactly n bytes or raise IOError on EOF/timeout"""
    conn.settimeout(timeout)
    data = b''
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise IOError("Unexpected EOF while reading")
        data += chunk
    return data

def send_to_lobe(socket_path, msg_type, content):
    """Send message to a lobe and get response"""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(8)
        sock.connect(socket_path)
        
        message = {'type': msg_type, **content}
        message_data = json.dumps(message).encode('utf-8')
        message_length = struct.pack('!I', len(message_data))
        sock.sendall(message_length + message_data)
        
        length_data = _recv_all(sock, 4, timeout=8)
        msg_length = struct.unpack('!I', length_data)[0]
        
        if msg_length <= 0 or msg_length > 10_000_000:
            raise ValueError(f"Invalid message length: {msg_length}")
        
        data = _recv_all(sock, msg_length, timeout=8)
        result = json.loads(data.decode('utf-8'))
        sock.close()
        return result
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def debug_conversation(user_input):
    """Trace the full conversation flow"""
    print("=" * 80)
    print(f"DEBUGGING: '{user_input}'")
    print("=" * 80)
    
    # 1. CONVERSATION LOBE
    print("\n[1] CONVERSATION LOBE")
    print("-" * 80)
    conv_result = send_to_lobe("/tmp/conversation.sock", "understand", {
        'user_input': user_input,
        'context': {}
    })
    print(f"Status: {conv_result.get('status')}")
    print(f"Response: {conv_result.get('response', 'N/A')}")
    print(f"Emotion: {conv_result.get('emotion', 'N/A')}")
    print(f"Understanding: {json.dumps(conv_result.get('understanding', {}), indent=2)}")
    
    understanding = conv_result.get('understanding', {})
    response = conv_result.get('response', '')
    emotion = conv_result.get('emotion', 'neutral')
    intensity = conv_result.get('intensity', 0.5)
    
    # 2. REASONING LOBE
    print("\n[2] REASONING LOBE")
    print("-" * 80)
    reasoning_result = send_to_lobe("/tmp/reasoning.sock", "think", {
        'input': {
            'user_input': user_input,
            'concepts': [],
            'understanding': understanding,
            'memory_context': {'emotional_state': {}},
            'beliefs': []
        }
    })
    print(f"Status: {reasoning_result.get('status')}")
    thinking = reasoning_result.get('thinking', {})
    print(f"Composed Response: {thinking.get('composed_response', 'N/A')}")
    print(f"Emotion: {thinking.get('emotion', 'N/A')}")
    print(f"Full thinking: {json.dumps(thinking, indent=2, default=str)}")
    
    if thinking.get('composed_response'):
        response = thinking.get('composed_response')
        reasoning_composed = True
    else:
        reasoning_composed = False
    
    # 3. LANGUAGE LOBE (if not composed)
    if not reasoning_composed:
        print("\n[3] LANGUAGE LOBE")
        print("-" * 80)
        user_words = user_input.split()
        stop_words = {'i', 'you', 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'to', 'of', 'in', 'on', 'at', 'for', 'with', 'by', 'from', 'as', 'this', 'that', 'these', 'those', 'what', 'when', 'where', 'who', 'why', 'how', 'hey', 'hi', 'hello'}
        meaningful_concepts = [w for w in user_words if w.lower() not in stop_words and len(w) > 2][:5]
        print(f"Extracted concepts: {meaningful_concepts}")
        
        lang_result = send_to_lobe("/tmp/language.sock", "generate_grounded", {
            'concepts': meaningful_concepts if meaningful_concepts else ['conversation'],
            'emotion': emotion,
            'intensity': intensity,
            'internal_state': {}
        })
        print(f"Status: {lang_result.get('status')}")
        print(f"Sentence: {lang_result.get('sentence', 'N/A')}")
        if lang_result.get('status') == 'success':
            response = lang_result.get('sentence', response)
    
    # 4. OUTPUT LOBE
    print("\n[4] OUTPUT LOBE")
    print("-" * 80)
    output_result = send_to_lobe("/tmp/output.sock", "generate_output", {
        'content': {
            'text': response,
            'emotion': emotion,
            'intensity': intensity
        }
    })
    print(f"Status: {output_result.get('status')}")
    print(f"Final text: {output_result.get('text', 'N/A')}")
    
    # 5. FINAL RESULT
    print("\n" + "=" * 80)
    print("FINAL RESPONSE:")
    print(f"  '{output_result.get('text', response)}'")
    print("=" * 80)
    
    return output_result.get('text', response)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_input = " ".join(sys.argv[1:])
    else:
        test_input = "hello"
    
    debug_conversation(test_input)

