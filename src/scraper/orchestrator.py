import logging
import signal
import datetime
import random
import time
import sys
from typing import Optional

from constants import MIN_DELAY_SECONDS, RANDOM_DELAY_MIN, RANDOM_DELAY_MAX, RETRY_DELAY_MULTIPLIER, MAX_RETRIES, OLD_ENTRY_HOURS, EXIT_CODE_RATE_LIMIT_ERROR, EXIT_CODE_INTERRUPT
from exceptions import RateLimitError, ServerError, ScraperParseError
from models import Product
from clients.factory import ScraperFactory
from data_manager import ProductsManager
from notifier import Notifier
from logger import save_traceback
from tui_bar import ProgressStrategy, SilentProgressStrategy

class ScrapingOrchestrator:
    def __init__(self, products_manager: ProductsManager, scraper_factory: ScraperFactory, notifier: Notifier, config_dir: str, progress_strategy: Optional[ProgressStrategy] = None):
        """Initializes the ScrapingOrchestrator.

        Args:
            products_manager (ProductsManager): The manager for product data.
            scraper_factory (ScraperFactory): The factory to create web scrapers.
            notifier (Notifier): The service used to send notifications.
            config_dir (str): The directory for saving user data and configuration.
            progress_strategy (Optional[ProgressStrategy]): The strategy for displaying progress.
        """
        self.products_manager = products_manager
        self.scraper_factory = scraper_factory
        self.notifier = notifier
        self.config_dir = config_dir
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

    def check_for_old_entries(self, hours: int) -> None:
        """Checks if any product hasn't been successfully scraped recently.

        Args:
            hours (int): The threshold in hours to consider an entry 'old'.
        """
        needs_save = False
        for row in self.products_manager.products_data.get("products", []):
            product = Product.from_dict(row)
            if product.skip:
                continue

            if product.last_checked:
                try:
                    timestamp = datetime.datetime.strptime(product.last_checked, "%d-%m-%Y %H:%M:%S")
                    current_time = datetime.datetime.now()
                    if (current_time - timestamp) > datetime.timedelta(hours=hours):
                        logging.warning(f"❗ Old entry found for {product.name}: {product.url} (Last check: {product.last_checked})")
                        self.notifier.notify_old_entries(product.name, hours, product.url)
                except ValueError:
                    logging.warning(f"❗ Invalid timestamp format found for {product.name}: {product.last_checked}. Resetting clock.")
                    self.products_manager.update_product(
                        url=product.url,
                        last_price=product.last_price,
                        last_checked=datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                    )
                    needs_save = True

        if needs_save:
            self.products_manager.save_atomically()

    def _handle_successful_scrape(self, product: Product, result) -> None:
        """Processes a successful product scrape, sending notifications if necessary.

        Args:
            product (Product): The product that was scraped.
            result (ScrapeResult): The result containing the current price and currency.
        """
        if result.price < product.target_price:
            logging.info(f"🎉 {product.name}: {result.price} {result.currency} (Target: {product.target_price} {result.currency})")
            if self.notifier.has_services:
                if self.notifier.notify_low_price(product.name, product.target_price, result.price, product.url, result.currency):
                    logging.info("    ↳ 📨 Notification sent to configured URL(s).")
                else:
                    logging.warning("    ↳ 🔕 Notification failed to send to one or more configured URL(s).")
            else:
                logging.info("    ↳ 🔕 No notification sent (no URL(s) configured in .env).")
        else:
            logging.info(f"✅ {product.name}: {result.price} {result.currency} (Target: {product.target_price} {result.currency})")

        self.products_manager.update_product(
            url=product.url,
            last_price=result.price,
            last_checked=datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        )

    def _process_product(self, row: dict, index: int) -> tuple[Exception | None, bool]:
        """Processes a single product from the configuration, attempting to scrape it.

        Args:
            row (dict): The dictionary representation of the product.
            index (int): The index of the product in the list.

        Returns:
            tuple[Exception | None, bool]: A tuple containing:
                - error: The Exception that caused the failure, or None if successful.
                - abort_scraping: True if scraping should be aborted entirely (e.g., rate limit).
        """
        product = Product.from_dict(row)

        if product.skip:
            logging.info("")
            logging.info(f"🔕 {product.name}: Skipped (skip field set to true)")
            return None, False

        if index >= 0:
            logging.info("")

        self._sleep_with_jitter(MIN_DELAY_SECONDS)
        if self.interrupted:
            return None, False

        if not product.url:
            logging.warning(f"❗ {product.name}: URL is missing, skipping product.")
            return None, False

        if product.target_price < 0:
            logging.warning(f"❗ {product.name}: Invalid target price '{row.get('target_price')}', skipping product.")
            return None, False

        if 'target_price' not in row:
            logging.warning(f"❗ {product.name}: Target price is missing, defaulting to 0.0.")

        scraper = self.scraper_factory.get_scraper(product.url)

        for attempt in range(MAX_RETRIES):
            if self.interrupted:
                break

            try:
                result = scraper.scrape_product(product.url, product.name)

                if self.interrupted:
                    break

                if result is not None:
                    self._handle_successful_scrape(product, result)
                    break
                else:
                    break

            except ScraperParseError as e:
                logging.warning(f"{product.name}: Attempt {attempt + 1} FAILED ({type(e).__name__}: {e}).")
                if attempt == MAX_RETRIES - 1:
                    return e, False
                scraper.refresh_identity()
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
            except RateLimitError as e:
                logging.warning(f"{product.name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!\n    ↳ ❗ {e}\n")
                if attempt == MAX_RETRIES - 1:
                    logging.error("🛑 RateLimitError: Max retries reached. Aborting scraping.")
                    save_traceback(url=product.url, headers=scraper.get_current_headers())
                    return e, True
                scraper.refresh_identity()
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
            except ServerError as e:
                logging.warning(f"{product.name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!\n    ↳ ❗ {e}\n")
                if attempt == MAX_RETRIES - 1:
                    return e, False
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
            except Exception as e:
                logging.error(f"{product.name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!\n    ↳ ❗ {e}\n")
                if attempt == MAX_RETRIES - 1:
                    save_traceback(url=product.url, headers=scraper.get_current_headers())
                    return e, False
                scraper.refresh_identity()
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)

        return None, False

    def run(self) -> None:
        """Starts the scraping orchestrator loop.

        Iterates through all configured products, attempts to scrape them,
        and manages the overall workflow, including saving state and error reporting.
        """
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        products_data = self.products_manager.products_data.get("products", [])
        failed_items = []
        abort_scraping = False

        for index, row in enumerate(products_data):
            if abort_scraping or self.interrupted:
                break

            product_error, product_abort = self._process_product(row, index)
            if product_error:
                failed_items.append((Product.from_dict(row), product_error))
            abort_scraping = abort_scraping or product_abort

        self.products_manager.save_atomically()

        if not self.interrupted:
            self.check_for_old_entries(OLD_ENTRY_HOURS)

        if not self.interrupted and failed_items:
            self.notifier.notify_errors(failed_items)

        if self.interrupted:
            sys.exit(EXIT_CODE_INTERRUPT)

        if abort_scraping:
            sys.exit(EXIT_CODE_RATE_LIMIT_ERROR)
