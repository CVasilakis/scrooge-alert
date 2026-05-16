from abc import ABC, abstractmethod
from typing import Dict, Optional
from models import ScrapeResult

class BaseScraperClient(ABC):
    @abstractmethod
    def get_current_headers(self) -> Dict[str, str]:
        pass

    @abstractmethod
    def refresh_identity(self) -> None:
        """Called before a retry to reset headers, sessions, or cookies to evade blocks."""
        pass

    @abstractmethod
    def scrape_product(self, product_url: str, product_name: str) -> Optional[ScrapeResult]:
        pass

    @abstractmethod
    def close(self) -> None:
        pass
