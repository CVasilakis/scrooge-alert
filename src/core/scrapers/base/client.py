from abc import ABC, abstractmethod
from typing import Dict, List
from scrapers.base.model import ScrapeResult

class BaseScraperClient(ABC):
    """Abstract base class for scraping clients."""

    def __init__(self) -> None:
        """Base initializer. Subclasses must call super().__init__()."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @staticmethod
    @abstractmethod
    def get_supported_domains() -> List[str]:
        """Returns a list of supported domains or suffixes."""
        pass

    @abstractmethod
    def get_current_headers(self) -> Dict[str, str]:
        """Retrieves the current HTTP headers being used by the client.

        Returns:
            Dict[str, str]: The current headers.
        """
        pass

    @abstractmethod
    def refresh_identity(self) -> None:
        """Called before a retry to reset headers, sessions, or cookies to evade blocks."""
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
            ScraperError: For other scraping-related errors.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Closes any underlying sessions or resources."""
        pass
