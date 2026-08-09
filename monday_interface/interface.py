#!/usr/bin/env python3
"""
Main Interface Window for Monday AI Assistant
"""

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLineEdit, QPushButton, QSplitter, QShortcut
)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QKeySequence, QFont
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monday_interface.components import ChatPanel, EmotionDisplay, DebugPanel
from monday_interface.brain_connector import BrainConnector
from monday_interface.styles import (
    MAIN_WINDOW_STYLE,
    INPUT_AREA_STYLE,
    COLORS,
    FONTS
)


class MondayInterface(QMainWindow):
    """Main window for Monday AI interface"""
    
    def __init__(self):
        super().__init__()
        self.brain_connector = None
        self.init_ui()
        self.init_brain_connector()
    
    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Monday AI Assistant")
        self.setGeometry(100, 100, 900, 700)
        self.setStyleSheet(MAIN_WINDOW_STYLE)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Top area: Emotion display
        self.emotion_display = EmotionDisplay()
        main_layout.addWidget(self.emotion_display)
        
        # Middle area: Chat panel
        self.chat_panel = ChatPanel()
        main_layout.addWidget(self.chat_panel, stretch=1)
        
        # Debug panel (initially hidden)
        self.debug_panel = DebugPanel()
        main_layout.addWidget(self.debug_panel)
        
        # Bottom area: Input field and send button
        input_layout = QHBoxLayout()
        input_layout.setSpacing(10)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type your message to Monday...")
        self.input_field.setStyleSheet(INPUT_AREA_STYLE)
        self.input_field.returnPressed.connect(self.send_message)
        self.input_field.textChanged.connect(self.on_input_changed)
        
        # Set font
        font = QFont(FONTS['main'].split(',')[0], FONTS['size_normal'])
        self.input_field.setFont(font)
        
        self.send_button = QPushButton("Send")
        self.send_button.setStyleSheet(INPUT_AREA_STYLE)
        self.send_button.setFont(font)
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setMinimumWidth(80)
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_button)
        
        main_layout.addLayout(input_layout)
        
        central_widget.setLayout(main_layout)
        
        # Keyboard shortcuts
        self.setup_shortcuts()
        
        # Welcome message
        self.chat_panel.add_system_message("Welcome to Monday AI Assistant!")
        self.chat_panel.add_system_message("Monday is initializing brain systems...")
    
    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # F12 to toggle debug panel
        debug_shortcut = QShortcut(QKeySequence(Qt.Key_F12), self)
        debug_shortcut.activated.connect(self.toggle_debug_panel)
        
        # Escape to clear input
        clear_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        clear_shortcut.activated.connect(self.clear_input)
    
    def init_brain_connector(self):
        """Initialize the brain connector"""
        try:
            self.brain_connector = BrainConnector()
            
            # Set up callbacks
            self.brain_connector.on_response = self.on_monday_response
            self.brain_connector.on_emotion_update = self.on_emotion_update
            self.brain_connector.on_thinking_update = self.on_thinking_update
            
            # Connect debug panel
            self.debug_panel.set_brain_connector(self.brain_connector)
            
            self.chat_panel.add_system_message("Brain systems connected! Ready to chat.")
            
        except Exception as e:
            self.chat_panel.add_system_message(f"Error connecting to brain: {str(e)}")
            print(f"Brain connector error: {e}")
    
    @pyqtSlot()
    def send_message(self):
        """Send a message to Monday"""
        message = self.input_field.text().strip()
        if not message:
            return
        
        # Display user message
        self.chat_panel.add_user_message(message)
        
        # Clear input
        self.input_field.clear()
        
        # Disable input while processing
        self.input_field.setEnabled(False)
        self.send_button.setEnabled(False)
        
        # Show thinking indicator
        self.chat_panel.add_thinking_indicator()
        
        # Send to brain connector
        if self.brain_connector:
            self.brain_connector.send_message(message)
        else:
            self.chat_panel.add_system_message("Brain connector not available")
            self.input_field.setEnabled(True)
            self.send_button.setEnabled(True)

    @pyqtSlot(str)
    def on_input_changed(self, text):
        """Let Speech hold autonomous messages while the user is composing."""
        if self.brain_connector:
            self.brain_connector.set_user_typing(bool(text.strip()))
    
    @pyqtSlot(str)
    def on_monday_response(self, response):
        """Handle response from Monday"""
        # Remove thinking indicator
        self.chat_panel.remove_thinking_indicator()
        
        # Display Monday's response
        self.chat_panel.add_monday_message(response)
        
        # Re-enable input
        self.input_field.setEnabled(True)
        self.send_button.setEnabled(True)
        self.input_field.setFocus()
    
    @pyqtSlot(str, float)
    def on_emotion_update(self, emotion, intensity):
        """Handle emotion update from brain"""
        self.emotion_display.update_emotion(emotion, intensity)
    
    @pyqtSlot(bool)
    def on_thinking_update(self, is_thinking):
        """Handle thinking state update"""
        # Could add visual feedback here if needed
        pass
    
    @pyqtSlot()
    def toggle_debug_panel(self):
        """Toggle the debug panel visibility"""
        self.debug_panel.toggle()
    
    @pyqtSlot()
    def clear_input(self):
        """Clear the input field"""
        self.input_field.clear()
    
    def closeEvent(self, event):
        """Handle window close event"""
        if self.brain_connector:
            self.brain_connector.shutdown()
        event.accept()
