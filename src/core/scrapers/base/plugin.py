from abc import ABC, abstractmethod
from typing import List, Type
from urllib.parse import urlparse
from scrapers.base.client import BaseScraperClient
from scrapers.base.storage import BaseDataManager


class BasePlugin(ABC):
    """Descriptor that binds a scraper's client, storage, model, and metadata
    into a single cohesive unit.

    One plugin = one scraper target. The plugin is the single source of truth
    for domain lists, config filenames, display names, and class bindings.
    This prevents drift between components (e.g. a client supporting domains
    that its storage does not recognize).
    """

    @staticmethod
    @abstractmethod
    def get_name() -> str:
        """Returns a unique machine-readable identifier (e.g. 'skroutz', 'amazon')."""
        ...

    @staticmethod
    @abstractmethod
    def get_display_name() -> str:
        """Returns a human-readable name for TUI/logs (e.g. 'Skroutz', 'Amazon')."""
        ...

    @staticmethod
    @abstractmethod
    def get_supported_domains() -> List[str]:
        """Returns the canonical list of domains this scraper handles.

        This is the SINGLE SOURCE OF TRUTH for domain matching. Both the
        client and the storage must reference this list to avoid mismatch.
        """
        ...

    @staticmethod
    @abstractmethod
    def get_config_filename() -> str:
        """Returns the JSON config filename (e.g. 'skroutz.json')."""
        ...

    @staticmethod
    @abstractmethod
    def get_client_class() -> Type[BaseScraperClient]:
        """Returns the client class for this scraper."""
        ...

    @staticmethod
    @abstractmethod
    def get_storage_class() -> Type[BaseDataManager]:
        """Returns the data manager class for this scraper."""
        ...

    def matches_url(self, url: str) -> bool:
        """Returns True if the URL's host is one this plugin handles.

        The single place the supported-domain match is performed: both the
        registry (URL routing) and a plugin's data manager (storage validation)
        delegate here, so domain matching can never drift between them. Matching is
        label-boundary-aware against ``get_supported_domains()`` (a supported domain
        or a subdomain of it) and tolerant of non-string or empty input. The boundary
        check prevents a host like ``myskroutz.gr`` from falsely matching ``skroutz.gr``.

        Args:
            url (str): The URL to test.

        Returns:
            bool: True if the URL is on a supported domain.
        """
        if not isinstance(url, str) or not url:
            return False
        domain = urlparse(url).netloc.lower()
        return any(domain == d or domain.endswith("." + d) for d in self.get_supported_domains())
