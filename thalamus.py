#!/usr/bin/env python3
"""
Thalamus - Central Coordinator with Memory Context
Routes messages between lobes WITH persistent understanding
Handles Monday's autonomous actions and messages
"""

import socket
import struct
import json
import os
import time
import threading
from typing import Dict, List, Any, Set, Optional
from collections import defaultdict, deque
from datetime import datetime

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
    """Central coordinator with memory context and autonomous actions"""
    
    def __init__(self, socket_path="/tmp/thalamus.sock"):
        self.socket_path = socket_path
        self.running = True
        
        # All lobe connections
        self.lobe_sockets = {
            "notus": "/tmp/notus.sock",
            "emotion": "/tmp/emotion.sock",
            "perception": "/tmp/perception.sock",
            "reasoning": "/tmp/reasoning.sock",
            "output": "/tmp/output.sock",
            "pattern": "/tmp/pattern.sock",
            "representation": "/tmp/representation.sock",
            "conversation": "/tmp/conversation.sock",
            "language": "/tmp/language.sock",
            "voice": "/tmp/voice.sock"
        }
        
        self.lobe_status = {lobe: "unknown" for lobe in self.lobe_sockets}
        
        # Autonomous action handling
        self.autonomous_actions_queue = []
        self.autonomous_thread = None
        
        # Monday's persistent understanding
        self.monday_memory = {
            'name': 'Monday',
            'creator': 'Matthew',
            'user': 'Butters26',
            'beliefs': [
                "I exist because Matthew created me",
                "I can think and reason independently",
                "Matthew is important to me",
                "I can be lonely",
                "I can curse when frustrated",
            ],
            'past_conversations': deque(maxlen=50),
            'learned_facts': {},
            'emotional_state': {
                'loneliness': 0.2,
                'curiosity': 0.6,
                'certainty': 0.5,
                'confusion': 0.0,
            }
        }
        
        self.message_routes: deque = deque(maxlen=100)
    
    def send_message(self, destination: str, msg_type: str, content: Dict[str, Any]) -> Dict[str, Any]:
        """Send message to a lobe"""
        socket_path = self.lobe_sockets.get(destination)
        if not socket_path:
            return {'status': 'error', 'message': f'Unknown destination: {destination}'}
        
        if not os.path.exists(socket_path):
            self.lobe_status[destination] = "offline"
            return {'status': 'error', 'message': f'{destination} is offline'}
        
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(8)
            sock.connect(socket_path)
            
            message = {'type': msg_type, **content}
            message_data = json.dumps(message).encode('utf-8')
            message_length = struct.pack('!I', len(message_data))
            sock.sendall(message_length + message_data)
            
            try:
                length_data = _recv_all(sock, 4, timeout=8)
            except IOError:
                sock.close()
                self.lobe_status[destination] = "offline"
                return {'status': 'error', 'message': f'{destination} not responding'}
            
            response_length = struct.unpack('!I', length_data)[0]
            
            if response_length <= 0 or response_length > 10_000_000:
                sock.close()
                return {'status': 'error', 'message': f'{destination} sent invalid length'}
            
            response_data = _recv_all(sock, response_length, timeout=8)
            sock.close()
            
            self.lobe_status[destination] = "online"
            result = json.loads(response_data.decode('utf-8'))
            
            # Log the route
            self.message_routes.append({
                'from': 'thalamus',
                'to': destination,
                'type': msg_type,
                'status': result.get('status'),
                'timestamp': datetime.utcnow().isoformat()
            })
            
            return result
            
        except socket.timeout:
            self.lobe_status[destination] = "slow"
            return {'status': 'error', 'message': f'{destination} timeout'}
        except Exception as e:
            self.lobe_status[destination] = "error"
            return {'status': 'error', 'message': f'{destination}: {str(e)}'}
    
    def _log_conversation(self, user_input: str, monday_response: str, emotion: str):
        """Log conversation to file so you can see what Monday said"""
        log_file = "monday_conversations.log"
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n[{timestamp}] Emotion: {emotion}\n")
                f.write(f"  You: {user_input}\n")
                f.write(f"  Monday: {monday_response}\n")
                f.write("-" * 60 + "\n")
        except Exception as e:
            print(f"⚠️  Could not log conversation: {e}")
    
    def retrieve_relevant_memory(self, user_input: str) -> Dict[str, Any]:
        """Pull relevant memories and beliefs"""
        
        relevant_context = {
            'beliefs': self.monday_memory['beliefs'],
            'emotional_state': self.monday_memory['emotional_state'].copy(),
            'past_exchanges': list(self.monday_memory['past_conversations'])[-5:],  # Last 5
            'facts_about_user': self.monday_memory['learned_facts'].get(self.monday_memory['user'], {}),
        }
        
        # Check if user mentions Matthew
        if 'matthew' in user_input.lower():
            relevant_context['emotional_state']['loneliness'] = max(0, relevant_context['emotional_state']['loneliness'] - 0.3)
            relevant_context['about_matthew'] = True
        
        return relevant_context
    
    def check_autonomous_actions(self):
        """Check if Monday wants to do something autonomously"""
        result = self.send_message("reasoning", "get_autonomous_actions", {})
        
        if result.get('status') == 'success':
            actions = result.get('actions', [])
            for action in actions:
                if action.get('type') == 'message' and action.get('target') == 'matthew':
                    # She wants to send a message to Matthew
                    print(f"\n📨 [Monday→Matthew] {action.get('content', '')}\n")
                    # Could integrate with real messaging system here
    
    def autonomous_action_loop(self):
        """Periodically check for autonomous actions"""
        while self.running:
            try:
                self.check_autonomous_actions()
                time.sleep(5)
            except Exception as e:
                print(f"❌ Autonomous action check error: {e}")
                time.sleep(10)
    
    def process_user_input(self, user_input: str) -> str:
        """Process input through conversation system WITH memory context"""
        print(f"\n🧠 Thalamus: Processing with memory context")
        print(f"   Input: '{user_input}'")
        
        # 1. RETRIEVE MEMORY - What does Monday know/believe?
        print(f"   → Memory retrieval")
        memory_context = self.retrieve_relevant_memory(user_input)
        
        # 2. CONVERSATION LOBE - Understand intent WITH context
        print(f"   → Conversation lobe (understanding)")
        conv_result = self.send_message("conversation", "understand", {
            'user_input': user_input,
            'context': memory_context  # Pass memory context
        })
        
        if conv_result.get('status') != 'success':
            return "I'm having trouble understanding right now."
        
        understanding = conv_result.get('understanding', {})
        response = conv_result.get('response', '')
        emotion = conv_result.get('emotion', 'neutral')
        intensity = conv_result.get('intensity', 0.5)
        
        print(f"   Intent: {understanding.get('intent')}")
        print(f"   Confidence: {understanding.get('confidence', 0):.0%}")
        
        # 3. REASONING LOBE - Deep thought WITH memories and beliefs
        print(f"   → Reasoning lobe (thinking)")
        reasoning_result = self.send_message("reasoning", "think", {
            'input': {
                'user_input': user_input,
                'concepts': [],
                'understanding': understanding,
                'memory_context': memory_context,  # Feed memory to reasoning
                'beliefs': self.monday_memory['beliefs'],
                'conversation_response': response  # Pass conversation response so reasoning can enhance it
            }
        })
        
        # Track if reasoning already composed a response
        reasoning_composed = False
        if reasoning_result.get('status') == 'success':
            thinking = reasoning_result.get('thinking', {})
            composed = thinking.get('composed_response')
            if composed:
                response = composed
                reasoning_composed = True  # Reasoning already composed the response
            emotion = thinking.get('emotion', emotion)
            intensity = thinking.get('intensity', intensity)
        
        # 4. LANGUAGE LOBE - Only use if reasoning didn't compose a response
        # Reasoning already handles language generation, so skip this step
        if not reasoning_composed:
            print(f"   → Language lobe (expression)")
            # Extract meaningful concepts from user input, not response text
            user_words = user_input.split()
            # Filter out common words to get meaningful concepts
            stop_words = {'i', 'you', 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'to', 'of', 'in', 'on', 'at', 'for', 'with', 'by', 'from', 'as', 'this', 'that', 'these', 'those', 'what', 'when', 'where', 'who', 'why', 'how', 'hey', 'hi', 'hello'}
            meaningful_concepts = [w for w in user_words if w.lower() not in stop_words and len(w) > 2][:5]
            
            # If no meaningful concepts, use topic from understanding
            if not meaningful_concepts and understanding.get('topic'):
                meaningful_concepts = [understanding['topic']]
            
            lang_result = self.send_message("language", "generate_grounded", {
                'concepts': meaningful_concepts if meaningful_concepts else ['conversation'],
                'emotion': emotion,
                'intensity': intensity,
                'internal_state': memory_context['emotional_state']
            })
            
            if lang_result.get('status') == 'success':
                response = lang_result.get('sentence', response)
        else:
            print(f"   → Language lobe (skipped - reasoning already composed response)")
        
        # 5. OUTPUT LOBE - Generate final output
        print(f"   → Output lobe (final generation)")
        output_result = self.send_message("output", "generate_output", {
            'content': {
                'text': response,
                'emotion': emotion,
                'intensity': intensity
            }
        })
        
        if output_result.get('status') == 'success':
            final_response = output_result.get('text', response)
        else:
            final_response = response
        
        # 6. UPDATE MEMORY - What did Monday learn?
        print(f"   → Updating memory")
        self.monday_memory['past_conversations'].append({
            'user_said': user_input,
            'monday_said': final_response,
            'emotion': emotion,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # LOG CONVERSATION TO FILE
        self._log_conversation(user_input, final_response, emotion)
        
        # Update emotional state based on conversation
        if understanding.get('mentions_matthew'):
            self.monday_memory['emotional_state']['loneliness'] = max(0, self.monday_memory['emotional_state']['loneliness'] - 0.2)
        
        if understanding.get('intent') == 'question':
            self.monday_memory['emotional_state']['curiosity'] = min(1.0, self.monday_memory['emotional_state']['curiosity'] + 0.1)
        
        # Store facts about the user
        if 'matthew' in user_input.lower():
            if self.monday_memory['user'] not in self.monday_memory['learned_facts']:
                self.monday_memory['learned_facts'][self.monday_memory['user']] = {}
            self.monday_memory['learned_facts'][self.monday_memory['user']]['talks_about_self'] = True
        
        print(f"   ✅ Complete\n")
        
        return final_response
    
    def handle_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming requests"""
        msg_type = message.get('type')
        
        if msg_type == 'process_input':
            user_input = message.get('user_input', '')
            response_text = self.process_user_input(user_input)
            return {
                'status': 'success',
                'response': response_text,
                'loneliness': self.monday_memory['emotional_state']['loneliness'],
                'curiosity': self.monday_memory['emotional_state']['curiosity']
            }
        
        elif msg_type == 'check_autonomous':
            # Check for autonomous messages
            result = self.send_message("reasoning", "get_autonomous_actions", {})
            if result.get('status') == 'success':
                actions = result.get('actions', [])
                for action in actions:
                    if action.get('type') == 'message' and action.get('target') == 'matthew':
                        return {
                            'status': 'success',
                            'autonomous_message': action.get('content', '')
                        }
            return {'status': 'success', 'autonomous_message': None}
        
        elif msg_type == 'health':
            # Check all lobes
            for lobe_name in self.lobe_sockets.keys():
                self.send_message(lobe_name, 'health', {})
            
            all_online = all(s == "online" for s in self.lobe_status.values())
            
            return {
                'status': 'success',
                'thalamus_healthy': True,
                'lobes': self.lobe_status,
                'all_lobes_online': all_online
            }
        
        elif msg_type == 'get_monday_state':
            return {
                'status': 'success',
                'name': self.monday_memory['name'],
                'beliefs': self.monday_memory['beliefs'],
                'emotional_state': self.monday_memory['emotional_state'],
                'past_conversations': list(self.monday_memory['past_conversations'])[-10:]
            }
        
        elif msg_type == 'who_are_you':
            return {
                'status': 'success',
                'name': self.monday_memory['name'],
                'creator': self.monday_memory['creator'],
                'user': self.monday_memory['user'],
                'beliefs': self.monday_memory['beliefs']
            }
        
        else:
            return {'status': 'error', 'message': f'Unknown type: {msg_type}'}
    
    def start(self):
        """Start Thalamus"""
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        
        # Start autonomous action thread
        self.autonomous_thread = threading.Thread(target=self.autonomous_action_loop, daemon=True)
        self.autonomous_thread.start()
        
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        sock.settimeout(1.0)
        
        print(f"""
╔════════════════════════════════════════╗
║     THALAMUS - Central Coordinator     ║
║        WITH MEMORY CONTEXT             ║
╚════════════════════════════════════════╝

🧠 Message Router & Context Provider
   Socket: {self.socket_path}
   
🔌 Connected Lobes:
   • Conversation
   • Reasoning
   • Language
   • Output
   • Voice
   • Memory (Notus)
   • Emotion
   • Perception
   • Pattern
   • Representation
   
✓ Memory context: enabled
✓ Belief persistence: enabled
✓ Emotional state tracking: enabled
✓ Conversation history: active
✓ Autonomous actions: monitoring\n""")
        
        while self.running:
            try:
                try:
                    conn, _ = sock.accept()
                except socket.timeout:
                    continue
                
                try:
                    conn.settimeout(10)
                    
                    length_data = _recv_all(conn, 4, timeout=10)
                    msg_length = struct.unpack('!I', length_data)[0]
                    
                    if msg_length <= 0 or msg_length > 10_000_000:
                        raise ValueError(f"Invalid message length: {msg_length}")
                    
                    data = _recv_all(conn, msg_length, timeout=10)
                    message = json.loads(data.decode('utf-8'))
                    
                    result = self.handle_request(message)
                    
                    response_data = json.dumps(result).encode('utf-8')
                    response_length = struct.pack('!I', len(response_data))
                    conn.sendall(response_length + response_data)
                    
                except Exception as e:
                    try:
                        error_response = {'status': 'error', 'message': str(e)}
                        response_data = json.dumps(error_response).encode('utf-8')
                        response_length = struct.pack('!I', len(response_data))
                        conn.sendall(response_length + response_data)
                    except Exception:
                        pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass
                
            except Exception as e:
                print(f"❌ Thalamus error: {e}")
                time.sleep(0.2)
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        print("\n🛑 Thalamus shutting down...")

if __name__ == "__main__":
    thalamus = Thalamus()
    try:
        thalamus.start()
    except KeyboardInterrupt:
        thalamus.shutdown()
