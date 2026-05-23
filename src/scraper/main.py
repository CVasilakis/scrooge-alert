import argparse
import sys
import os
import logging
from filelock import FileLock, Timeout

# Ensure the script directory is in the python path to allow imports when running as a module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from constants import LOCK_FILE_PATH, LOCK_TIMEOUT, CONFIG_DIR, EXIT_CODE_SKIPPED, EXIT_CODE_ERROR, PRODUCTS_FILE_PATH
from validators import ConfigValidator
from updater import InteractiveUpdateChecker, SilentUpdateChecker
from data_manager import ProductsManager
from notifier import Notifier
from logger import setup_logging, save_traceback
from clients.factory import ScraperFactory
from orchestrator import ScrapingOrchestrator
from tui_bar import InteractiveProgressStrategy, SilentProgressStrategy

def main() -> None:
    """Main entry point for the Skroutz Price Alert scraper application.

    This function initializes the environment, parses arguments, sets up logging,
    checks for updates, loads products, and starts the scraping orchestrator.
    It manages file locks to prevent multiple concurrent instances and handles
    unexpected errors by notifying the user and saving tracebacks.
    """
    parser = argparse.ArgumentParser(description='Skroutz Price Alert scraper')
    parser.add_argument('--quiet', action='store_true', help='Run script with no console output')
    args, _ = parser.parse_known_args()

    setup_logging(args.quiet)

    logging.info("")
    logging.info("Starting Skroutz Price Alert...")
    logging.info("")

    if args.quiet:
        update_checker = SilentUpdateChecker()
        progress_strategy = SilentProgressStrategy()
    else:
        update_checker = InteractiveUpdateChecker()
        progress_strategy = InteractiveProgressStrategy()
    update_checker.check()
    ConfigValidator.print_prod_status(fatal_on_error=True)

    products_manager = ProductsManager(PRODUCTS_FILE_PATH)
    products_manager.load()

    ConfigValidator.print_env_status(fatal_on_error=False)

    notification_urls = os.environ.get("NOTIFICATION_URLS", "")
    notifier = Notifier(notification_urls)

    lock = FileLock(LOCK_FILE_PATH, timeout=LOCK_TIMEOUT)

    try:
        with lock:
            scraper_factory = ScraperFactory()
            try:
                orchestrator = ScrapingOrchestrator(products_manager, scraper_factory, notifier, CONFIG_DIR, progress_strategy)
                orchestrator.run()
            finally:
                scraper_factory.close_all()

    except Timeout:
        logging.info("")
        logging.error('🛑 Skroutz Price Alert script did not start! Another instance is currently running.')
        logging.info("")
        sys.exit(EXIT_CODE_SKIPPED)
    except Exception:
        save_traceback()
        logging.info("")
        notifier.notify_crash()
        sys.exit(EXIT_CODE_ERROR)

if __name__ == "__main__":
    main()
