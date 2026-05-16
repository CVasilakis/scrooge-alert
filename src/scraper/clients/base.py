from abc import ABC, abstractmethod
from typing import Dict, Optional
from models import ScrapeResult

class BaseScraperClient(ABC):
    @abstractmethod
    def get_current_headers(self) -> Dict[str, str]:
        pass

    @abstractmethod
    def cycle_headers(self) -> None:
        pass

    @abstractmethod
    def scrape_product(self, product_url: str, product_name: str) -> Optional[ScrapeResult]:
        pass

    @abstractmethod
    def close(self) -> None:
        pass
