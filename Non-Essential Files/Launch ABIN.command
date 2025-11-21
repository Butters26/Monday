#!/bin/bash
# ABIN Launcher - Double-click to start

cd "$(dirname "$0")"

echo "🚀 Starting ABIN System..."
echo ""

# Start lobes individually instead of using start_brain.py
python3 representation.py > /dev/null 2>&1 &
python3 pattern_recognition.py > /dev/null 2>&1 &
python3 reasoning.py > /dev/null 2>&1 &
python3 perception.py > /dev/null 2>&1 &
python3 output.py > /dev/null 2>&1 &
python3 thalamus.py > /dev/null 2>&1 &

# Wait for everything to start
echo "Waiting for all lobes to start..."
sleep 8

echo ""
echo "🎯 Launching interface..."
echo "Close the interface window to shut down ABIN"
echo ""

# Launch interface (blocks until window closes)
python3 abin_interface.py 2>&1 | tee /tmp/abin_interface.log

# When interface closes, kill all python processes
echo ""
echo "🛑 Shutting down ABIN..."
pkill -f "representation.py"
pkill -f "pattern_recognition.py"
pkill -f "reasoning.py"
pkill -f "perception.py"
pkill -f "output.py"
pkill -f "thalamus.py"

# Clean up sockets
rm -f /tmp/*.sock

echo "✅ ABIN shut down"
sleep 2

