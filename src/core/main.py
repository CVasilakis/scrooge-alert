import argparse
import sys
import os
import logging
import apprise

# Ensure the script directory is in the python path to allow imports when running as a module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from constants import CONFIG_DIR, EXIT_CODE_ERROR, EXIT_CODE_PRODUCTS_ERROR, EXIT_CODE_ENV_ERROR
from utils import APPRISE_PLACEHOLDERS, check_env_file, check_for_updates
from exceptions import StorageFileError, EnvFileError, UpdateCheckError
from storage.factory import DataManagerFactory
from notifier import Notifier
from logger import setup_global_logging, save_traceback, get_target_logger
from clients.factory import ScraperFactory
from orchestrator import ScrapingOrchestrator
from tui import InteractiveExecutionStrategy, SilentExecutionStrategy

from rich.console import Console
from panel import StatusPanelBuilder

def main() -> None:
    """Main entry point for the Scrooge Alert application.

    This function initializes the environment, parses arguments, sets up logging,
    checks for updates, loads products, and starts the scraping orchestrator.
    It delegates file locking and scraping execution to the ScrapingOrchestrator.
    """
    parser = argparse.ArgumentParser(description='Scrooge Alert scraper')
    parser.add_argument('--quiet', action='store_true', help='Run script with no console output')

    registered_scrapers = ScraperFactory.registered_targets()
    for scraper in registered_scrapers:
        parser.add_argument(f'--{scraper}', action='store_true', help=f'Run the {scraper.capitalize()} scraper')

    args, _ = parser.parse_known_args()

    setup_global_logging(args.quiet)

    data_manager_factory = DataManagerFactory(CONFIG_DIR)
    targets_to_run = [s for s in registered_scrapers if getattr(args, s, False)]

    if not targets_to_run:
        targets_to_run = registered_scrapers

    if not args.quiet:
        console = Console()
        console.print()

        init_panel = StatusPanelBuilder("Configuration Check")

        with console.status("[bold green]Checking for updates...[/bold green]", spinner="dots"):
            # Update Check
            try:
                has_update = check_for_updates()
                if has_update:
                    ref = init_panel.add_note_ref("Run ./update.sh to install the latest version.")
                    init_panel.add_row("🟡", "Software Version", f"[yellow]Update available!{ref}[/yellow]")
                else:
                    init_panel.add_row("✅", "Software Version", "Up to date")
            except UpdateCheckError as e:
                ref = init_panel.add_note_ref(str(e))
                init_panel.add_row("❗", "Software Version", f"[red]Update check failed{ref}[/red]")

            # Config Check
            init_fatal_error = None
            for target in targets_to_run:
                try:
                    manager = data_manager_factory.get_manager(target)
                    total, faulty_indices = manager.validate_storage()
                    val_str = f"{total} items loaded"
                    if faulty_indices:
                        ref = init_panel.add_note_ref(f"Problematic items found at JSON index: {', '.join(map(str, faulty_indices))}.")
                        val_str += f", [yellow]{len(faulty_indices)} misconfigured{ref}[/yellow]"
                        init_panel.add_row("🟡", f"{target.capitalize()} Config", val_str)
                    else:
                        init_panel.add_row("✅", f"{target.capitalize()} Config", val_str)
                except StorageFileError as e:
                    ref = init_panel.add_note_ref(str(e))
                    init_panel.add_row("❗", f"{target.capitalize()} Config", f"[red]Failed{ref}[/red]")
                    init_fatal_error = EXIT_CODE_PRODUCTS_ERROR
                    break
                except ValueError:
                    continue

            if not init_fatal_error:
                # Env Check
                env_error_msg = ""
                try:
                    check_env_file()
                except EnvFileError as e:
                    env_error_msg = str(e)

                notification_urls = os.environ.get("NOTIFICATION_URLS", "")
                valid_urls = []
                invalid_urls = []
                if notification_urls:
                    for u in notification_urls.split(','):
                        u = u.strip()
                        if u:
                            if not any(p in u for p in APPRISE_PLACEHOLDERS) and apprise.Apprise.instantiate(u):
                                valid_urls.append(u)
                            else:
                                invalid_urls.append(u)

                if valid_urls or invalid_urls:
                    if not invalid_urls:
                        init_panel.add_row("✅", ".env File", f"{len(valid_urls)} valid URL(s)")
                    else:
                        ref = init_panel.add_note_ref("Run ./scripts/run.sh --ping for more details.")
                        init_panel.add_row("🟡", ".env File", f"{len(valid_urls)} valid URL(s), [yellow]{len(invalid_urls)} invalid{ref}[/yellow]")
                else:
                    ref = init_panel.add_note_ref(env_error_msg or "No notification URLs found.")
                    init_panel.add_row("❗", ".env File", f"[red]Not configured{ref}[/red]")

        init_panel.render(console)
        console.print()

        if init_fatal_error:
            sys.exit(init_fatal_error)

        ui_strategy = InteractiveExecutionStrategy()
    else:
        # Silent checking logic
        for target in targets_to_run:
            try:
                manager = data_manager_factory.get_manager(target)
                manager.validate_storage()
            except StorageFileError as e:
                get_target_logger(target, True).error(f"❗ Config check failed: {e}")
                logging.critical(f"Config check failed for {target}: {e}")
                sys.exit(EXIT_CODE_PRODUCTS_ERROR)
            except ValueError:
                continue

        try:
            check_env_file()
        except EnvFileError as e:
            for target in targets_to_run:
                get_target_logger(target, True).error(f"❗ Env configuration failed: {e}")
            logging.critical(f"Env configuration failed: {e}")
            sys.exit(EXIT_CODE_ENV_ERROR)

        notification_urls = os.environ.get("NOTIFICATION_URLS", "")
        if notification_urls:
            urls = [u.strip() for u in notification_urls.split(',') if u.strip()]
            invalid_urls = [u for u in urls if any(p in u for p in APPRISE_PLACEHOLDERS) or not apprise.Apprise.instantiate(u)]
            if invalid_urls:
                for target in targets_to_run:
                    get_target_logger(target, True).warning(f"❗ {len(invalid_urls)} invalid notification URL(s) detected in .env file.")

        ui_strategy = SilentExecutionStrategy()

    notification_urls = os.environ.get("NOTIFICATION_URLS", "")
    notifier = Notifier(notification_urls)

    try:
        scraper_factory = ScraperFactory()
        try:
            orchestrator = ScrapingOrchestrator(targets_to_run, data_manager_factory, scraper_factory, notifier, CONFIG_DIR, args.quiet, ui_strategy)
            exit_code = orchestrator.run()
        finally:
            scraper_factory.close_all()

        sys.exit(exit_code)

    except Exception:
        if 'ui_strategy' in locals():
            ui_strategy.complete_target()
        save_traceback(logging.root)
        notifier.notify_crash()
        sys.exit(EXIT_CODE_ERROR)

if __name__ == "__main__":
    main()
