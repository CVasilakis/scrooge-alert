import os
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from rich.console import Console

from constants import EXIT_CODE_PRODUCTS_ERROR, EXIT_CODE_ENV_ERROR
from exceptions import StorageFileError, EnvFileError, UpdateCheckError, PluginDependencyError
from utils import check_env_file, check_for_updates, classify_notification_urls
from logger import get_target_logger
from panel import StatusPanelBuilder
from scrapers.registry import ScraperRegistry


@dataclass
class TargetLoad:
    """Outcome of loading a single target's storage during the preflight load phase.

    Attributes:
        target (str): The target name.
        count (int): The number of loaded items (0 when the load failed).
        faulty_indices (List[int]): 1-based indices of items failing validation.
        error (Optional[str]): The failure message if the storage could not be loaded.
    """
    target: str
    count: int = 0
    faulty_indices: List[int] = field(default_factory=list)
    error: Optional[str] = None


def load_targets(registry: ScraperRegistry, targets: list) -> List[TargetLoad]:
    """Loads every target's storage exactly once — the single read/validation point.

    The managers are cached in the registry, so the orchestrator later reuses the
    very same in-memory snapshot without re-reading any file. This is the only
    place a config file is opened for validation.

    Args:
        registry (ScraperRegistry): The registry used to resolve and cache managers.
        targets (list): The targets to load.

    Returns:
        List[TargetLoad]: One outcome per resolvable target, in the given order
            (targets without a registered plugin are skipped).
    """
    results: List[TargetLoad] = []
    for target in targets:
        try:
            manager = registry.get_manager(target)
        except ValueError:
            continue
        except PluginDependencyError:
            # The plugin's storage layer needs dependencies that are not
            # installed. Skip it here so preflight does not crash; the
            # orchestrator surfaces the actionable './install.sh --<plugin>'
            # message per-target and lets the other targets proceed, matching
            # how a missing transport (client) dependency is handled at runtime.
            continue
        try:
            manager.load()
            results.append(TargetLoad(target, manager.get_item_count(), manager.get_faulty_indices()))
        except StorageFileError as e:
            results.append(TargetLoad(target, error=str(e)))
    return results


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


def _append_config_rows(panel: StatusPanelBuilder, load_results: List[TargetLoad], gate: bool) -> Optional[int]:
    """Appends one config row per target from the preflight load outcomes.

    Args:
        panel (StatusPanelBuilder): The panel to populate.
        load_results (List[TargetLoad]): The outcomes from load_targets.
        gate (bool): When True, the first storage error stops further checks and
            yields a fatal exit code (pre-flight gating). When False, all targets
            are reported regardless (health-report mode).

    Returns:
        Optional[int]: A fatal exit code if gating tripped, otherwise None.
    """
    for result in load_results:
        label = f"{result.target.capitalize()} Config"
        if result.error is not None:
            ref = panel.add_note_ref(result.error)
            panel.add_row("❗", label, f"[red]Failed{ref}[/red]")
            if gate:
                return EXIT_CODE_PRODUCTS_ERROR
        elif result.faulty_indices:
            ref = panel.add_note_ref(f"Problematic items found at JSON index: {', '.join(map(str, result.faulty_indices))}.")
            panel.add_row("🟡", label, f"{result.count} items loaded, [yellow]{len(result.faulty_indices)} misconfigured{ref}[/yellow]")
        else:
            panel.add_row("✅", label, f"{result.count} items loaded")
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


def render_config_panel(console: Console, load_results: List[TargetLoad], gate: bool = False) -> Optional[int]:
    """Builds and renders the shared 'Configuration Check' panel.

    Runs the update and .env checks behind a single spinner and reports the
    already-completed per-target load outcomes, then renders the panel. This is
    the single presentation path shared by the interactive scraper run (main.py)
    and the health check (status.py); it performs no config-file I/O itself.

    Args:
        console (Console): The Rich console to render to.
        load_results (List[TargetLoad]): The outcomes from load_targets.
        gate (bool): When True (pre-flight), a storage error stops further checks
            and the returned exit code is non-None so the caller can abort.

    Returns:
        Optional[int]: A fatal exit code when gating tripped, otherwise None.
    """
    panel = StatusPanelBuilder("Configuration Check")
    fatal_exit_code = None

    with console.status("[bold green]Checking for updates...[/bold green]", spinner="dots"):
        _append_version_row(panel)
        fatal_exit_code = _append_config_rows(panel, load_results, gate)
        if not (gate and fatal_exit_code):
            _append_env_row(panel)

    panel.render(console)
    return fatal_exit_code


def _silent_preflight(load_results: List[TargetLoad], targets_to_run: list) -> Optional[int]:
    """Validates config and .env for a background (``--quiet``) run, logging to file.

    Mirrors the gating of the interactive panel but emits to each target's file
    logger instead of rendering, and additionally gates on the .env (a service with
    no usable notification URL cannot do its job).

    Args:
        load_results (List[TargetLoad]): The outcomes from load_targets.
        targets_to_run (list): The targets being run (for per-target logging).

    Returns:
        Optional[int]: A fatal exit code to abort on, or None to proceed.
    """
    for result in load_results:
        if result.error is not None:
            get_target_logger(result.target, True).error(f"❗ Config check failed: {result.error}")
            logging.critical(f"Config check failed for {result.target}: {result.error}")
            return EXIT_CODE_PRODUCTS_ERROR

    try:
        check_env_file()
    except EnvFileError as e:
        for target in targets_to_run:
            get_target_logger(target, True).error(f"❗ Env configuration failed: {e}")
        logging.critical(f"Env configuration failed: {e}")
        return EXIT_CODE_ENV_ERROR

    _, invalid_urls = classify_notification_urls(os.environ.get("NOTIFICATION_URLS", ""))
    if invalid_urls:
        for target in targets_to_run:
            get_target_logger(target, True).warning(
                f"❗ {len(invalid_urls)} invalid notification URL(s) detected in .env file."
            )

    return None


def preflight(console: Optional[Console], load_results: List[TargetLoad], targets_to_run: list, quiet: bool) -> Optional[int]:
    """Single preflight-validation entry point shared by both run modes.

    This is the one place all pre-scrape validation policy lives, so a new check
    is added once and both modes honor it. Storage was already read by
    ``load_targets``; this only renders/logs the verdict and decides whether to abort.

    Gating policy (intentionally mode-specific):
        * A storage/config failure is always fatal (``EXIT_CODE_PRODUCTS_ERROR``).
        * A missing/invalid ``.env`` is fatal only in quiet/service mode
          (``EXIT_CODE_ENV_ERROR``); interactively it is surfaced as a panel row so
          the user can see it and still proceed.

    Args:
        console (Optional[Console]): The console for interactive rendering; unused
            (may be None) in quiet mode.
        load_results (List[TargetLoad]): The outcomes from load_targets.
        targets_to_run (list): The targets being run.
        quiet (bool): Whether this is a silent/background run.

    Returns:
        Optional[int]: A fatal exit code to abort on, or None to proceed.
    """
    if quiet:
        return _silent_preflight(load_results, targets_to_run)
    assert console is not None, "console is required for interactive (non-quiet) preflight"
    return render_config_panel(console, load_results, gate=True)
