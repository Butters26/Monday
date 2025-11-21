#!/usr/bin/env python3
"""
Thalamus - Central Coordinator
Not just a router - manages priority, attention, and coordination between brain lobes
"""

import socket
import struct
import json
import os
import time
import heapq
from typing import Dict, List, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

class MessagePriority(Enum):
    CRITICAL = 10
    HIGH = 7
    NORMAL = 5
    LOW = 3
    BACKGROUND = 1

@dataclass
class Message:
    """Message between brain lobes"""
    source: str
    destination: str
    msg_type: str
    content: Dict[str, Any]
    priority: int
    timestamp: float
    message_id: str

@dataclass
class Coalition:
    """Group of lobes working together on a task"""
    task_id: str
    members: Set[str]
    coordinator: str
    priority: int
    created_at: float
    results: Dict[str, Any] = field(default_factory=dict)

# FIX: robust recv helper
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

class Thalamus:
    """Central coordinator - manages all brain lobe communication and coordination"""
    
    def __init__(self, socket_path="/tmp/thalamus.sock"):
        self.socket_path = socket_path
        self.running = True
        
        # Socket connections to each lobe
        self.lobe_sockets = {
            "notus": "/tmp/notus.sock",
            "emotion": "/tmp/emotion.sock",
            "perception": "/tmp/perception.sock",
            "reasoning": "/tmp/reasoning.sock",
            "output": "/tmp/output.sock",
            "pattern": "/tmp/pattern.sock",
            "representation": "/tmp/representation.sock"
        }
        
        # Global state
        self.global_state = {}
        self.priority_queue = []
        self.active_coalitions: Dict[str, Coalition] = {}
        self.attention_focus = None
        self.message_counter = 0
        
        # Autonomous message queue
        self.autonomous_message_queue = []
        
        # Lobe status
        self.lobe_status = {lobe: "unknown" for lobe in self.lobe_sockets}
        
    def send_message(self, destination: str, msg_type: str, content: Dict[str, Any]) -> Dict[str, Any]:
        """Send message to a specific lobe with error handling and FIX: per-connection timeout"""
        socket_path = self.lobe_sockets.get(destination)
        if not socket_path:
            return {'status': 'error', 'message': f'Unknown destination: {destination}'}
        
        # Check if lobe is online
        if not os.path.exists(socket_path):
            self.lobe_status[destination] = "offline"
            return {'status': 'error', 'message': f'{destination} is offline'}
        
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(8)  # FIX: per-connection timeout
            sock.connect(socket_path)
            
            message = {'type': msg_type, **content}
            
            message_data = json.dumps(message).encode('utf-8')
            message_length = struct.pack('!I', len(message_data))
            sock.send(message_length + message_data)
            
            # FIX: use recv_all instead of raw recv
            try:
                length_data = _recv_all(sock, 4, timeout=8)
            except IOError:
                sock.close()
                self.lobe_status[destination] = "offline"
                return {'status': 'error', 'message': f'{destination} not responding'}
            
            response_length = struct.unpack('!I', length_data)[0]
            
            # FIX: validate response length
            if response_length <= 0 or response_length > 10_000_000:
                sock.close()
                return {'status': 'error', 'message': f'{destination} sent invalid length'}
            
            response_data = _recv_all(sock, response_length, timeout=8)
            
            sock.close()
            
            # Update status
            self.lobe_status[destination] = "online"
            
            response = json.loads(response_data.decode('utf-8'))
            return response
            
        except socket.timeout:
            self.lobe_status[destination] = "slow"
            return {'status': 'error', 'message': f'{destination} timeout'}
        except Exception as e:
            self.lobe_status[destination] = "error"
            return {'status': 'error', 'message': f'{destination}: {str(e)}'}
    
    def form_coalition(self, task_type: str, content: Dict[str, Any]) -> Coalition:
        """Form a coalition of lobes to work on a task"""
        task_id = f"task_{self.message_counter}"
        self.message_counter += 1
        
        # Determine which lobes need to work together
        members = set()
        coordinator = None
        priority = MessagePriority.NORMAL.value
        
        if task_type == "user_input":
            members = {"perception", "representation", "pattern", "notus", "emotion", "reasoning", "output"}
            coordinator = "reasoning"
            priority = MessagePriority.HIGH.value
            
        elif task_type == "memory_query":
            members = {"notus", "reasoning"}
            coordinator = "reasoning"
            priority = MessagePriority.NORMAL.value
            
        elif task_type == "emotional_response":
            members = {"emotion", "notus", "output"}
            coordinator = "emotion"
            priority = MessagePriority.HIGH.value
            
        coalition = Coalition(
            task_id=task_id,
            members=members,
            coordinator=coordinator,
            priority=priority,
            created_at=time.time()
        )
        
        self.active_coalitions[task_id] = coalition
        return coalition
    
    def process_user_input(self, user_input: str) -> str:
        """Process user input through all brain lobes with filtering"""
        print(f"\n🧠 Thalamus: Processing: '{user_input}'")
        
        # Special handling for self-awareness questions
        user_lower = user_input.lower()
        if any(phrase in user_lower for phrase in ['who are you', 'what are you', 'tell me about yourself']):
            print(f"   -> Direct to Reasoning for self-awareness response")
            identity_result = self.send_message("reasoning", "who_are_you", {})
            if identity_result.get('status') == 'success':
                identity = identity_result.get('identity', {})
                response_parts = []
                response_parts.append(f"I'm {identity.get('name', 'ABIN')}")
                response_parts.append(identity.get('what_i_am', ''))
                if identity.get('creator'):
                    response_parts.append(f"{identity.get('creator')} created me")
                if identity.get('relationship'):
                    response_parts.append(identity.get('relationship'))
                return ". ".join([p for p in response_parts if p])
        
        # Form coalition
        coalition = self.form_coalition("user_input", {"user_input": user_input})
        print(f"   Coalition: {', '.join(coalition.members)}")
        
        # Collect filtered data from each lobe
        concepts = []
        patterns = {}
        memories = []
        emotions = {}
        perception_data = {}
        highly_active = []
        
        # Step 1: Perception
        print(f"   -> Perception...")
        perception_result = self.send_message("perception", "process_text", {"text": user_input})
        if perception_result.get('status') == 'success':
            perception_data = perception_result.get('perception', {})
            concepts = perception_data.get('concepts', {}).get('words', [])
            print(f"   <- Extracted {len(concepts)} concepts")
        else:
            print(f"   <- Perception offline, using empty data")
        
        # Step 2: Representation
        print(f"   -> Representation...")
        self.send_message("representation", "translate_from", {
            'lobe': 'perception',
            'data': perception_data.get('concepts', {})
        })
        
        repr_result = self.send_message("representation", "get_highly_active", {'threshold': 0.6})
        if repr_result.get('status') == 'success':
            highly_active = repr_result.get('highly_active_concepts', [])
            print(f"   <- {len(highly_active)} highly active concepts (filtered)")
        
        # Step 3: Pattern Recognition
        print(f"   -> Pattern Recognition...")
        self.send_message("pattern", "observe", {
            'data': {
                'items': concepts[:10],
                'statement': user_input,
                'words': concepts
            }
        })
        
        pattern_result = self.send_message("pattern", "get_significant", {})
        if pattern_result.get('status') == 'success':
            patterns = pattern_result.get('significant_patterns', {})
            print(f"   <- Significant patterns only (filtered)")
        else:
            print(f"   <- Pattern Recognition offline, using empty data")
        
        # Step 4: Memory
        print(f"   -> Notus (unfiltered direct connection)...")
        memory_result = self.send_message("notus", "context", {"user_input": user_input})
        if memory_result.get('status') == 'success':
            memories = memory_result.get('context', {}).get('memories', [])
            print(f"   <- All memories ({len(memories)} items)")
        else:
            print(f"   <- Notus offline, using empty data")
        
        # Step 5: Emotional Engine
        print(f"   -> Emotional Engine...")
        emotion_result = self.send_message("emotion", "process_input", {"user_input": user_input})
        if emotion_result.get('status') == 'success':
            intensity = emotion_result.get('intensity', 0)
            if intensity > 0.5:
                emotions = {
                    'type': emotion_result.get('current_emotion'),
                    'intensity': intensity
                }
                print(f"   <- {emotions['type']} ({intensity:.2f}) - significant")
            else:
                emotions = {'type': 'neutral', 'intensity': 0.3}
                print(f"   <- Filtered out (low intensity)")
        else:
            emotions = {'type': 'neutral', 'intensity': 0.3}
            print(f"   <- Emotional Engine offline, using neutral")
        
        # Step 6: REASONING
        print(f"   -> Reasoning (combining all filtered inputs)...")
        reasoning_input = {
            'user_input': user_input,
            'emotion': emotions,
            'memories': memories,
            'concepts': concepts[:10],
            'patterns': patterns,
            'highly_active_concepts': highly_active
        }
        
        reasoning_result = self.send_message("reasoning", "think", {'input': reasoning_input})
        
        if reasoning_result.get('status') == 'success':
            thinking = reasoning_result.get('thinking', {})
            composed_response = thinking.get('composed_response', '')
            if not composed_response or not isinstance(composed_response, str) or len(composed_response.strip()) == 0:
                composed_response = None
            print(f"   <- Response composed")
        else:
            composed_response = None
            print(f"   <- Reasoning offline, system broken")
        
        # Step 7: Output
        print(f"   -> Output...")
        output_result = self.send_message("output", "generate_output", {
            'content': {
                'text': composed_response,
                'emotion': emotions.get('type'),
                'intensity': emotions.get('intensity', 0.5)
            }
        })
        
        if output_result.get('status') == 'success':
            final_response = output_result.get('text', composed_response)
            print(f"   <- Formatted")
        else:
            final_response = composed_response
            print(f"   <- Output offline, using unformatted text")
        
        # Store in Notus
        try:
            self.send_message("notus", "store", {
                "content": f"User: {user_input}\nABIN: {final_response}",
                "memory_type": "episodic"
            })
        except Exception:
            pass
        
        print(f"   ✅ Complete\n")
        
        if not final_response or not isinstance(final_response, str) or len(final_response.strip()) == 0:
            return "I'm not working right now."
        
        return final_response
    
    def start(self):
        """Start the Thalamus coordinator with socket interface and FIX: per-connection timeout"""
        import os
        
        # Remove old socket if exists
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        
        print("🧠 Thalamus Central Coordinator: Starting...")
        
        # Check lobe status
        print("\n📡 Checking lobe connections...")
        for lobe, socket_path in self.lobe_sockets.items():
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect(socket_path)
                sock.close()
                self.lobe_status[lobe] = "online"
                print(f"   ✅ {lobe}: online")
            except Exception:
                self.lobe_status[lobe] = "offline"
                print(f"   ❌ {lobe}: offline")
        
        # Create socket server
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        sock.settimeout(1.0)  # FIX: accept timeout
        
        print(f"\n🧠 Thalamus: Online at {self.socket_path}")
        print("   Coordinating all brain lobes")
        print("=" * 60)
        
        while self.running:
            try:
                try:
                    conn, _ = sock.accept()
                except socket.timeout:
                    continue  # FIX: allow check of self.running
                
                # FIX: per-connection timeout + recv_all
                try:
                    conn.settimeout(10)
                    
                    length_data = _recv_all(conn, 4, timeout=10)
                    msg_length = struct.unpack('!I', length_data)[0]
                    
                    # FIX: validate message length
                    if msg_length <= 0 or msg_length > 10_000_000:
                        raise ValueError(f"Invalid message length: {msg_length}")
                    
                    data = _recv_all(conn, msg_length, timeout=10)
                    message = json.loads(data.decode('utf-8'))
                    
                    # Process message
                    msg_type = message.get('type')
                    if msg_type == 'process_input':
                        user_input = message.get('user_input', '')
                        response_text = self.process_user_input(user_input)
                        result = {'status': 'success', 'response': response_text}
                    elif msg_type == 'autonomous_message':
                        autonomous_msg = message.get('message', '')
                        if autonomous_msg:
                            self.autonomous_message_queue.append(autonomous_msg)
                            if len(self.autonomous_message_queue) > 10:
                                self.autonomous_message_queue.pop(0)
                            result = {'status': 'success', 'message': 'Autonomous message queued'}
                        else:
                            result = {'status': 'error', 'message': 'Empty autonomous message'}
                    elif msg_type == 'check_autonomous':
                        if self.autonomous_message_queue:
                            msg = self.autonomous_message_queue.pop(0)
                            result = {'status': 'success', 'autonomous_message': msg}
                        else:
                            result = {'status': 'success', 'autonomous_message': None}
                    else:
                        result = {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
                    
                    # Send response
                    response_data = json.dumps(result).encode('utf-8')
                    response_length = struct.pack('!I', len(response_data))
                    conn.sendall(response_length + response_data)
                    
                except Exception as e:
                    # FIX: try to send error
                    try:
                        error_response = {'status': 'error', 'message': str(e)}
                        response_data = json.dumps(error_response).encode('utf-8')
                        response_length = struct.pack('!I', len(response_data))
                        conn.sendall(response_length + response_data)
                    except Exception:
                        pass
                finally:
                    # FIX: always close
                    try:
                        conn.close()
                    except Exception:
                        pass
                
            except Exception as e:
                print(f"❌ Thalamus error: {e}")
                time.sleep(0.2)
    
    def shutdown(self):
        """Graceful shutdown"""
        import os
        self.running = False
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

if __name__ == "__main__":
    thalamus = Thalamus()
    thalamus.start()
