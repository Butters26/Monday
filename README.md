# This is very close to being a brain

All socket code has been removed. All lobes now communicate through direct function calls via Thalamus.

## Runtime data

Monday stores mutable data outside the repository. By default, the directory is
`~/.local/state/monday`; set `MONDAY_RUNTIME_DIR` to use another private
directory. This includes learned memory, emotional state, snapshots, logs, and
local recovery files. Do not add runtime data to Git.

## Legacy and experimental modules

The direct core intentionally excludes the legacy/experimental launcher,
PostgreSQL-backed `notus.py`, GUI, socket integrations, and autonomous loops.
They remain in the repository for compatibility work but are not imported by
`run_abin.py`.

## Communication Architecture:

All lobes now use:
- `from thalamus import get_thalamus`
- `self.thalamus = get_thalamus()`
- Direct function calls: `self.thalamus.register_lobe()`, `self.thalamus.send_message()`, etc.

**NO SOCKETS. NO SOCKET IMPORTS. NO SOCKET CODE.**

## Direct-call core

`run_abin.create_core_systems()` creates only the prompted path:
conversation → Notus → emotion → reasoning → language → output.  Each lobe
receives `{"type", "content", "source", "message_id"}`; `content` is the
message payload.  Runtime memory is private SQLite state, so core startup does
not require PostgreSQL, API keys, sockets, a GUI, or background loops.

The direct reasoning lobe derives conclusions and propositions from structured
understanding plus user-scoped SQLite memory. It can recall stable personal
facts across a restart, and its conclusion passes through language and output.
The deterministic response provider is a fallback only when reasoning supplies
no usable answer or proposition; it does not replace a reasoning result.

## Status

✅ `run_abin.py` is the active direct-core launcher. It uses the lightweight
`direct_notus.py` SQLite adapter and a dependency-free direct reasoning lobe;
it does not start sockets, PostgreSQL, a GUI, or background loops.
