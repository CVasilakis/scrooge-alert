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

SERVICE_NAME="skroutz-price-alert"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

cd "$SCRIPT_DIR"

if ! command -v systemctl > /dev/null 2>&1; then
    printf "%b\n" "${RED}Error: systemctl (systemd) is not installed or not available.${NC}"
    exit 1
fi

# ------------------------------------------------------------------------------
# ENABLING SERVICE
# ------------------------------------------------------------------------------

IS_ENABLED=$(systemctl --user is-enabled "$SERVICE_NAME.timer" 2>/dev/null || true)
IS_ACTIVE=$(systemctl --user is-active "$SERVICE_NAME.timer" 2>/dev/null || true)

if [ "$IS_ENABLED" = "enabled" ] && [ "$IS_ACTIVE" = "active" ]; then
    printf "%b\n" "\n${GREEN}The background service timer is already enabled and active. Nothing to do.${NC}"
    printf "%b\n" "\nTo disable background execution, run: ${CYAN}./scripts/disable.sh${NC}"
    printf "%b\n" "To completely remove the application, run: ${CYAN}./scripts/uninstall.sh${NC}\n"
    exit 0
fi

printf "%b\n" "\n${CYAN}Enabling and starting background schedule (timer)...${NC}"

# Attempt to enable and start the timer
if systemctl --user enable --now "$SERVICE_NAME.timer" >/dev/null 2>&1; then
    printf "%b\n" "\n${GREEN}Background execution enabled successfully.${NC}"
    printf "%b\n" "\nTo disable background execution, run: ${CYAN}./scripts/disable.sh${NC}"
    printf "%b\n" "To completely remove the application, run: ${CYAN}./scripts/uninstall.sh${NC}\n"
else
    printf "%b\n" "\n${RED}Error: Failed to enable the timer!${NC}"
    printf "%b\n" "${RED}Try running ./install.sh to fix the issue.${NC}\n"
    exit 1
fi
