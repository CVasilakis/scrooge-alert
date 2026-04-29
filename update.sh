#!/bin/sh
set -eu

main() {
    # ==============================================================================
    # COLORS
    # ==============================================================================
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    CYAN='\033[0;36m'
    NC='\033[0m' # No Color

    # ==============================================================================
    # GLOBAL VARIABLES
    # ==============================================================================

    # Automatically get the directory where the script is located
    SCRIPT_DIR="$( cd "$( dirname "$0" )" >/dev/null 2>&1 && pwd )"

    # ==============================================================================
    # EXECUTION
    # ==============================================================================

    cd "$SCRIPT_DIR"

    printf "%b\n" "\n${CYAN}Updating Skroutz Price Alert...${NC}"

    if ! git pull; then
        printf "%b\n" "\n${RED}Error: Failed to pull latest changes from the repository. Update aborted.${NC}\n"
        exit 1
    fi

    if [ -f "$SCRIPT_DIR/install.sh" ]; then
        chmod +x "$SCRIPT_DIR/install.sh"
        if ! "$SCRIPT_DIR/install.sh" --update; then
            printf "%b\n" "\n${RED}Error: Installation failed after update. Please run ./install.sh manually.${NC}\n"
            exit 1
        fi
    fi

    printf "%b\n" "\n${GREEN}Update complete! You are now running the latest version.${NC}\n"

    # Exit immediately to prevent the shell from reading any new lines
    # if this script was modified by 'git pull'
    exit 0
}

main "$@"
