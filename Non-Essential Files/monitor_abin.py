#!/usr/bin/env python3
"""
Continuous monitoring of ABIN while running
"""

import socket
import struct
import json
import time
import os
import subprocess
from datetime import datetime
from typing import Dict, List

def check_socket(sock_path: str) -> bool:
    """Check if socket exists"""
    return os.path.exists(sock_path)

def send_test_message(sock_path: str, msg_type: str, data: Dict) -> Dict:
    """Send test message"""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(sock_path)
        
        message = {'type': msg_type, **data}
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

def monitor_loop():
    """Main monitoring loop"""
    sockets_to_check = {
        'Reasoning': '/tmp/reasoning.sock',
        'Language Generation': '/tmp/language.sock',
        'Thalamus': '/tmp/thalamus.sock',
        'Output': '/tmp/output.sock',
        'Notus': '/tmp/notus.sock'
    }
    
    log = []
    check_count = 0
    
    print("🔍 Monitoring ABIN... (Press Ctrl+C or close brain to stop)")
    print("=" * 70)
    
    try:
        while True:
            check_count += 1
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # Check sockets
            socket_status = {}
            for name, path in sockets_to_check.items():
                socket_status[name] = check_socket(path)
            
            # Test Reasoning
            reasoning_test = None
            if socket_status['Reasoning']:
                reasoning_test = send_test_message('/tmp/reasoning.sock', 'think', {
                    'user_input': 'test',
                    'context': {}
                })
            
            # Test Language Generation
            lang_test = None
            if socket_status['Language Generation']:
                lang_test = send_test_message('/tmp/language.sock', 'generate', {
                    'semantic_input': {
                        'intent': 'greet',
                        'concepts': [],
                        'certainty': 1.0
                    }
                })
            
            # Log this check
            log_entry = {
                'timestamp': timestamp,
                'check': check_count,
                'sockets': socket_status,
                'reasoning_response': reasoning_test,
                'language_response': lang_test
            }
            log.append(log_entry)
            
            # Print status every 5 checks
            if check_count % 5 == 0:
                print(f"\n[{timestamp}] Check #{check_count}")
                for name, status in socket_status.items():
                    status_icon = "✅" if status else "❌"
                    print(f"  {status_icon} {name}")
                
                if reasoning_test:
                    resp = reasoning_test.get('composed_response', 'N/A')
                    if resp == 'test':
                        print(f"  ⚠️  Reasoning ECHOING: '{resp}'")
                    else:
                        print(f"  Reasoning response: '{resp[:50]}...'")
            
            time.sleep(2)  # Check every 2 seconds
            
    except KeyboardInterrupt:
        print("\n\n🛑 Monitoring stopped")
    finally:
        # Save log
        with open('/tmp/abin_monitor_log.json', 'w') as f:
            json.dump(log, f, indent=2)
        
        print(f"\n📊 Monitoring Summary:")
        print(f"  Total checks: {check_count}")
        print(f"  Log saved to: /tmp/abin_monitor_log.json")
        
        # Analyze log
        echo_count = 0
        for entry in log:
            if entry.get('reasoning_response', {}).get('composed_response') == 'test':
                echo_count += 1
        
        if echo_count > 0:
            print(f"  ⚠️  Echo detected in {echo_count} checks")
        
        return log

if __name__ == "__main__":
    monitor_loop()

