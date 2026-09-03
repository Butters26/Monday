#!/usr/bin/env python3
"""
Chat Panel Component - Displays conversation between user and Monday
"""

from PyQt5.QtWidgets import QTextEdit, QWidget, QVBoxLayout
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QTextCursor, QTextCharFormat, QColor, QFont
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monday_interface.styles import (
    CHAT_PANEL_STYLE, 
    COLORS, 
    FONTS
)


class ChatPanel(QWidget):
    """Chat display widget showing user and Monday's conversation"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the chat panel UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Chat display area
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet(CHAT_PANEL_STYLE)
        
        # Set font
        font = QFont(FONTS['main'].split(',')[0], FONTS['size_normal'])
        self.chat_display.setFont(font)
        
        layout.addWidget(self.chat_display)
        self.setLayout(layout)
    
    def add_user_message(self, message: str):
        """Add a user message to the chat"""
        self._add_message("You", message, COLORS['user_text'])
    
    def add_monday_message(self, message: str):
        """Add a Monday response to the chat"""
        self._add_message("Monday", message, COLORS['monday_text'])
    
    def add_system_message(self, message: str):
        """Add a system message to the chat"""
        self._add_message("System", message, COLORS['debug_text'])
    
    def _add_message(self, sender: str, message: str, color: str):
        """Internal method to add a formatted message"""
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        # Format for sender
        sender_format = QTextCharFormat()
        sender_format.setForeground(QColor(color))
        sender_format.setFontWeight(QFont.Bold)
        
        # Format for message
        message_format = QTextCharFormat()
        message_format.setForeground(QColor(color))
        
        # Add sender
        cursor.insertText(f"{sender}: ", sender_format)
        
        # Add message
        cursor.insertText(f"{message}\n\n", message_format)
        
        # Auto-scroll to bottom
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()
    
    def clear(self):
        """Clear all messages from the chat"""
        self.chat_display.clear()
    
    def add_thinking_indicator(self):
        """Show that Monday is thinking"""
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        format = QTextCharFormat()
        format.setForeground(QColor(COLORS['debug_text']))
        format.setFontItalic(True)
        
        cursor.insertText("Monday is thinking...\n", format)
        
        self.chat_display.setTextCursor(cursor)
        self.chat_display.ensureCursorVisible()
    
    def remove_thinking_indicator(self):
        """Remove the thinking indicator (removes last line if it's the indicator)"""
        text = self.chat_display.toPlainText()
        if text.endswith("Monday is thinking...\n"):
            # Remove the last line
            cursor = self.chat_display.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
            cursor.movePosition(QTextCursor.Up, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
