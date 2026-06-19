#!/bin/sh
set -eu

# ==============================================================================
# GLOBAL VARIABLES
# ==============================================================================

# Automatically get the directory where the script is located (repository root)
SCRIPT_DIR="$( cd "$( dirname "$0" )" >/dev/null 2>&1 && pwd )"
BASE_DIR="$SCRIPT_DIR"

# Shared helpers (colors, plugin enumeration, systemd helpers)
. "$SCRIPT_DIR/scripts/lib/common.sh"

# Environment and File Configurations
VENV_DIR="venv"
REQUIREMENTS_FILE="requirements.txt"

# ==============================================================================
# ARGUMENTS
# ==============================================================================
# Usage:
#   ./install.sh                        Install everything and provision every plugin.
#   ./install.sh --<plugin> [...]       (Re)provision and enable only the named plugin(s).
#   ./install.sh --update [<plugin>..]  Invoked by update.sh (quiet banner). Reprovisions
#                                       only the named plugins (the set update.sh derived
#                                       from the already-installed units), or every plugin
#                                       when none are named. Plugins that no longer exist in
#                                       the registry (removed/renamed in the new version) are
#                                       skipped instead of aborting the update.

INSTALL_MODE="all"   # all | selected
IS_UPDATE=0
SELECTED=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --update)
            IS_UPDATE=1
            ;;
        --*)
            INSTALL_MODE="selected"
            SELECTED="$SELECTED ${1#--}"
            ;;
        *)
            printf "%b\n" "${RED}Error: Invalid argument: $1${NC}"
            exit 1
            ;;
    esac
    shift
done

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

require_systemctl

# Make the management scripts executable (lib/common.sh is sourced, not executed,
# so the scripts/*.sh glob deliberately skips the scripts/lib/ subdirectory).
for s in "$BASE_DIR"/install.sh "$BASE_DIR"/update.sh "$BASE_DIR"/scripts/*.sh; do
    [ -e "$s" ] || continue
    chmod +x "$s"
done


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
# PLUGIN DISCOVERY
# ------------------------------------------------------------------------------
# The venv now exists, so the registry can be queried (the single source of truth
# for which scrapers exist). One systemd unit pair is generated per plugin.

ALL_PLUGINS="$(list_plugins || true)"
if [ -z "$ALL_PLUGINS" ]; then
    printf "%b\n" "${RED}Error: Failed to enumerate scraper plugins. The virtual environment may be broken.${NC}\n"
    exit 1
fi

if [ "$INSTALL_MODE" = "selected" ]; then
    PLUGINS=""
    for sel in $SELECTED; do
        if plugin_in_list "$sel" $ALL_PLUGINS; then
            PLUGINS="$PLUGINS $sel"
        elif [ "$IS_UPDATE" -eq 1 ]; then
            # During an update the selection is derived from the installed units;
            # a plugin removed or renamed in the incoming version is no longer in
            # the registry. Skip it (its orphaned unit was already stopped by
            # update.sh; uninstall clears it) rather than aborting the whole update.
            printf "%b\n" "${YELLOW}Note: Skipping '$sel' - no longer a registered scraper in this version.${NC}"
            printf "%b\n" "${YELLOW}      Its leftover units can be removed with: ${CYAN}./scripts/uninstall.sh --$sel${NC}"
        else
            printf "%b\n" "${RED}Error: Unknown plugin '$sel'.${NC}"
            printf "%b\n" "Available plugins: ${CYAN}$(printf '%s ' $ALL_PLUGINS)${NC}"
            exit 1
        fi
    done
else
    PLUGINS="$ALL_PLUGINS"
fi

# ------------------------------------------------------------------------------
# PER-PLUGIN DEPENDENCIES
# ------------------------------------------------------------------------------
# The root requirements.txt installed above carries only the core framework. Each
# plugin may ship its own requirements.txt (next to its plugin.py) listing the
# transport/parsing libraries only it needs (e.g. tls-client, selenium). Only the
# requirements of the plugin(s) being provisioned are installed, so an install
# that skips a heavy scraper never pulls that scraper's dependencies.

PLUGIN_REQS="$(list_plugin_requirements || true)"
OLD_IFS="$IFS"
IFS='
'
for pair in $PLUGIN_REQS; do
    req_name="${pair%% *}"
    req_path="${pair#* }"
    plugin_in_list "$req_name" $PLUGINS || continue

    printf "%b\n" "${CYAN}Installing dependencies for the '$req_name' scraper...${NC}"
    if ! "$VENV_DIR/bin/python3" -m pip install -q --upgrade -r "$req_path"; then
        IFS="$OLD_IFS"
        printf "%b\n" "${RED}Error: Failed to install dependencies for the '$req_name' scraper.${NC}\n"
        exit 1
    fi
done
IFS="$OLD_IFS"

# ------------------------------------------------------------------------------
# SYSTEMD SETUP
# ------------------------------------------------------------------------------

printf "%b\n" "\n${CYAN}Setting up Systemd timer(s)...${NC}"

mkdir -p "$SYSTEMD_USER_DIR"

# Each plugin declares only its own [Timer] *trigger* (cadence) via
# plugin.get_timer_directives(); RandomizedDelaySec and Persistent are
# framework-managed (hardcoded in the timer below, identically for every plugin)
# and the [Service] dispatches identically through run.sh. Fetched once, then
# filtered per plugin.
TAB="$(printf '\t')"
ALL_TIMER_DIRECTIVES="$(list_plugin_timer_directives || true)"

for plugin in $PLUGINS; do
    service_file="$SYSTEMD_USER_DIR/$(unit_name "$plugin" service)"
    timer_file="$SYSTEMD_USER_DIR/$(unit_name "$plugin" timer)"

    # Collect this plugin's [Timer] trigger directives (one "Key=Value" per line).
    timer_directives=""
    OLD_IFS="$IFS"
    IFS='
'
    for line in $ALL_TIMER_DIRECTIVES; do
        [ "${line%%"$TAB"*}" = "$plugin" ] || continue
        directive="${line#*"$TAB"}"
        # RandomizedDelaySec and Persistent are framework-managed (hardcoded
        # below), not plugin-configurable; drop any a plugin tries to set.
        case "$directive" in
            RandomizedDelaySec=*|Persistent=*) continue ;;
        esac
        timer_directives="$timer_directives$directive
"
    done
    IFS="$OLD_IFS"

    if [ -z "$timer_directives" ]; then
        printf "%b\n" "${RED}Error: Plugin '$plugin' declares no [Timer] directives.${NC}\n"
        exit 1
    fi

    cat > "$service_file" << EOF
[Unit]
Description=Scrooge Alert notification task for $plugin

[Service]
Type=oneshot
WorkingDirectory=$BASE_DIR
ExecStart="$BASE_DIR/scripts/run.sh" --quiet --$plugin
EOF

    cat > "$timer_file" << EOF
[Unit]
Description=Run $plugin scraper

[Timer]
${timer_directives}RandomizedDelaySec=180s
Persistent=true

[Install]
WantedBy=timers.target
EOF

    if [ ! -f "$service_file" ] || [ ! -f "$timer_file" ]; then
        printf "%b\n" "${RED}Error: Failed to create systemd configuration files for '$plugin'.${NC}\n"
        exit 1
    fi
done

systemctl --user daemon-reload

for plugin in $PLUGINS; do
    enable_one "$plugin"
done

if command -v loginctl >/dev/null 2>&1; then
    if [ "$(loginctl show-user "$USER" --property=Linger 2>/dev/null)" != "Linger=yes" ]; then
        printf "%b\n" "${CYAN}Enabling user lingering to allow timer to run when logged out...${NC}"
        loginctl enable-linger "$USER"
    fi
fi

printf "%b\n" "${GREEN}Systemd timer(s) configured successfully.${NC}"

# ------------------------------------------------------------------------------
# LAST CHECKS
# ------------------------------------------------------------------------------
# Report any plugin whose products config file is still missing (non-fatal), and
# whether the shared .env is missing. Config filenames come from each plugin
# descriptor, so this stays correct as plugins are added.

MISSING_CONFIGS=""
CONFIG_PAIRS="$(list_plugin_configs || true)"
OLD_IFS="$IFS"
IFS='
'
for pair in $CONFIG_PAIRS; do
    pair_name="${pair%% *}"
    pair_cfg="${pair#* }"
    plugin_in_list "$pair_name" $PLUGINS || continue
    [ -f "config/$pair_cfg" ] || MISSING_CONFIGS="$MISSING_CONFIGS $pair_cfg"
done
IFS="$OLD_IFS"

ENV_MISSING=0
[ -f ".env" ] || ENV_MISSING=1

if [ -n "$MISSING_CONFIGS" ] || [ "$ENV_MISSING" -eq 1 ]; then
    printf "%b\n" "\n${YELLOW}Note: Configuration required!${NC}"

    for cfg in $MISSING_CONFIGS; do
        printf "%b\n" "- Copy config/$cfg.example to config/$cfg"
        printf "%b\n" "  and fill it with your desired products."
    done

    if [ "$ENV_MISSING" -eq 1 ]; then
        printf "%b\n" "- Copy .env.example to .env"
        printf "%b\n" "  and configure your apprise notification URLs."
    fi

    printf "%b\n" "- Read the README.md file for more information."
fi

if [ "$IS_UPDATE" -eq 0 ]; then
    printf "%b\n" "\n${GREEN}Installation complete!${NC}\n"
fi
