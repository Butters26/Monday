# How to Use ABIN

## Starting ABIN

```bash
python3 start_brain.py
```

This starts all lobes:
- Representation Layer (230 concepts loaded)
- Pattern Recognition (detects patterns, contradictions, learns)
- Reasoning (thinking system)
- Notus (memory)
- Emotional Engine
- Perception (eyes=webcam, ears=microphone, both autonomous)
- Output (formatting and voice)
- Thalamus (coordinates everything)

## Launching Interface

In a new terminal:
```bash
python3 abin_interface.py
```

Shows USS Arizona battleship and chat interface.
Type to communicate with ABIN.

## What Works

**Perception (6/10):**
- Webcam runs constantly (autonomous vision)
- Microphone listens constantly (autonomous hearing)
- Processes text input

**Representation (9/10):**
- 230 concepts loaded (emotions, objects, actions, abstract)
- Relationships between concepts
- Spreading activation network

**Pattern Recognition (8/10):**
- Detects contradictions
- Multi-step sequences (A→B→C→D)
- Meta-patterns
- Pareidolia mode (sees patterns when bored)
- **Can learn** - teach it new patterns with messages

**Output (6/10):**
- Formats text with emotional emphasis
- Cleans up spacing and grammar
- Voice synthesis ready (disabled)

**Thalamus (6/10):**
- Coordinates all lobes
- Filters data (only significant info to reasoning)
- Direct connection between Memory and Reasoning

**Notus (8/10):**
- Already works well

## What Still Needs Work

**Reasoning (1/10):**
- Pattern matching broken
- No real inference
- Theory generation is weak
- Response composition just echoes

**Interface (3/10):**
- Works functionally
- USS Arizona is geometric shapes, not detailed

## Teaching ABIN

You can teach Pattern Recognition:

```python
# Teach opposites
send_message('teach_opposites', {
    'word': 'awesome',
    'opposites': ['terrible']
})

# Teach behavioral patterns
send_message('teach_pattern', {
    'pattern_name': 'sarcasm',
    'definition': {
        'signals': {
            'required': ['positive_words', 'negative_emotion'],
            'optional': ['exaggeration']
        }
    }
})
```

ABIN learns and adapts based on what you teach it.

## Current Limitations

- Reasoning system doesn't actually reason yet
- Responses are mostly echoing or generic
- No autonomous thinking (just reactive)
- Interface is functional but basic

## Files

- `start_brain.py` - Starts all lobes
- `abin_interface.py` - Main interface
- `pattern_recognition.py` - Pattern detector (905 lines, advanced)
- `reasoning.py` - Thinking system (needs major work)
- `representation.py` - Concept network
- `perception.py` - Eyes and ears
- `output.py` - Response formatting
- `thalamus.py` - Coordinator
- `.cursorrules` - Rules I must follow

