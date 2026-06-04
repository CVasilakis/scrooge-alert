from .base import BaseScraperClient
from .factory import ScraperFactory
from .skroutz import SkroutzClient

# Register scraper clients for each supported domain.
# To add a new scraper, import its Client class and register it here.
ScraperFactory.register('skroutz', SkroutzClient)

__all__ = [
    "BaseScraperClient",
    "ScraperFactory",
    "SkroutzClient",
]
