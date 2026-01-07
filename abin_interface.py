#!/usr/bin/env python3
"""
Monday Communication Interface
With detailed USS Arizona battleship visualization
"""

import sys
import os
import json
import time
import math
from typing import Dict, Any, Optional, List
from thalamus import get_thalamus
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QTextEdit, QLineEdit, QPushButton,
                              QLabel, QFrame, QScrollArea, QGraphicsView, 
                              QGraphicsScene, QGraphicsPolygonItem, QGraphicsRectItem,
                              QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsPathItem)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPointF, QRectF
from PyQt5.QtGui import (QColor, QFont, QPainter, QBrush, QPen, QLinearGradient,
                         QPolygonF, QPainterPath, QRadialGradient, QPixmap)

# NO SOCKETS - Direct function calls only

class USSArizonaBattleship(QLabel):
    """USS Arizona battleship photo display"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Load USS Arizona image
        image_path = os.path.join(os.path.dirname(__file__), 'uss_arizona.png')
        
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            # Scale to fit width while maintaining aspect ratio
            scaled_pixmap = pixmap.scaledToWidth(1000, Qt.SmoothTransformation)
            self.setPixmap(scaled_pixmap)
            self.setAlignment(Qt.AlignCenter)
        else:
            # Fallback text if image not found
            self.setText("USS ARIZONA (BB-39)\n[Save battleship image as 'uss_arizona.png' in project folder]")
            self.setAlignment(Qt.AlignCenter)
            self.setFont(QFont("Arial", 14, QFont.Bold))
        
        self.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(20, 40, 80, 255),
                    stop:1 rgba(10, 30, 60, 255));
                border: 3px solid rgba(100, 120, 150, 200);
                border-radius: 15px;
                padding: 10px;
            }
        """)
        
        self.setMinimumHeight(250)
        self.setMaximumHeight(400)

class BrainWorker(QThread):
    """Thread for communicating with Monday"""
    response_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, user_input: str):
        super().__init__()
        self.user_input = user_input
        
    def run(self):
        """Send to Thalamus and get response directly"""
        try:
            print(f"📤 Sending to Perception: {self.user_input[:50]}...")
            result = self.send_to_perception(self.user_input)
            print(f"📥 Got response: {result.get('status', 'unknown')}")
            # Response comes directly from Thalamus now
            self.response_ready.emit(result)
        except Exception as e:
            print(f"❌ Error in BrainWorker: {e}")
            import traceback
            traceback.print_exc()
            self.error_occurred.emit(str(e))
    
    def send_to_perception(self, text: str) -> Dict[str, Any]:
        """Send message to Perception first (Perception is the eyes/brain that receives input)"""
        try:
            # Get Perception instance from Thalamus
            thalamus = get_thalamus()
            if not thalamus:
                return {'status': 'error', 'message': 'Thalamus not initialized'}
            
            # Retry if Perception not registered yet (wait up to 2 seconds)
            perception = None
            for attempt in range(4):
                with thalamus.lobe_handlers_lock:
                    perception = thalamus.lobe_handlers.get('perception')
                if perception:
                    break
                time.sleep(0.5)
            
            if not perception:
                return {'status': 'error', 'message': 'Perception not registered - system may still be starting up'}
            
            # Send to Perception - it will receive input, process it, and broadcast to all lobes
            print("  → Sending to Perception...")
            perception_result = perception.process_message({'type': 'user_input', 'user_input': text})
            print(f"  ← Perception result: {perception_result.get('status', 'unknown')}")
            
            # After Perception broadcasts, Reasoning needs to query other lobes for their responses
            # Get response from Reasoning through Thalamus - Thalamus just routes the message
            print("  → Sending to Reasoning...")
            reasoning_response = thalamus.send_message('reasoning', 'think', {
                'input': {
                    'user_input': text,
                    'perception_result': perception_result if perception_result.get('status') == 'success' else {'status': 'error'},
                    'emotion_result': {'status': 'error'},
                    'memory_result': {'status': 'error'},
                    'representation_result': {'status': 'error'},
                    'pattern_result': {'status': 'error'}
                }
            })
            if reasoning_response.get('status') == 'success':
                thinking = reasoning_response.get('thinking', {})
                composed = thinking.get('composed_response', '')
                if composed:
                    return {'status': 'success', 'response': composed}
            return {'status': 'error', 'message': 'No response from Reasoning'}
        except Exception as e:
            return {'status': 'error', 'message': f'System error: {str(e)}'}

class MessageBubble(QFrame):
    """Chat message bubble"""
    
    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        
        label = QLabel(text)
        label.setWordWrap(True)
        label.setFont(QFont("Arial", 12))
        
        if is_user:
            self.setStyleSheet("""
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 rgba(30, 80, 150, 200),
                        stop:1 rgba(20, 60, 120, 220));
                    border: 2px solid rgba(100, 140, 200, 180);
                    border-radius: 18px;
                }
            """)
            label.setStyleSheet("color: white; background: transparent;")
            label.setAlignment(Qt.AlignRight)
        else:
            self.setStyleSheet("""
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 rgba(80, 60, 100, 180),
                        stop:1 rgba(60, 40, 80, 200));
                    border: 2px solid rgba(140, 100, 160, 180);
                    border-radius: 18px;
                }
            """)
            label.setStyleSheet("color: white; background: transparent;")
            label.setAlignment(Qt.AlignLeft)
        
        layout.addWidget(label)
        self.setLayout(layout)
        self.setMaximumWidth(600)

# REMOVED: ResponseListener - all responses come directly from Thalamus, no socket needed

class MondayInterface(QMainWindow):
    """Monday Communication Interface"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Monday Communication System")
        self.setMinimumSize(1200, 900)
        
        self.worker = None
        
        self.setup_ui()
        self.apply_style()
    
    def closeEvent(self, event):
        """Clean up on window close"""
        event.accept()
        
    def setup_ui(self):
        """Setup interface"""
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QLabel("Monday")
        header.setAlignment(Qt.AlignCenter)
        header.setFont(QFont("Arial", 32, QFont.Bold))
        header.setStyleSheet("""
            color: rgba(220, 220, 255, 255);
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(60, 40, 100, 220),
                stop:0.5 rgba(100, 60, 140, 220),
                stop:1 rgba(60, 40, 100, 220));
            border: 3px solid rgba(140, 100, 180, 200);
            border-radius: 20px;
            padding: 20px;
        """)
        main_layout.addWidget(header)
        
        # USS Arizona battleship
        self.battleship = USSArizonaBattleship()
        main_layout.addWidget(self.battleship)
        
        # Status
        self.status_label = QLabel("System Ready")
        self.status_label.setFont(QFont("Arial", 11, QFont.Bold))
        self.status_label.setStyleSheet("color: #00ff88; padding: 5px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        # Chat area
        chat_scroll = QScrollArea()
        chat_scroll.setWidgetResizable(True)
        chat_scroll.setStyleSheet("""
            QScrollArea {
                background: rgba(20, 15, 35, 180);
                border: 2px solid rgba(100, 80, 130, 150);
                border-radius: 15px;
            }
            QScrollBar:vertical {
                background: rgba(40, 30, 60, 200);
                width: 14px;
                border-radius: 7px;
            }
            QScrollBar::handle:vertical {
                background: rgba(100, 60, 140, 200);
                border-radius: 7px;
            }
        """)
        
        self.chat_widget = QWidget()
        self.chat_layout = QVBoxLayout()
        self.chat_layout.setSpacing(15)
        self.chat_layout.setContentsMargins(20, 20, 20, 20)
        self.chat_layout.addStretch()
        self.chat_widget.setLayout(self.chat_layout)
        chat_scroll.setWidget(self.chat_widget)
        main_layout.addWidget(chat_scroll, stretch=1)
        
        # Input
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(50, 30, 90, 230),
                    stop:1 rgba(70, 40, 110, 250));
                border: 3px solid rgba(120, 80, 160, 200);
                border-radius: 20px;
                padding: 15px;
            }
        """)
        
        input_layout = QHBoxLayout()
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Communicate with Monday...")
        self.input_field.setMinimumHeight(50)
        self.input_field.setFont(QFont("Arial", 13))
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: rgba(25, 15, 45, 200);
                border: 2px solid rgba(100, 60, 140, 150);
                border-radius: 12px;
                padding: 12px;
                color: white;
            }
            QLineEdit:focus {
                border: 3px solid rgba(140, 100, 180, 255);
                background: rgba(35, 20, 55, 220);
            }
        """)
        self.input_field.returnPressed.connect(self.send_message)
        
        self.send_btn = QPushButton("⚡ TRANSMIT")
        self.send_btn.setMinimumSize(180, 50)
        self.send_btn.setFont(QFont("Arial", 13, QFont.Bold))
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(120, 80, 160, 255),
                    stop:1 rgba(80, 50, 120, 255));
                border: 3px solid rgba(160, 120, 200, 200);
                border-radius: 12px;
                color: white;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(160, 120, 200, 255),
                    stop:1 rgba(120, 80, 160, 255));
            }
            QPushButton:disabled {
                background: rgba(80, 60, 100, 150);
                color: rgba(150, 150, 150, 200);
            }
        """)
        self.send_btn.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.input_field, stretch=1)
        input_layout.addWidget(self.send_btn)
        input_frame.setLayout(input_layout)
        main_layout.addWidget(input_frame)
        
        central.setLayout(main_layout)
        
        self.add_system_message("Monday online. Communication channel established.")
        
        # Poll for unprompted speech every 5 seconds
        self.speech_timer = QTimer()
        self.speech_timer.timeout.connect(self.check_unprompted_speech)
        self.speech_timer.start(5000)  # Check every 5 seconds
    
    def apply_style(self):
        """Global styling"""
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(15, 10, 25, 255),
                    stop:0.5 rgba(25, 15, 40, 255),
                    stop:1 rgba(15, 10, 25, 255));
            }
        """)
    
    def add_user_message(self, text: str):
        """Add user message"""
        bubble = MessageBubble(text, True)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble, alignment=Qt.AlignRight)
        QTimer.singleShot(50, self.scroll_to_bottom)
    
    def add_system_message(self, text: str):
        """Add Monday response"""
        bubble = MessageBubble(text, False)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble, alignment=Qt.AlignLeft)
        QTimer.singleShot(50, self.scroll_to_bottom)
    
    def scroll_to_bottom(self):
        """Scroll to bottom"""
        scroll_area = self.chat_widget.parent().parent()
        if isinstance(scroll_area, QScrollArea):
            scroll_area.verticalScrollBar().setValue(scroll_area.verticalScrollBar().maximum())
    
    def send_message(self):
        """Send to Monday"""
        text = self.input_field.text().strip()
        if not text:
            return
        
        self.add_user_message(text)
        self.input_field.clear()
        
        self.input_field.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.status_label.setText("Processing...")
        self.status_label.setStyleSheet("color: #ffaa00; padding: 5px;")
        
        self.worker = BrainWorker(text)
        self.worker.response_ready.connect(self.handle_response)
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.start()
    
    def handle_response(self, result: Dict[str, Any]):
        """Handle response from Output lobe"""
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.status_label.setText("System Ready")
        self.status_label.setStyleSheet("color: #00ff88; padding: 5px;")
        self.input_field.setFocus()
        
        if result.get('status') != 'success':
            error_msg = result.get('message', 'Unknown error')
            # Show the actual error
            if 'Error:' in error_msg:
                self.add_system_message(error_msg)
            else:
                self.add_system_message(f"Error: {error_msg}")
            return
        
        # Perception returns the final response (from Reasoning)
        response_text = result.get('response', 'No response')
        if response_text and response_text != 'No response':
            self.add_system_message(response_text)
        else:
            # Fallback if no response
            self.add_system_message("I'm processing that...")
    
    def handle_error(self, error: str):
        """Handle error"""
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.status_label.setText("Error")
        self.status_label.setStyleSheet("color: #ff4444; padding: 5px;")
        self.add_system_message(f"Error: {error}")
    
    def check_unprompted_speech(self):
        """Check if Monday wants to say something without prompting"""
        try:
            thalamus = get_thalamus()
            if not thalamus:
                return
            
            # Check if conversation system has unprompted speech
            result = thalamus.send_message('conversation', 'check_unprompted_speech', {})
            
            if result and result.get('status') == 'success':
                if result.get('has_speech'):
                    speech_text = result.get('speech', '')
                    if speech_text:
                        # Monday is speaking unprompted!
                        self.add_system_message(f"💭 {speech_text}")
                        
                        # Notify speech system that it was delivered
                        thalamus.send_message('speech', 'speech_delivered', {})
        except Exception as e:
            # Silently fail - don't interrupt user experience
            pass

def main():
    app = QApplication(sys.argv)
    window = MondayInterface()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
