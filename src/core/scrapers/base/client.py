from abc import ABC, abstractmethod
from typing import Dict
from scrapers.base.model import ScrapeResult

class BaseScraperClient(ABC):
    """Abstract base class for scraping clients.

    Error-handling contract (this is what drives the orchestrator's
    retry / abort / notify behavior):
        ``scrape_product`` communicates its outcome purely through the exception
        it raises. The orchestrator branches on the exception *type*:

        * ``ProductNotFoundError`` / ``ProductUnavailableError`` /
          ``InvalidURLError`` — terminal for this item, NO retry; the item is
          skipped (not counted as a failure, not notified).
        * ``ScraperParseError`` — retried (with ``refresh_identity`` between
          attempts); if it still fails after all retries it counts as a failure.
        * ``RateLimitError`` — retried (with ``refresh_identity``); a terminal
          failure ABORTS the whole run for the target and saves a traceback.
        * ``ServerError`` — retried WITHOUT ``refresh_identity``; a terminal 5xx
          is shown and logged but intentionally NOT notified and NOT counted as a
          failure (a sustained outage instead surfaces via stale-entry tracking).
        * any other ``Exception`` — retried (with ``refresh_identity``); a
          terminal failure is counted and a traceback is saved.

        A successful call must return a :class:`ScrapeResult`. To plug a new
        store into the retry machinery, raise these exceptions accordingly.
    """

    def __init__(self) -> None:
        """Base initializer. Subclasses performing setup should call super().__init__()."""
        pass

    @abstractmethod
    def scrape_product(self, product_url: str) -> ScrapeResult:
        """Scrapes the product page to find the current price.

        Args:
            product_url (str): The URL of the product to scrape.

        Returns:
            ScrapeResult: The result of the scrape.

        Raises:
            ProductNotFoundError: If the product is not found.
            ProductUnavailableError: If the product is found but price is unavailable.
            InvalidURLError: If the provided URL is invalid.
            ScraperParseError: If the response cannot be parsed.
            RateLimitError: If the request is blocked or rate limited.
            ServerError: For server-side (5xx) errors.
            ScraperError: For other scraping-related errors.

        See the class docstring for how each exception drives retry/abort/notify behavior.
        """
        pass

    @abstractmethod
    def refresh_identity(self) -> None:
        """Resets headers, sessions, or cookies before a retry to evade blocks.

        Called by the orchestrator between retries for most error types. A client
        with nothing to rotate may implement this as a no-op.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Closes any underlying sessions or resources."""
        pass

    def get_current_headers(self) -> Dict[str, str]:
        """Returns request headers for diagnostic logging (optional hook).

        Used only to annotate saved tracebacks. HTTP-based clients should return
        their active headers; non-HTTP clients can rely on the empty default.

        Returns:
            Dict[str, str]: The current headers, or an empty dict.
        """
        return {}
