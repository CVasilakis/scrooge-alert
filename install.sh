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
REQUIREMENTS_FILE="requirements.txt"
MAIN_SCRIPT="scripts/run_scraper.sh"

# Cronjob Configurations
CRON_SCHEDULE="0 * * * *"
CRON_DESC="Skroutz_check notification task"


# ==============================================================================
# PREREQUISITES
# ==============================================================================

cd "$SCRIPT_DIR"

if ! command -v python3 > /dev/null 2>&1; then
    printf "%b\n" "${RED}Error: python3 is not installed. Please install it first.${NC}"
    exit 1
fi

if ! python3 -c "import ensurepip" > /dev/null 2>&1; then
    printf "%b\n" "${RED}Error: python3-venv is not installed. Please install it first.${NC}"
    exit 1
fi

if ! command -v crontab > /dev/null 2>&1; then
    printf "%b\n" "${RED}Error: crontab is not installed. Please install it first.${NC}"
    exit 1
fi

# Make the wrapper script executable
chmod +x "$SCRIPT_DIR/$MAIN_SCRIPT"


# ------------------------------------------------------------------------------
# PYTHON VIRTUAL ENVIRONMENT SETUP
# ------------------------------------------------------------------------------

# Initialize or update python virtual environment
if [ ! -d "$VENV_DIR" ]; then
    printf "%b\n" "\n${CYAN}Creating python virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
else
    printf "%b\n" "\n${CYAN}Updating python packages in existing virtual environment...${NC}"
fi

. "$VENV_DIR/bin/activate"

# Safely upgrade pip and install matching requirements
pip install -q --upgrade pip
if [ -f "$REQUIREMENTS_FILE" ]; then
    pip install -q --upgrade -r "$REQUIREMENTS_FILE"
else
    printf "%b\n" "${YELLOW}Warning: $REQUIREMENTS_FILE not found, skipping package installation.${NC}"
fi

deactivate
printf "%b\n" "${GREEN}Python virtual environment successfully created/updated.${NC}"

# ------------------------------------------------------------------------------
# CRONJOB SETUP
# ------------------------------------------------------------------------------

printf "%b\n" "\n${CYAN}Setting up Cronjob...${NC}"

# Execute the wrapper script directly
CRON_CMD="$CRON_SCHEDULE \"$SCRIPT_DIR/$MAIN_SCRIPT\" --silent"
CRON_COMMENT="# ${CRON_DESC} (runs every hour)"

# Capture existing crontab
CURRENT_CRON=$(crontab -l 2>/dev/null || true)

# Remove any existing cronjob and comment for this script (handles directory changes)
if echo "$CURRENT_CRON" | grep -q "$MAIN_SCRIPT"; then
    printf "%b\n" "${CYAN}Found old project cronjob entries. Updating...${NC}"
    # Filter out both the old script command and the associated comment
    CURRENT_CRON=$(echo "$CURRENT_CRON" | grep -v "$MAIN_SCRIPT" | grep -v "$CRON_DESC" || true)
fi

# Append the new cronjob and install
if [ -z "$CURRENT_CRON" ]; then
    (echo "$CRON_COMMENT"; echo "$CRON_CMD") | crontab -
else
    (echo "$CURRENT_CRON"; echo "$CRON_COMMENT"; echo "$CRON_CMD") | crontab -
fi

printf "%b\n" "${GREEN}Cronjob configured successfully.${NC}"

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

printf "%b\n" "\n${GREEN}Installation complete!${NC}"
