from urllib.parse import urlparse
from typing import Dict, List, Type
from clients.base import BaseScraperClient


class ScraperFactory:
    """Factory for creating and managing scraper client instances.

    Uses a class-level registry so new scrapers can be added without modifying
    this file. To add a new scraper, implement BaseScraperClient and register
    it via the package's __init__.py.
    """
    _registry: Dict[str, Type[BaseScraperClient]] = {}

    @classmethod
    def register(cls, domain_pattern: str, scraper_class: Type[BaseScraperClient]) -> None:
        """Registers a scraper class for URLs matching the given domain pattern.

        Args:
            domain_pattern (str): A substring to match against URL domains (e.g., 'skroutz').
            scraper_class (Type[BaseScraperClient]): The scraper class to instantiate for matching URLs.
        """
        cls._registry[domain_pattern] = scraper_class

    @classmethod
    def registered_targets(cls) -> List[str]:
        """Returns a list of all registered scraper target identifiers.

        Returns:
            List[str]: The registered domain patterns.
        """
        return list(cls._registry.keys())

    def __init__(self):
        """Initializes the ScraperFactory with an empty cache of scraper instances."""
        self._scrapers: Dict[str, BaseScraperClient] = {}

    def get_scraper_type(self, url: str) -> str:
        """Determines the scraper type based on the URL domain.

        Args:
            url (str): The product URL.

        Returns:
            str: The identifier for the scraper type (e.g., 'skroutz').

        Raises:
            ValueError: If the URL belongs to an unsupported domain.
        """
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()

        for pattern in self._registry:
            if pattern in domain:
                return pattern

        raise ValueError(f"Unsupported domain: {domain}")

    def get_scraper(self, url: str) -> BaseScraperClient:
        """Retrieves or creates an appropriate scraper client for the given URL.

        Args:
            url (str): The product URL to determine the correct scraper for.

        Returns:
            BaseScraperClient: The instantiated scraper client.

        Raises:
            ValueError: If the URL belongs to an unsupported domain.
        """
        scraper_type = self.get_scraper_type(url)

        if scraper_type not in self._scrapers:
            scraper_class = self._registry[scraper_type]
            self._scrapers[scraper_type] = scraper_class()

        return self._scrapers[scraper_type]

    def close_all(self) -> None:
        """Closes all cached scraper clients."""
        for scraper in self._scrapers.values():
            scraper.close()
