import tkinter as tk
from tkinter import scrolledtext, ttk
import threading
import queue
import json
from datetime import datetime


class USSArizonaBattleship:
    """
    Main data structure for managing communication between components.
    Handles message routing and state management.
    """
    def __init__(self):
        self.message_queue = queue.Queue()
        self.response_queue = queue.Queue()
        self.emotional_state = "neutral"
        self.conversation_history = []
        self.is_active = True
        
    def send_message(self, message, sender="user"):
        """Add message to queue for processing"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg_data = {
            "content": message,
            "sender": sender,
            "timestamp": timestamp
        }
        self.message_queue.put(msg_data)
        self.conversation_history.append(msg_data)
        
    def get_response(self, timeout=0.1):
        """Retrieve response from queue if available"""
        try:
            return self.response_queue.get(timeout=timeout)
        except queue.Empty:
            return None
            
    def update_emotional_state(self, state):
        """Update the current emotional state"""
        self.emotional_state = state
        
    def get_emotional_state(self):
        """Get current emotional state"""
        return self.emotional_state
        
    def shutdown(self):
        """Gracefully shutdown the system"""
        self.is_active = False


class BrainWorker(threading.Thread):
    """
    Worker thread that processes messages and generates responses.
    Handles the AI/brain processing in the background.
    """
    def __init__(self, battleship):
        super().__init__(daemon=True)
        self.battleship = battleship
        self.running = True
        self.processing = False
        
    def run(self):
        """Main worker loop"""
        while self.running and self.battleship.is_active:
            try:
                # Check for new messages to process
                if not self.battleship.message_queue.empty():
                    msg_data = self.battleship.message_queue.get(timeout=0.1)
                    self.process_message(msg_data)
            except queue.Empty:
                pass
            except Exception as e:
                print(f"Error in BrainWorker: {e}")
                
    def process_message(self, msg_data):
        """Process incoming message and generate response"""
        self.processing = True
        message = msg_data.get("content", "")
        
        # Send to perception system
        perception_result = self.send_to_perception(message)
        
        # Generate response based on perception
        response = self.generate_response(message, perception_result)
        
        # Update emotional state based on content
        self.update_emotion(message, response)
        
        # Send response back
        response_data = {
            "content": response,
            "sender": "Monday",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "emotional_state": self.battleship.get_emotional_state()
        }
        self.battleship.response_queue.put(response_data)
        self.processing = False
        
    def send_to_perception(self, message):
        """
        Send message to perception system for analysis.
        Returns analyzed perception data including sentiment, intent, and context.
        """
        perception_data = {
            "sentiment": self.analyze_sentiment(message),
            "intent": self.detect_intent(message),
            "keywords": self.extract_keywords(message),
            "context": self.analyze_context(message)
        }
        return perception_data
        
    def analyze_sentiment(self, message):
        """Analyze sentiment of the message"""
        message_lower = message.lower()
        if any(word in message_lower for word in ["happy", "great", "awesome", "love", "good"]):
            return "positive"
        elif any(word in message_lower for word in ["sad", "bad", "hate", "terrible", "angry"]):
            return "negative"
        else:
            return "neutral"
            
    def detect_intent(self, message):
        """Detect user intent from message"""
        message_lower = message.lower()
        if "?" in message:
            return "question"
        elif any(word in message_lower for word in ["help", "assist", "support"]):
            return "request_help"
        elif any(word in message_lower for word in ["hello", "hi", "hey"]):
            return "greeting"
        else:
            return "statement"
            
    def extract_keywords(self, message):
        """Extract important keywords from message"""
        # Simple keyword extraction
        words = message.split()
        return [w for w in words if len(w) > 4][:5]
        
    def analyze_context(self, message):
        """Analyze conversational context"""
        return {
            "length": len(message),
            "word_count": len(message.split()),
            "has_question": "?" in message
        }
        
    def generate_response(self, message, perception):
        """Generate appropriate response based on message and perception"""
        intent = perception.get("intent", "statement")
        sentiment = perception.get("sentiment", "neutral")
        
        if intent == "greeting":
            return "Hello! How can I help you today?"
        elif intent == "question":
            return f"That's an interesting question. Let me think about that..."
        elif intent == "request_help":
            return "I'm here to help! What do you need assistance with?"
        else:
            if sentiment == "positive":
                return "I'm glad to hear that! Is there anything else you'd like to discuss?"
            elif sentiment == "negative":
                return "I understand. How can I help make things better?"
            else:
                return "I see. Tell me more about that."
                
    def update_emotion(self, message, response):
        """Update emotional state based on conversation"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ["happy", "joy", "excited"]):
            self.battleship.update_emotional_state("happy")
        elif any(word in message_lower for word in ["sad", "down", "depressed"]):
            self.battleship.update_emotional_state("concerned")
        elif any(word in message_lower for word in ["angry", "mad", "furious"]):
            self.battleship.update_emotional_state("calm")
        else:
            self.battleship.update_emotional_state("neutral")
            
    def stop(self):
        """Stop the worker thread"""
        self.running = False


class MondarInterface:
    """
    Main GUI interface for Monday AI assistant.
    Provides chat display, input controls, and emotional state monitoring.
    """
    def __init__(self, root):
        self.root = root
        self.root.title("Monday - AI Assistant Interface")
        self.root.geometry("800x600")
        self.root.configure(bg="#2b2b2b")
        
        # Initialize battleship and worker
        self.battleship = USSArizonaBattleship()
        self.brain_worker = BrainWorker(self.battleship)
        self.brain_worker.start()
        
        # Setup GUI components
        self.setup_ui()
        
        # Start response polling
        self.poll_responses()
        
    def setup_ui(self):
        """Setup all UI components"""
        # Main container
        main_frame = tk.Frame(self.root, bg="#2b2b2b")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Title label
        title_label = tk.Label(
            main_frame,
            text="🤖 Monday AI Assistant",
            font=("Arial", 18, "bold"),
            bg="#2b2b2b",
            fg="#00ff00"
        )
        title_label.pack(pady=(0, 10))
        
        # Emotional state display
        self.emotion_frame = tk.Frame(main_frame, bg="#1a1a1a", relief=tk.RAISED, borderwidth=2)
        self.emotion_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(
            self.emotion_frame,
            text="Emotional State:",
            font=("Arial", 10, "bold"),
            bg="#1a1a1a",
            fg="#ffffff"
        ).pack(side=tk.LEFT, padx=10, pady=5)
        
        self.emotion_label = tk.Label(
            self.emotion_frame,
            text="😐 Neutral",
            font=("Arial", 12, "bold"),
            bg="#1a1a1a",
            fg="#ffaa00"
        )
        self.emotion_label.pack(side=tk.LEFT, padx=10, pady=5)
        
        # Chat display area
        chat_frame = tk.Frame(main_frame, bg="#1a1a1a")
        chat_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        tk.Label(
            chat_frame,
            text="Conversation",
            font=("Arial", 11, "bold"),
            bg="#1a1a1a",
            fg="#00ccff"
        ).pack(anchor=tk.W, padx=5, pady=5)
        
        self.chat_display = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg="#1e1e1e",
            fg="#00ff00",
            insertbackground="#00ff00",
            state=tk.DISABLED,
            relief=tk.FLAT,
            padx=10,
            pady=10
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        
        # Configure text tags for different message types
        self.chat_display.tag_config("user", foreground="#00ccff")
        self.chat_display.tag_config("monday", foreground="#00ff00")
        self.chat_display.tag_config("timestamp", foreground="#888888")
        self.chat_display.tag_config("system", foreground="#ffaa00")
        
        # Input area
        input_frame = tk.Frame(main_frame, bg="#2b2b2b")
        input_frame.pack(fill=tk.X)
        
        tk.Label(
            input_frame,
            text="Your Message:",
            font=("Arial", 10),
            bg="#2b2b2b",
            fg="#ffffff"
        ).pack(anchor=tk.W, pady=(0, 5))
        
        # Input field and send button container
        entry_frame = tk.Frame(input_frame, bg="#2b2b2b")
        entry_frame.pack(fill=tk.X)
        
        self.input_field = tk.Entry(
            entry_frame,
            font=("Arial", 11),
            bg="#1e1e1e",
            fg="#00ff00",
            insertbackground="#00ff00",
            relief=tk.FLAT,
            borderwidth=2
        )
        self.input_field.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        self.input_field.bind("<Return>", lambda e: self.send_message())
        
        self.send_button = tk.Button(
            entry_frame,
            text="📤 Send",
            font=("Arial", 11, "bold"),
            bg="#00aa00",
            fg="#ffffff",
            activebackground="#00ff00",
            activeforeground="#000000",
            relief=tk.RAISED,
            borderwidth=2,
            padx=20,
            pady=5,
            cursor="hand2",
            command=self.send_message
        )
        self.send_button.pack(side=tk.RIGHT)
        
        # Add welcome message
        self.add_system_message("Monday AI Assistant initialized. How can I help you today?")
        
    def send_message(self):
        """Send user message to the brain worker"""
        message = self.input_field.get().strip()
        if not message:
            return
            
        # Display user message
        self.display_message(message, "user")
        
        # Send to battleship for processing
        self.battleship.send_message(message, sender="user")
        
        # Clear input field
        self.input_field.delete(0, tk.END)
        
    def display_message(self, message, sender):
        """Display message in chat window"""
        self.chat_display.config(state=tk.NORMAL)
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if sender == "user":
            self.chat_display.insert(tk.END, f"[{timestamp}] ", "timestamp")
            self.chat_display.insert(tk.END, "You: ", "user")
            self.chat_display.insert(tk.END, f"{message}\n\n")
        elif sender == "Monday":
            self.chat_display.insert(tk.END, f"[{timestamp}] ", "timestamp")
            self.chat_display.insert(tk.END, "Monday: ", "monday")
            self.chat_display.insert(tk.END, f"{message}\n\n")
            
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)
        
    def add_system_message(self, message):
        """Add system message to chat"""
        self.chat_display.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.chat_display.insert(tk.END, f"[{timestamp}] ", "timestamp")
        self.chat_display.insert(tk.END, "SYSTEM: ", "system")
        self.chat_display.insert(tk.END, f"{message}\n\n")
        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)
        
    def update_emotional_display(self, emotion):
        """Update the emotional state display"""
        emotion_map = {
            "neutral": "😐 Neutral",
            "happy": "😊 Happy",
            "concerned": "😟 Concerned",
            "calm": "😌 Calm",
            "curious": "🤔 Curious",
            "excited": "😃 Excited"
        }
        
        display_text = emotion_map.get(emotion, f"❓ {emotion.capitalize()}")
        self.emotion_label.config(text=display_text)
        
    def poll_responses(self):
        """Poll for responses from brain worker"""
        response_data = self.battleship.get_response()
        
        if response_data:
            # Display response
            self.display_message(response_data["content"], "Monday")
            
            # Update emotional state
            emotional_state = response_data.get("emotional_state", "neutral")
            self.update_emotional_display(emotional_state)
            
        # Continue polling
        self.root.after(100, self.poll_responses)
        
    def on_closing(self):
        """Handle window closing"""
        self.battleship.shutdown()
        self.brain_worker.stop()
        self.root.destroy()


def main():
    """
    Main entry point for the Monday AI Assistant interface.
    Initializes the GUI and starts the application.
    """
    root = tk.Tk()
    app = MondarInterface(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
