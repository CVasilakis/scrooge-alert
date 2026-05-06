#!/bin/sh
set -eu

main() {
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

    # ==============================================================================
    # EXECUTION
    # ==============================================================================

    printf "%b\n" "\n${CYAN}Updating Skroutz Price Alert...${NC}"

    cd "$SCRIPT_DIR"

    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    IS_DIRTY=$(git status --porcelain)

    if [ -n "$IS_DIRTY" ]; then
        printf "%b\n" "\n${YELLOW}Uncommitted modifications detected in your working directory.${NC}"
        printf "%b\n" "${YELLOW}This update will reset to the remote 'main' branch and discard any uncommitted changes${NC}."
        printf "%b\n" "${YELLOW}Please commit or stash your work before proceeding to avoid data loss.${NC}"
        printf "Do you want to proceed and discard these changes? [y/N]: "
        read -r response
        case "$response" in
            [Yy]* ) ;;
            * ) printf "%b\n" "\n${RED}Update aborted by the user.${NC}\n"; exit 1 ;;
        esac
    elif [ "$CURRENT_BRANCH" != "main" ]; then
        printf "%b\n" "\n${YELLOW}Switching from branch '${CURRENT_BRANCH}' to 'main'.${NC}"
    fi

    if ! git checkout -f main --quiet; then
        printf "%b\n" "\n${RED}Error: Failed to checkout 'main' branch. Update aborted.${NC}\n"
        exit 1
    fi

    if ! git fetch --all --quiet; then
        printf "%b\n" "\n${RED}Error: Failed to fetch latest changes from the repository. Update aborted.${NC}\n"
        exit 1
    fi

    if ! git reset --hard origin/main --quiet; then
        printf "%b\n" "\n${RED}Error: Failed to reset to origin/main. Update aborted.${NC}\n"
        exit 1
    fi

    if [ -f "$SCRIPT_DIR/install.sh" ]; then
        chmod +x "$SCRIPT_DIR/install.sh"
        if ! "$SCRIPT_DIR/install.sh" --update; then
            printf "%b\n" "\n${RED}Error: Installation failed during update. Please run ./install.sh manually.${NC}\n"
            exit 1
        fi
    fi

    printf "%b\n" "\n${GREEN}Update complete! You are now running the latest version.${NC}\n"

    # Exit immediately to prevent the shell from reading any new lines
    # if this script was modified by 'git pull'
    exit 0
}

main "$@"
