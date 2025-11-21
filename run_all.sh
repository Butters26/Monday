#!/usr/bin/env bash
# Simple helper to start core lobes in background for local testing.
# Run: bash run_all.sh
set -e

# Start Notus (memory)
python3 notus.py &
sleep 0.3

# Start Emotional engine
python3 advanced_emotional_engine.py &
sleep 0.3

# Start Representation
python3 representation.py &
sleep 0.3

# Start Language
python3 language_generation.py &
sleep 0.3

# Start Output
python3 output.py &
sleep 0.3

# Start Pattern
python3 pattern_recognition.py &
sleep 0.3

# Start Perception (optional; comment if no webcam/mic)
python3 perception.py &
sleep 0.3

# Start Reasoning
python3 reasoning.py &
sleep 0.3

# Finally, start Thalamus
python3 thalamus.py &
sleep 0.3

echo "Started lobes. Give them a second to create sockets under /tmp/*.sock"
echo "Check they are running with: ps aux | grep python"

