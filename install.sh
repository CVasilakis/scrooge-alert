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
#   ./install.sh              Install everything and provision every plugin.
#   ./install.sh --update     Like above, but invoked by update.sh (quiet banner).
#   ./install.sh --<plugin>   (Re)provision and enable only that plugin's unit.

INSTALL_MODE="all"   # all | single
IS_UPDATE=0
TARGET=""

if [ "$#" -gt 0 ]; then
    case "$1" in
        --update)
            IS_UPDATE=1
            ;;
        --*)
            INSTALL_MODE="single"
            TARGET="${1#--}"
            ;;
        *)
            printf "%b\n" "${RED}Error: Invalid argument: $1${NC}"
            exit 1
            ;;
    esac
fi

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

if [ "$INSTALL_MODE" = "single" ]; then
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
# SYSTEMD SETUP
# ------------------------------------------------------------------------------

printf "%b\n" "\n${CYAN}Setting up Systemd timer(s)...${NC}"

mkdir -p "$SYSTEMD_USER_DIR"

for plugin in $PLUGINS; do
    service_file="$SYSTEMD_USER_DIR/$(unit_name "$plugin" service)"
    timer_file="$SYSTEMD_USER_DIR/$(unit_name "$plugin" timer)"

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
Description=Run $plugin scraper hourly

[Timer]
OnCalendar=hourly
RandomizedDelaySec=300s
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
