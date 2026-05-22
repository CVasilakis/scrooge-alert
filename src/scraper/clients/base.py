from abc import ABC, abstractmethod
from typing import Dict, Optional
from models import ScrapeResult

class BaseScraperClient(ABC):
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
    def scrape_product(self, product_url: str, product_name: str) -> Optional[ScrapeResult]:
        """Scrapes the product page to find the current price.
        
        Args:
            product_url (str): The URL of the product to scrape.
            product_name (str): The name of the product (used for logging).
            
        Returns:
            Optional[ScrapeResult]: The result of the scrape, or None if the product was not found/available.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Closes any underlying sessions or resources."""
        pass
