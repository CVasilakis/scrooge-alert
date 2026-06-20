#!/bin/sh
# ==============================================================================
# common.sh - shared POSIX sh helpers for the Scrooge Alert management scripts.
#
# This file is meant to be SOURCED (with the POSIX `.` builtin), never executed:
#
#     . "$SCRIPT_DIR/lib/common.sh"          # from scripts/*.sh
#     . "$SCRIPT_DIR/scripts/lib/common.sh"  # from root install.sh / update.sh
#
# Caller contract: define BASE_DIR (the repository root) BEFORE sourcing.
# This file intentionally does NOT set `set -eu` (the sourcing script owns its
# shell options) and uses no `local` (a bashism); helper-internal variables use
# unique names to avoid clobbering the caller's scope.
# ==============================================================================

# ------------------------------------------------------------------------------
# COLORS
# ------------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

# ------------------------------------------------------------------------------
# ENVIRONMENT CHECKS
# ------------------------------------------------------------------------------

# Abort with an error if systemctl (systemd) is not available.
require_systemctl() {
    if ! command -v systemctl > /dev/null 2>&1; then
        printf "%b\n" "${RED}Error: systemctl (systemd) is not installed or not available.${NC}"
        exit 1
    fi
}

# ------------------------------------------------------------------------------
# PLUGIN / UNIT NAMING
# ------------------------------------------------------------------------------

# unit_name <plugin> <suffix>  ->  "<plugin>-scraper.<suffix>"
# This is the same convention status.py uses to locate per-plugin systemd units.
unit_name() {
    printf '%s-scraper.%s' "$1" "$2"
}

# plugin_in_list <needle> <item>...  ->  returns 0 if <needle> is one of the items.
# Call unquoted to split a space/newline list, e.g. plugin_in_list "$x" $PLUGINS
plugin_in_list() {
    _needle="$1"
    shift
    for _item in "$@"; do
        [ "$_item" = "$_needle" ] && return 0
    done
    return 1
}

# ------------------------------------------------------------------------------
# PLUGIN ENUMERATION
# ------------------------------------------------------------------------------

# list_plugins: print the machine name of every registered plugin, one per line,
# by querying the ScraperRegistry (the single source of truth). Requires the venv,
# but plugin discovery only imports each plugin's lightweight descriptor (plugin.py)
# - never its client/storage or transport libraries (tls_client, selenium, ...),
# which load lazily only when a scrape actually runs. Returns non-zero (printing
# nothing) if the venv is unavailable, so callers can fall back to
# list_installed_plugins.
list_plugins() {
    [ -x "$BASE_DIR/venv/bin/python3" ] || return 1
    PYTHONPATH="$BASE_DIR/src/core" "$BASE_DIR/venv/bin/python3" - 2>/dev/null <<'PY'
from scrapers.registry import ScraperRegistry
for target in ScraperRegistry.registered_targets():
    print(target)
PY
}

# list_plugin_configs: print "<plugin> <config_filename>" for every registered
# plugin (one pair per line), reusing plugin.get_config_filename(). Same venv
# requirement as list_plugins.
list_plugin_configs() {
    [ -x "$BASE_DIR/venv/bin/python3" ] || return 1
    PYTHONPATH="$BASE_DIR/src/core" "$BASE_DIR/venv/bin/python3" - 2>/dev/null <<'PY'
from scrapers.registry import ScraperRegistry
for target in ScraperRegistry.registered_targets():
    print(target, ScraperRegistry.get_plugin(target).get_config_filename())
PY
}

# list_plugin_requirements: print "<plugin> <abs_requirements_path>" for every
# registered plugin that ships its own requirements.txt (one pair per line),
# reusing plugin.get_requirements_path(). Plugins with no extra dependencies are
# omitted. The path is absolute, so it installs regardless of cwd. Same venv
# requirement as list_plugins.
list_plugin_requirements() {
    [ -x "$BASE_DIR/venv/bin/python3" ] || return 1
    PYTHONPATH="$BASE_DIR/src/core" "$BASE_DIR/venv/bin/python3" - 2>/dev/null <<'PY'
from scrapers.registry import ScraperRegistry
for target in ScraperRegistry.registered_targets():
    path = ScraperRegistry.get_plugin(target).get_requirements_path()
    if path:
        print(target, path)
PY
}

# list_plugin_timer_directives: print "<plugin><TAB><Key>=<Value>" for every
# systemd [Timer] directive of every registered plugin (one per line), from
# plugin.get_timer_directives(). The plugin name is machine-readable (no
# whitespace), so a literal tab cleanly separates it from the directive, whose
# value may itself contain spaces (e.g. an OnCalendar like "*-*-* 06:00:00").
# Same venv requirement as list_plugins.
list_plugin_timer_directives() {
    [ -x "$BASE_DIR/venv/bin/python3" ] || return 1
    PYTHONPATH="$BASE_DIR/src/core" "$BASE_DIR/venv/bin/python3" - 2>/dev/null <<'PY'
from scrapers.registry import ScraperRegistry
for target in ScraperRegistry.registered_targets():
    for key, value in ScraperRegistry.get_plugin(target).get_timer_directives().items():
        print(f"{target}\t{key}={value}")
PY
}

# list_installed_plugins <suffix>: print the plugin name behind every installed
# "<plugin>-scraper.<suffix>" unit file in SYSTEMD_USER_DIR (<suffix> is "service"
# or "timer"). Glob based, so it needs no venv and still finds units whose plugin
# was deleted from the source tree - essential for robust teardown.
list_installed_plugins() {
    _suffix="$1"
    for _f in "$SYSTEMD_USER_DIR"/*-scraper."$_suffix"; do
        [ -e "$_f" ] || continue   # POSIX sh has no nullglob: skip the literal pattern
        _base="${_f##*/}"                       # strip directory
        printf '%s\n' "${_base%-scraper.$_suffix}"  # strip "-scraper.<suffix>"
    done
}

# known_targets <suffix>: print every plugin a teardown command may act on - the
# union of registered plugins and installed "<plugin>-scraper.<suffix>" units -
# one per line, de-duplicated, preserving first-seen order. It is the validation
# set for an explicit --<plugin> (the name only has to resolve to something a
# teardown can act on), so a plugin removed from the source tree but still
# installed continues to appear. The no-flag set is narrower: the teardown scripts
# act on the installed units alone (list_installed_plugins), since a registered
# plugin that was never installed has nothing to stop/disable/remove.
known_targets() {
    _seen=" "
    for _t in $(list_plugins) $(list_installed_plugins "$1"); do
        case "$_seen" in
            *" $_t "*) ;;                          # already emitted
            *) _seen="$_seen$_t "; printf '%s\n' "$_t" ;;
        esac
    done
}

# is_known_target <plugin> <suffix>: succeed if <plugin> is a registered plugin
# OR has an installed "<plugin>-scraper.<suffix>" unit. The membership test for
# the teardown commands (disable/stop/uninstall): they only need a unit to act
# on, so they accept this union, whereas install/enable validate against the
# registry alone (they need code to run). A name in neither set is a real typo.
is_known_target() {
    plugin_in_list "$1" $(known_targets "$2")
}

# ------------------------------------------------------------------------------
# SYSTEMD UNIT STATE QUERIES
# ------------------------------------------------------------------------------

# timer_is_enabled <plugin> / timer_is_active <plugin>: echo the systemctl verdict
# ("enabled"/"active"/"" etc.) for that plugin's timer.
timer_is_enabled() {
    systemctl --user is-enabled "$(unit_name "$1" timer)" 2>/dev/null || true
}
timer_is_active() {
    systemctl --user is-active "$(unit_name "$1" timer)" 2>/dev/null || true
}

# service_state <plugin>: echo the ActiveState of that plugin's service
# (e.g. "active", "activating", "inactive", "").
service_state() {
    systemctl --user show -p ActiveState "$(unit_name "$1" service)" 2>/dev/null | cut -d= -f2
}

# ------------------------------------------------------------------------------
# SYSTEMD UNIT ACTIONS (per plugin)
# ------------------------------------------------------------------------------

# enable_one <plugin>: enable + start the plugin's timer. Returns systemctl's code.
enable_one() {
    systemctl --user enable --now "$(unit_name "$1" timer)" >/dev/null 2>&1
}

# stop_one <plugin>: stop the plugin's (oneshot) service, aborting a running scrape.
stop_one() {
    systemctl --user stop "$(unit_name "$1" service)" 2>/dev/null || true
}

# disable_one <plugin>: stop + disable the plugin's timer and service and clear any
# failed state. Mirrors the original single-plugin disable sequence.
disable_one() {
    _tmr="$(unit_name "$1" timer)"
    _svc="$(unit_name "$1" service)"
    systemctl --user stop    "$_tmr" 2>/dev/null || true
    systemctl --user disable "$_tmr" 2>/dev/null || true
    systemctl --user stop    "$_svc" 2>/dev/null || true
    systemctl --user disable "$_svc" 2>/dev/null || true
    systemctl --user reset-failed "$_svc" "$_tmr" 2>/dev/null || true
}
