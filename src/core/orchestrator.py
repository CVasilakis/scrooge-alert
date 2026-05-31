import logging
import signal
import datetime
import random
import time
import sys
from typing import Optional

from locks import acquire_lock
from constants import MIN_DELAY_SECONDS, RANDOM_DELAY_MIN, RANDOM_DELAY_MAX, RETRY_DELAY_MULTIPLIER, MAX_RETRIES, OLD_ENTRY_HOURS, EXIT_CODE_RATE_LIMIT_ERROR, EXIT_CODE_INTERRUPT
from exceptions import RateLimitError, ServerError, ScraperParseError, LockAcquisitionError
from models.base import BaseTrackedItem
from clients.factory import ScraperFactory
from storage.factory import DataManagerFactory
from storage.base import BaseDataManager
from notifier import Notifier
from logger import save_traceback, get_target_logger
from tui_bar import ProgressStrategy, SilentProgressStrategy

class ScrapingOrchestrator:
    def __init__(self, targets_to_run: list, data_manager_factory: DataManagerFactory, scraper_factory: ScraperFactory, notifier: Notifier, config_dir: str, quiet: bool = False, progress_strategy: Optional[ProgressStrategy] = None):
        """Initializes the ScrapingOrchestrator.

        Args:
            targets_to_run (list): A list of scraper types to run.
            data_manager_factory (DataManagerFactory): The factory to create data managers.
            scraper_factory (ScraperFactory): The factory to create web scrapers.
            notifier (Notifier): The service used to send notifications.
            config_dir (str): The directory for saving user data and configuration.
            quiet (bool): Whether to log to file silently.
            progress_strategy (Optional[ProgressStrategy]): The strategy for displaying progress.
        """
        self.targets_to_run = targets_to_run
        self.data_manager_factory = data_manager_factory
        self.scraper_factory = scraper_factory
        self.notifier = notifier
        self.config_dir = config_dir
        self.quiet = quiet
        self.interrupted = False
        self.progress_strategy = progress_strategy or SilentProgressStrategy()

    def signal_handler(self, signum, _frame):
        """Handles termination signals gracefully.

        Args:
            signum (int): The signal number received.
            _frame: The current stack frame (unused).
        """
        sig_name = 'SIGINT (Ctrl+C)' if signum == signal.SIGINT else 'SIGTERM (System Shutdown/Termination)' if signum == signal.SIGTERM else signum
        logging.info("")
        logging.info("")
        logging.info(f"🛑 Received signal {sig_name}. Gracefully shutting down...")
        logging.info("")
        self.interrupted = True

    def _sleep_with_jitter(self, base_delay: float, attempt: int = 0) -> None:
        """Pauses execution for a calculated duration with random jitter.

        Args:
            base_delay (float): The minimum delay in seconds.
            attempt (int): The retry attempt number to increase the delay. Defaults to 0.
        """
        jitter = random.uniform(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)
        total_delay = base_delay + (RETRY_DELAY_MULTIPLIER * attempt) + jitter

        start_time = time.time()
        while time.time() - start_time < total_delay:
            if self.interrupted:
                break
            remaining = max(0.0, total_delay - (time.time() - start_time))
            self.progress_strategy.display_progress(remaining)
            time.sleep(0.1)

        if not self.interrupted:
            actual_delay = time.time() - start_time
            self.progress_strategy.complete(actual_delay)

    def check_for_old_entries(self, hours: int, target_logger: logging.Logger) -> None:
        """Checks if any product hasn't been successfully scraped recently.

        Args:
            hours (int): The threshold in hours to consider an entry 'old'.
            target_logger (logging.Logger): The logger for the current target.
        """
        for target in self.targets_to_run:
            try:
                data_manager = self.data_manager_factory.get_manager(target)
            except ValueError:
                continue

            needs_save = False
            for row in data_manager.get_items():
                item = data_manager.parse_item(row)
                if item.skip:
                    continue

                if item.last_checked:
                    try:
                        timestamp = datetime.datetime.strptime(item.last_checked, "%d-%m-%Y %H:%M:%S")
                        current_time = datetime.datetime.now()
                        if (current_time - timestamp) > datetime.timedelta(hours=hours):
                            # Ensure backwards compatibility for naming where possible
                            name = getattr(item, 'name', 'Unknown')
                            target_logger.warning(f"❗ Old entry found for {name}: {item.url} (Last check: {item.last_checked})")
                            self.notifier.notify_old_entries(name, hours, item.url)
                    except ValueError:
                        name = getattr(item, 'name', 'Unknown')
                        target_logger.warning(f"❗ Invalid timestamp format found for {name}: {item.last_checked}. Resetting clock.")
                        data_manager.update_item(
                            url=item.url,
                            last_price=getattr(item, 'last_price', 0.0),
                            last_checked=datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                        )
                        needs_save = True

            if needs_save:
                data_manager.save_atomically()

    def _handle_successful_scrape(self, item: BaseTrackedItem, result, data_manager: BaseDataManager, target_logger: logging.Logger) -> None:
        """Processes a successful product scrape, sending notifications if necessary.

        Args:
            item (BaseTrackedItem): The product that was scraped.
            result (ScrapeResult): The result containing the current price and currency.
            data_manager (BaseDataManager): The data manager responsible for saving the updates.
            target_logger (logging.Logger): The logger for the current target.
        """
        # Assume Product structure for current skroutz implementation compatibility
        name = getattr(item, 'name', 'Unknown')
        target_price = getattr(item, 'target_price', 0.0)

        if result.price < target_price:
            target_logger.info(f"🎉 {name}: {result.price} {result.currency} (Target: {target_price} {result.currency})")
            if self.notifier.has_services:
                if self.notifier.notify_low_price(name, target_price, result.price, item.url, result.currency):
                    target_logger.info("    ↳ 📨 Notification sent to configured URL(s).")
                else:
                    target_logger.warning("    ↳ 🔕 Notification failed to send to one or more configured URL(s).")
            else:
                target_logger.info("    ↳ 🔕 No notification sent (no URL(s) configured in .env).")
        else:
            target_logger.info(f"✅ {name}: {result.price} {result.currency} (Target: {target_price} {result.currency})")

        data_manager.update_item(
            url=item.url,
            last_price=result.price,
            last_checked=datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        )

    def _process_product(self, row: dict, index: int, data_manager: BaseDataManager, target_logger: logging.Logger) -> tuple[Exception | None, bool]:
        """Processes a single product from the configuration, attempting to scrape it.

        Args:
            row (dict): The dictionary representation of the product.
            index (int): The index of the product in the list.
            data_manager (BaseDataManager): The data manager.
            target_logger (logging.Logger): The logger for the current target.

        Returns:
            tuple[Exception | None, bool]: A tuple containing:
                - error: The Exception that caused the failure, or None if successful.
                - abort_scraping: True if scraping should be aborted entirely (e.g., rate limit).
        """
        item = data_manager.parse_item(row)
        name = getattr(item, 'name', 'Unknown')
        target_price = getattr(item, 'target_price', 0.0)

        if item.skip:
            target_logger.info("")
            target_logger.info(f"🔕 {name}: Skipped (skip field set to true)")
            return None, False

        if index >= 0:
            target_logger.info("")

        self._sleep_with_jitter(MIN_DELAY_SECONDS)
        if self.interrupted:
            return None, False

        if not item.url:
            target_logger.warning(f"❗ {name}: URL is missing, skipping product.")
            return None, False

        if target_price < 0:
            target_logger.warning(f"❗ {name}: Invalid target price '{row.get('target_price')}', skipping product.")
            return None, False

        if 'target_price' not in row:
            target_logger.warning(f"❗ {name}: Target price is missing, defaulting to 0.0.")

        scraper = self.scraper_factory.get_scraper(item.url)

        for attempt in range(MAX_RETRIES):
            if self.interrupted:
                break

            try:
                result = scraper.scrape_product(item.url, name)

                if self.interrupted:
                    break

                if result is not None:
                    self._handle_successful_scrape(item, result, data_manager, target_logger)
                    break
                else:
                    break

            except ScraperParseError as e:
                if attempt == MAX_RETRIES - 1:
                    target_logger.error(f"{name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!")
                    target_logger.error(f"    ↳ ❗ {e}")
                    target_logger.info("")
                    return e, False
                else:
                    target_logger.warning(f"{name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!")
                    target_logger.warning(f"    ↳ ❗ {e}")
                    target_logger.info("")
                scraper.refresh_identity()
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
            except RateLimitError as e:
                if attempt == MAX_RETRIES - 1:
                    target_logger.error(f"{name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!")
                    target_logger.error(f"    ↳ ❗ {e}")
                    target_logger.info("")
                    target_logger.error("🛑 RateLimitError: Max retries reached. Aborting scraping.")
                    target_logger.info("")
                    save_traceback(target_logger, target_name=scraper.__class__.__name__, url=item.url, headers=scraper.get_current_headers())
                    return e, True
                else:
                    target_logger.warning(f"{name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!")
                    target_logger.warning(f"    ↳ ❗ {e}")
                    target_logger.info("")
                scraper.refresh_identity()
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
            except ServerError as e:
                if attempt == MAX_RETRIES - 1:
                    target_logger.error(f"{name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!")
                    target_logger.error(f"    ↳ ❗ {e}")
                    target_logger.info("")
                    return e, False
                else:
                    target_logger.warning(f"{name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!")
                    target_logger.warning(f"    ↳ ❗ {e}")
                    target_logger.info("")
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    target_logger.error(f"{name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!")
                    target_logger.error(f"    ↳ ❗ {e}")
                    target_logger.info("")
                    save_traceback(target_logger, target_name=scraper.__class__.__name__, url=item.url, headers=scraper.get_current_headers())
                    return e, False
                else:
                    target_logger.warning(f"{name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!")
                    target_logger.warning(f"    ↳ ❗ {e}")
                    target_logger.info("")
                scraper.refresh_identity()
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)

        return None, False

    def run(self) -> None:
        """Starts the scraping orchestrator loop.

        Iterates through all configured targets, attempts to scrape their products,
        and manages the overall workflow, including saving state and error reporting.
        """
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        failed_items = []
        abort_scraping = False
        needs_save = False

        for target in self.targets_to_run:
            if abort_scraping or self.interrupted:
                break
                
            target_logger = get_target_logger(target, self.quiet)

            try:
                data_manager = self.data_manager_factory.get_manager(target)
                data_manager.load()
            except ValueError:
                continue

            target_items = data_manager.get_items()
            if not target_items:
                continue

            try:
                with acquire_lock(target):
                    for index, row in enumerate(target_items):
                        if abort_scraping or self.interrupted:
                            break

                        product_error, product_abort = self._process_product(row, index, data_manager, target_logger)
                        if product_error:
                            failed_items.append((data_manager.parse_item(row), product_error))
                        abort_scraping = abort_scraping or product_abort
                        needs_save = True

                if needs_save:
                    data_manager.save_atomically()

            except LockAcquisitionError:
                logging.info("")
                logging.warning(f"🛑 Another instance of the {target} scraper is currently running. Aborting...")
                continue

        if not self.interrupted:
            # We use the global logger here as it spans across targets, or pick the first target's logger 
            # if we wanted it isolated. For simplicity and consistency with old behavior, 
            # we'll pass the root logger or skip checking old entries if we want strict isolation.
            # We'll pass the root logger since old entries checking spans all targets.
            self.check_for_old_entries(OLD_ENTRY_HOURS, logging.root)

        if not self.interrupted and failed_items:
            self.notifier.notify_errors(failed_items)

        if self.interrupted:
            sys.exit(EXIT_CODE_INTERRUPT)

        if abort_scraping:
            sys.exit(EXIT_CODE_RATE_LIMIT_ERROR)

        logging.info("")
