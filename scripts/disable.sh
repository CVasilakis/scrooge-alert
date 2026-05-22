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
# DISABLING SERVICE
# ------------------------------------------------------------------------------

TIMER_ENABLED=$(systemctl --user is-enabled "$SERVICE_NAME.timer" 2>/dev/null || true)
TIMER_ACTIVE=$(systemctl --user is-active "$SERVICE_NAME.timer" 2>/dev/null || true)
SERVICE_ACTIVE=$(systemctl --user show -p ActiveState "$SERVICE_NAME.service" 2>/dev/null | cut -d= -f2)

# The service itself cannot be "enabled" (it lacks an [Install] section and is driven by the timer).
# We only need to do work if the timer is enabled/active, or if the service is currently executing.
if [ "$TIMER_ENABLED" != "enabled" ] && [ "$TIMER_ACTIVE" != "active" ] && \
   [ "$SERVICE_ACTIVE" != "active" ] && [ "$SERVICE_ACTIVE" != "activating" ]; then
    printf "%b\n" "\n${GREEN}The background service and timer are already disabled. Nothing to do.${NC}"
    printf "%b\n" "\nTo re-enable background execution, run: ${CYAN}./scripts/enable.sh${NC}"
    printf "%b\n" "To completely remove the application, run: ${CYAN}./uninstall.sh${NC}\n"
    exit 0
fi

printf "%b\n" "\n${CYAN}Stopping and disabling background schedule (timer)...${NC}"

systemctl --user stop "$SERVICE_NAME.timer" 2>/dev/null || true
systemctl --user disable "$SERVICE_NAME.timer" 2>/dev/null || true
systemctl --user stop "$SERVICE_NAME.service" 2>/dev/null || true
systemctl --user disable "$SERVICE_NAME.service" 2>/dev/null || true
systemctl --user reset-failed "$SERVICE_NAME.service" "$SERVICE_NAME.timer" 2>/dev/null || true

printf "%b\n" "\n${GREEN}Background execution disabled successfully.${NC}"
printf "%b\n" "\nTo re-enable background execution, run: ${CYAN}./scripts/enable.sh${NC}"
printf "%b\n" "To completely remove the application, run: ${CYAN}./uninstall.sh${NC}\n"
