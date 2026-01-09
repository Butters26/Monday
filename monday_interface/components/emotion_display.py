#!/usr/bin/env python3
"""
Emotion Display Component - Shows Monday's current emotional state
"""

from PyQt5.QtWidgets import QLabel, QWidget, QVBoxLayout, QGraphicsOpacityEffect
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QPalette, QColor
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monday_interface.styles import (
    EMOTION_DISPLAY_STYLE,
    COLORS,
    FONTS,
    get_emotion_color,
    get_emotion_emoji,
    ANIMATION
)


class EmotionDisplay(QWidget):
    """Widget displaying Monday's current emotional state"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_emotion = 'neutral'
        self.current_intensity = 0.5
        self.init_ui()
    
    def init_ui(self):
        """Initialize the emotion display UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Emotion label
        self.emotion_label = QLabel("😐 Neutral")
        self.emotion_label.setAlignment(Qt.AlignCenter)
        self.emotion_label.setStyleSheet(EMOTION_DISPLAY_STYLE)
        
        # Set font
        font = QFont(FONTS['main'].split(',')[0], FONTS['size_large'])
        font.setBold(True)
        self.emotion_label.setFont(font)
        
        # Set initial color
        self._update_color('neutral', 0.5)
        
        layout.addWidget(self.emotion_label)
        self.setLayout(layout)
    
    def update_emotion(self, emotion: str, intensity: float = 0.5):
        """Update the displayed emotion with smooth transition"""
        if emotion == self.current_emotion and abs(intensity - self.current_intensity) < 0.1:
            return  # No significant change
        
        self.current_emotion = emotion
        self.current_intensity = intensity
        
        # Update text with emoji
        emoji = get_emotion_emoji(emotion)
        emotion_text = emotion.replace('_', ' ').title()
        intensity_text = f"{int(intensity * 100)}%"
        
        self.emotion_label.setText(f"{emoji} {emotion_text} ({intensity_text})")
        
        # Update color with animation
        self._update_color(emotion, intensity)
        
        # Fade animation
        self._fade_animation()
    
    def _update_color(self, emotion: str, intensity: float):
        """Update the text color based on emotion"""
        color = get_emotion_color(emotion)
        
        # Adjust alpha based on intensity (50% to 100%)
        alpha = int(128 + (intensity * 127))
        
        # Apply color with glow effect
        style = f"""
        QLabel {{
            background-color: {COLORS['input_bg']};
            color: {color};
            border: 1px solid {color};
            border-radius: 5px;
            padding: 10px;
            font-family: {FONTS['main']};
            font-size: {FONTS['size_large']}pt;
        }}
        """
        
        self.emotion_label.setStyleSheet(style)
    
    def _fade_animation(self):
        """Create a subtle fade animation on emotion change"""
        try:
            # Create opacity effect if it doesn't exist
            if not hasattr(self, 'opacity_effect'):
                self.opacity_effect = QGraphicsOpacityEffect()
                self.emotion_label.setGraphicsEffect(self.opacity_effect)
            
            # Create animation
            self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
            self.animation.setDuration(ANIMATION['fade_duration'])
            self.animation.setStartValue(0.5)
            self.animation.setEndValue(1.0)
            self.animation.setEasingCurve(QEasingCurve.InOutQuad)
            self.animation.start()
        except Exception as e:
            # Animation is optional, silently fail
            pass
