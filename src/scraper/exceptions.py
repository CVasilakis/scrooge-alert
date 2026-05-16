class ScraperError(Exception):
    """Base exception for scraping related errors."""
    pass

class RateLimitError(ScraperError):
    """Raised when the scraper is rate limited or blocked."""
    pass

class ServerError(ScraperError):
    """Raised when the server returns a 5xx error."""
    pass

class EnvFileError(Exception):
    """Raised when there is an issue with the environment configuration."""
    pass

class ProductFileError(Exception):
    """Raised when there is an issue with the products data file."""
    pass

class UpdateCheckError(Exception):
    """Raised when there is an issue checking for script updates."""
    pass
