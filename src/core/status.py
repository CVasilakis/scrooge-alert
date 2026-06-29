import sys
import os
import glob
import signal
import subprocess

# Ensure the script directory is in the python path to allow imports when running as a module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from constants import CONFIG_DIR
from exit_status import classify_service_state
from scrapers.registry import ScraperRegistry
from scrapers.base.settings import STATUS_OK, STATUS_DEFAULT, STATUS_INVALID, KEY_INTERVAL
from logger import setup_global_logging
from panel import StatusPanelBuilder
from config_check import render_config_panel, load_targets
from utils import install_interrupt_handler

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

def get_systemd_user_dir() -> str:
    """Returns the systemd user unit directory, honoring ``XDG_CONFIG_HOME``.

    Mirrors ``${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user`` from the shell
    helpers (``common.sh``), so Python and the management scripts agree on where
    units live even under a non-default ``XDG_CONFIG_HOME``.
    """
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "systemd", "user")

def get_installed_plugin_units() -> dict:
    """Maps each installed scraper plugin to the set of unit suffixes it has.

    Globs ``<plugin>-scraper.{timer,service}`` in the systemd user directory -
    the same naming convention install.sh provisions and the shell helpers
    enumerate. Glob-based (no registry), so it also finds units whose plugin was
    removed from the source tree, which is exactly how orphans are detected.

    Returns:
        dict: ``{plugin_name: {"timer", "service"}}`` for every installed unit.
    """
    unit_dir = get_systemd_user_dir()

    found: dict = {}
    for suffix in ("timer", "service"):
        marker = f"-scraper.{suffix}"
        for path in glob.glob(os.path.join(unit_dir, f"*{marker}")):
            name = os.path.basename(path)[:-len(marker)]
            found.setdefault(name, set()).add(suffix)
    return found

def read_timer_oncalendar(target: str) -> str:
    """Returns the ``OnCalendar`` value written in the target's installed timer unit.

    Reads the generated ``<target>-scraper.timer`` file (the schedule actually on
    disk) and returns its first ``OnCalendar=`` value, or ``""`` if the unit is
    absent or declares none. Compared against the config-resolved schedule to detect
    drift between the user's ``execution_interval`` and the live timer - the same
    on-disk value ``schedule.sh`` reads and writes, so the two agree exactly.

    Args:
        target (str): The scraper target name (e.g. ``'skroutz'``).

    Returns:
        str: The unit's ``OnCalendar`` value, or ``""`` when none is present.
    """
    timer_path = os.path.join(get_systemd_user_dir(), f"{target}-scraper.timer")
    try:
        with open(timer_path, "r") as timer_file:
            for line in timer_file:
                stripped = line.strip()
                if stripped.startswith("OnCalendar="):
                    return stripped[len("OnCalendar="):].strip()
    except OSError:
        return ""
    return ""

def get_systemd_properties(unit: str, properties: str) -> dict:
    """Retrieves specified properties for a given systemd user unit.

    Args:
        unit (str): The name of the systemd unit (e.g., 'service.timer').
        properties (str): A comma-separated list of properties to query.

    Returns:
        dict: A dictionary mapping property names to their values.
    """
    service_file_path = os.path.join(get_systemd_user_dir(), unit)
    if not os.path.exists(service_file_path) or os.path.getsize(service_file_path) == 0:
        return {}

    try:
        output = subprocess.check_output(
            ['systemctl', '--user', 'show', unit, f'--property={properties}'],
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()
        if not output:
            return {}
        return dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
    except (subprocess.CalledProcessError, ValueError):
        return {}

def add_setting_row(panel: StatusPanelBuilder, view) -> None:
    """Renders one resolved setting as a row in the panel's settings section.

    A valid, explicitly-set value shows as ``✅``. An unset value (or a missing config)
    shows its active default as ``✅`` with a dim ``(default)`` marker. An invalid value
    shows the default it fell back to as ``🟡`` plus a footnote naming the problem.

    Args:
        panel (StatusPanelBuilder): The panel being built.
        view (SettingView): The resolved setting (label, display value, status, footnote).
    """
    if view.status == STATUS_INVALID:
        value = f"{view.display_value}{panel.add_note_ref(view.footnote)}"
    else:
        value = view.display_value
        if view.is_default:
            value += " [dim](default)[/dim]"
    panel.add_row(view.icon, view.label, value)

def main():
    """Main entry point for checking the status of the Scrooge Alert service.

    This function retrieves status information from systemd, validates configuration,
    checks for updates, and prints a formatted status report to the console using rich panels.
    """
    install_interrupt_handler()

    setup_global_logging()
    console = Console()

    # Print a starting empty line
    console.print()

    registry = ScraperRegistry(CONFIG_DIR)

    # Discover targets via the plugin registry (single source of truth), not by
    # scanning config filenames — a plugin's config name may differ from its name.
    # registered_targets() triggers idempotent plugin discovery on first use.
    registered_scrapers = ScraperRegistry.registered_targets()

    # --- Configuration Checks Panel ---
    load_results = load_targets(registry, registered_scrapers)
    render_config_panel(console, load_results, gate=False)

    # Disable custom signal handling after the update/test phase is complete
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    # --- Systemd Service Panels ---
    for target in registered_scrapers:
        timer_props = get_systemd_properties(f'{target}-scraper.timer', 'ActiveState,NextElapseUSecRealtime')
        service_props = get_systemd_properties(f'{target}-scraper.service', 'ActiveState,Result,ExecMainStartTimestamp,ExecMainStatus')

        if not timer_props and not service_props:
            service_table = Table(show_header=False, box=None, padding=(0, 2))
            service_table.add_column("Icon", justify="center")
            service_table.add_column("Message", style="dim")

            service_table.add_row("❗", "Background service not installed.")

            console.print()
            console.print(Panel(service_table, title=f"[bold]{target.capitalize()} Service Status[/bold]", border_style="red", width=75))
            continue

        service_panel = StatusPanelBuilder(f"{target.capitalize()} Service Status")

        # Settings section: report each scraper's settings (or its active default) on
        # top, then a separator, then the systemd status rows. Only reached once the
        # service is installed (the not-installed branch above already returned).
        for view in ScraperRegistry.resolve_settings(target, CONFIG_DIR):
            add_setting_row(service_panel, view)
        service_panel.add_separator()

        timer_active_val = timer_props.get("ActiveState") == "active"
        timer_icon = "✅" if timer_active_val else "❗"
        timer_active = "[green]Yes[/green]" if timer_active_val else "[red]No[/red]"

        result = service_props.get("Result", "")
        exec_status = service_props.get("ExecMainStatus", "")
        last_exec_time = service_props.get("ExecMainStartTimestamp", "")
        service_active = service_props.get("ActiveState", "")

        is_currently_running = service_active in ("active", "activating")

        next_exec = timer_props.get("NextElapseUSecRealtime", "")
        if is_currently_running:
            ref = service_panel.add_note_ref("Script is currently running in the background.")
            next_exec = f"[green]Running Now{ref}[/green]"
            next_exec_icon = "✅"
        elif not next_exec or next_exec in ("n/a", "0"):
            next_exec = "[red]Not Scheduled[/red]"
            next_exec_icon = "❗"
        else:
            next_exec_icon = "✅"

        service_panel.add_row(timer_icon, "Systemd Timer Active", timer_active)

        # A service that has never run yet is a healthy pending state, already
        # conveyed by the Timer Active and Next Scheduled Execution rows, so the
        # Last Execution rows are added only once it has actually executed -
        # otherwise they would read an alarming red "Never" (and any footnote
        # they carried would have no visible row to reference it).
        if last_exec_time:
            # Exit-code presentation lives in one table (exit_status.py); status
            # only renders the resolved verdict and links its note as a footnote.
            verdict = classify_service_state(result, exec_status, ScraperRegistry.get_plugin(target).get_config_filename())
            ref = service_panel.add_note_ref(verdict.note) if verdict.note else ""
            completed_str = f"[{verdict.color}]{verdict.label}{ref}[/{verdict.color}]"
            service_panel.add_row("✅", "Last Execution Time", last_exec_time)
            service_panel.add_row(verdict.icon, "Last Execution Status", completed_str)

        # Flag schedule *drift* only: the live timer's OnCalendar (what is on disk)
        # versus the effective schedule the user's configured execution_interval resolves
        # to (resolve_timer_directives owns the canonical-key -> OnCalendar translation and
        # the plugin-default fallback). A config edited without re-running schedule.sh
        # surfaces here as a footnote. An *invalid*/missing execution_interval is not
        # flagged here — the Execution Interval row in the settings section above owns that
        # report — so the check is gated to a usable (ok/default) interval.
        interval = ScraperRegistry.resolve_value(target, KEY_INTERVAL, CONFIG_DIR)
        if interval.status in (STATUS_OK, STATUS_DEFAULT):
            expected_oncalendar = ScraperRegistry.resolve_timer_directives(target, CONFIG_DIR).get("OnCalendar", "")
            active_oncalendar = read_timer_oncalendar(target)
            if active_oncalendar and active_oncalendar != expected_oncalendar:
                next_exec += service_panel.add_note_ref(
                    "Timer differs from config. Run `./scripts/schedule.sh`."
                )

        service_panel.add_row(next_exec_icon, "Next Scheduled Execution", next_exec)

        console.print()
        service_panel.render(console)

    # --- Orphaned Unit Panels ---
    # Units installed for a plugin that is no longer registered (removed or
    # renamed in the source tree). They never appear in the loop above (it
    # iterates registered plugins) and can never run - the service's
    # `run.sh --quiet --<plugin>` would be rejected as an unknown flag - so each
    # one is surfaced explicitly, in its own red panel, with removal instructions.
    registered_set = set(registered_scrapers)
    installed_units = get_installed_plugin_units()
    orphans = sorted(name for name in installed_units if name not in registered_set)

    for name in orphans:
        # One panel per orphan: a single error line, with the removal command
        # carried as a footnote (rendered cyan from the backticks). The exact unit
        # filenames are intentionally omitted - the plugin name in the title and
        # the command are enough to identify and remove it. The "❗" icon makes
        # StatusPanelBuilder color the border red on its own (no forced override).
        orphan_panel = StatusPanelBuilder(f"{name.capitalize()} Service Status (Orphaned)")
        ref = orphan_panel.add_note_ref(f"Run `./scripts/uninstall.sh --{name}` to remove it")
        orphan_panel.add_row("❗", f"[red]This scraper was removed but is still scheduled.[/red]{ref}", "")

        console.print()
        orphan_panel.render(console)

    console.print()

if __name__ == "__main__":
    main()
