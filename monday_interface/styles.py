#!/usr/bin/env python3
"""
Cyberpunk Theme Styles for Monday AI Interface
Dark navy/black background with cyan accents and neon glow effects
"""

# Color Palette
COLORS = {
    'background': '#0a0e1a',      # Deep navy
    'accent': '#00d9ff',          # Electric cyan
    'user_text': '#00d9ff',       # User messages
    'monday_text': '#00ff88',     # Monday responses (neon green)
    'debug_text': '#ffaa00',      # Debug info (orange)
    'border': '#1a2332',          # Panel borders
    'hover': '#152030',           # Hover state
    'input_bg': '#0f1523',        # Input field background
    'error': '#ff4466',           # Error color
    'warning': '#ffaa00',         # Warning color
    'success': '#00ff88',         # Success color
}

# Font Settings
FONTS = {
    'main': 'Consolas, Courier New, monospace',
    'size_normal': 10,
    'size_large': 12,
    'size_small': 9,
    'size_header': 14,
}

# Animation Settings
ANIMATION = {
    'fade_duration': 200,  # milliseconds
}

# Main Window Stylesheet
MAIN_WINDOW_STYLE = f"""
QMainWindow {{
    background-color: {COLORS['background']};
}}
"""

# Chat Panel Stylesheet
CHAT_PANEL_STYLE = f"""
QTextEdit {{
    background-color: {COLORS['background']};
    color: {COLORS['monday_text']};
    border: 1px solid {COLORS['border']};
    border-radius: 5px;
    padding: 10px;
    font-family: {FONTS['main']};
    font-size: {FONTS['size_normal']}pt;
    selection-background-color: {COLORS['accent']};
}}

QTextEdit:focus {{
    border: 1px solid {COLORS['accent']};
}}
"""

# Input Area Stylesheet
INPUT_AREA_STYLE = f"""
QLineEdit {{
    background-color: {COLORS['input_bg']};
    color: {COLORS['accent']};
    border: 1px solid {COLORS['border']};
    border-radius: 5px;
    padding: 8px;
    font-family: {FONTS['main']};
    font-size: {FONTS['size_normal']}pt;
}}

QLineEdit:focus {{
    border: 1px solid {COLORS['accent']};
    background-color: {COLORS['background']};
}}

QPushButton {{
    background-color: {COLORS['accent']};
    color: {COLORS['background']};
    border: none;
    border-radius: 5px;
    padding: 8px 16px;
    font-family: {FONTS['main']};
    font-size: {FONTS['size_normal']}pt;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: #00eeff;
}}

QPushButton:pressed {{
    background-color: #00b8d4;
}}

QPushButton:disabled {{
    background-color: {COLORS['border']};
    color: {COLORS['hover']};
}}
"""

# Emotion Display Stylesheet
EMOTION_DISPLAY_STYLE = f"""
QLabel {{
    background-color: {COLORS['input_bg']};
    color: {COLORS['monday_text']};
    border: 1px solid {COLORS['border']};
    border-radius: 5px;
    padding: 10px;
    font-family: {FONTS['main']};
    font-size: {FONTS['size_large']}pt;
}}
"""

# Debug Panel Stylesheet
DEBUG_PANEL_STYLE = f"""
QTextEdit {{
    background-color: #050812;
    color: {COLORS['debug_text']};
    border: 1px solid {COLORS['border']};
    border-radius: 5px;
    padding: 10px;
    font-family: {FONTS['main']};
    font-size: {FONTS['size_small']}pt;
}}

QLabel {{
    color: {COLORS['debug_text']};
    font-family: {FONTS['main']};
    font-size: {FONTS['size_small']}pt;
    padding: 2px;
}}
"""

# Emotion Color Mapping
EMOTION_COLORS = {
    # Primary emotions
    'happy': '#00ff88',
    'sad': '#4488ff',
    'angry': '#ff4466',
    'excited': '#ffaa00',
    'calm': '#88ddff',
    'worried': '#dd88ff',
    'curious': '#00d9ff',
    'proud': '#ffdd00',
    'scared': '#aa44ff',
    'surprised': '#ff88dd',
    'disgusted': '#88ff44',
    'contempt': '#ff6644',
    # Complex blends
    'nostalgic': '#8888ff',
    'anxious': '#dd44ff',
    'frustrated': '#ff8844',
    'euphoric': '#ffff00',
    'melancholic': '#6666ff',
    'playful': '#ff88ff',
    'protective': '#44ff88',
    'mischievous': '#ff44ff',
    'neutral': '#88aacc',
    'unknown': '#666666',
}

# Emotion Emoji Mapping
EMOTION_EMOJI = {
    'happy': '😊',
    'sad': '😢',
    'angry': '😠',
    'excited': '🤩',
    'calm': '😌',
    'worried': '😟',
    'curious': '🤔',
    'proud': '😎',
    'scared': '😨',
    'surprised': '😲',
    'disgusted': '🤢',
    'contempt': '😤',
    'nostalgic': '🥺',
    'anxious': '😰',
    'frustrated': '😣',
    'euphoric': '🥳',
    'melancholic': '😔',
    'playful': '😜',
    'protective': '🛡️',
    'mischievous': '😏',
    'neutral': '😐',
    'unknown': '❓',
}

def get_emotion_color(emotion_name):
    """Get color for emotion, default to neutral if unknown"""
    return EMOTION_COLORS.get(emotion_name.lower(), EMOTION_COLORS['neutral'])

def get_emotion_emoji(emotion_name):
    """Get emoji for emotion, default to unknown if not found"""
    return EMOTION_EMOJI.get(emotion_name.lower(), EMOTION_EMOJI['unknown'])
