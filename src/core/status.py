import sys
import os
import signal
import subprocess

# Ensure the script directory is in the python path to allow imports when running as a module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from constants import CONFIG_DIR
from exit_status import classify_service_state
from scrapers.registry import ScraperRegistry
from logger import setup_global_logging
from panel import StatusPanelBuilder
from config_check import render_config_panel, load_targets
from utils import install_interrupt_handler

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

def get_systemd_properties(unit: str, properties: str) -> dict:
    """Retrieves specified properties for a given systemd user unit.

    Args:
        unit (str): The name of the systemd unit (e.g., 'service.timer').
        properties (str): A comma-separated list of properties to query.

    Returns:
        dict: A dictionary mapping property names to their values.
    """
    service_file_path = os.path.expanduser(f'~/.config/systemd/user/{unit}')
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

        timer_active_val = timer_props.get("ActiveState") == "active"
        timer_icon = "✅" if timer_active_val else "❗"
        timer_active = "[green]Yes[/green]" if timer_active_val else "[red]No[/red]"

        result = service_props.get("Result", "")
        exec_status = service_props.get("ExecMainStatus", "")
        last_exec_time = service_props.get("ExecMainStartTimestamp", "")
        service_active = service_props.get("ActiveState", "")

        is_currently_running = service_active in ("active", "activating")
        is_pending_first_execution = timer_active_val and not last_exec_time

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

        if not last_exec_time:
            last_exec_time = "[red]Never[/red]"
            if is_pending_first_execution:
                ref = service_panel.add_note_ref("Background service is pending its first execution.")
            else:
                ref = service_panel.add_note_ref("The background service has not been executed yet.")
            completed_str = f"[red]Not executed yet{ref}[/red]"
            last_exec_icon = "❗"
            completed_icon = "❗"
        else:
            last_exec_icon = "✅"
            # Exit-code presentation lives in one table (exit_status.py); status only
            # renders the resolved verdict and links its note as a footnote.
            verdict = classify_service_state(result, exec_status, ScraperRegistry.get_plugin(target).get_config_filename())
            completed_icon = verdict.icon
            ref = service_panel.add_note_ref(verdict.note) if verdict.note else ""
            completed_str = f"[{verdict.color}]{verdict.label}{ref}[/{verdict.color}]"

        service_panel.add_row(timer_icon, "Systemd Timer Active", timer_active)
        if last_exec_time != "[red]Never[/red]":
            service_panel.add_row(last_exec_icon, "Last Execution Time", last_exec_time)
            service_panel.add_row(completed_icon, "Last Execution Status", completed_str)
        service_panel.add_row(next_exec_icon, "Next Scheduled Execution", next_exec)

        console.print()
        service_panel.render(console)

    console.print()

if __name__ == "__main__":
    main()
