# Monday - AI Cognitive Architecture System

**Monday** is an advanced AI cognitive architecture project that implements a modular "brain" system inspired by biological neural organization. The system is designed around the concept of specialized processing units ("lobes") that work together to create an autonomous, reasoning-capable AI entity.

## 🧠 System Architecture

Monday is structured as a distributed cognitive system with specialized components:

### Core Lobes (Processing Units)

- **Representation Layer** (`representation.py`) - Encodes and represents information in internal formats
- **Pattern Recognition** (`pattern_recognition.py`) - Identifies patterns, sequences, and clusters in data
- **Reasoning System** (`reasoning.py`) - Handles causal inference, sensorimotor grounding, and autonomous agency
- **Notus Memory** (`notus.py`) - Persistent memory storage using `superhuman_memory.db`
- **Emotional Engine** (`advanced_emotional_engine.py`) - Emotional state management
- **Perception** (`perception.py`) - Processes sensory inputs (text, voice, etc.)
- **Output** (`output.py`) - Generates responses and actions
- **Thalamus** (`thalamus.py`) - Central coordinator routing messages between lobes
- **Conversation** (`conversation.py`) - Manages dialogue and conversation flow
- **Language Generation** (`language_generation.py`) - Natural language generation capabilities
- **Voice Lobe** (`voice_lobe.py`) - Voice processing and synthesis

### Communication Architecture

All lobes communicate via Unix domain sockets located in `/tmp/`:
- `/tmp/representation.sock`
- `/tmp/pattern.sock`
- `/tmp/reasoning.sock`
- `/tmp/notus.sock`
- `/tmp/emotion.sock`
- `/tmp/perception.sock`
- `/tmp/output.sock`
- `/tmp/thalamus.sock`
- `/tmp/conversation.sock`
- `/tmp/language.sock`
- `/tmp/voice.sock`

## 🚀 Getting Started

### Prerequisites

- Python 3.x
- Unix-like operating system (for Unix domain sockets)

### Starting the Brain System

```bash
# Start all brain lobes
python3 start_brain.py

# Or use the shell script
./run_all.sh

# Launch ABIN interface
python3 launch_abin.py
```

### Running Individual Components

```bash
# Run a specific lobe
python3 reasoning.py

# Test the system
python3 test_client.py
```

## 📋 Configuration Files

The system uses JSON configuration files for each component:

- `brain_config.json` - Main brain system configuration
- `CONFIG_INDEX.json` - Index of all configuration files
- `representation_config.json` - Representation layer settings
- `pattern_config.json` - Pattern recognition thresholds
- `reasoning_config.json` - Reasoning system parameters
- `perception_config.json` - Perception settings
- `output_config.json` - Output generation settings
- `thalamus_config.json` - Thalamus coordination settings
- `interface_config.json` - Interface configuration

## 🎯 Key Features

### Autonomous Agency
Monday is designed with **true autonomous agency** - the ability to:
- Initiate actions without external prompts
- Send messages proactively
- Form and test hypotheses through active inference
- Understand causal relationships and consequences

### Sensorimotor Grounding
The reasoning system implements sensorimotor grounding where:
- Actions create meaning through perception loops
- Understanding emerges from interaction
- Concepts are grounded in experience

### Memory System
- Persistent memory storage via SQLite (`superhuman_memory.db`)
- Contextual memory retrieval
- Emotional state persistence (`monday_emotional_state.json`)

### Modular Design
Each cognitive function is isolated in its own module ("lobe"), allowing for:
- Independent development and testing
- Scalable architecture
- Easy debugging and maintenance

## 📁 Project Structure

```
Monday/
├── Core Brain Components
│   ├── start_brain.py              # Brain system launcher
│   ├── thalamus.py                 # Central coordinator
│   ├── reasoning.py                # Reasoning and inference
│   ├── representation.py           # Data representation
│   ├── pattern_recognition.py      # Pattern detection
│   ├── perception.py               # Sensory input processing
│   ├── output.py                   # Response generation
│   └── conversation.py             # Conversation management
│
├── Language & Communication
│   ├── language_generation.py      # Natural language generation
│   ├── voice_lobe.py               # Voice processing
│   └── voice_analyzer.py           # Voice analysis
│
├── Launch & Interface
│   ├── launch_abin.py              # ABIN interface launcher
│   ├── run_abin.py                 # ABIN runner
│   └── test_client.py              # Testing client
│
├── Configuration
│   ├── CONFIG_INDEX.json           # Configuration index
│   ├── brain_config.json           # Main configuration
│   ├── reasoning_config.json       # Reasoning settings
│   ├── perception_config.json      # Perception settings
│   ├── output_config.json          # Output settings
│   ├── thalamus_config.json        # Thalamus settings
│   ├── representation_config.json  # Representation settings
│   ├── pattern_config.json         # Pattern recognition settings
│   └── interface_config.json       # Interface settings
│
├── Data & State
│   ├── superhuman_memory.db        # Memory database
│   ├── monday_emotional_state.json # Emotional state
│   └── concept_data.json           # Concept definitions
│
└── Utilities
    ├── analyze_shadowheart.py      # Analysis tool
    ├── convert_wem_to_wav.py       # Audio conversion
    └── Non-Essential Files/        # Additional resources
```

## 🔧 Development

### Adding New Lobes

1. Create a new Python module following the existing lobe pattern
2. Implement Unix socket communication
3. Add configuration file
4. Update `brain_config.json` and `CONFIG_INDEX.json`
5. Add to startup sequence in `start_brain.py`

### Message Protocol

Lobes communicate using a simple protocol:
- 4-byte length header (network byte order)
- JSON message payload
- Timeout handling for robust communication

## 📝 Notes

- The system uses Unix domain sockets for inter-process communication
- Each lobe runs as an independent process
- The Thalamus coordinates message routing between lobes
- Memory persists across sessions via SQLite database
- Emotional state is maintained and persists to JSON

## ⚠️ Requirements

- The system is designed for Unix-like operating systems
- Requires write access to `/tmp/` for socket files
- Python 3.x with standard library (no external dependencies shown in core files)

## 🎓 Philosophy

Monday implements a cognitive architecture that emphasizes:
- **True understanding** over pattern matching
- **Autonomous agency** over reactive responses
- **Grounded cognition** over abstract reasoning alone
- **Modular design** inspired by biological neural organization

---

*This is an experimental AI cognitive architecture project exploring autonomous agency and grounded cognition.*
