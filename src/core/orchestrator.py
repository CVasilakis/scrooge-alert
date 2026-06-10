import signal
import datetime
import random
import time
from typing import Optional

from locks import acquire_lock
from constants import MIN_DELAY_SECONDS, RANDOM_DELAY_MIN, RANDOM_DELAY_MAX, RETRY_DELAY_MULTIPLIER, MAX_RETRIES, OLD_ENTRY_HOURS, EXIT_CODE_RATE_LIMIT_ERROR, EXIT_CODE_INTERRUPT, EXIT_CODE_SKIPPED, EXIT_CODE_SUCCESS
from exceptions import RateLimitError, ServerError, ScraperParseError, LockAcquisitionError, StorageFileError, ProductNotFoundError, ProductUnavailableError, InvalidURLError
from models.base import BaseTrackedItem
from clients.factory import ScraperFactory
from storage.factory import DataManagerFactory
from storage.base import BaseDataManager
from notifier import Notifier
from logger import save_traceback, get_target_logger
from tui import ExecutionStrategy, SilentExecutionStrategy

class ScrapingOrchestrator:
    """Orchestrates the scraping process across multiple targets and manages execution flow."""
    def __init__(self, targets_to_run: list, data_manager_factory: DataManagerFactory, scraper_factory: ScraperFactory, notifier: Notifier, config_dir: str, quiet: bool = False, ui_strategy: Optional[ExecutionStrategy] = None):
        """Initializes the ScrapingOrchestrator.

        Args:
            targets_to_run (list): A list of scraper types to run.
            data_manager_factory (DataManagerFactory): The factory to create data managers.
            scraper_factory (ScraperFactory): The factory to create web scrapers.
            notifier (Notifier): The service used to send notifications.
            config_dir (str): The directory for saving user data and configuration.
            quiet (bool): Whether to log to file silently.
            ui_strategy (Optional[ExecutionStrategy]): The strategy for the UI console output.
        """
        self.targets_to_run = targets_to_run
        self.data_manager_factory = data_manager_factory
        self.scraper_factory = scraper_factory
        self.notifier = notifier
        self.config_dir = config_dir
        self.quiet = quiet
        self.interrupted = False
        self._interrupt_message = ""
        self._current_target = ""
        self._current_logger = None
        self.ui_strategy = ui_strategy or SilentExecutionStrategy()

    def signal_handler(self, signum, _frame):
        """Handles termination signals gracefully.

        Only sets the interrupted flag and stores the message. All UI cleanup
        is deferred to the main loop to avoid race conditions with the Rich
        Live display's background refresh thread.

        Args:
            signum (int): The signal number received.
            _frame: The current stack frame (unused).
        """
        sig_name = 'SIGINT (Ctrl+C)' if signum == signal.SIGINT else 'SIGTERM (System Shutdown/Termination)' if signum == signal.SIGTERM else signum
        self._interrupt_message = f"Received signal {sig_name}"
        self.interrupted = True

    def _sleep_with_jitter(self, base_delay: float, attempt: int = 0) -> None:
        """Pauses execution for a calculated duration with random jitter.

        Args:
            base_delay (float): The minimum delay in seconds.
            attempt (int): The retry attempt number to increase the delay. Defaults to 0.
        """
        jitter = random.uniform(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)
        total_delay = base_delay + (RETRY_DELAY_MULTIPLIER * attempt) + jitter

        start_time = time.monotonic()
        self.ui_strategy.start_sleep(total_delay)
        while time.monotonic() - start_time < total_delay:
            if self.interrupted:
                break
            remaining = max(0.0, total_delay - (time.monotonic() - start_time))
            self.ui_strategy.update_sleep(remaining)
            time.sleep(0.05)

        if not self.interrupted:
            actual_delay = time.monotonic() - start_time
            self.ui_strategy.complete_sleep(actual_delay)

    def check_for_old_entries(self, target: str, hours: int) -> None:
        """Checks if any product hasn't been successfully scraped recently for a specific target.

        Args:
            target (str): The specific target to check.
            hours (int): The threshold in hours to consider an entry 'old'.
        """
        try:
            data_manager = self.data_manager_factory.get_manager(target)
        except ValueError:
            return

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
                        name = getattr(item, 'name', 'Unknown')
                        self.ui_strategy.log_warning(name, "Stale item", f"Last time scraped: {item.last_checked}.")
                        self.notifier.notify_old_entries(name, hours, item.url)
                except ValueError:
                    name = getattr(item, 'name', 'Unknown')
                    self.ui_strategy.log_warning(name, "Corrupted timestamp detected", "Resetting stored timestamp to the current system time.")
                    data_manager.update_item(
                        item.url,
                        last_price=getattr(item, 'last_price', 0.0),
                        last_checked=datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                    )
                    needs_save = True

        if needs_save:
            try:
                data_manager.save()
            except StorageFileError as e:
                self.ui_strategy.log_error("Storage", f"Failed to update config/{target}.json file!", str(e))

    def _handle_successful_scrape(self, item: BaseTrackedItem, result, data_manager: BaseDataManager) -> None:
        """Processes a successful product scrape, sending notifications if necessary.

        Args:
            item (BaseTrackedItem): The product that was scraped.
            result (ScrapeResult): The result containing the current price and currency.
            data_manager (BaseDataManager): The data manager responsible for saving the updates.
        """
        name = getattr(item, 'name', 'Unknown')
        target_price = getattr(item, 'target_price', 0.0)

        price_str = f"{result.price} {result.currency}"
        target_str = f"(Target: {target_price} {result.currency})"

        notes = []
        original_invalid_price = getattr(item, '_original_invalid_price', None)
        missing_target_price = getattr(item, '_missing_target_price', False)

        if original_invalid_price is not None:
            val = str(original_invalid_price)[:15]
            notes.append(f"Invalid target price '{val}'. Defaulting to 0.0 {result.currency}")
        elif missing_target_price:
            notes.append(f"Missing target price. Defaulting to 0.0 {result.currency}")

        if result.price < target_price:
            if self.notifier.has_services:
                if self.notifier.notify_low_price(name, target_price, result.price, item.url, result.currency):
                    notes.append("Notification delivered to all valid apprise URL(s).")
                else:
                    notes.append("Notification delivery failed for some apprise URL(s).")
            else:
                notes.append("No notification sent (.env not configured).")
            self.ui_strategy.log_result("🎉", name, f"[bold green]{price_str}[/bold green] {target_str}", notes)
        elif target_price == 0.0:
            self.ui_strategy.log_result("🟡", name, f"{price_str} [yellow]{target_str}[/yellow]", notes)
        else:
            self.ui_strategy.log_result("✅", name, f"{price_str} {target_str}", notes)

        data_manager.update_item(
            item.url,
            last_price=result.price,
            last_checked=datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        )

    def _process_product(self, row: dict, data_manager: BaseDataManager) -> tuple[Exception | None, bool]:
        """Processes a single product from the configuration, attempting to scrape it.

        Args:
            row (dict): The dictionary representation of the product.
            data_manager (BaseDataManager): The data manager.

        Returns:
            tuple[Exception | None, bool]: A tuple containing:
                - error: The Exception that caused the failure, or None if successful.
                - abort_scraping: True if scraping should be aborted entirely (e.g., rate limit).
        """
        item = data_manager.parse_item(row)
        name = getattr(item, 'name', 'Unknown')
        target_price = getattr(item, 'target_price', 0.0)

        if item.skip:
            self.ui_strategy.log_result("✅", name, "Skipped", "The skip field was set to true in the configuration file.")
            return None, False

        if not data_manager.is_scrappable_item(row):
            self.ui_strategy.log_warning(name, "Invalid URL. Skipping product...")
            return None, False

        if target_price < 0:
            target_price = 0.0
            setattr(item, 'target_price', 0.0)
            setattr(item, '_original_invalid_price', row.get('target_price'))

        self._sleep_with_jitter(MIN_DELAY_SECONDS)
        if self.interrupted:
            return None, False

        if 'target_price' not in row:
            setattr(item, '_missing_target_price', True)

        scraper = self.scraper_factory.get_scraper(item.url)

        for attempt in range(MAX_RETRIES):
            if self.interrupted:
                break

            try:
                self.ui_strategy.start_scraping(name)
                try:
                    result = scraper.scrape_product(item.url, name)
                finally:
                    self.ui_strategy.complete_scraping()

                if self.interrupted:
                    break

                self._handle_successful_scrape(item, result, data_manager)
                break

            except (ProductNotFoundError, ProductUnavailableError, InvalidURLError) as e:
                self.ui_strategy.log_warning(name, f"Skipping ({type(e).__name__})", str(e))
                break
            except ScraperParseError as e:
                if attempt == MAX_RETRIES - 1:
                    self.ui_strategy.log_error(name, f"Attempt {attempt + 1} FAILED", f"{type(e).__name__}: {e}")
                    return e, False
                else:
                    self.ui_strategy.log_warning(name, f"Attempt {attempt + 1} FAILED", f"{type(e).__name__}: {e}")
                scraper.refresh_identity()
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
            except RateLimitError as e:
                if attempt == MAX_RETRIES - 1:
                    self.ui_strategy.log_error(name, f"Attempt {attempt + 1} FAILED ({type(e).__name__}): {e}")
                    self.ui_strategy.log_error(name, "Rate limit block", "Max retries reached. Aborting scraping.")
                    if self._current_logger:
                        save_traceback(self._current_logger, target_name=self._current_target, url=item.url, headers=scraper.get_current_headers(), log_to_console=False)
                    self.ui_strategy.log_error("System", "An error occurred!", f"Check logs/{self._current_target}/errors.txt for details.")
                    return e, True
                else:
                    self.ui_strategy.log_warning(name, f"Attempt {attempt + 1} FAILED ({type(e).__name__}): {e}")
                scraper.refresh_identity()
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
            except ServerError as e:
                if attempt == MAX_RETRIES - 1:
                    self.ui_strategy.log_error(name, f"Attempt {attempt + 1} FAILED", f"{type(e).__name__}: {e}")
                    return e, False
                else:
                    self.ui_strategy.log_warning(name, f"Attempt {attempt + 1} FAILED", f"{type(e).__name__}: {e}")
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    self.ui_strategy.log_error(name, f"Attempt {attempt + 1} FAILED", f"{type(e).__name__}: {e}")
                    if self._current_logger:
                        save_traceback(self._current_logger, target_name=self._current_target, url=item.url, headers=scraper.get_current_headers(), log_to_console=False)
                    self.ui_strategy.log_error("System", "An error occurred!", f"Check logs/{self._current_target}/errors.txt for details.")
                    return e, False
                else:
                    self.ui_strategy.log_warning(name, f"Attempt {attempt + 1} FAILED", f"{type(e).__name__}: {e}")
                scraper.refresh_identity()
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)

        return None, False

    def run(self) -> int:
        """Starts the scraping orchestrator loop.

        Iterates through all configured targets, attempts to scrape their products,
        and manages the overall workflow, including saving state and error reporting.
        """
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        any_rate_limited = False
        skipped_count = 0

        for target in self.targets_to_run:
            failed_items = []
            needs_save = False
            abort_target = False

            if self.interrupted:
                break

            self._current_target = target
            self._current_logger = get_target_logger(target, self.quiet)

            try:
                data_manager = self.data_manager_factory.get_manager(target)
                data_manager.load()
                data_manager.clean_storage()
            except ValueError:
                continue
            except StorageFileError as e:
                self.ui_strategy.log_error("Storage", f"Failed to load config/{target}.json file!", str(e))
                continue

            target_items = data_manager.get_items()
            if not target_items:
                continue

            self.ui_strategy.start_target(target, self._current_logger)

            try:
                with acquire_lock(target):
                    for row in target_items:
                        if abort_target or self.interrupted:
                            break

                        product_error, product_abort = self._process_product(row, data_manager)
                        if product_error:
                            failed_items.append((data_manager.parse_item(row), product_error))
                        abort_target = abort_target or product_abort
                        any_rate_limited = any_rate_limited or product_abort
                        needs_save = True

                if needs_save:
                    try:
                        data_manager.save()
                    except StorageFileError as e:
                        self.ui_strategy.log_error("Storage", f"Failed to update config/{target}.json file!", str(e))

                if not self.interrupted:
                    self.check_for_old_entries(target, OLD_ENTRY_HOURS)

                if not self.interrupted and failed_items:
                    self.notifier.notify_errors(failed_items)

            except LockAcquisitionError:
                self.ui_strategy.log_error("System", "Another instance is currently running. Aborting...")
                self.ui_strategy.complete_target()
                skipped_count += 1
                continue

            if self.interrupted:
                self.ui_strategy.log_interrupt(self._interrupt_message)
            self.ui_strategy.complete_target()

        if self.interrupted:
            return EXIT_CODE_INTERRUPT

        if any_rate_limited:
            return EXIT_CODE_RATE_LIMIT_ERROR

        if skipped_count > 0 and skipped_count == len(self.targets_to_run):
            return EXIT_CODE_SKIPPED

        return EXIT_CODE_SUCCESS
