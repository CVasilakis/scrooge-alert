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
# With no flag, enable every plugin's timer; with --<plugin>, enable just that
# one. Enabling requires the registry: you can only enable a plugin that exists
# and was provisioned by install.sh.

TARGET=""
if [ "$#" -gt 0 ]; then
    case "$1" in
        --*) TARGET="${1#--}" ;;
        *) printf "%b\n" "${RED}Error: Invalid argument: $1${NC}"; exit 1 ;;
    esac
fi

ALL_PLUGINS="$(list_plugins || true)"
if [ -z "$ALL_PLUGINS" ]; then
    printf "%b\n" "${RED}Error: Failed to enumerate scraper plugins. Run ./install.sh first.${NC}"
    exit 1
fi

if [ -n "$TARGET" ]; then
    if ! plugin_in_list "$TARGET" $ALL_PLUGINS; then
        printf "%b\n" "${RED}Error: Unknown plugin '$TARGET'.${NC}"
        printf "%b\n" "Available plugins: ${CYAN}$(printf '%s ' $ALL_PLUGINS)${NC}"
        exit 1
    fi
    PLUGINS="$TARGET"
else
    PLUGINS="$ALL_PLUGINS"
fi

# ------------------------------------------------------------------------------
# ENABLING SERVICE(S)
# ------------------------------------------------------------------------------

for plugin in $PLUGINS; do
    if [ "$(timer_is_enabled "$plugin")" = "enabled" ] && [ "$(timer_is_active "$plugin")" = "active" ]; then
        printf "%b\n" "\n${GREEN}[$plugin] Timer is already enabled and active. Nothing to do.${NC}"
        continue
    fi

    printf "%b\n" "\n${CYAN}[$plugin] Enabling and starting background schedule (timer)...${NC}"
    if enable_one "$plugin"; then
        printf "%b\n" "${GREEN}[$plugin] Background execution enabled successfully.${NC}"
    else
        printf "%b\n" "${RED}[$plugin] Error: Failed to enable the timer!${NC}"
        printf "%b\n" "${RED}Try running ./install.sh to fix the issue.${NC}\n"
        exit 1
    fi
done

printf "%b\n" "\nTo disable background execution, run: ${CYAN}./scripts/disable.sh${NC}"
printf "%b\n" "To completely remove the application, run: ${CYAN}./scripts/uninstall.sh${NC}\n"
