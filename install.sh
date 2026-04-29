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

# Automatically get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "$0" )" >/dev/null 2>&1 && pwd )"

# Environment and File Configurations
VENV_DIR="venv"
REQUIREMENTS_FILE="requirements.txt"
MAIN_SCRIPT="scripts/run_scraper.sh"

# Systemd Configurations
SERVICE_NAME="skroutz-price-alert"
SERVICE_DESC="Skroutz Price Alert notification task"


# ==============================================================================
# PREREQUISITES
# ==============================================================================

cd "$SCRIPT_DIR"

if ! command -v python3 > /dev/null 2>&1; then
    printf "%b\n" "${RED}Error: python3 is not installed. Please install it first.${NC}"
    exit 1
fi

if ! python3 -c "import ensurepip" > /dev/null 2>&1; then
    printf "%b\n" "${RED}Error: The python venv module is not available. Please install it first.${NC}"
    exit 1
fi

if ! command -v systemctl > /dev/null 2>&1; then
    printf "%b\n" "${RED}Error: systemctl (systemd) is not installed or not available. Please install it first.${NC}"
    exit 1
fi

# Make the scripts executable
if [ -f "$SCRIPT_DIR/$MAIN_SCRIPT" ]; then
    chmod +x "$SCRIPT_DIR/$MAIN_SCRIPT"
fi
if [ -f "$SCRIPT_DIR/uninstall.sh" ]; then
    chmod +x "$SCRIPT_DIR/uninstall.sh"
fi
if [ -f "$SCRIPT_DIR/update.sh" ]; then
    chmod +x "$SCRIPT_DIR/update.sh"
fi


# ------------------------------------------------------------------------------
# PYTHON VIRTUAL ENVIRONMENT SETUP
# ------------------------------------------------------------------------------

# Initialize or update python virtual environment
VENV_NEWLY_CREATED=false
if [ ! -d "$VENV_DIR" ]; then
    printf "%b\n" "\n${CYAN}Creating python virtual environment...${NC}"
    if ! python3 -m venv "$VENV_DIR"; then
        printf "%b\n" "${RED}Error: Failed to create python virtual environment.${NC}\n"
        exit 1
    fi
    VENV_NEWLY_CREATED=true
else
    printf "%b\n" "\n${CYAN}Updating python packages in existing virtual environment...${NC}"
fi

# Safely upgrade pip and install matching requirements
if ! "$VENV_DIR/bin/python3" -m pip install -q --upgrade pip; then
    printf "%b\n" "${RED}Error: Failed to upgrade pip in the virtual environment.${NC}\n"
    exit 1
fi

if [ -f "$REQUIREMENTS_FILE" ]; then
    if ! "$VENV_DIR/bin/python3" -m pip install -q --upgrade -r "$REQUIREMENTS_FILE"; then
        printf "%b\n" "${RED}Error: Failed to install packages from $REQUIREMENTS_FILE.${NC}\n"
        exit 1
    fi
else
    printf "%b\n" "${RED}Error: $REQUIREMENTS_FILE not found. The script cannot run without its dependencies.${NC}\n"
    exit 1
fi

if [ "$VENV_NEWLY_CREATED" = true ]; then
    printf "%b\n" "${GREEN}Python virtual environment successfully created.${NC}"
else
    printf "%b\n" "${GREEN}Python virtual environment successfully updated.${NC}"
fi

# ------------------------------------------------------------------------------
# SYSTEMD SETUP
# ------------------------------------------------------------------------------

SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if [ -f "$SYSTEMD_USER_DIR/$SERVICE_NAME.service" ] && [ -f "$SYSTEMD_USER_DIR/$SERVICE_NAME.timer" ]; then
    printf "%b\n" "\n${CYAN}Updating Systemd Timer...${NC}"
else
    printf "%b\n" "\n${CYAN}Setting up Systemd Timer...${NC}"
fi

mkdir -p "$SYSTEMD_USER_DIR"

cat > "$SYSTEMD_USER_DIR/$SERVICE_NAME.service" << EOF
[Unit]
Description=$SERVICE_DESC

[Service]
Type=oneshot
WorkingDirectory=$SCRIPT_DIR
ExecStart="$SCRIPT_DIR/$MAIN_SCRIPT" --silent
EOF

cat > "$SYSTEMD_USER_DIR/$SERVICE_NAME.timer" << EOF
[Unit]
Description=Run $SERVICE_NAME hourly

[Timer]
OnCalendar=hourly
RandomizedDelaySec=60s
Persistent=true

[Install]
WantedBy=timers.target
EOF

if [ -f "$SYSTEMD_USER_DIR/$SERVICE_NAME.service" ] && [ -f "$SYSTEMD_USER_DIR/$SERVICE_NAME.timer" ]; then
    systemctl --user daemon-reload
    systemctl --user enable --now "$SERVICE_NAME.timer" >/dev/null 2>&1
else
    printf "%b\n" "${RED}Error: Failed to create systemd configuration files.${NC}\n"
    exit 1
fi

if command -v loginctl >/dev/null 2>&1; then
    if [ "$(loginctl show-user "$USER" --property=Linger 2>/dev/null)" != "Linger=yes" ]; then
        printf "%b\n" "${CYAN}Enabling user lingering to allow timer to run when logged out...${NC}"
        loginctl enable-linger "$USER"
    fi
fi

printf "%b\n" "${GREEN}Systemd timer configured successfully.${NC}"

# ------------------------------------------------------------------------------
# LAST CHECKS
# ------------------------------------------------------------------------------

if [ ! -f "data/products.json" ] || [ ! -f ".env" ]; then
    printf "%b\n" "\n${YELLOW}Note: Configuration required!${NC}"
fi

if [ ! -f "data/products.json" ]; then
    printf "%b\n" "- Copy data/products.json.example to data/products.json"
    printf "%b\n" "  and fill it with your desired products."
fi

if [ ! -f ".env" ]; then
    printf "%b\n" "- Copy .env.example to .env"
    printf "%b\n" "  and configure your apprise notification URLs."
fi

if [ ! -f "data/products.json" ] || [ ! -f ".env" ]; then
    printf "%b\n" "- Read the README.md file for more information."
fi

if [ "${1:-}" != "--update" ]; then
    printf "%b\n" "\n${GREEN}Installation complete!${NC}\n"
fi
