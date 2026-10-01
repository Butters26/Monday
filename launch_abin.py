#!/usr/bin/env python3
"""Compatibility entry point for Mercy's single-process direct-call core.

The old multiprocess launcher waited for obsolete lobe sockets and launched a
standalone GUI that did not call the core. Use the canonical REPL instead.
"""

from run_abin import main


if __name__ == "__main__":
    raise SystemExit(main())
