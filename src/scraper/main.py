import argparse
import sys
import os
import logging

# Ensure the script directory is in the python path to allow imports when running as a module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from constants import CONFIG_DIR, EXIT_CODE_ERROR, SKROUTZ_FILE_PATH
from validators import ConfigValidator
from updater import InteractiveUpdateChecker, SilentUpdateChecker
from data_manager import ProductsManager
from notifier import Notifier
from logger import setup_logging, save_traceback
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

    setup_logging(args.quiet)

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
    ConfigValidator.print_prod_status(fatal_on_error=True)

    products_manager = ProductsManager(SKROUTZ_FILE_PATH)
    products_manager.load()

    ConfigValidator.print_env_status(fatal_on_error=False)

    notification_urls = os.environ.get("NOTIFICATION_URLS", "")
    notifier = Notifier(notification_urls)

    registered_scrapers = ['skroutz']
    targets_to_run = []
    
    if args.skroutz:
        targets_to_run.append('skroutz')
        
    if not targets_to_run:
        targets_to_run = registered_scrapers

    try:
        scraper_factory = ScraperFactory()
        try:
            orchestrator = ScrapingOrchestrator(targets_to_run, products_manager, scraper_factory, notifier, CONFIG_DIR, progress_strategy)
            orchestrator.run()
        finally:
            scraper_factory.close_all()

    except Exception:
        logging.info("")
        logging.error("🛑 A fatal error occurred! Check logs/errors.txt for details.")
        logging.info("")
        save_traceback()
        notifier.notify_crash()
        sys.exit(EXIT_CODE_ERROR)

if __name__ == "__main__":
    main()
