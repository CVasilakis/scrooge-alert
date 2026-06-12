import os
from urllib.parse import urlparse
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from scrapers.base.plugin import BasePlugin
    from scrapers.base.client import BaseScraperClient
    from scrapers.base.storage import BaseDataManager


class ScraperRegistry:
    """Unified registry that replaces ScraperFactory + DataManagerFactory.

    Each plugin is registered as a cohesive unit. The registry can:
    - Resolve a URL to a plugin (using plugin.get_supported_domains())
    - Create client instances (lazy, cached)
    - Create storage/data-manager instances (lazy, cached)
    """
    _plugins: Dict[str, 'BasePlugin'] = {}

    @classmethod
    def register(cls, plugin: 'BasePlugin') -> None:
        """Registers a plugin descriptor.

        Args:
            plugin (BasePlugin): The plugin descriptor instance to register.
        """
        cls._plugins[plugin.get_name()] = plugin

    @classmethod
    def registered_targets(cls) -> List[str]:
        """Returns a list of all registered plugin target identifiers.

        Returns:
            List[str]: The registered target names.
        """
        return list(cls._plugins.keys())

    @classmethod
    def get_plugin(cls, target: str) -> 'BasePlugin':
        """Retrieves a plugin descriptor by its target name.

        Args:
            target (str): The target identifier (e.g. 'skroutz').

        Returns:
            BasePlugin: The plugin descriptor.

        Raises:
            ValueError: If the target is not registered.
        """
        if target not in cls._plugins:
            raise ValueError(f"Unsupported target: {target}")
        return cls._plugins[target]

    def __init__(self, config_dir: str):
        """Initializes the ScraperRegistry with a configuration directory.

        Args:
            config_dir (str): The directory containing configuration files.
        """
        self._scrapers: Dict[str, 'BaseScraperClient'] = {}
        self._managers: Dict[str, 'BaseDataManager'] = {}
        self.config_dir = config_dir

    def resolve_target(self, url: str) -> str:
        """Determines the scraper target based on the URL domain.

        Args:
            url (str): The product URL.

        Returns:
            str: The identifier for the scraper target (e.g. 'skroutz').

        Raises:
            ValueError: If the URL belongs to an unsupported domain.
        """
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()

        for name, plugin in self._plugins.items():
            supported_domains = plugin.get_supported_domains()
            if any(domain.endswith(d) for d in supported_domains):
                return name

        raise ValueError(f"Unsupported domain: {domain}")

    def get_scraper(self, url: str) -> 'BaseScraperClient':
        """Retrieves or creates an appropriate scraper client for the given URL.

        Args:
            url (str): The product URL to determine the correct scraper for.

        Returns:
            BaseScraperClient: The instantiated scraper client.

        Raises:
            ValueError: If the URL belongs to an unsupported domain.
        """
        target = self.resolve_target(url)

        if target not in self._scrapers:
            plugin = self._plugins[target]
            self._scrapers[target] = plugin.get_client_class()()

        return self._scrapers[target]

    def get_manager(self, target: str) -> 'BaseDataManager':
        """Retrieves or creates an appropriate data manager for the given target.

        Args:
            target (str): The target identifier (e.g. 'skroutz').

        Returns:
            BaseDataManager: The instantiated data manager.

        Raises:
            ValueError: If the target is unsupported.
        """
        if target not in self._managers:
            if target not in self._plugins:
                raise ValueError(f"Unsupported storage target: {target}")

            plugin = self._plugins[target]
            path = os.path.join(self.config_dir, plugin.get_config_filename())
            self._managers[target] = plugin.get_storage_class()(path)

        return self._managers[target]

    def close_all(self) -> None:
        """Closes all cached scraper clients."""
        for scraper in self._scrapers.values():
            scraper.close()
