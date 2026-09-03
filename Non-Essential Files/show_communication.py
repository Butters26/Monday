#!/usr/bin/env python3
"""
Show how all the brain lobes communicate with each other
Visualizes the message flow between lobes
"""

import subprocess
import socket
import struct
import json
import time
import sys
import os

def send_message(socket_path, msg_type, content):
    """Send message to a lobe"""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(socket_path)
        
        message = {'type': msg_type, **content}
        message_data = json.dumps(message).encode('utf-8')
        message_length = struct.pack('!I', len(message_data))
        sock.send(message_length + message_data)
        
        length_data = sock.recv(4)
        if not length_data:
            sock.close()
            return None
            
        response_length = struct.unpack('!I', length_data)[0]
        response_data = b''
        while len(response_data) < response_length:
            chunk = sock.recv(min(response_length - len(response_data), 4096))
            if not chunk:
                break
            response_data += chunk
        
        sock.close()
        return json.loads(response_data.decode('utf-8'))
        
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def demonstrate_communication():
    """Show how lobes communicate"""
    
    print("🔗 DEMONSTRATING LOBE COMMUNICATION")
    print("=" * 80)
    print("\nUser Input: 'Why do people fall in love?'")
    print("\n" + "=" * 80)
    
    user_input = "Why do people fall in love?"
    
    # Step 1: Would go to Perception first
    print("\n📍 STEP 1: PERCEPTION LOBE")
    print("-" * 80)
    print("Receives: User text input")
    print("Processes: Extracts concepts, detects questions, identifies emotions")
    print("Output: Concepts ['Why', 'people', 'fall', 'love'], question detected")
    
    # Step 2: Representation Layer
    print("\n📍 STEP 2: REPRESENTATION LAYER")
    print("-" * 80)
    print("Receives: Concepts from Perception")
    print("Processes: Activates related concepts in shared space")
    print("Output: Activated concept network around 'love', 'people', 'emotion'")
    
    # Step 3: Pattern Recognition
    print("\n📍 STEP 3: PATTERN RECOGNITION")
    print("-" * 80)
    print("Receives: Active concepts")
    
    result = send_message("/tmp/pattern.sock", 'observe', {
        'items': ['love', 'people', 'emotion', 'connection'],
        'item_type': 'concept'
    })
    
    if result and result.get('status') == 'success':
        patterns = result.get('patterns', {})
        print(f"Processes: Watching for patterns")
        print(f"Output: Found {len(patterns.get('co_occurrences', []))} co-occurrences")
        if patterns.get('new_patterns'):
            print("        🆕 New pattern detected!")
    else:
        print("Processes: Pattern detection")
        print("Output: Pattern data")
    
    # Step 4: Memory (Notus)
    print("\n📍 STEP 4: NOTUS (MEMORY)")
    print("-" * 80)
    print("Receives: Question + active concepts")
    print("Processes: Retrieves relevant memories and context")
    print("Output: Past conversations about love, stored facts about emotions")
    
    # Step 5: Emotional Engine
    print("\n📍 STEP 5: EMOTIONAL ENGINE")
    print("-" * 80)
    print("Receives: Question content")
    print("Processes: Assesses emotional tone of question")
    print("Output: Curious (0.7 intensity), interested in understanding")
    
    # Step 6: Reasoning (the thinker)
    print("\n📍 STEP 6: REASONING LOBE")
    print("-" * 80)
    print("Receives: ALL data from above lobes:")
    print("  - Concepts from Perception")
    print("  - Activated network from Representation")
    print("  - Patterns from Pattern Recognition")
    print("  - Context from Notus")
    print("  - Emotional state from Emotional Engine")
    
    result = send_message("/tmp/reasoning.sock", 'think', {
        'input': {
            'user_input': user_input,
            'emotion': {'type': 'curious', 'intensity': 0.7},
            'memories': [
                {'content': 'Love involves emotional connection'},
                {'content': 'People seek companionship'}
            ],
            'concepts': ['love', 'people', 'emotion']
        }
    })
    
    if result and result.get('status') == 'success':
        thinking = result.get('thinking', {})
        print("Processes: Thinks about all inputs, generates theories, makes meaning")
        print("\nThinking Output:")
        
        if thinking.get('curiosities'):
            theories = thinking['curiosities'][0].get('theories', [])
            print(f"  Generated {len(theories)} theories")
            for i, theory in enumerate(theories, 1):
                print(f"    {i}. {theory['theory']}")
        
        composed = thinking.get('composed_response', 'No response')
        print(f"\nComposed Response: \"{composed}\"")
    else:
        print("Processes: Logical reasoning, theory generation")
        print("Output: Response about love and connection")
    
    # Step 7: Output Lobe
    print("\n📍 STEP 7: OUTPUT LOBE")
    print("-" * 80)
    print("Receives: Composed response from Reasoning")
    print("Processes: Formats with emotion, prepares for voice/text")
    print("Output: Final formatted response")
    
    # Step 8: Back to user
    print("\n📍 STEP 8: BACK TO USER")
    print("-" * 80)
    print("Interface displays the final response")
    print(f"User sees: \"{composed if 'composed' in locals() else 'Response from ABIN'}\"")
    
    print("\n" + "=" * 80)
    print("COMMUNICATION FLOW COMPLETE")
    print("=" * 80)
    
    print("\n💡 KEY POINTS:")
    print("  - Each lobe processes independently")
    print("  - They communicate through Unix sockets")
    print("  - Thalamus would coordinate the flow (not shown here)")
    print("  - Reasoning combines ALL inputs to generate response")
    print("  - Output formats the final response")
    print("  - User gets coherent answer from combined brain activity")

if __name__ == "__main__":
    # Start required lobes
    print("🚀 Starting required lobes...")
    
    lobes = [
        ("pattern_recognition.py", "/tmp/pattern.sock"),
        ("reasoning.py", "/tmp/reasoning.sock")
    ]
    
    processes = []
    for script, socket_path in lobes:
        if not os.path.exists(socket_path):
            process = subprocess.Popen(
                [sys.executable, script],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            processes.append(process)
            time.sleep(1.5)
    
    try:
        demonstrate_communication()
    finally:
        print("\n🛑 Cleaning up...")
        for p in processes:
            p.terminate()

