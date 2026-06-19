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

VENV_DIR="venv"

require_systemctl

# ------------------------------------------------------------------------------
# ARGUMENTS
# ------------------------------------------------------------------------------
# Usage:
#   ./scripts/uninstall.sh              Full teardown (all units + venv).
#   ./scripts/uninstall.sh --<plugin>   Remove only that plugin's units (keep venv).

TARGET=""
if [ "$#" -gt 0 ]; then
    case "$1" in
        --*) TARGET="${1#--}" ;;
        *) printf "%b\n" "${RED}Error: Invalid argument: $1${NC}"; exit 1 ;;
    esac
fi

# ------------------------------------------------------------------------------
# SINGLE-PLUGIN REMOVAL
# ------------------------------------------------------------------------------

if [ -n "$TARGET" ]; then
    printf "%b\n" "\n${CYAN}Removing systemd units for '$TARGET'...${NC}"

    disable_one "$TARGET"
    rm -f "$SYSTEMD_USER_DIR/$(unit_name "$TARGET" timer)"
    rm -f "$SYSTEMD_USER_DIR/$(unit_name "$TARGET" service)"
    systemctl --user daemon-reload

    printf "%b\n" "${GREEN}Removed '$TARGET' scraper units.${NC}"
    printf "%b\n" "The virtual environment and any other plugins were left intact.\n"
    exit 0
fi

# ------------------------------------------------------------------------------
# FULL SYSTEMD CLEANUP
# ------------------------------------------------------------------------------
# Glob every installed *-scraper.{timer,service}, so units are removed even for a
# plugin that was already deleted from the source tree. Timers and services are
# handled separately to also catch an orphaned half of a pair.

printf "%b\n" "\n${CYAN}Disabling and removing Systemd Timer(s) and Service(s)...${NC}"

for plugin in $(list_installed_plugins timer); do
    disable_one "$plugin"
    rm -f "$SYSTEMD_USER_DIR/$(unit_name "$plugin" timer)"
done

for plugin in $(list_installed_plugins service); do
    systemctl --user stop "$(unit_name "$plugin" service)" 2>/dev/null || true
    rm -f "$SYSTEMD_USER_DIR/$(unit_name "$plugin" service)"
done

# Reload systemd daemon to apply changes
systemctl --user daemon-reload

printf "%b\n" "${GREEN}Systemd configurations removed successfully.${NC}"

# ------------------------------------------------------------------------------
# PYTHON VIRTUAL ENVIRONMENT CLEANUP
# ------------------------------------------------------------------------------

printf "%b\n" "\n${CYAN}Removing Python virtual environment...${NC}"

if [ -d "$BASE_DIR/$VENV_DIR" ]; then
    rm -rf "$BASE_DIR/$VENV_DIR"
    printf "%b\n" "${GREEN}Python virtual environment ($VENV_DIR) removed.${NC}"
else
    printf "%b\n" "${GREEN}Python virtual environment ($VENV_DIR) already removed.${NC}"
fi

printf "%b\n" "\n${GREEN}Uninstallation complete!${NC}"
printf "%b\n" "\nUser configurations (.env, config/*.json) were NOT removed."
printf "%b\n" "User lingering (loginctl) was left enabled as other services might rely on it.\n"
printf "%b\n" "To re-install the application, run: ${CYAN}./install.sh${NC}"
printf "%b\n" "To completely purge everything, you can safely delete this folder.\n"
