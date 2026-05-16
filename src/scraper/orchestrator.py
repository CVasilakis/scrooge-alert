import logging
import signal
import datetime
import random
import time
import sys

from config import MIN_DELAY_SECONDS, RANDOM_DELAY_MIN, RANDOM_DELAY_MAX, RETRY_DELAY_MULTIPLIER, MAX_RETRIES, OLD_ENTRY_HOURS, EXIT_CODE_RATE_LIMIT_ERROR
from exceptions import RateLimitError, ServerError, ScraperParseError
from models import Product
from clients.factory import ScraperFactory
from data_manager import ProductsManager
from notifier import Notifier
from utils import ErrorHandler

class ScrapingOrchestrator:
    def __init__(self, products_manager: ProductsManager, scraper_factory: ScraperFactory, notifier: Notifier, data_dir: str):
        self.products_manager = products_manager
        self.scraper_factory = scraper_factory
        self.notifier = notifier
        self.data_dir = data_dir
        self.interrupted = False

    def signal_handler(self, signum, _frame):
        sig_name = 'SIGINT (Ctrl+C)' if signum == signal.SIGINT else 'SIGTERM (System Shutdown/Termination)' if signum == signal.SIGTERM else signum
        logging.info(f"\n\n🛑 Received signal {sig_name}. Gracefully shutting down...")
        self.interrupted = True

    def _sleep_with_jitter(self, base_delay: float, attempt: int = 0) -> None:
        jitter = random.uniform(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)
        total_delay = base_delay + (RETRY_DELAY_MULTIPLIER * attempt) + jitter

        start_time = time.time()
        is_info = logging.getLogger().isEnabledFor(logging.INFO)
        while time.time() - start_time < total_delay:
            if self.interrupted:
                break
            if is_info:
                remaining = max(0.0, total_delay - (time.time() - start_time))
                print(f"\r⏳ Sleeping for {remaining:.1f} seconds...   ", end="", flush=True)
            time.sleep(0.1)

        if is_info and not self.interrupted:
            print("\r" + " " * 40 + "\r", end="", flush=True)
            actual_delay = time.time() - start_time
            logging.info(f"⏳ Slept for {actual_delay:.1f} seconds.")

    def check_for_old_entries(self, hours: int) -> None:
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

    def _process_product(self, row: dict, index: int) -> tuple[bool, bool]:
        product = Product.from_dict(row)

        if product.skip:
            logging.info(f"\n🔕 {product.name}: Skipped (skip field set to true)")
            return False, False

        if index >= 0:
            logging.info("")

        self._sleep_with_jitter(MIN_DELAY_SECONDS)
        if self.interrupted:
            return False, False

        if not product.url:
            logging.warning(f"❗ {product.name}: URL is missing, skipping product.")
            return False, False

        if product.target_price < 0:
            logging.warning(f"❗ {product.name}: Invalid target price '{row.get('target_price')}', skipping product.")
            return False, False

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
                scraper.refresh_identity()
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
            except RateLimitError as e:
                logging.warning(f"{product.name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!\n    ↳ ❗ {e}\n")
                if attempt == MAX_RETRIES - 1:
                    logging.error("🛑 RateLimitError: Max retries reached. Aborting scraping.")
                    ErrorHandler.save_traceback(self.data_dir, url=product.url, headers=scraper.get_current_headers())
                    return True, True
                scraper.refresh_identity()
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
            except ServerError as e:
                logging.warning(f"{product.name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!\n    ↳ ❗ {e}\n")
                if attempt == MAX_RETRIES - 1:
                    break
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
            except Exception as e:
                logging.error(f"{product.name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!\n    ↳ ❗ {e}\n")
                if attempt == MAX_RETRIES - 1:
                    ErrorHandler.save_traceback(self.data_dir, url=product.url, headers=scraper.get_current_headers())
                    return True, False
                scraper.refresh_identity()
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)

        return False, False

    def run(self) -> None:
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        products_data = self.products_manager.products_data.get("products", [])
        has_errors = False
        abort_scraping = False

        for index, row in enumerate(products_data):
            if abort_scraping or self.interrupted:
                break

            product_has_errors, product_abort = self._process_product(row, index)
            has_errors = has_errors or product_has_errors
            abort_scraping = abort_scraping or product_abort

        self.products_manager.save_atomically()

        if not self.interrupted:
            self.check_for_old_entries(OLD_ENTRY_HOURS)

        if not self.interrupted and has_errors:
            self.notifier.notify_errors()

        if abort_scraping:
            sys.exit(EXIT_CODE_RATE_LIMIT_ERROR)
