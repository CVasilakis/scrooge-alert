from abc import ABC, abstractmethod
from typing import List, Type
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
