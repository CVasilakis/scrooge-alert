import os
from typing import Optional

from rich.console import Console

from constants import EXIT_CODE_PRODUCTS_ERROR
from exceptions import StorageFileError, EnvFileError, UpdateCheckError
from utils import check_env_file, check_for_updates, classify_notification_urls
from panel import StatusPanelBuilder
from scrapers.registry import ScraperRegistry


def _append_version_row(panel: StatusPanelBuilder) -> None:
    """Appends the software-version row, querying the remote for updates."""
    try:
        if check_for_updates():
            ref = panel.add_note_ref("Run `./update.sh` to install the latest version.")
            panel.add_row("🟡", "Software Version", f"Update available!{ref}")
        else:
            panel.add_row("✅", "Software Version", "Up to date")
    except UpdateCheckError:
        ref = panel.add_note_ref("Check your internet connection and retry shortly.")
        panel.add_row("🟡", "Software Version", f"Could not check for updates{ref}")


def _append_config_rows(panel: StatusPanelBuilder, registry: ScraperRegistry, targets: list, gate: bool) -> Optional[int]:
    """Appends one config row per target by validating its storage.

    Args:
        panel (StatusPanelBuilder): The panel to populate.
        registry (ScraperRegistry): The registry used to resolve data managers.
        targets (list): The targets to validate.
        gate (bool): When True, the first storage error stops further checks and
            yields a fatal exit code (pre-flight gating). When False, all targets
            are reported regardless (health-report mode).

    Returns:
        Optional[int]: A fatal exit code if gating tripped, otherwise None.
    """
    for target in targets:
        try:
            manager = registry.get_manager(target)
            total, faulty_indices = manager.validate_storage()
            val_str = f"{total} items loaded"
            if faulty_indices:
                ref = panel.add_note_ref(f"Problematic items found at JSON index: {', '.join(map(str, faulty_indices))}.")
                val_str += f", [yellow]{len(faulty_indices)} misconfigured{ref}[/yellow]"
                panel.add_row("🟡", f"{target.capitalize()} Config", val_str)
            else:
                panel.add_row("✅", f"{target.capitalize()} Config", val_str)
        except StorageFileError as e:
            ref = panel.add_note_ref(str(e))
            panel.add_row("❗", f"{target.capitalize()} Config", f"[red]Failed{ref}[/red]")
            if gate:
                return EXIT_CODE_PRODUCTS_ERROR
        except ValueError:
            continue
    return None


def _append_env_row(panel: StatusPanelBuilder) -> None:
    """Appends the .env row summarizing configured Apprise notification URLs."""
    env_error_msg = ""
    try:
        check_env_file()
    except EnvFileError as e:
        env_error_msg = str(e)

    valid_urls, invalid_urls = classify_notification_urls(os.environ.get("NOTIFICATION_URLS", ""))

    if valid_urls or invalid_urls:
        if not invalid_urls:
            panel.add_row("✅", ".env File", f"{len(valid_urls)} valid URL(s)")
        else:
            ref = panel.add_note_ref("Run `./scripts/run.sh --ping` for more details.")
            panel.add_row("🟡", ".env File", f"{len(valid_urls)} valid URL(s), [yellow]{len(invalid_urls)} invalid{ref}[/yellow]")
    else:
        ref = panel.add_note_ref(env_error_msg or "No notification URLs found.")
        panel.add_row("❗", ".env File", f"[red]Not configured{ref}[/red]")


def render_config_panel(console: Console, registry: ScraperRegistry, targets: list, gate: bool = False) -> Optional[int]:
    """Builds and renders the shared 'Configuration Check' panel.

    Runs the update, per-target config, and .env checks behind a single spinner,
    then renders the panel. This is the single source of truth shared by the
    interactive scraper run (main.py) and the health check (status.py).

    Args:
        console (Console): The Rich console to render to.
        registry (ScraperRegistry): The registry used to resolve data managers.
        targets (list): The targets whose configuration should be validated.
        gate (bool): When True (pre-flight), a storage error stops further checks
            and the returned exit code is non-None so the caller can abort.

    Returns:
        Optional[int]: A fatal exit code when gating tripped, otherwise None.
    """
    panel = StatusPanelBuilder("Configuration Check")
    fatal_exit_code = None

    with console.status("[bold green]Checking for updates...[/bold green]", spinner="dots"):
        _append_version_row(panel)
        fatal_exit_code = _append_config_rows(panel, registry, targets, gate)
        if not (gate and fatal_exit_code):
            _append_env_row(panel)

    panel.render(console)
    return fatal_exit_code
