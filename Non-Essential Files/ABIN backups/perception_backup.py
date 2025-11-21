#!/usr/bin/env python3
"""
Perception Lobe - Sensory Input Processing
Handles: Speech-to-text, text input, converts to concepts
"""

import socket
import struct
import json
import os
import threading
import queue
from typing import Dict, Any, Optional

class PerceptionLobe:
    """Perception system - processes all sensory input"""
    
    def __init__(self, socket_path="/tmp/perception.sock"):
        self.socket_path = socket_path
        self.running = True
        
        # Input queues
        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue()
        self.visual_queue = queue.Queue()
        
        # Speech-to-text engine (will be initialized when needed)
        self.stt_engine = None
        self.stt_available = False
        self.audio_thread = None
        
        # Visual processing
        self.vision_available = False
        self.camera = None
        self.visual_thread = None
        
        self._initialize_stt()
        self._start_autonomous_vision()
        self._start_autonomous_hearing()
        
    def _initialize_stt(self):
        """Initialize speech-to-text engine"""
        try:
            import speech_recognition as sr
            self.stt_engine = sr.Recognizer()
            self.stt_available = True
            print("✅ Speech-to-text engine initialized")
        except ImportError:
            print("⚠️  speech_recognition not available - voice input disabled")
            print("   Install with: pip install SpeechRecognition pyaudio")
            self.stt_available = False
    
    def _start_autonomous_vision(self):
        """Start autonomous vision processing - runs constantly"""
        try:
            import cv2
            self.camera = cv2.VideoCapture(0)
            if self.camera.isOpened():
                self.vision_available = True
                print("✅ Webcam initialized - autonomous vision active")
                
                # Start vision processing thread
                self.visual_thread = threading.Thread(target=self._vision_loop, daemon=True)
                self.visual_thread.start()
            else:
                print("⚠️  Webcam not available")
                self.vision_available = False
        except ImportError:
            print("⚠️  opencv-python not available - vision disabled")
            print("   Install with: pip install opencv-python")
            self.vision_available = False
    
    def _vision_loop(self):
        """Continuously process visual input"""
        import cv2
        import time
        
        while self.running:
            try:
                ret, frame = self.camera.read()
                if not ret:
                    time.sleep(1)
                    continue
                
                # Process frame
                visual_data = self._process_frame(frame)
                
                # Add to queue if significant
                if visual_data and visual_data.get('significant'):
                    self.visual_queue.put(visual_data)
                
                # Process every 2 seconds
                time.sleep(2)
                
            except Exception as e:
                print(f"❌ Vision loop error: {e}")
                time.sleep(5)
    
    def _process_frame(self, frame) -> Optional[Dict[str, Any]]:
        """Process a video frame"""
        import cv2
        
        height, width, channels = frame.shape
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        # Calculate brightness
        brightness = float(gray.mean())
        
        # Check if anything significant
        significant = len(faces) > 0 or brightness < 50 or brightness > 200
        
        visual_data = {
            'faces_detected': len(faces),
            'brightness': brightness,
            'resolution': f"{width}x{height}",
            'significant': significant,
            'timestamp': time.time()
        }
        
        return visual_data
    
    def _start_autonomous_hearing(self):
        """Start autonomous audio processing - runs constantly"""
        if not self.stt_available:
            print("⚠️  Audio input not available - hearing disabled")
            return
        
        print("✅ Microphone initialized - autonomous hearing active")
        
        # Start audio processing thread
        self.audio_thread = threading.Thread(target=self._hearing_loop, daemon=True)
        self.audio_thread.start()
    
    def _hearing_loop(self):
        """Continuously listen for audio"""
        import speech_recognition as sr
        import time
        
        while self.running:
            try:
                with sr.Microphone() as source:
                    # Quick adjustment for ambient noise
                    self.stt_engine.adjust_for_ambient_noise(source, duration=0.3)
                    
                    # Listen with timeout
                    try:
                        audio = self.stt_engine.listen(source, timeout=5, phrase_time_limit=10)
                        
                        # Convert to text
                        text = self.stt_engine.recognize_google(audio)
                        
                        # Process as text and queue
                        audio_data = self.process_text_input(text)
                        audio_data['source'] = 'audio'
                        audio_data['original_audio'] = True
                        self.audio_queue.put(audio_data)
                        
                        print(f"🎤 Heard: {text}")
                        
                    except sr.WaitTimeoutError:
                        # No speech detected, keep listening
                        pass
                    except sr.UnknownValueError:
                        # Could not understand, keep listening
                        pass
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"❌ Hearing loop error: {e}")
                time.sleep(5)
    
    def process_text_input(self, text: str) -> Dict[str, Any]:
        """Process text input into concepts"""
        # Basic text processing
        concepts = self._extract_concepts(text)
        
        return {
            'type': 'text_input',
            'raw_text': text,
            'concepts': concepts,
            'input_type': 'text'
        }
    
    def process_audio_input(self) -> Optional[Dict[str, Any]]:
        """Process audio input (speech-to-text)"""
        if not self.stt_available:
            return None
            
        try:
            import speech_recognition as sr
            
            # Listen for audio
            with sr.Microphone() as source:
                print("🎤 Listening...")
                self.stt_engine.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.stt_engine.listen(source, timeout=5, phrase_time_limit=10)
            
            # Convert to text
            print("🔄 Processing audio...")
            text = self.stt_engine.recognize_google(audio)
            print(f"📝 Heard: {text}")
            
            # Process as text
            return self.process_text_input(text)
            
        except sr.WaitTimeoutError:
            print("⏱️  No speech detected")
            return None
        except sr.UnknownValueError:
            print("❓ Could not understand audio")
            return None
        except Exception as e:
            print(f"❌ Audio processing error: {e}")
            return None
    
    def process_visual_input(self) -> Optional[Dict[str, Any]]:
        """Process visual input from webcam"""
        if not self.vision_available:
            return None
        
        try:
            import cv2
            
            # Capture frame
            ret, frame = self.camera.read()
            if not ret:
                print("❌ Could not read from webcam")
                return None
            
            print("📷 Processing visual input...")
            
            # Basic image analysis
            height, width, channels = frame.shape
            
            # Convert to grayscale for analysis
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Detect faces (basic object detection)
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            
            # Extract visual concepts
            visual_concepts = {
                'type': 'visual_input',
                'resolution': f"{width}x{height}",
                'faces_detected': len(faces),
                'brightness': float(gray.mean()),
                'objects': []
            }
            
            if len(faces) > 0:
                visual_concepts['objects'].append('face')
                print(f"👤 Detected {len(faces)} face(s)")
            
            return {
                'type': 'visual_input',
                'raw_data': 'frame_data',  # Don't send actual frame data
                'concepts': visual_concepts,
                'input_type': 'vision'
            }
            
        except Exception as e:
            print(f"❌ Visual processing error: {e}")
            return None
    
    def _extract_concepts(self, text: str) -> Dict[str, Any]:
        """Extract concepts from text"""
        # Basic concept extraction
        text_lower = text.lower()
        
        concepts = {
            'words': text.split(),
            'length': len(text),
            'questions': [],
            'emotions': [],
            'entities': []
        }
        
        # Detect questions
        question_words = ['what', 'why', 'how', 'when', 'where', 'who', 'which']
        for word in question_words:
            if word in text_lower:
                concepts['questions'].append(word)
        
        # Detect emotional words
        emotion_words = {
            'happy': ['happy', 'joy', 'great', 'wonderful', 'amazing'],
            'sad': ['sad', 'unhappy', 'depressed', 'down'],
            'angry': ['angry', 'mad', 'furious', 'hate'],
            'excited': ['excited', 'thrilled', 'amazing'],
            'worried': ['worried', 'anxious', 'concerned', 'scared']
        }
        
        for emotion, words in emotion_words.items():
            for word in words:
                if word in text_lower:
                    concepts['emotions'].append(emotion)
                    break
        
        # Basic entity detection (names, places)
        words = text.split()
        for i, word in enumerate(words):
            if word[0].isupper() and i > 0:  # Capitalized word not at start
                concepts['entities'].append(word)
        
        return concepts
    
    def start(self):
        """Start perception lobe as independent process"""
        # Remove old socket if exists
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
            
        # Create Unix socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(5)
        
        print(f"👁️  Perception Lobe: Online at {self.socket_path}")
        if self.stt_available:
            print("   🎤 Voice input: enabled")
        else:
            print("   🎤 Voice input: disabled")
        if self.vision_available:
            print("   📷 Vision input: enabled")
        else:
            print("   📷 Vision input: disabled")
        print("   ⌨️  Text input: enabled")
        
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
                print(f"❌ Perception error: {e}")
                try:
                    conn.close()
                except:
                    pass
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming message"""
        msg_type = message.get('type')
        
        if msg_type == 'process_text':
            # Process text input
            text = message.get('text')
            result = self.process_text_input(text)
            return {'status': 'success', 'perception': result}
            
        elif msg_type == 'listen_audio':
            # Listen for audio input
            result = self.process_audio_input()
            if result:
                return {'status': 'success', 'perception': result}
            else:
                return {'status': 'no_input', 'message': 'No audio detected'}
                
        elif msg_type == 'capture_visual':
            # Capture visual input from webcam
            result = self.process_visual_input()
            if result:
                return {'status': 'success', 'perception': result}
            else:
                return {'status': 'no_input', 'message': 'No visual input'}
                
        elif msg_type == 'get_status':
            # Get perception system status
            return {
                'status': 'success',
                'stt_available': self.stt_available,
                'vision_available': self.vision_available,
                'text_input': True
            }
            
        else:
            return {'status': 'error', 'message': f'Unknown message type: {msg_type}'}
    
    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        if self.camera:
            try:
                self.camera.release()
            except:
                pass
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)

if __name__ == "__main__":
    lobe = PerceptionLobe()
    try:
        lobe.start()
    except KeyboardInterrupt:
        print("\n🛑 Perception lobe shutting down...")
        lobe.shutdown()

