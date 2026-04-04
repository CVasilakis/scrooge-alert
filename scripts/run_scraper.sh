#!/bin/bash
# Wrapper script to run the Skroutz Price Alert scraper

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

# Activate virtual environment
source "$BASE_DIR/venv/bin/activate"

# Export data directory to be safe (though default handles it)
export DATA_DIR="$BASE_DIR/data"

# Run the python script and pass any arguments
python "$BASE_DIR/src/scraper/skroutz_price_alert.py" "$@"
