# Configuration Files

All the JSON configs for the Brain System - makes everything work together smoothly.

## 📋 Main Config

**brain_config.json** - Master config for the entire brain system
- All lobe paths and socket locations
- Startup settings
- Communication parameters
- Enable/disable individual lobes

## 🧩 Lobe Configs

**representation_config.json** - Concept space settings
- Activation and decay rates
- Relationship strengths
- Max concepts and active concepts

**pattern_config.json** - Pattern recognition settings
- Co-occurrence thresholds
- Sequence detection parameters
- Decay rates and timeouts

**reasoning_config.json** - Thinking system settings
- Logic parameters (forward/backward chaining)
- Curiosity settings
- Opinion formation rules
- Meaning-making configuration

**perception_config.json** - Input processing settings
- Text/audio/visual input toggles
- Emotion keyword mappings
- Entity detection rules

**output_config.json** - Expression settings
- Voice configuration
- Text formatting rules
- Emotional formatting

**thalamus_config.json** - Coordination settings
- All socket paths
- Coalition definitions
- Priority levels
- Communication timeouts

## 🎨 Interface Config

**interface_config.json** - GUI settings
- Window dimensions
- Colors for each lobe
- 3D effects parameters
- Fonts and styling

## 📖 Config Index

**CONFIG_INDEX.json** - Map of all configs
- Shows which config controls what
- Load order for startup
- File locations

## 🔧 How To Use

Each lobe can load its own config:

```python
import json

with open('reasoning_config.json', 'r') as f:
    config = json.load(f)

threshold = config['reasoning']['logic']['min_confidence_threshold']
```

Or load the main config for everything:

```python
with open('brain_config.json', 'r') as f:
    brain_config = json.load(f)

socket_path = brain_config['lobes']['reasoning']['socket']
```

## ✏️ Customization

Edit any config to change behavior:
- Thresholds and limits
- Enable/disable features
- Adjust timing and delays
- Change visual appearance

Changes take effect on next startup (or reload if live config is implemented).

## 🎯 Quick Reference

**Want to change pattern sensitivity?** → pattern_config.json
**Want to adjust reasoning depth?** → reasoning_config.json  
**Want to change interface colors?** → interface_config.json
**Want to enable/disable voice?** → output_config.json
**Want to change socket paths?** → brain_config.json (main) or individual configs


