#!/bin/sh
set -eu

# ==============================================================================
# COLORS
# ==============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# ==============================================================================
# GLOBAL VARIABLES
# ==============================================================================

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "$0" )" >/dev/null 2>&1 && pwd )"
BASE_DIR="$( dirname "$SCRIPT_DIR" )"

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

print_help() {
    cat << 'EOF'

Usage: run.sh [-h] [--quiet] [--status] [--ping] [--skroutz]

Optional arguments:
  -h, --help        show this help message and exit
  --quiet           Run script with no console output
  --status          Perform a health check of the background service
  --ping            Send a test notification via Apprise
  --skroutz         Run exclusively the Skroutz scraper

EOF
}

# ==============================================================================
# EXECUTION
# ==============================================================================

TARGET="main.py"
ARGS=""

# Flags tracking for validation
FLAG_PING=0
FLAG_STATUS=0
FLAG_QUIET=0
FLAG_SKROUTZ=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        -h|--help)
            print_help
            exit 0
            ;;
        --ping)
            FLAG_PING=1
            TARGET="ping.py"
            shift
            ;;
        --status)
            FLAG_STATUS=1
            TARGET="status.py"
            shift
            ;;
        --quiet)
            FLAG_QUIET=1
            ARGS="$ARGS --quiet"
            shift
            ;;
        --skroutz)
            FLAG_SKROUTZ=1
            ARGS="$ARGS --skroutz"
            shift
            ;;
        *)
            printf "%b\n" "${RED}\nError: Invalid flag provided: $1${NC}"
            print_help
            exit 1
            ;;
    esac
done

# ==============================================================================
# VALIDATION
# ==============================================================================

TOTAL_FLAGS=$((FLAG_PING + FLAG_STATUS + FLAG_QUIET + FLAG_SKROUTZ))

# Check --ping rules
if [ "$FLAG_PING" -eq 1 ]; then
    if [ "$TOTAL_FLAGS" -gt 1 ]; then
        printf "%b\n" "${RED}\nError: The --ping flag must be used alone.${NC}"
        print_help
        exit 1
    fi
fi

# Check --status rules
if [ "$FLAG_STATUS" -eq 1 ]; then
    if [ "$TOTAL_FLAGS" -gt 1 ]; then
        printf "%b\n" "${RED}\nError: The --status flag must be used alone.${NC}"
        print_help
        exit 1
    fi
fi

# Intentionally unquoted ARGS to allow multiple arguments to expand properly
# shellcheck disable=SC2086
exec "$BASE_DIR/venv/bin/python3" "$BASE_DIR/src/scraper/$TARGET" $ARGS
