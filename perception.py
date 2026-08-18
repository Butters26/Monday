#!/usr/bin/env python3
"""
Perception Lobe - Sensory Input Processing
Handles: Speech-to-text, text input, converts to concepts
"""

import json
import os
import threading
import queue
import time
import sys
from typing import Dict, Any, Optional
from thalamus import get_thalamus

class PerceptionLobe:
    """Perception system - processes all sensory input"""
    
    def __init__(self, thalamus=None, autonomous: bool = True):
        self.running = True
        self.autonomous = autonomous
        
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
        
        # Direct reference to Thalamus (NO SOCKETS)
        self.thalamus = thalamus or get_thalamus()
        
        # Track concepts we've seen before (for novelty detection)
        self.seen_concepts = set()
        self.seen_entities = set()
        
        # Register immediately so GUI can access it right away
        self._register_with_thalamus()
        
        self._initialize_stt()
        self._initialize_vision()
        if self.autonomous:
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
    
    def _initialize_vision(self):
        """Initialize webcam availability."""
        try:
            import cv2
            self.camera = cv2.VideoCapture(0)
            if self.camera.isOpened():
                self.vision_available = True
                print("✅ Webcam initialized")
            else:
                print("⚠️  Webcam not available")
                self.vision_available = False
        except ImportError:
            print("⚠️  opencv-python not available - vision disabled")
            print("   Install with: pip install opencv-python")
            self.vision_available = False

    def _start_autonomous_vision(self):
        """Start autonomous vision processing - runs constantly"""
        if not self.vision_available:
            return
        print("👁️  Autonomous vision active")
        self.visual_thread = threading.Thread(target=self._vision_loop, daemon=True)
        self.visual_thread.start()
    
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
        
        # Start audio queue processor thread - reads queue and sends to Thalamus
        self.audio_processor_thread = threading.Thread(target=self._audio_queue_processor, daemon=True)
        self.audio_processor_thread.start()
    
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
                        audio_data['confidence'] = 0.85  # Speech-to-text confidence (lower than direct text)
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
    
    def _audio_queue_processor(self):
        """Process audio queue and send to Thalamus using persistent connection"""
        while self.running:
            try:
                # Get audio from queue (blocking with timeout)
                try:
                    audio_data = self.audio_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                
                # Send to Reasoning via Thalamus with standardized format
                result = self.thalamus.send_message(
                    destination='reasoning',
                    msg_type='process_perception',
                    content={
                        'text': audio_data.get('text', ''),
                        'confidence': audio_data.get('confidence', 0.85),
                        'intent_hints': audio_data.get('intent_hints', []),
                        'entities': audio_data.get('entities', []),
                        'source': 'audio',
                        'timestamp': audio_data.get('timestamp')
                    },
                    source='perception'
                )
                
                if result and result.get('status') == 'success':
                    print(f"📤 Sent audio to Reasoning: {audio_data.get('text', '')[:50]}")
                    
            except Exception as e:
                print(f"❌ Audio queue processor error: {e}")
                time.sleep(1)
    
    def _register_with_thalamus(self):
        """Register with Thalamus - DIRECT FUNCTION CALL (NO SOCKETS)"""
        try:
            result = self.thalamus.register_lobe('perception', self)
            if result.get('status') == 'success':
                print("✅ Perception registered with Thalamus (direct function calls)")
                return True
            return False
        except Exception as e:
            print(f"⚠️  Failed to register with Thalamus: {e}")
            return False
    
    def _send_to_thalamus(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send message to Thalamus - DIRECT FUNCTION CALL (NO SOCKETS)"""
        try:
            msg_type = message.get('type')
            if msg_type == 'route_message':
                destination = message.get('destination')
                route_msg_type = message.get('msg_type')
                content = message.get('content', {})
                return self.thalamus.send_message(destination, route_msg_type, content)
            elif msg_type == 'broadcast_message':
                destinations = message.get('destinations', [])
                broadcast_msg_type = message.get('msg_type')
                broadcast_content = message.get('content', {})
                return self.thalamus.broadcast_message(destinations, broadcast_msg_type, broadcast_content)
            else:
                return self.thalamus.handle_request(message)
        except Exception:
            return None
    
    def process_text_input(self, text: str) -> Dict[str, Any]:
        """Process text input into concepts and return standardized format"""
        # Extract concepts from text
        concepts = self._extract_concepts(text)
        
        # Detect novelty in the input
        self._detect_and_signal_novelty(text, concepts)
        
        return {
            'type': 'text_input',
            'raw_text': text,
            'text': text,  # Standardized key
            'confidence': 0.95,  # High confidence for direct text input
            'concepts': concepts,
            'intent_hints': concepts.get('questions', []),
            'entities': concepts.get('entities', []),
            'input_type': 'text',
            'timestamp': time.time()
        }
    
    def _detect_and_signal_novelty(self, text: str, concepts: Dict[str, Any]):
        """Detect novel concepts in the input and signal Novelty Lobe"""
        # Check for novel entities (proper nouns, names, places)
        novel_entities = []
        for entity in concepts.get('entities', []):
            if entity not in self.seen_entities:
                novel_entities.append(entity)
                self.seen_entities.add(entity)
        
        # Check for novel concepts/words
        novel_concepts = []
        for word in concepts.get('words', []):
            word_lower = word.lower()
            # Consider it novel if it's longer than 3 chars and not commonly seen
            if len(word_lower) > 3 and word_lower not in self.seen_concepts:
                # Skip common words
                common = {'what', 'this', 'that', 'have', 'from', 'with', 'will', 'know', 'think', 'about', 'which'}
                if word_lower not in common:
                    novel_concepts.append(word)
                    self.seen_concepts.add(word_lower)
        
        # Check for novel questions (if present)
        novel_questions = bool(concepts.get('questions', []))
        
        # Send novelty signal if we found novel elements
        if novel_entities or novel_concepts or (novel_questions and len(text) > 20):
            try:
                novelty_message = {
                    'type': 'novelty_signal',
                    'source': 'perception',
                    'stimulus': text,
                    'stimulus_type': 'text_input',
                    'novel_entities': novel_entities,
                    'novel_concepts': novel_concepts,
                    'has_novel_questions': novel_questions,
                    'confidence': min(0.95, (len(novel_entities) * 0.3 + len(novel_concepts) * 0.2 + (0.15 if novel_questions else 0)))
                }
                
                # Send to Novelty Lobe
                result = self.thalamus.send_message(
                    destination='novelty',
                    msg_type='novelty_signal',
                    content=novelty_message,
                    source='perception'
                )
                
                if result and result.get('status') == 'success':
                    print(f"✨ Detected novelty: {len(novel_entities)} entities, {len(novel_concepts)} concepts")
                    
            except Exception as e:
                # Novelty Lobe might not be available, that's OK
                pass
    
    def _broadcast_to_lobes(self, perception_data: Dict[str, Any]):
        """Broadcast perception data to ALL lobes through Thalamus - DIRECT FUNCTION CALL"""
        # Use Thalamus broadcast_message to send to ALL lobes at once
        destinations = ['reasoning', 'emotion', 'pattern', 'notus', 'representation', 'language', 'output', 'voice', 'conversation']
        self.thalamus.broadcast_message(destinations, 'perception_input', {
            'perception_data': perception_data
        })
    
    def process_audio_input(self) -> Optional[Dict[str, Any]]:
        """Process audio input (speech-to-text) - returns standardized format"""
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
            
            # Process as text and return standardized format
            result = self.process_text_input(text)
            result['source'] = 'audio'
            result['confidence'] = 0.85  # Speech-to-text confidence
            return result
            
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
            self._initialize_vision()
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
        """Extract concepts with proper language understanding"""
        # Query Notus for known concepts/entities
        known_concepts = []
        try:
            notus_concepts = self._send_to_thalamus({
                'type': 'route_message',
                'destination': 'notus',
                'msg_type': 'query',
                'content': {'type': 'get_known_concepts', 'text': text}
            })
            if notus_concepts and notus_concepts.get('status') == 'success':
                known_concepts = notus_concepts.get('concepts', [])
        except Exception:
            pass
        
        text_lower = text.lower()
        words = text.split()
        
        # Ensure we always have meaningful words, even for simple inputs
        meaningful_words = []
        for word in words:
            word_clean = word.lower().strip('.,!?;:')
            if len(word_clean) >= 2:  # Include short words like "hi", "I", "am"
                meaningful_words.append(word_clean)
        
        # If no meaningful words extracted, use the original words
        if not meaningful_words:
            meaningful_words = [w.lower().strip('.,!?;:') for w in words if w.strip()]
        
        concepts = {
            'words': meaningful_words,  # Use meaningful_words instead of raw words
            'length': len(text),
            'questions': [],
            'emotions': [],
            'entities': [],
            'negations': [],
            'subject': None,
            'verb': None,
            'object': None,
            'sentiment': 'neutral'
        }
        
        # Detect questions
        question_words = ['what', 'why', 'how', 'when', 'where', 'who', 'which']
        for word in question_words:
            if word in text_lower:
                concepts['questions'].append(word)
        
        # Detect negations (not, never, no, etc)
        negation_words = ['not', 'never', 'no', "n't", 'dont', "don't", 'cant', "can't", 'wont', "won't"]
        for i, word in enumerate(words):
            word_lower = word.lower()
            if word_lower in negation_words:
                # Track what's being negated
                if i + 1 < len(words):
                    negated_word = words[i+1]
                    concepts['negations'].append(negated_word.lower())
        
        # Detect emotions with negation awareness
        emotion_words = {
            'happy': ['happy', 'joy', 'great', 'wonderful', 'amazing', 'glad', 'pleased'],
            'sad': ['sad', 'unhappy', 'depressed', 'down', 'miserable', 'blue'],
            'angry': ['angry', 'mad', 'furious', 'hate', 'pissed'],
            'excited': ['excited', 'thrilled', 'pumped', 'enthusiastic'],
            'worried': ['worried', 'anxious', 'concerned', 'scared', 'nervous']
        }
        
        for emotion, emotion_word_list in emotion_words.items():
            for emo_word in emotion_word_list:
                if emo_word in text_lower:
                    # Check if negated
                    if emo_word in concepts['negations']:
                        # Inverted emotion
                        if emotion == 'happy':
                            concepts['emotions'].append('sad')
                        elif emotion == 'sad':
                            concepts['emotions'].append('happy')
                        # Don't add the negated emotion
                    else:
                        concepts['emotions'].append(emotion)
                    break
        
        # Simple subject-verb-object extraction
        if len(words) >= 3:
            # Very basic SVO
            concepts['subject'] = words[0]
            # Look for common verbs
            common_verbs = ['is', 'are', 'was', 'were', 'feel', 'think', 'want', 'need', 'like', 'love', 'hate']
            for i, word in enumerate(words):
                if word.lower() in common_verbs:
                    concepts['verb'] = word
                    if i + 1 < len(words):
                        concepts['object'] = ' '.join(words[i+1:])
                    break
        
        # Sentiment analysis
        positive_words = ['good', 'great', 'wonderful', 'amazing', 'love', 'like', 'happy', 'excellent']
        negative_words = ['bad', 'terrible', 'awful', 'hate', 'dislike', 'sad', 'horrible']
        
        pos_count = sum(1 for w in text_lower.split() if w in positive_words and w not in concepts['negations'])
        neg_count = sum(1 for w in text_lower.split() if w in negative_words and w not in concepts['negations'])
        
        if pos_count > neg_count:
            concepts['sentiment'] = 'positive'
        elif neg_count > pos_count:
            concepts['sentiment'] = 'negative'
        
        # Entity detection
        for i, word in enumerate(words):
            if len(word) > 1 and word[0].isupper() and i > 0:
                concepts['entities'].append(word)
        
        return concepts
    
    def start(self):
        """Start perception - register with Thalamus (NO SOCKETS)"""
        print(f"👁️  Perception Lobe: Registering with Thalamus...")
        if self.stt_available:
            print("   🎤 Voice input: enabled")
        else:
            print("   🎤 Voice input: disabled")
        if self.vision_available:
            print("   📷 Vision input: enabled")
        else:
            print("   📷 Vision input: disabled")
        print("   ⌨️  Text input: enabled")
        print("   Communication: Direct function calls (NO SOCKETS)")
        
        # Already registered in __init__, but verify
        if 'perception' not in self.thalamus.lobe_handlers:
            if not self._register_with_thalamus():
                print("❌ Failed to register with Thalamus")
                return
        
        # Keep running (Thalamus calls us directly, no listening loop needed)
        while self.running:
            time.sleep(0.1)
    
    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming message"""
        msg_type = message.get('type')
        
        # FIX: add health probe
        if msg_type == 'health':
            return {'status': 'success', 'healthy': True, 'pid': os.getpid()}
        
        if msg_type == 'process_text' or msg_type == 'user_input':
            # Process text input (from GUI or other sources)
            text = message.get('text') or message.get('user_input', '')
            result = self.process_text_input(text)
            
            # Return standardized perception output
            return {
                'status': 'success',
                'content': result  # Thalamus will transform this
            }
            
        elif msg_type == 'listen_audio':
            # Listen for audio input
            result = self.process_audio_input()
            if result:
                return {
                    'status': 'success',
                    'content': result  # Thalamus will transform this
                }
            else:
                return {'status': 'no_input', 'message': 'No audio detected'}
                
        elif msg_type == 'capture_visual':
            # Capture visual input from webcam
            result = self.process_visual_input()
            if result:
                return {
                    'status': 'success',
                    'content': result  # Thalamus will transform this
                }
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
            except Exception:
                pass
        # No sockets to close

if __name__ == "__main__":
    lobe = PerceptionLobe()
    try:
        lobe.start()
    except KeyboardInterrupt:
        print("\n🛑 Perception lobe shutting down...")
        lobe.shutdown()
