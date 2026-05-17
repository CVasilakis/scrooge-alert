#!/bin/sh
set -eu

# ==============================================================================
# COLORS
# ==============================================================================
RED='\033[0;31m'
NC='\033[0m' # No Color

# ==============================================================================
# GLOBAL VARIABLES
# ==============================================================================

# Automatically get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" >/dev/null 2>&1 && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

print_help() {
    cat << 'EOF'

Usage: run.sh [-h] [--quiet] [--status] [--ping]

Optional arguments:
  -h, --help  show this help message and exit
  --quiet     Run script with no console output
  --status    Perform a health check of the background service
  --ping      Send a test notification via Apprise

EOF
}

# ==============================================================================
# EXECUTION
# ==============================================================================

if [ "$#" -gt 1 ]; then
    printf "${RED}\nPlease provide no more than one flag!${NC}\n"
    print_help
    exit 1
fi

TARGET="main.py"

if [ "$#" -eq 1 ]; then
    case "$1" in
        -h|--help)
            print_help
            exit 0
            ;;
        --ping)
            TARGET="ping.py"
            shift
            ;;
        --status)
            TARGET="status.py"
            shift
            ;;
        --quiet)
            TARGET="main.py"
            ;;
        *)
            printf "${RED}\nInvalid flag provided: $1${NC}\n"
            print_help
            exit 1
            ;;
    esac
fi

exec "$BASE_DIR/venv/bin/python3" "$BASE_DIR/src/scraper/$TARGET" "$@"
