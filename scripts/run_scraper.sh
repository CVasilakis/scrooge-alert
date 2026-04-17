#!/bin/sh
set -e

# Wrapper script to run the Skroutz Price Alert scraper
SCRIPT_DIR="$(cd "$(dirname "$0")" >/dev/null 2>&1 && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

# Activate virtual environment
. "$BASE_DIR/venv/bin/activate"

# Run the python script and pass arguments
python "$BASE_DIR/src/scraper/skroutz_price_alert.py" "$@"
