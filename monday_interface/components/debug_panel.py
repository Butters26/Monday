#!/usr/bin/env python3
"""
Debug Panel Component - Shows brain state, lobes, and performance metrics
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLabel
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
import sys
import os
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monday_interface.styles import (
    DEBUG_PANEL_STYLE,
    COLORS,
    FONTS
)


class DebugPanel(QWidget):
    """Collapsible debug panel showing brain internals"""
    
    def __init__(self, brain_connector=None, parent=None):
        super().__init__(parent)
        self.brain_connector = brain_connector
        self.visible = False
        self.init_ui()
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(1000)  # Update every second
    
    def init_ui(self):
        """Initialize the debug panel UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Title
        title = QLabel("🔧 DEBUG PANEL [F12 to toggle]")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['debug_text']};
                font-family: {FONTS['main']};
                font-size: {FONTS['size_normal']}pt;
                font-weight: bold;
                padding: 5px;
                background-color: #050812;
                border: 1px solid {COLORS['border']};
                border-radius: 3px;
            }}
        """)
        
        # Debug display area
        self.debug_display = QTextEdit()
        self.debug_display.setReadOnly(True)
        self.debug_display.setStyleSheet(DEBUG_PANEL_STYLE)
        self.debug_display.setMaximumHeight(250)
        
        # Set font
        font = QFont(FONTS['main'].split(',')[0], FONTS['size_small'])
        self.debug_display.setFont(font)
        
        layout.addWidget(title)
        layout.addWidget(self.debug_display)
        self.setLayout(layout)
        
        # Initially hidden
        self.hide()
    
    def toggle(self):
        """Toggle visibility of the debug panel"""
        self.visible = not self.visible
        if self.visible:
            self.show()
            self.update_display()
        else:
            self.hide()
    
    def update_display(self):
        """Update the debug information display"""
        if not self.visible or not self.brain_connector:
            return
        
        try:
            state = self.brain_connector.get_brain_state()
            
            # Build debug text
            debug_text = []
            
            # Lobes status
            debug_text.append("═══ ACTIVE LOBES ═══")
            lobes = state.get('lobes', {})
            if lobes:
                for lobe_name, status in sorted(lobes.items()):
                    status_icon = "✅" if status == "online" else "❌"
                    debug_text.append(f"  {status_icon} {lobe_name}: {status}")
            else:
                debug_text.append("  No lobes registered")
            
            debug_text.append("")
            
            # Current thinking mode
            debug_text.append("═══ THINKING MODE ═══")
            thinking = "🧠 PROCESSING..." if state.get('thinking', False) else "💤 Idle"
            debug_text.append(f"  {thinking}")
            debug_text.append("")
            
            # Emotional state
            debug_text.append("═══ EMOTIONAL STATE ═══")
            emotion = state.get('emotion', 'unknown')
            intensity = state.get('intensity', 0.0)
            debug_text.append(f"  Current: {emotion} ({intensity:.1%})")
            debug_text.append("")
            
            # Recent thoughts
            debug_text.append("═══ RECENT THOUGHTS ═══")
            recent = state.get('recent_thoughts', [])
            if recent:
                for idx, thought in enumerate(recent[-5:], 1):
                    if isinstance(thought, dict):
                        user_said = thought.get('user_said', '')[:50]
                        monday_said = thought.get('monday_said', '')[:50]
                        debug_text.append(f"  [{idx}] U: {user_said}...")
                        debug_text.append(f"      M: {monday_said}...")
                    else:
                        debug_text.append(f"  [{idx}] {str(thought)[:50]}...")
            else:
                debug_text.append("  No recent conversations")
            
            debug_text.append("")
            
            # Performance metrics
            debug_text.append("═══ PERFORMANCE ═══")
            conv_count = state.get('conversation_count', 0)
            debug_text.append(f"  Total conversations: {conv_count}")
            beliefs_count = len(state.get('beliefs', []))
            debug_text.append(f"  Beliefs: {beliefs_count}")
            facts_count = len(state.get('learned_facts', {}))
            debug_text.append(f"  Learned facts: {facts_count}")
            
            # Update display
            self.debug_display.setPlainText('\n'.join(debug_text))
            
        except Exception as e:
            self.debug_display.setPlainText(f"Error updating debug panel:\n{str(e)}")
    
    def set_brain_connector(self, brain_connector):
        """Set or update the brain connector"""
        self.brain_connector = brain_connector
