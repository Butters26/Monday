#!/bin/bash
# Starts Mercy (chat daemon, live tracer on) and the chat page on port 8765.
# Codespaces runs this every time the codespace starts.
cd "$(dirname "$0")/.."
export MERCY_RUNTIME_DIR="$HOME/.local/state/mercy-chat"
export MERCY_TRACE="$HOME/mercy_trace.jsonl"
mkdir -p "$MERCY_RUNTIME_DIR"
rm -f "$MERCY_RUNTIME_DIR/chat.sock"
nohup python _mercy_chat_daemon.py > "$HOME/mercy_daemon.log" 2>&1 &
for i in $(seq 1 120); do
  [ -S "$MERCY_RUNTIME_DIR/chat.sock" ] && break
  sleep 1
done
if [ ! -S "$MERCY_RUNTIME_DIR/chat.sock" ]; then
  echo "Mercy did not start. Last lines of $HOME/mercy_daemon.log:"
  tail -20 "$HOME/mercy_daemon.log"
  exit 1
fi
nohup python _mercy_web_chat.py > "$HOME/mercy_web.log" 2>&1 &
echo "Mercy is up. Open the 'Talk to Mercy' port (8765)."
