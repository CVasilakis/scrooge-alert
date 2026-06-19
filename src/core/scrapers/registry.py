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

        Every discovered plugin is additionally validated against the lightweight
        descriptor contract (:meth:`_validate_plugin_contract`) and, once all are
        registered, the full set is checked for overlapping domains
        (:meth:`_check_domain_conflicts`). This turns a malformed plugin or an
        ambiguously-routed domain into a loud failure at startup rather than a
        confusing error (or silent misrouting) at first scrape. Validation of the
        bound client/storage *classes* is deliberately NOT done here: resolving
        them would trigger each plugin's deferred import of its concrete
        client/storage module (and any heavy transport library it pulls in, e.g.
        ``tls_client`` or ``selenium``), defeating lazy loading for callers that
        only enumerate plugins (argparse flags, ``list_plugins``, ``--status``).
        That check is deferred to first instantiation in :meth:`_resolve_bound_class`.

        Raises:
            PluginDiscoveryError: If a plugin package cannot be imported, does not
                expose a ``plugin`` attribute, exposes a non-BasePlugin value, fails
                the descriptor contract, or claims a domain another plugin handles.
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
            cls._validate_plugin_contract(modname, plugin)
            cls.register(plugin)

        cls._check_domain_conflicts()
        cls._discovered = True

    @classmethod
    def _validate_plugin_contract(cls, modname: str, plugin: 'BasePlugin') -> None:
        """Validates that a discovered plugin returns usable descriptor values.

        The :class:`BasePlugin` ABC only guarantees the descriptor methods *exist*;
        this additionally checks they return usable values — a non-empty, unique
        name, a non-empty display name and config filename, and a non-empty list of
        string domains. A plugin that fails any check is rejected here so the
        mistake surfaces at startup instead of breaking later at first scrape.

        Only the *cheap* descriptor metadata is checked here. The bound
        client/storage classes are intentionally NOT resolved (that would import a
        plugin's transport stack just to enumerate it); their type is validated
        lazily in :meth:`_resolve_bound_class` at first instantiation.

        Args:
            modname (str): The plugin package name, for error messages.
            plugin (BasePlugin): The plugin descriptor to validate.

        Raises:
            PluginDiscoveryError: If any part of the descriptor contract is unmet.
        """
        where = f"scrapers.{modname}"

        name = plugin.get_name()
        if not isinstance(name, str) or not name.strip():
            raise PluginDiscoveryError(f"Plugin '{where}' must return a non-empty string from get_name().")
        if name in cls._plugins:
            raise PluginDiscoveryError(
                f"Duplicate plugin name '{name}' (from '{where}'): another registered plugin "
                f"already uses it. Each plugin's get_name() must be unique."
            )

        for getter_name, value in (("get_display_name", plugin.get_display_name()),
                                   ("get_config_filename", plugin.get_config_filename())):
            if not isinstance(value, str) or not value.strip():
                raise PluginDiscoveryError(f"Plugin '{name}' ({where}) must return a non-empty string from {getter_name}().")

        domains = plugin.get_supported_domains()
        if not isinstance(domains, (list, tuple)) or not domains:
            raise PluginDiscoveryError(f"Plugin '{name}' ({where}) must return a non-empty list from get_supported_domains().")
        if any(not isinstance(d, str) or not d.strip() for d in domains):
            raise PluginDiscoveryError(f"Plugin '{name}' ({where}) returned an empty or non-string entry in get_supported_domains().")

    @staticmethod
    def _resolve_bound_class(plugin: 'BasePlugin', getter_name: str, base: type) -> type:
        """Resolves and type-checks a plugin's bound client/storage class on first use.

        Calling the getter triggers the plugin's deferred import of its concrete
        client/storage module — and any heavy transport library it pulls in (e.g.
        ``tls_client`` or ``selenium``). This is done lazily here, at first
        instantiation, rather than during discovery, so merely enumerating plugins
        never loads a scraper's transport stack. The subclass check that used to
        live in discovery moves with it, so a mis-bound class still fails loudly —
        just at the point the store is first used.

        Args:
            plugin (BasePlugin): The plugin whose class binding to resolve.
            getter_name (str): The descriptor method name ('get_client_class' or
                'get_storage_class').
            base (type): The base class the resolved class must subclass.

        Returns:
            type: The validated client/storage class.

        Raises:
            PluginDiscoveryError: If the getter raises or returns a non-subclass.
        """
        name = plugin.get_name()
        try:
            bound_class = getattr(plugin, getter_name)()
        except Exception as e:
            raise PluginDiscoveryError(f"Plugin '{name}' failed to provide {getter_name}(): {e}") from e
        if not (isinstance(bound_class, type) and issubclass(bound_class, base)):
            raise PluginDiscoveryError(
                f"Plugin '{name}': {getter_name}() must return a {base.__name__} subclass, got {bound_class!r}."
            )
        return bound_class

    @staticmethod
    def _domains_overlap(d1: str, d2: str) -> bool:
        """Returns True if a single host could match both domains.

        ``BasePlugin.matches_url`` accepts a host that equals a supported domain or
        is a label-boundary subdomain of it, so two domains conflict when they are
        equal or one is a subdomain-suffix of the other (e.g. ``skroutz.gr`` and
        ``shop.skroutz.gr`` both match a host of ``shop.skroutz.gr``).
        """
        if d1 == d2:
            return True
        return d1.endswith("." + d2) or d2.endswith("." + d1)

    @classmethod
    def _check_domain_conflicts(cls) -> None:
        """Ensures no two registered plugins claim overlapping domains.

        ``plugin_for_url`` returns the *first* plugin whose ``matches_url`` accepts a
        URL, iterating in (non-guaranteed) discovery order. If two plugins claimed
        the same — or a nesting — domain, routing would be silent and order-dependent.
        Detecting it once at discovery turns that latent ambiguity into a loud failure.

        Raises:
            PluginDiscoveryError: If two plugins claim overlapping domains.
        """
        seen: List[tuple] = []  # (normalized_domain, owning_plugin_name)
        for name, plugin in cls._plugins.items():
            for domain in plugin.get_supported_domains():
                norm = domain.strip().lower()
                for existing_domain, owner in seen:
                    if owner != name and cls._domains_overlap(norm, existing_domain):
                        raise PluginDiscoveryError(
                            f"Domain conflict: plugin '{name}' claims '{norm}', which overlaps with "
                            f"'{existing_domain}' already claimed by plugin '{owner}'. A domain may be "
                            f"handled by only one plugin."
                        )
                seen.append((norm, name))

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
            from scrapers.base.client import BaseScraperClient
            plugin = self._plugins[target]
            client_cls = self._resolve_bound_class(plugin, "get_client_class", BaseScraperClient)
            self._scrapers[target] = client_cls()

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

            from scrapers.base.storage import BaseDataManager
            plugin = self._plugins[target]
            storage_cls = self._resolve_bound_class(plugin, "get_storage_class", BaseDataManager)
            path = os.path.join(self.config_dir, plugin.get_config_filename())
            # Inject the plugin so the manager resolves supported domains through
            # it (the single source of truth) instead of importing a concrete plugin.
            self._managers[target] = storage_cls(path, plugin)

        return self._managers[target]

    def close_all(self) -> None:
        """Closes all cached scraper clients."""
        for scraper in self._scrapers.values():
            scraper.close()
