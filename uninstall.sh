#!/bin/sh
set -e

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

# Automatically get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "$0" )" >/dev/null 2>&1 && pwd )"

# Environment and File Configurations
VENV_DIR="venv"

# Systemd Configurations
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

printf "%b\n" "\n${CYAN}Stopping and disabling Systemd Timer and Service...${NC}"

# Stop and disable the timer and service
systemctl --user stop "$SERVICE_NAME.timer" 2>/dev/null || true
systemctl --user disable "$SERVICE_NAME.timer" 2>/dev/null || true
systemctl --user stop "$SERVICE_NAME.service" 2>/dev/null || true
systemctl --user disable "$SERVICE_NAME.service" 2>/dev/null || true

printf "%b\n" "${CYAN}Removing Systemd configuration files...${NC}"

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
    printf "%b\n" "${YELLOW}Virtual environment not found, skipping.${NC}"
fi

# ------------------------------------------------------------------------------
# DATA FOLDER NOTE
# ------------------------------------------------------------------------------
printf "%b\n" "\n${YELLOW}Note: Your data folder (products.json) and .env file have NOT been removed.${NC}"
printf "%b\n" "If you wish to completely remove all data, you can manually delete them:"
printf "%b\n" "  rm -rf data/ .env"

printf "%b\n" "\n${GREEN}Uninstallation complete!${NC}"