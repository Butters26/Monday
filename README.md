# This is very close to being a brain

All socket code has been removed. All lobes now communicate through direct function calls via Thalamus.

## Runtime data

Monday stores mutable data outside the repository. By default, the directory is
`~/.local/state/monday`; set `MONDAY_RUNTIME_DIR` to use another private
directory. This includes learned memory, emotional state, snapshots, logs, and
local recovery files. Do not add runtime data to Git.

## Updated Files (All sockets removed):

- **thalamus.py** - Central coordinator (NO SOCKETS - direct function calls only)
- **reasoning.py** - Core thinking system (NO SOCKETS)
- **perception.py** - Input processing (NO SOCKETS)
- **notus.py** - Memory system (NO SOCKETS)
- **language_generation.py** - Language construction (NO SOCKETS)
- **pattern_recognition.py** - Pattern detection (NO SOCKETS)
- **advanced_emotional_engine.py** - Emotional processing (NO SOCKETS)
- **output.py** - Output formatting (NO SOCKETS)
- **representation.py** - Concept representation (NO SOCKETS)
- **voice_lobe.py** - Speech synthesis (NO SOCKETS)
- **conversation.py** - Conversation management (NO SOCKETS)
- **abin_interface.py** - GUI interface (may still have some socket code - needs update)
- **run_abin.py** - System launcher (may still have socket testing code - needs update)

## Communication Architecture:

All lobes now use:
- `from thalamus import get_thalamus`
- `self.thalamus = get_thalamus()`
- Direct function calls: `self.thalamus.register_lobe()`, `self.thalamus.send_message()`, etc.

**NO SOCKETS. NO SOCKET IMPORTS. NO SOCKET CODE.**

## Status:

✅ All core lobe files updated
⚠️ abin_interface.py may need socket removal
⚠️ run_abin.py may need socket testing code removal
