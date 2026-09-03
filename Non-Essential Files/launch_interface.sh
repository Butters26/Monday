#!/bin/bash
# Launch the Brain Interface System

echo "🧠 Launching Brain Control Interface..."
echo ""

cd "$(dirname "$0")"

# Check if brain is running
if [ ! -e "/tmp/reasoning.sock" ]; then
    echo "⚠️  Warning: Brain system doesn't appear to be running"
    echo "   Start it with: python3 start_brain.py"
    echo ""
    read -p "Launch interface anyway? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Launch interface
python3 brain_interface.py


