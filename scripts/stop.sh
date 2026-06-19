#!/bin/sh
set -eu

# ==============================================================================
# GLOBAL VARIABLES
# ==============================================================================

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "$0" )" >/dev/null 2>&1 && pwd )"
BASE_DIR="$( dirname "$SCRIPT_DIR" )"

# Shared helpers (colors, plugin enumeration, systemd helpers)
. "$SCRIPT_DIR/lib/common.sh"

cd "$SCRIPT_DIR"

require_systemctl

# ------------------------------------------------------------------------------
# TARGET RESOLUTION
# ------------------------------------------------------------------------------
# With no flag, stop every plugin's running service; with --<plugin>, stop just
# that one. Falls back to installed units so it still works when the venv is
# missing or a plugin was removed from the source tree.

TARGET=""
if [ "$#" -gt 0 ]; then
    case "$1" in
        --*) TARGET="${1#--}" ;;
        *) printf "%b\n" "${RED}Error: Invalid argument: $1${NC}"; exit 1 ;;
    esac
fi

if [ -n "$TARGET" ]; then
    # Teardown acts on installed units, so accept a plugin that is registered OR
    # still has an installed service (e.g. a leftover from a plugin removed upstream);
    # reject only a name in neither set.
    if ! is_known_target "$TARGET" service; then
        printf "%b\n" "${RED}Error: Unknown plugin '$TARGET'.${NC}"
        printf "%b\n" "Available plugins: ${CYAN}$(printf '%s ' $(known_targets service))${NC}"
        exit 1
    fi
    PLUGINS="$TARGET"
else
    PLUGINS="$(all_targets service)"
fi

if [ -z "$PLUGINS" ]; then
    printf "%b\n" "\n${GREEN}No scraper services found. Nothing to stop.${NC}\n"
    exit 0
fi

# ------------------------------------------------------------------------------
# STOPPING SERVICE(S)
# ------------------------------------------------------------------------------
# For Type=oneshot services, the state is 'activating' while the script is running.

for plugin in $PLUGINS; do
    state="$(service_state "$plugin")"
    if [ "$state" = "active" ] || [ "$state" = "activating" ]; then
        printf "%b\n" "\n${CYAN}[$plugin] Stopping active background execution...${NC}"
        stop_one "$plugin"
        printf "%b\n" "${GREEN}[$plugin] Active background execution stopped successfully.${NC}"
    else
        printf "%b\n" "\n${GREEN}[$plugin] No active background execution detected. Nothing to stop.${NC}"
    fi
done

printf "%b\n" "\nTo disable future background executions, run: ${CYAN}./scripts/disable.sh${NC}"
printf "%b\n" "To completely remove the application, run: ${CYAN}./scripts/uninstall.sh${NC}\n"
