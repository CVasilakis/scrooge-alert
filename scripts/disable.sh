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
# With no flag, disable every plugin's timer; with --<plugin>, disable just that
# one. Disabling falls back to installed units so it still works when the venv is
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
    # still has an installed timer (e.g. a leftover from a plugin removed upstream);
    # reject only a name in neither set.
    if ! is_known_target "$TARGET" timer; then
        printf "%b\n" "${RED}Error: Unknown plugin '$TARGET'.${NC}"
        printf "%b\n" "Available plugins: ${CYAN}$(printf '%s ' $(known_targets timer))${NC}"
        exit 1
    fi
    PLUGINS="$TARGET"
else
    PLUGINS="$(all_targets timer)"
fi

if [ -z "$PLUGINS" ]; then
    printf "%b\n" "\n${GREEN}No scraper timers found. Nothing to do.${NC}\n"
    exit 0
fi

# ------------------------------------------------------------------------------
# DISABLING SERVICE(S)
# ------------------------------------------------------------------------------
# A plugin's service has no [Install] section (it is driven by its timer), so it
# is never "enabled". Work is only needed when the timer is enabled/active or the
# service is currently executing.

for plugin in $PLUGINS; do
    timer_enabled="$(timer_is_enabled "$plugin")"
    timer_active="$(timer_is_active "$plugin")"
    svc_state="$(service_state "$plugin")"

    if [ "$timer_enabled" != "enabled" ] && [ "$timer_active" != "active" ] && \
       [ "$svc_state" != "active" ] && [ "$svc_state" != "activating" ]; then
        printf "%b\n" "\n${GREEN}[$plugin] Background service and timer are already disabled. Nothing to do.${NC}"
        continue
    fi

    printf "%b\n" "\n${CYAN}[$plugin] Stopping and disabling background schedule (timer)...${NC}"
    disable_one "$plugin"
    printf "%b\n" "${GREEN}[$plugin] Background execution disabled successfully.${NC}"
done

printf "%b\n" "\nTo re-enable background execution, run: ${CYAN}./scripts/enable.sh${NC}"
printf "%b\n" "To completely remove the application, run: ${CYAN}./scripts/uninstall.sh${NC}\n"
