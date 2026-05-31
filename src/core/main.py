import argparse
import sys
import os
import logging

# Ensure the script directory is in the python path to allow imports when running as a module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from constants import CONFIG_DIR, EXIT_CODE_ERROR, EXIT_CODE_PRODUCTS_ERROR
from env import print_env_status
from exceptions import StorageFileError
from updater import InteractiveUpdateChecker, SilentUpdateChecker
from storage.factory import DataManagerFactory
from notifier import Notifier
from logger import setup_global_logging, save_traceback
from clients.factory import ScraperFactory
from orchestrator import ScrapingOrchestrator
from tui_bar import InteractiveProgressStrategy, SilentProgressStrategy

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

    logging.info("")
    logging.info("Starting Scrooge Alert...")
    logging.info("")

    if args.quiet:
        update_checker = SilentUpdateChecker()
        progress_strategy = SilentProgressStrategy()
    else:
        update_checker = InteractiveUpdateChecker()
        progress_strategy = InteractiveProgressStrategy()
    update_checker.check()

    data_manager_factory = DataManagerFactory(CONFIG_DIR)

    registered_scrapers = ['skroutz']
    targets_to_run = []

    if args.skroutz:
        targets_to_run.append('skroutz')

    if not targets_to_run:
        targets_to_run = registered_scrapers

    for target in targets_to_run:
        try:
            manager = data_manager_factory.get_manager(target)
            total, faulty = manager.validate_storage()
            logging.info(f"✅ Loaded {total} items from {target} config")
            if faulty > 0:
                logging.warning(f"    ↳ ❗ Detected {faulty} misconfigured item(s) in {target} config")
        except StorageFileError as e:
            logging.error(f"🛑 {e}!")
            logging.info("")
            sys.exit(EXIT_CODE_PRODUCTS_ERROR)
        except ValueError:
            continue

    print_env_status(fatal_on_error=False)

    notification_urls = os.environ.get("NOTIFICATION_URLS", "")
    notifier = Notifier(notification_urls)

    try:
        scraper_factory = ScraperFactory()
        try:
            orchestrator = ScrapingOrchestrator(targets_to_run, data_manager_factory, scraper_factory, notifier, CONFIG_DIR, args.quiet, progress_strategy)
            orchestrator.run()
        finally:
            scraper_factory.close_all()

    except Exception:
        logging.info("")
        save_traceback(logging.root)
        notifier.notify_crash()
        sys.exit(EXIT_CODE_ERROR)

if __name__ == "__main__":
    main()
