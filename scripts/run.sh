#!/bin/sh
set -eu

# Wrapper script to run the Skroutz Price Alert scraper
SCRIPT_DIR="$(cd "$(dirname "$0")" >/dev/null 2>&1 && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

# Replace the shell process with the virtual environment's Python process
exec "$BASE_DIR/venv/bin/python3" "$BASE_DIR/src/scraper/main.py" "$@"
