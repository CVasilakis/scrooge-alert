import signal
import datetime
import random
import time
from dataclasses import dataclass
from typing import Optional

from locks import acquire_lock
from constants import MIN_DELAY_SECONDS, RANDOM_DELAY_MIN, RANDOM_DELAY_MAX, RETRY_DELAY_MULTIPLIER, MAX_RETRIES, OLD_ENTRY_HOURS, EXIT_CODE_RATE_LIMIT_ERROR, EXIT_CODE_INTERRUPT, EXIT_CODE_SKIPPED, EXIT_CODE_SUCCESS, TIMESTAMP_FORMAT
from exceptions import RateLimitError, ServerError, ScraperParseError, LockAcquisitionError, StorageFileError, ProductNotFoundError, ProductUnavailableError, InvalidURLError
from scrapers.base.model import BaseTrackedItem
from scrapers.base.storage import BaseDataManager
from scrapers.registry import ScraperRegistry
from notifier import Notifier
from logger import save_traceback, get_target_logger
from tui import ExecutionStrategy, SilentExecutionStrategy, Notes, PriceOutcome
from utils import describe_signal


# --- Error handling policy -------------------------------------------------
# scrape_product signals every outcome through the exception it raises. The
# behavior for each retryable error — whether to refresh identity before
# retrying, abort the whole target, count it as a notified failure, save a
# traceback, and any extra footnotes — is declared here once instead of in a
# branching ladder. See BaseScraperClient's docstring for the full contract.

# Terminal, non-retryable errors: the item is skipped (warning, not a failure).
SKIP_ERRORS = (ProductNotFoundError, ProductUnavailableError, InvalidURLError)

# Placeholder in extra_notes, replaced at runtime with the per-target error-log pointer.
ERRORS_LOG_TOKEN = "<errors_log>"


@dataclass(frozen=True)
class ErrorPolicy:
    """How the orchestrator treats a single retryable scrape error.

    Attributes:
        refresh_before_retry: Call ``scraper.refresh_identity()`` between attempts.
        abort: Abort the entire target run once this error becomes terminal.
        counts_as_failure: Include the item in the notified ``failed_items`` list.
        save_traceback: Append a full traceback to the target's errors.txt when terminal.
        extra_notes: Footnotes shown on the terminal failure row. ``ERRORS_LOG_TOKEN``
            entries are replaced with the per-target error-log pointer at runtime.
    """
    refresh_before_retry: bool = True
    abort: bool = False
    counts_as_failure: bool = True
    save_traceback: bool = False
    extra_notes: tuple = ()


_DEFAULT_POLICY = ErrorPolicy(save_traceback=True, extra_notes=(ERRORS_LOG_TOKEN,))

# Matched by isinstance in insertion order; first hit wins, else _DEFAULT_POLICY.
_RETRY_POLICIES: dict = {
    RateLimitError: ErrorPolicy(
        abort=True,
        save_traceback=True,
        extra_notes=("Rate limit reached; scraping aborted.", ERRORS_LOG_TOKEN),
    ),
    # A 5xx is a transient server-side fault: shown and logged, but intentionally
    # not notified and not counted as a failure (a long outage surfaces via stale
    # tracking instead). Retried without rotating identity.
    ServerError: ErrorPolicy(refresh_before_retry=False, counts_as_failure=False),
    ScraperParseError: ErrorPolicy(),
}


def _policy_for(exc: Exception) -> ErrorPolicy:
    """Returns the ErrorPolicy for a retryable exception (isinstance match, else default)."""
    for exc_type, policy in _RETRY_POLICIES.items():
        if isinstance(exc, exc_type):
            return policy
    return _DEFAULT_POLICY


class ScrapingOrchestrator:
    """Orchestrates the scraping process across multiple targets and manages execution flow."""
    def __init__(self, targets_to_run: list, registry: ScraperRegistry, notifier: Notifier, config_dir: str, quiet: bool = False, ui_strategy: Optional[ExecutionStrategy] = None):
        """Initializes the ScrapingOrchestrator.

        Args:
            targets_to_run (list): A list of scraper types to run.
            registry (ScraperRegistry): The unified registry for scraper clients and data managers.
            notifier (Notifier): The service used to send notifications.
            config_dir (str): The directory for saving user data and configuration.
            quiet (bool): Whether to log to file silently.
            ui_strategy (Optional[ExecutionStrategy]): The strategy for the UI console output.
        """
        self.targets_to_run = targets_to_run
        self.registry = registry
        self.notifier = notifier
        self.config_dir = config_dir
        self.quiet = quiet
        self.interrupted = False
        self._interrupt_message = ""
        self._current_target = ""
        self._current_logger = None
        self._stale_items: list[BaseTrackedItem] = []
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
        self._interrupt_message = f"Received signal {describe_signal(signum)}"
        self.interrupted = True

    def _sleep_with_jitter(self, base_delay: float, attempt: int = 0, is_retry: bool = False) -> None:
        """Pauses execution for a calculated duration with random jitter.

        Args:
            base_delay (float): The minimum delay in seconds.
            attempt (int): The retry attempt number to increase the delay. Defaults to 0.
            is_retry (bool): True when this is a retry back-off rather than the normal
                pacing delay between products (controls the sleep row label).
        """
        jitter = random.uniform(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)
        total_delay = base_delay + (RETRY_DELAY_MULTIPLIER * attempt) + jitter

        start_time = time.monotonic()
        # During a retry back-off the upcoming attempt is the failed (0-based) attempt + 2.
        retry_attempt = attempt + 2 if is_retry else 0
        self.ui_strategy.start_sleep(total_delay, retry_attempt, MAX_RETRIES if is_retry else 0)
        while time.monotonic() - start_time < total_delay:
            if self.interrupted:
                break
            remaining = max(0.0, total_delay - (time.monotonic() - start_time))
            self.ui_strategy.update_sleep(remaining)
            time.sleep(0.05)

        if not self.interrupted:
            actual_delay = time.monotonic() - start_time
            self.ui_strategy.complete_sleep(actual_delay)

    def _flag_if_stale(self, item: BaseTrackedItem, data_manager: BaseDataManager) -> Optional[str]:
        """Evaluates the stored timestamp of a product that was not scraped this cycle.

        Called only for non-skipped products whose scrape did not succeed (a
        successful scrape refreshes the timestamp to now, so such a product is
        never stale). Records genuinely stale products for the aggregated
        end-of-target notification and repairs corrupted timestamps in place.

        Args:
            item (BaseTrackedItem): The product whose timestamp is being evaluated.
            data_manager (BaseDataManager): The data manager, used to repair a
                corrupted timestamp via the atomic update mechanism.

        Returns:
            Optional[str]: A footnote to attach to the product's row, or None when
                the product has no usable timestamp or is still fresh.
        """
        if not item.last_checked:
            return None

        try:
            timestamp = datetime.datetime.strptime(item.last_checked, TIMESTAMP_FORMAT)
        except ValueError:
            data_manager.update_item(
                item.url,
                last_price=item.last_price,
                last_checked=datetime.datetime.now().strftime(TIMESTAMP_FORMAT)
            )
            return "Corrupted timestamp! Updated to current system time."

        if (datetime.datetime.now() - timestamp) > datetime.timedelta(hours=OLD_ENTRY_HOURS):
            self._stale_items.append(item)
            return f"Stale: last scraped {item.last_checked} (over {OLD_ENTRY_HOURS}h ago)."

        return None

    @staticmethod
    def _combine_notes(*notes) -> Optional[list]:
        """Flattens the given note values (strings, lists, or None) into one list.

        Returns:
            Optional[list]: A flat list of note strings, or None when empty.
        """
        flat = []
        for note in notes:
            if not note:
                continue
            if isinstance(note, str):
                flat.append(note)
            else:
                flat.extend(note)
        return flat or None

    def _record_attempt(self, item_name: str, attempt: int, error_type: str, detail: str, attempt_notes: list) -> None:
        """Records a single failed scrape attempt.

        Streams the full detail to the silent strategy (one log line per attempt) and
        buffers a concise footnote for the collapsed interactive failure row.

        Args:
            item_name (str): The product name.
            attempt (int): The 0-based attempt index.
            error_type (str): The exception type name of this attempt.
            detail (str): The full error detail (type and message).
            attempt_notes (list): The accumulator for the per-attempt footnotes.
        """
        self.ui_strategy.log_attempt(item_name, attempt + 1, MAX_RETRIES, detail)
        attempt_notes.append(f"Attempt {attempt + 1}: {error_type}")

    def _emit_failure(self, item: BaseTrackedItem, data_manager: BaseDataManager, error_type: str, attempt_notes: list, extra_notes: Notes = None) -> None:
        """Emits the terminal failure row for a product after all retries are exhausted.

        Args:
            item (BaseTrackedItem): The product that failed.
            data_manager (BaseDataManager): The data manager, for stale evaluation.
            error_type (str): The exception type of the final failed attempt.
            attempt_notes (list): The accumulated per-attempt footnotes.
            extra_notes (Notes): Additional footnotes for this failure (e.g. an
                errors.txt pointer), shown by every strategy alongside the stale note.
        """
        stale_note = self._flag_if_stale(item, data_manager)
        self.ui_strategy.log_failure(item.name, error_type, attempt_notes, self._combine_notes(extra_notes, stale_note))

    def _errors_log_pointer(self) -> str:
        """Returns the footnote pointing at the current target's error log."""
        return f"See logs/{self._current_target}/errors.txt for details."

    def _resolve_policy_notes(self, policy: ErrorPolicy) -> Optional[list]:
        """Expands a policy's extra_notes, substituting the runtime error-log pointer."""
        if not policy.extra_notes:
            return None
        return [self._errors_log_pointer() if n == ERRORS_LOG_TOKEN else n for n in policy.extra_notes]

    def _handle_successful_scrape(self, item: BaseTrackedItem, result, data_manager: BaseDataManager, original_invalid_price=None, missing_target_price: bool = False, retries_used: int = 0, attempt_notes: Optional[list] = None) -> None:
        """Processes a successful product scrape, sending notifications if necessary.

        Args:
            item (BaseTrackedItem): The product that was scraped.
            result (ScrapeResult): The result containing the current price and currency.
            data_manager (BaseDataManager): The data manager responsible for saving the updates.
            original_invalid_price: The raw value from the config if the target price was
                unparseable, or None if it was valid.
            missing_target_price (bool): True if the config entry had no target_price field.
            retries_used (int): The number of failed attempts preceding this success.
            attempt_notes (Optional[list]): Per-attempt footnotes for preceding failed
                retries, surfaced on the interactive row ahead of the success notes.
        """
        notes = []
        if retries_used > 0:
            notes.append(f"Succeeded on attempt {retries_used + 1}/{MAX_RETRIES}")
        if original_invalid_price is not None:
            val = str(original_invalid_price)[:15]
            notes.append(f"Invalid target price '{val}'. Defaulting to 0.0 {result.currency}")
        elif missing_target_price:
            notes.append(f"Missing target price. Defaulting to 0.0 {result.currency}")

        if result.price < item.target_price:
            outcome = PriceOutcome.DROP
            if self.notifier.has_services:
                if self.notifier.notify_low_price(item.name, item.target_price, result.price, item.url, result.currency):
                    notes.append("Notification delivered to all valid apprise URL(s).")
                else:
                    notes.append("Notification delivery failed for some apprise URL(s).")
            else:
                notes.append("No notification sent (.env not configured).")
        elif item.target_price == 0.0:
            outcome = PriceOutcome.NO_TARGET
        else:
            outcome = PriceOutcome.OK

        self.ui_strategy.log_price_result(item.name, result.price, result.currency, item.target_price, outcome, notes, attempt_notes)

        data_manager.update_item(
            item.url,
            last_price=result.price,
            last_checked=datetime.datetime.now().strftime(TIMESTAMP_FORMAT)
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

        if item.skip:
            self.ui_strategy.log_result("✅", item.name, "Skipped", "The skip field was set to true in the configuration file.")
            return None, False

        if not data_manager.is_scrappable_item(row):
            stale_note = self._flag_if_stale(item, data_manager)
            self.ui_strategy.log_warning(item.name, "Invalid URL. Skipping product...", stale_note)
            return None, False

        # Detect and normalize invalid / missing target prices.
        # These are passed explicitly to _handle_successful_scrape
        # instead of being injected onto the item at runtime.
        original_invalid_price = None
        missing_target_price = 'target_price' not in row

        if item.target_price < 0:
            original_invalid_price = row.get('target_price')
            item.target_price = 0.0

        self._sleep_with_jitter(MIN_DELAY_SECONDS)
        if self.interrupted:
            return None, False

        scraper = self.registry.get_scraper(item.url)
        attempt_notes: list = []

        for attempt in range(MAX_RETRIES):
            if self.interrupted:
                break

            try:
                self.ui_strategy.start_scraping(item.name, attempt + 1, MAX_RETRIES)
                try:
                    result = scraper.scrape_product(item.url)
                finally:
                    self.ui_strategy.complete_scraping()

                if self.interrupted:
                    break

                self._handle_successful_scrape(item, result, data_manager, original_invalid_price, missing_target_price, retries_used=attempt, attempt_notes=attempt_notes)
                return None, False

            except SKIP_ERRORS as e:
                # Terminal for this item, no retry: the product is gone, unavailable,
                # or its URL is unusable. Surfaced as a warning, not a failure.
                stale_note = self._flag_if_stale(item, data_manager)
                self.ui_strategy.log_warning(item.name, f"Skipping ({type(e).__name__})", self._combine_notes(str(e), stale_note), attempt_notes)
                return None, False

            except Exception as e:
                # Retryable errors: how each is handled (refresh, abort, notify,
                # traceback, footnotes) is declared once in the ErrorPolicy table.
                policy = _policy_for(e)
                self._record_attempt(item.name, attempt, type(e).__name__, f"{type(e).__name__}: {e}", attempt_notes)

                if attempt == MAX_RETRIES - 1:
                    self._emit_failure(item, data_manager, type(e).__name__, attempt_notes, self._resolve_policy_notes(policy))
                    if policy.save_traceback and self._current_logger:
                        save_traceback(self._current_logger, target_name=self._current_target, url=item.url, headers=scraper.get_current_headers(), log_to_console=False)
                    return (e if policy.counts_as_failure else None), policy.abort

                if policy.refresh_before_retry:
                    scraper.refresh_identity()
                self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt, is_retry=True)

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
            self._stale_items = []
            needs_save = False
            abort_target = False

            if self.interrupted:
                break

            self._current_target = target
            self._current_logger = get_target_logger(target, self.quiet)

            try:
                data_manager = self.registry.get_manager(target)
            except ValueError:
                continue

            # Storage was already read and validated during the preflight load phase;
            # the registry returns that same cached, in-memory snapshot here.
            if data_manager.get_item_count() == 0:
                continue

            self.ui_strategy.start_target(target, self._current_logger)

            try:
                with acquire_lock(target):
                    # Normalize the in-memory snapshot the loop iterates. The
                    # actual rewrite happens in save() below, under this same lock,
                    # so a concurrent instance can't race the read-merge-rewrite.
                    data_manager.clean_storage()
                    for row in data_manager.get_items():
                        if abort_target or self.interrupted:
                            break

                        product_error, product_abort = self._process_product(row, data_manager)
                        if product_error:
                            failed_items.append((data_manager.parse_item(row), product_error))
                        abort_target = abort_target or product_abort
                        any_rate_limited = any_rate_limited or product_abort
                        needs_save = True

                    # Persist under the same lock as clean_storage(): save() does a
                    # read-merge-rewrite, so a concurrent instance must not race the
                    # final write.
                    if needs_save:
                        try:
                            data_manager.save()
                        except StorageFileError as e:
                            self.ui_strategy.log_error("Storage", f"Failed to update config/{target}.json file!", str(e))

                # Notifications involve network I/O and need no lock.
                if not self.interrupted and self._stale_items:
                    self.notifier.notify_old_entries(self._stale_items, OLD_ENTRY_HOURS)

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
