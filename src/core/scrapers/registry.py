import os
import importlib
import pkgutil
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, List, Optional, TYPE_CHECKING

from exceptions import PluginDiscoveryError

if TYPE_CHECKING:
    from scrapers.base.plugin import BasePlugin
    from scrapers.base.client import BaseScraperClient
    from scrapers.base.storage import BaseDataManager


class ScraperRegistry:
    """Unified registry that replaces ScraperFactory + DataManagerFactory.

    Each plugin is registered as a cohesive unit. The registry can:
    - Discover and register all plugin packages under scrapers/ (idempotent)
    - Resolve a URL to a plugin (using plugin.get_supported_domains())
    - Create client instances (lazy, cached)
    - Create storage/data-manager instances (lazy, cached)
    """
    _plugins: Dict[str, 'BasePlugin'] = {}
    _discovered: bool = False

    @classmethod
    def register(cls, plugin: 'BasePlugin') -> None:
        """Registers a plugin descriptor.

        Args:
            plugin (BasePlugin): The plugin descriptor instance to register.
        """
        cls._plugins[plugin.get_name()] = plugin

    @classmethod
    def discover(cls) -> None:
        """Imports and registers every plugin package under scrapers/ (idempotent).

        Auto-discovery is a no-op after the first successful call, so any entrypoint
        or component may call it freely without worrying about ordering or repeated
        work. The registry's lookup methods call this themselves, so a populated
        registry never depends on a caller remembering to import the package first.

        Each plugin sub-package must expose a module-level ``plugin`` attribute
        (a :class:`BasePlugin` instance) in its ``__init__.py``. A package that
        fails to import, omits ``plugin``, or exposes a non-:class:`BasePlugin`
        value is a programming error in that plugin, so discovery fails loudly with
        a :class:`PluginDiscoveryError` naming the offending package rather than
        silently skipping it.

        Raises:
            PluginDiscoveryError: If a plugin package cannot be imported, does not
                expose a ``plugin`` attribute, or exposes a non-BasePlugin value.
        """
        if cls._discovered:
            return

        from scrapers.base.plugin import BasePlugin

        package_dir = Path(__file__).parent
        for _importer, modname, ispkg in pkgutil.iter_modules([str(package_dir)]):
            if not ispkg or modname == "base":
                continue

            try:
                module = importlib.import_module(f"scrapers.{modname}")
            except Exception as e:
                raise PluginDiscoveryError(
                    f"Failed to import scraper plugin package 'scrapers.{modname}': {e}"
                ) from e

            plugin = getattr(module, "plugin", None)
            if plugin is None:
                raise PluginDiscoveryError(
                    f"Scraper plugin package 'scrapers.{modname}' does not expose a "
                    f"module-level 'plugin' attribute. Add `plugin = {modname.capitalize()}Plugin()` "
                    f"to scrapers/{modname}/__init__.py."
                )
            if not isinstance(plugin, BasePlugin):
                raise PluginDiscoveryError(
                    f"The 'plugin' attribute of scraper package 'scrapers.{modname}' is "
                    f"a {type(plugin).__name__}, not a BasePlugin instance."
                )
            cls.register(plugin)

        cls._discovered = True

    @classmethod
    def registered_targets(cls) -> List[str]:
        """Returns a list of all registered plugin target identifiers.

        Returns:
            List[str]: The registered target names.
        """
        cls.discover()
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
        cls.discover()
        if target not in cls._plugins:
            raise ValueError(f"Unsupported target: {target}")
        return cls._plugins[target]

    @classmethod
    def plugin_for_url(cls, url: str) -> Optional['BasePlugin']:
        """Resolves a URL to its registered plugin, or None if no plugin matches.

        A class-level lookup that needs no registry instance (and no config dir):
        it is the single place the supported-domain match is performed, used both
        by ``resolve_target`` and by components such as the notifier that only need
        a plugin's metadata (e.g. its display name) for a given product URL.

        Args:
            url (str): The product URL.

        Returns:
            Optional[BasePlugin]: The matching plugin, or None when unsupported.
        """
        cls.discover()
        for plugin in cls._plugins.values():
            if plugin.matches_url(url):
                return plugin
        return None

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
        plugin = self.plugin_for_url(url)
        if plugin is None:
            raise ValueError(f"Unsupported domain: {urlparse(url).netloc.lower()}")
        return plugin.get_name()

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
            self.discover()
            if target not in self._plugins:
                raise ValueError(f"Unsupported storage target: {target}")

            plugin = self._plugins[target]
            path = os.path.join(self.config_dir, plugin.get_config_filename())
            # Inject the plugin so the manager resolves supported domains through
            # it (the single source of truth) instead of importing a concrete plugin.
            self._managers[target] = plugin.get_storage_class()(path, plugin)

        return self._managers[target]

    def close_all(self) -> None:
        """Closes all cached scraper clients."""
        for scraper in self._scrapers.values():
            scraper.close()
