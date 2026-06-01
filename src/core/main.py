import argparse
import sys
import os
import logging
import apprise

# Ensure the script directory is in the python path to allow imports when running as a module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from constants import CONFIG_DIR, EXIT_CODE_ERROR, EXIT_CODE_PRODUCTS_ERROR, EXIT_CODE_ENV_ERROR
from env import APPRISE_PLACEHOLDERS, check_env_file
from exceptions import StorageFileError, EnvFileError, UpdateCheckError
from updater import check_for_updates
from storage.factory import DataManagerFactory
from notifier import Notifier
from logger import setup_global_logging, save_traceback, get_target_logger
from clients.factory import ScraperFactory
from orchestrator import ScrapingOrchestrator
from tui import InteractiveExecutionStrategy, SilentExecutionStrategy

from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.markup import escape

def main() -> None:
    """Main entry point for the Scrooge Alert application.

    This function initializes the environment, parses arguments, sets up logging,
    checks for updates, loads products, and starts the scraping orchestrator.
    It delegates file locking and scraping execution to the ScrapingOrchestrator.
    """
    parser = argparse.ArgumentParser(description='Scrooge Alert scraper')
    parser.add_argument('--quiet', action='store_true', help='Run script with no console output')
    parser.add_argument('--skroutz', action='store_true', help='Run the Skroutz scraper')
    args, _ = parser.parse_known_args()

    setup_global_logging(args.quiet)

    data_manager_factory = DataManagerFactory(CONFIG_DIR)
    registered_scrapers = ['skroutz']
    targets_to_run = []

    if args.skroutz:
        targets_to_run.append('skroutz')

    if not targets_to_run:
        targets_to_run = registered_scrapers

    if not args.quiet:
        console = Console()
        console.print()

        init_table = Table(show_header=False, box=None, padding=(0, 2))
        init_table.add_column("Icon", justify="center")
        init_table.add_column("Property", style="bold")
        init_table.add_column("Value")

        init_notes = []
        def get_init_note_ref(note: str) -> str:
            init_notes.append(note)
            return f" [dim default][{len(init_notes)}][/dim default]"

        with console.status("[bold green]Starting Scrooge Alert...[/bold green]", spinner="dots"):
            # Update Check
            try:
                has_update = check_for_updates()
                if has_update:
                    ref = get_init_note_ref("Run ./update.sh to install the latest version.")
                    init_table.add_row("🟡", "Software Version", f"[yellow]Update available!{ref}[/yellow]")
                else:
                    init_table.add_row("✅", "Software Version", "[green]Up to date[/green]")
            except UpdateCheckError as e:
                ref = get_init_note_ref(str(e))
                init_table.add_row("❗", "Software Version", f"[red]Update check failed{ref}[/red]")

            # Config Check
            init_fatal_error = None
            for target in targets_to_run:
                try:
                    manager = data_manager_factory.get_manager(target)
                    total, faulty_indices = manager.validate_storage()
                    val_str = f"[green]{total} items loaded[/green]"
                    if faulty_indices:
                        ref = get_init_note_ref(f"Problematic items found at JSON index: {', '.join(map(str, faulty_indices))}.")
                        val_str += f", [yellow]{len(faulty_indices)} misconfigured{ref}[/yellow]"
                        init_table.add_row("🟡", f"{target.capitalize()} Config", val_str)
                    else:
                        init_table.add_row("✅", f"{target.capitalize()} Config", val_str)
                except StorageFileError as e:
                    ref = get_init_note_ref(str(e))
                    init_table.add_row("❗", f"{target.capitalize()} Config", f"[red]Failed{ref}[/red]")
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
                        init_table.add_row("✅", ".env File", f"[green]{len(valid_urls)} valid URL(s)[/green]")
                    else:
                        ref = get_init_note_ref("Run ./scripts/run.sh --ping for more details on invalid URLs.")
                        init_table.add_row("🟡", ".env File", f"[green]{len(valid_urls)} valid URL(s)[/green], [yellow]{len(invalid_urls)} invalid{ref}[/yellow]")
                else:
                    ref = get_init_note_ref(env_error_msg or "No notification URLs found.")
                    init_table.add_row("❗", ".env File", f"[red]Not configured{ref}[/red]")

        if init_notes:
            init_notes_group = [""]
            for i, note in enumerate(init_notes, 1):
                init_notes_group.append(f"  [{i}] {escape(note)}")
            console.print(Panel(Group(init_table, Text.from_markup("\n".join(init_notes_group), style="dim")), title="[bold]Initialization[/bold]", border_style="blue", width=75))
        else:
            console.print(Panel(init_table, title="[bold]Initialization[/bold]", border_style="blue", width=75))

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
                sys.exit(EXIT_CODE_PRODUCTS_ERROR)
            except ValueError:
                continue

        try:
            check_env_file()
        except EnvFileError as e:
            logging.critical(f"Env configuration failed: {e}")
            sys.exit(EXIT_CODE_ENV_ERROR)

        ui_strategy = SilentExecutionStrategy()

    notification_urls = os.environ.get("NOTIFICATION_URLS", "")
    notifier = Notifier(notification_urls)

    try:
        scraper_factory = ScraperFactory()
        try:
            orchestrator = ScrapingOrchestrator(targets_to_run, data_manager_factory, scraper_factory, notifier, CONFIG_DIR, args.quiet, ui_strategy)
            orchestrator.run()
        finally:
            scraper_factory.close_all()

    except Exception:
        if 'ui_strategy' in locals():
            ui_strategy.complete_target()
        save_traceback(logging.root)
        notifier.notify_crash()
        sys.exit(EXIT_CODE_ERROR)

if __name__ == "__main__":
    main()
