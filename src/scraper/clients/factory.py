from urllib.parse import urlparse
from clients.base import BaseScraperClient
from clients.skroutz import SkroutzClient

class ScraperFactory:
    def __init__(self):
        """Initializes the ScraperFactory with an empty cache of scrapers."""
        self._scrapers = {}

    def get_scraper(self, url: str) -> BaseScraperClient:
        """Retrieves or creates an appropriate scraper client for the given URL.
        
        Args:
            url (str): The product URL to determine the correct scraper for.
            
        Returns:
            BaseScraperClient: The instantiated scraper client.
            
        Raises:
            ValueError: If the URL belongs to an unsupported domain.
        """
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()

        scraper_type = 'skroutz'
        if 'skroutz' in domain:
            scraper_type = 'skroutz'
        # Add more domains here if needed

        if scraper_type not in self._scrapers:
            if scraper_type == 'skroutz':
                self._scrapers[scraper_type] = SkroutzClient()
            else:
                raise ValueError(f"Unsupported domain: {domain}")

        return self._scrapers[scraper_type]

    def close_all(self) -> None:
        """Closes all cached scraper clients."""
        for scraper in self._scrapers.values():
            scraper.close()
