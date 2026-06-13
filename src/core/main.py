import argparse
import sys
import os
import logging
import signal

# Ensure the script directory is in the python path to allow imports when running as a module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from constants import CONFIG_DIR, EXIT_CODE_ERROR, EXIT_CODE_PRODUCTS_ERROR, EXIT_CODE_ENV_ERROR, EXIT_CODE_INTERRUPT
from utils import check_env_file, classify_notification_urls
from exceptions import EnvFileError
from scrapers.registry import ScraperRegistry
from notifier import Notifier
from logger import setup_global_logging, save_traceback, get_target_logger
from orchestrator import ScrapingOrchestrator
from tui import InteractiveExecutionStrategy, SilentExecutionStrategy
from config_check import render_config_panel, load_targets

from rich.console import Console

def main() -> None:
    """Main entry point for the Scrooge Alert application.

    This function initializes the environment, parses arguments, sets up logging,
    checks for updates, loads products, and starts the scraping orchestrator.
    It delegates file locking and scraping execution to the ScrapingOrchestrator.
    """
    def _handle_signal(signum, _frame):
        sig_name = 'SIGINT (Ctrl+C)' if signum == signal.SIGINT else 'SIGTERM (System Shutdown/Termination)' if signum == signal.SIGTERM else signum
        os.write(1, b"\033[2K\r")
        Console().print(f"🛑 Interrupted! Received signal {sig_name}.\n")
        sys.exit(EXIT_CODE_INTERRUPT)

    parser = argparse.ArgumentParser(description='Scrooge Alert scraper')
    parser.add_argument('--quiet', action='store_true', help='Run script with no console output')

    # Trigger auto-discovery of all scraper plugins
    import scrapers  # noqa: F401

    registered_scrapers = ScraperRegistry.registered_targets()
    for scraper in registered_scrapers:
        parser.add_argument(f'--{scraper}', action='store_true', help=f'Run the {scraper.capitalize()} scraper')

    args, _ = parser.parse_known_args()

    setup_global_logging(args.quiet)

    registry = ScraperRegistry(CONFIG_DIR)
    targets_to_run = [s for s in registered_scrapers if getattr(args, s, False)]

    if not targets_to_run:
        targets_to_run = registered_scrapers

    # Single load/validation phase: read each config once into its cached manager.
    # The orchestrator later reuses these same in-memory snapshots.
    load_results = load_targets(registry, targets_to_run)

    if not args.quiet:
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        console = Console()
        console.print()

        init_fatal_error = render_config_panel(console, load_results, gate=True)

        # Restore default handlers immediately after the spinner vanishes
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

        console.print()

        if init_fatal_error:
            sys.exit(init_fatal_error)

        ui_strategy = InteractiveExecutionStrategy()
    else:
        # Silent checking logic
        for result in load_results:
            if result.error is not None:
                get_target_logger(result.target, True).error(f"❗ Config check failed: {result.error}")
                logging.critical(f"Config check failed for {result.target}: {result.error}")
                sys.exit(EXIT_CODE_PRODUCTS_ERROR)

        try:
            check_env_file()
        except EnvFileError as e:
            for target in targets_to_run:
                get_target_logger(target, True).error(f"❗ Env configuration failed: {e}")
            logging.critical(f"Env configuration failed: {e}")
            sys.exit(EXIT_CODE_ENV_ERROR)

        _, invalid_urls = classify_notification_urls(os.environ.get("NOTIFICATION_URLS", ""))
        if invalid_urls:
            for target in targets_to_run:
                get_target_logger(target, True).warning(f"❗ {len(invalid_urls)} invalid notification URL(s) detected in .env file.")

        ui_strategy = SilentExecutionStrategy()

    notification_urls = os.environ.get("NOTIFICATION_URLS", "")
    notifier = Notifier(notification_urls)

    try:
        try:
            orchestrator = ScrapingOrchestrator(targets_to_run, registry, notifier, CONFIG_DIR, args.quiet, ui_strategy)
            exit_code = orchestrator.run()
        finally:
            registry.close_all()

        sys.exit(exit_code)

    except Exception:
        if 'ui_strategy' in locals():
            ui_strategy.complete_target()
        save_traceback(logging.root)
        notifier.notify_crash()
        sys.exit(EXIT_CODE_ERROR)

if __name__ == "__main__":
    main()
