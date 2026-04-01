#!/bin/bash
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
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Environment and File Configurations
VENV_DIR="venv"
REQUIREMENTS_FILE="requirements.txt"
MAIN_SCRIPT="skroutz_scrapper.py"

# Cronjob Configurations
CRON_SCHEDULE="0 * * * *"
CRON_DESC="Skroutz_check notification task"


# ==============================================================================
# PREREQUISITES
# ==============================================================================

cd "$SCRIPT_DIR"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed. Please install it first.${NC}"
    exit 1
fi

if ! command -v crontab &> /dev/null; then
    echo -e "${RED}Error: crontab is not installed. Please install it first.${NC}"
    exit 1
fi


# ------------------------------------------------------------------------------
# PYTHON VIRTUAL ENVIRONMENT SETUP
# ------------------------------------------------------------------------------

# Initialize or update python virtual environment
if [ ! -d "$VENV_DIR" ]; then
    echo -e "\n${CYAN}Creating python virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
else
    echo -e "\n${CYAN}Updating python packages in existing virtual environment...${NC}"
fi

source "$VENV_DIR/bin/activate"

# Safely upgrade pip and install matching requirements
pip install -q --upgrade pip
if [ -f "$REQUIREMENTS_FILE" ]; then
    pip install -q --upgrade -r "$REQUIREMENTS_FILE"
else
    echo -e "${YELLOW}Warning: $REQUIREMENTS_FILE not found, skipping package installation.${NC}"
fi

deactivate


# ------------------------------------------------------------------------------
# CRONJOB SETUP
# ------------------------------------------------------------------------------

echo -e "\n${CYAN}Setting up Cronjob...${NC}"

CRON_CMD="$CRON_SCHEDULE $SCRIPT_DIR/$VENV_DIR/bin/python $SCRIPT_DIR/$MAIN_SCRIPT"
CRON_COMMENT="# ${CRON_DESC} (run based on schedule: ${CRON_SCHEDULE})"

# Capture existing crontab
CURRENT_CRON=$(crontab -l 2>/dev/null || true)

# Remove any existing cronjob and comment for this script (handles directory changes)
if echo "$CURRENT_CRON" | grep -q "$MAIN_SCRIPT"; then
    echo -e "${YELLOW}Found old cronjob entries. Updating...${NC}"
    # Filter out both the old script command and the associated comment
    CURRENT_CRON=$(echo "$CURRENT_CRON" | grep -v "$MAIN_SCRIPT" | grep -v "$CRON_DESC" || true)
fi

# Append the new cronjob and install
if [ -z "$CURRENT_CRON" ]; then
    (echo "$CRON_COMMENT"; echo "$CRON_CMD") | crontab -
else
    (echo "$CURRENT_CRON"; echo "$CRON_COMMENT"; echo "$CRON_CMD") | crontab -
fi

echo -e "${GREEN}Cronjob configured successfully.${NC}"

echo -e "\n${GREEN}Installation complete!${NC}"

