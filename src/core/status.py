import sys
import os
import subprocess
import apprise

# Ensure the script directory is in the python path to allow imports when running as a module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from constants import EXIT_CODE_SKIPPED, EXIT_CODE_SUCCESS, EXIT_CODE_PRODUCTS_ERROR, EXIT_CODE_ENV_ERROR, EXIT_CODE_RATE_LIMIT_ERROR, EXIT_CODE_INTERRUPT, CONFIG_DIR
from env import check_env_file, APPRISE_PLACEHOLDERS
from exceptions import StorageFileError, EnvFileError, UpdateCheckError
from storage.factory import DataManagerFactory
from updater import check_for_updates
from logger import setup_global_logging
from panel import StatusPanelBuilder

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
    setup_global_logging()
    console = Console()

    # Print a starting empty line
    console.print()

    data_manager_factory = DataManagerFactory(CONFIG_DIR)

    registered_scrapers = []
    if os.path.exists(CONFIG_DIR):
        for f in os.listdir(CONFIG_DIR):
            if f.endswith('.json'):
                registered_scrapers.append(f[:-5])

    if not registered_scrapers:
        registered_scrapers = ['skroutz'] # Default fallback

    # --- Configuration Checks Panel ---
    config_panel = StatusPanelBuilder("Configuration Check")

    with console.status("[bold green]Running diagnostics...[/bold green]", spinner="dots"):
        # 1. Update Check
        try:
            has_update = check_for_updates()
            if has_update:
                ref = config_panel.add_note_ref("Run ./update.sh to install the latest version.")
                config_panel.add_row("🟡", "Software Version", f"[yellow]Update available!{ref}[/yellow]")
            else:
                config_panel.add_row("✅", "Software Version", "Up to date")
        except UpdateCheckError as e:
            ref = config_panel.add_note_ref(str(e))
            config_panel.add_row("❗", "Software Version", f"[red]Update check failed{ref}[/red]")

        # 2. Config Checks
        for target in registered_scrapers:
            try:
                manager = data_manager_factory.get_manager(target)
                total, faulty_indices = manager.validate_storage()
                val_str = f"{total} items loaded"
                if faulty_indices:
                    faulty_count = len(faulty_indices)
                    ref = config_panel.add_note_ref(f"Problematic items found at JSON index: {', '.join(map(str, faulty_indices))}.")
                    val_str += f", [yellow]{faulty_count} misconfigured{ref}[/yellow]"
                    config_panel.add_row("🟡", f"{target.capitalize()} Config", val_str)
                else:
                    config_panel.add_row("✅", f"{target.capitalize()} Config", val_str)
            except StorageFileError as e:
                ref = config_panel.add_note_ref(str(e))
                config_panel.add_row("❗", f"{target.capitalize()} Config", f"[red]Failed{ref}[/red]")
            except ValueError:
                continue

        # 3. Env Checks
        try:
            check_env_file()
            notification_urls = os.environ.get("NOTIFICATION_URLS", "")
            valid_urls = []
            invalid_urls = []
            for u in notification_urls.split(','):
                u = u.strip()
                if u:
                    if not any(p in u for p in APPRISE_PLACEHOLDERS) and apprise.Apprise.instantiate(u):
                        valid_urls.append(u)
                    else:
                        invalid_urls.append(u)
            if not invalid_urls:
                config_panel.add_row("✅", ".env File", f"{len(valid_urls)} valid URL(s)")
            else:
                ref = config_panel.add_note_ref("Run ./scripts/run.sh --ping for more details on invalid URLs.")
                config_panel.add_row("🟡", ".env File", f"{len(valid_urls)} valid URL(s), [yellow]{len(invalid_urls)} invalid{ref}[/yellow]")
        except EnvFileError as e:
            ref = config_panel.add_note_ref(str(e))
            config_panel.add_row("❗", ".env File", f"[red]Not configured{ref}[/red]")

    config_panel.render(console)

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

        no_errors = (result == "success" and exec_status == str(EXIT_CODE_SUCCESS))
        skipped = (exec_status == str(EXIT_CODE_SKIPPED))
        products_error = (exec_status == str(EXIT_CODE_PRODUCTS_ERROR))
        env_error = (exec_status == str(EXIT_CODE_ENV_ERROR))
        rate_limit_error = (exec_status == str(EXIT_CODE_RATE_LIMIT_ERROR))
        interrupted = (exec_status == str(EXIT_CODE_INTERRUPT))
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
            error_details = "None" if no_errors else f"Reason: {result or 'Unknown'}, Exit Code: {exec_status or 'Unknown'}"
            if no_errors:
                completed_icon = "✅"
                completed_str = "[green]OK[/green]"
            elif skipped:
                completed_icon = "🟡"
                ref = service_panel.add_note_ref("Another instance of the scraper was running.")
                completed_str = f"[yellow]Skipped{ref}[/yellow]"
            elif products_error:
                completed_icon = "❗"
                ref = service_panel.add_note_ref(f"Issue with the config/{target}.json file.")
                completed_str = f"[red]Failed{ref}[/red]"
            elif env_error:
                completed_icon = "❗"
                ref = service_panel.add_note_ref("Issue with the .env file.")
                completed_str = f"[red]Failed{ref}[/red]"
            elif rate_limit_error:
                completed_icon = "❗"
                ref = service_panel.add_note_ref("Blocked by server due to rate limits.")
                completed_str = f"[red]Failed{ref}[/red]"
            elif interrupted:
                completed_icon = "🟡"
                ref = service_panel.add_note_ref("Process was terminated by the user or system.")
                completed_str = f"[yellow]Interrupted{ref}[/yellow]"
            else:
                completed_icon = "❗"
                ref = service_panel.add_note_ref(error_details)
                completed_str = f"[red]Failed{ref}[/red]"

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
