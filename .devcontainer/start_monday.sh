#!/bin/bash
# Starts Monday (chat daemon, live tracer on) and the chat page on port 8765.
# Codespaces runs this every time the codespace starts.
cd "$(dirname "$0")/.."
export MONDAY_RUNTIME_DIR="$HOME/.local/state/monday-chat"
export MONDAY_TRACE="$HOME/monday_trace.jsonl"
mkdir -p "$MONDAY_RUNTIME_DIR"
rm -f "$MONDAY_RUNTIME_DIR/chat.sock"
nohup python _monday_chat_daemon.py > "$HOME/monday_daemon.log" 2>&1 &
for i in $(seq 1 120); do
  [ -S "$MONDAY_RUNTIME_DIR/chat.sock" ] && break
  sleep 1
done
if [ ! -S "$MONDAY_RUNTIME_DIR/chat.sock" ]; then
  echo "Monday did not start. Last lines of $HOME/monday_daemon.log:"
  tail -20 "$HOME/monday_daemon.log"
  exit 1
fi
nohup python _monday_web_chat.py > "$HOME/monday_web.log" 2>&1 &
echo "Monday is up. Open the 'Talk to Monday' port (8765)."
