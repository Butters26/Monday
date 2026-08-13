#!/usr/bin/env python3
"""Compatibility launcher for Monday's single-process direct-call core."""

from run_abin import create_core_systems, shutdown_core_systems


def main() -> int:
    systems = create_core_systems()
    print("Monday direct-call core ready.")
    shutdown_core_systems(systems)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
