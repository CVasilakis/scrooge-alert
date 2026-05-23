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

VENV_DIR="venv"

SERVICE_NAME="skroutz-price-alert"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

cd "$SCRIPT_DIR"

if ! command -v systemctl > /dev/null 2>&1; then
    printf "%b\n" "${RED}Error: systemctl (systemd) is not installed or not available.${NC}"
    exit 1
fi

# ------------------------------------------------------------------------------
# SYSTEMD CLEANUP
# ------------------------------------------------------------------------------

printf "%b\n" "\n${CYAN}Disabling and removing Systemd Timer and Service...${NC}"

# Stop and disable the timer and service
systemctl --user stop "$SERVICE_NAME.timer" 2>/dev/null || true
systemctl --user disable "$SERVICE_NAME.timer" 2>/dev/null || true
systemctl --user stop "$SERVICE_NAME.service" 2>/dev/null || true
systemctl --user disable "$SERVICE_NAME.service" 2>/dev/null || true
systemctl --user reset-failed "$SERVICE_NAME.service" "$SERVICE_NAME.timer" 2>/dev/null || true

if [ -f "$SYSTEMD_USER_DIR/$SERVICE_NAME.timer" ]; then
    rm "$SYSTEMD_USER_DIR/$SERVICE_NAME.timer"
fi

if [ -f "$SYSTEMD_USER_DIR/$SERVICE_NAME.service" ]; then
    rm "$SYSTEMD_USER_DIR/$SERVICE_NAME.service"
fi

# Reload systemd daemon to apply changes
systemctl --user daemon-reload

printf "%b\n" "${GREEN}Systemd configurations removed successfully.${NC}"

# ------------------------------------------------------------------------------
# PYTHON VIRTUAL ENVIRONMENT CLEANUP
# ------------------------------------------------------------------------------

printf "%b\n" "\n${CYAN}Removing Python virtual environment...${NC}"

if [ -d "$VENV_DIR" ]; then
    rm -rf "$VENV_DIR"
    printf "%b\n" "${GREEN}Python virtual environment ($VENV_DIR) removed.${NC}"
else
    printf "%b\n" "${GREEN}Python virtual environment ($VENV_DIR) already removed.${NC}"
fi

printf "%b\n" "\n${GREEN}Uninstallation complete!${NC}"
printf "%b\n" "\nUser configurations (.env, config/products.json) were NOT removed."
printf "%b\n" "User lingering (loginctl) was left enabled as other services might rely on it.\n"
printf "%b\n" "To re-install the application, run: ${CYAN}./install.sh${NC}"
printf "%b\n" "To completely purge everything, you can safely delete this folder.\n"
