#!/usr/bin/env python3
"""
Live monitoring of ABIN - runs in background
Captures all interactions and system state
"""

import socket
import struct
import json
import time
import os
import subprocess
from datetime import datetime
from typing import Dict, List

class LiveMonitor:
    def __init__(self):
        self.log_file = "/tmp/abin_live_monitor.jsonl"
        self.running = True
        self.check_interval = 2  # Check every 2 seconds
        
    def log_event(self, event_type: str, data: Dict):
        """Log event to file"""
        event = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'data': data
        }
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(event) + '\n')
    
    def check_socket(self, path: str) -> bool:
        """Check if socket exists"""
        return os.path.exists(path)
    
    def test_reasoning(self, test_input: str = "test") -> Dict:
        """Test Reasoning with input"""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect("/tmp/reasoning.sock")
            
            message = {'type': 'think', 'input': {
                'user_input': test_input,
                'emotion': {'type': 'neutral', 'intensity': 0.5},
                'memories': [],
                'concepts': [],
                'patterns': {},
                'highly_active_concepts': []
            }}
            
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
    
    def monitor_loop(self):
        """Main monitoring loop"""
        check_count = 0
        
        # Log start
        self.log_event('monitor_start', {'time': datetime.now().isoformat()})
        
        sockets_to_check = {
            'Reasoning': '/tmp/reasoning.sock',
            'Language Generation': '/tmp/language.sock',
            'Thalamus': '/tmp/thalamus.sock',
            'Output': '/tmp/output.sock',
            'Notus': '/tmp/notus.sock'
        }
        
        while self.running:
            check_count += 1
            timestamp = datetime.now()
            
            # Check socket status
            socket_status = {}
            for name, path in sockets_to_check.items():
                socket_status[name] = self.check_socket(path)
            
            # Test Reasoning every 10 checks (every 20 seconds)
            reasoning_test = None
            if check_count % 10 == 0 and socket_status.get('Reasoning'):
                reasoning_test = self.test_reasoning("monitor test")
                if reasoning_test.get('status') == 'success':
                    thinking = reasoning_test.get('thinking', {})
                    composed = thinking.get('composed_response', '')
                    if composed == "monitor test":
                        self.log_event('echo_detected', {
                            'input': 'monitor test',
                            'response': composed
                        })
            
            # Log status
            self.log_event('status_check', {
                'check_number': check_count,
                'sockets': socket_status,
                'reasoning_test': reasoning_test
            })
            
            # Check if brain is still running (check for process)
            if not any(self.check_socket(p) for p in sockets_to_check.values()):
                # All sockets gone - brain probably shut down
                self.log_event('brain_shutdown_detected', {
                    'check_number': check_count
                })
                time.sleep(5)  # Wait a bit to see if it restarts
                if not any(self.check_socket(p) for p in sockets_to_check.values()):
                    self.running = False
                    break
            
            time.sleep(self.check_interval)
        
        # Log end
        self.log_event('monitor_stop', {
            'time': datetime.now().isoformat(),
            'total_checks': check_count
        })
        
        print(f"\n📊 Monitoring complete: {check_count} checks logged to {self.log_file}")

if __name__ == "__main__":
    monitor = LiveMonitor()
    try:
        monitor.monitor_loop()
    except KeyboardInterrupt:
        monitor.running = False
        monitor.log_event('monitor_interrupted', {'time': datetime.now().isoformat()})

