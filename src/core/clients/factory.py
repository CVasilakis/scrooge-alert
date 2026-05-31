from urllib.parse import urlparse
from clients.base import BaseScraperClient
from clients.skroutz import SkroutzClient

class ScraperFactory:
    def __init__(self):
        """Initializes the ScraperFactory with an empty cache of scrapers."""
        self._scrapers = {}

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

        if 'skroutz' in domain:
            return 'skroutz'
        else:
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
            if scraper_type == 'skroutz':
                self._scrapers[scraper_type] = SkroutzClient()
            else:
                raise ValueError(f"Unsupported scraper type: {scraper_type}")

        return self._scrapers[scraper_type]

    def close_all(self) -> None:
        """Closes all cached scraper clients."""
        for scraper in self._scrapers.values():
            scraper.close()
