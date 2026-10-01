#!/usr/bin/env bash
# Start the registered direct-call lobes together in one process.
set -euo pipefail

brain_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$brain_directory/run_abin.py" "$@"
