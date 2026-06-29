#!/usr/bin/env bash
# Record a clean run of the two-agent demo. Output is a script-friendly log
# suitable for piping to asciinema / Loom's terminal-capture mode.
#
# Usage: bash scripts/record_demo.sh > demo.log 2>&1
set -euo pipefail
cd "$(dirname "$0")"
NO_COLOR=1 exec python3 two_agent_demo.py
