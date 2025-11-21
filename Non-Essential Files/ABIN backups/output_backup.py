#!/usr/bin/env python3
"""
Output Lobe - Expression and Communication
Handles: Text-to-speech, text output, voice configuration
"""

import socket
import struct
import json
import os
from typing import Dict, Any, Optional

class OutputLobe:
    """Output system - handles all expression and communication"""
    
    def __init__(self, socket_path="/tmp/output.sock"):
        self.socket_path = socket_path
        self.running = True
        
        # Text-to-speech engine
        self.tts_engine = None
        self.tts_available = False
        
        # Voice configuration
        self.voice_config = {
            'enabled': False,
            'rate': 150,
            'volume': 1.0,
            'voice_id': None
        }
        
        # Sentence building components
        self.connectors = ['and', 'but', 'so', 'because', 'also', 'however', 'therefore']
        self.acknowledgments = ['I see', 'I understand', 'Got it', 'Okay', 'Right']
        self.transitions = ['by the way', 'also', 'additionally', 'furthermore']
        
        self._initialize_tts()
        
    def _initialize_tts(self):
        """Initialize text-to-speech engine"""
        try:
            import pyttsx3
            self.tts_engine = pyttsx3.init()
            self.tts_available = True
            
            # Configure voice
            self.tts_engine.setProperty('rate', self.voice_config['rate'])
            self.tts_engine.setProperty('volume', self.voice_config['volume'])
            
            print("✅ Text-to-speech engine initialized")
            
            # List available voices
            voices = self.tts_engine.getProperty('voices')
            print(f"   Available voices: {len(voices)}")
            
        except ImportError:
            print("⚠️  pyttsx3 not available - voice output disabled")
            print("   Install with: pip install pyttsx3")
            self.tts_available = False
        except Exception as e:
            print(f"⚠️  TTS initialization error: {e}")
            self.tts_available = False
    
    def speak(self, text: str) -> bool:
        """Speak text using TTS"""
        if not self.tts_available or not self.voice_config['enabled']:
            # Voice disabled - just return text
            return False
            
        try:
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()
            return True
        except Exception as e:
            print(f"❌ TTS error: {e}")
            return False
    
    def generate_text_output(self, content: Dict[str, Any]) -> str:
        """Generate formatted text output"""
        output_type = content.get('type', 'response')
        
        if output_type == 'response':
            # Standard response
            text = content.get('text', '')
            emotion = content.get('emotion')
            
            # Add emotional context if present
            if emotion:
                return f"[{emotion}] {text}"
            return text
            
        elif output_type == 'thought':
            # Internal thought
            text = content.get('text', '')
            return f"💭 {text}"
            
        elif output_type == 'action':
            # Action description
            text = content.get('text', '')
            return f"*{text}*"
            
        else:
            return content.get('text', '')
    
    def format_output(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Format output with emotion and personality"""
        text = content.get('text', '')
        emotion = content.get('emotion')
        intensity = content.get('intensity', 0.5)
        
        # Apply emotional formatting
        if emotion and intensity > 0.6:
            # High intensity - add emphasis
            if emotion in ['excited', 'happy']:
                text = f"{text}!"
            elif emotion in ['worried', 'scared']:
                text = f"{text}..."
            elif emotion == 'angry':
                text = text.upper() if intensity > 0.8 else text
        
        return {
            'text': text,
            'emotion': emotion,
            'intensity': intensity,
            'formatted': True
        }
    
    def start(self):
        """Start output lobe as independent process"""
        # Remove old socket if exists
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
            
        # Create Unix socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        
        print(f"🗣️  Output Lobe: Online at {self.socket_path}")
        if self.tts_available:
            if self.voice_config['enabled']:
                print("   🔊 Voice output: enabled")
            else:
                print("   🔊 Voice output: disabled (waiting for Shadowheart voice)")
        else:
            print("   🔊 Voice output: not available")
        print("   📝 Text output: enabled")
        
        while self.running:
            try:
                # Accept connection from Thalamus
                conn, _ = sock.accept()
                
                # Read message length (4 bytes)
                length_data = conn.recv(4)
                if not length_data:
                    conn.close()
                    continue
                    
                msg_length = struct.unpack('!I', length_data)[0]
                
                # Read full message
                data = b''
                while len(data) < msg_length:
                    chunk = conn.recv(min(msg_length - len(data), 4096))
                    if not chunk:
                        break
                    data += chunk
                
                # Parse message
                message = json.loads(data.decode('utf-8'))
                
                # Process based on message type
                result = self.process_message(message)
                
                # Send response
                response_data = json.dumps(result).encode('utf-8')
                response_length = struct.pack('!I', len(response_data))
                conn.send(response_length + response_data)
                conn.close()
                
            except Exception as e:
                print(f"❌ Output error: {e}")
                try:
                    conn.close()
                except:
                    pass
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming message"""
        msg_type = message.get('type')
        
        if msg_type == 'generate_output':
            # Generate output from content
            content = message.get('content', {})
            formatted = self.format_output(content)
            text_output = self.generate_text_output(formatted)
            
            # Speak if voice enabled
            spoke = False
            if self.voice_config['enabled']:
                spoke = self.speak(text_output)
            
            return {
                'status': 'success',
                'text': text_output,
                'spoke': spoke,
                'formatted': formatted
            }
            
        elif msg_type == 'speak':
            # Just speak the text
            text = message.get('text', '')
            spoke = self.speak(text)
            return {'status': 'success', 'spoke': spoke}
            
        elif msg_type == 'configure_voice':
            # Configure voice settings
            if 'enabled' in message:
                self.voice_config['enabled'] = message['enabled']
            if 'rate' in message:
                self.voice_config['rate'] = message['rate']
                if self.tts_engine:
                    self.tts_engine.setProperty('rate', message['rate'])
            if 'volume' in message:
                self.voice_config['volume'] = message['volume']
                if self.tts_engine:
                    self.tts_engine.setProperty('volume', message['volume'])
            
            return {'status': 'success', 'config': self.voice_config}
            
        elif msg_type == 'get_status':
            # Get output system status
            return {
                'status': 'success',
                'tts_available': self.tts_available,
                'voice_enabled': self.voice_config['enabled'],
                'text_output': True
            }
            
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        if self.tts_engine:
            try:
                self.tts_engine.stop()
            except:
                pass
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

if __name__ == "__main__":
    lobe = OutputLobe()
    try:
        lobe.start()
    except KeyboardInterrupt:
        print("\n🛑 Output lobe shutting down...")
        lobe.shutdown()

