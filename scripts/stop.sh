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

SERVICE_NAME="skroutz-scraper"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

cd "$SCRIPT_DIR"

if ! command -v systemctl > /dev/null 2>&1; then
    printf "%b\n" "${RED}Error: systemctl (systemd) is not installed or not available.${NC}"
    exit 1
fi

# ------------------------------------------------------------------------------
# STOPPING SERVICE
# ------------------------------------------------------------------------------

# For Type=oneshot services, the state is 'activating' while the script is running.
STATE=$(systemctl --user show -p ActiveState "$SERVICE_NAME.service" 2>/dev/null | cut -d= -f2)

if [ "$STATE" = "active" ] || [ "$STATE" = "activating" ]; then
    printf "%b\n" "\n${CYAN}Stopping active background execution...\n${NC}"

    # Stop the service (aborts the currently running script)
    systemctl --user stop "$SERVICE_NAME.service" 2>/dev/null || true

    printf "%b\n" "${GREEN}Active background execution stopped successfully.${NC}"
else
    printf "%b\n" "\n${GREEN}No active background execution detected. Nothing to stop.${NC}"
fi

printf "%b\n" "\nTo disable future background executions, run: ${CYAN}./scripts/disable.sh${NC}"
printf "%b\n" "To completely remove the application, run: ${CYAN}./scripts/uninstall.sh${NC}\n"
