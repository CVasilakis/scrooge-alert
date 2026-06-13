import json
import os
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, Any, List, Optional, Type, TYPE_CHECKING
from urllib.parse import urlparse

from scrapers.base.model import BaseTrackedItem
from exceptions import StorageFileError
from utils import parse_price

if TYPE_CHECKING:
    from scrapers.base.plugin import BasePlugin


class BaseDataManager(ABC):
    """Abstract base class for managing data storage and retrieval.

    Subclasses must call ``super().__init__(filepath, plugin)`` in their
    ``__init__`` and use ``self.filepath`` for all file operations. The manager
    is given its owning :class:`BasePlugin` so that domain matching resolves
    through ``plugin.get_supported_domains()`` (the single source of truth)
    rather than importing a concrete plugin.

    Note:
        Most plugins back their storage with a JSON file. Such plugins should
        extend :class:`JsonProductDataManager` (below) instead of this class
        directly — it implements the entire generic JSON lifecycle and leaves
        only ``_matches_product_path`` (the store-specific URL-path rule) abstract.
        Subclass this class directly only for non-JSON backends (DB, API).
    """
    def __init__(self, filepath: str, plugin: Optional['BasePlugin'] = None) -> None:
        """Initializes the data manager.

        Args:
            filepath (str): The path to the storage file.
            plugin (Optional[BasePlugin]): The owning plugin, used to resolve the
                supported domains for URL matching. Injected by the registry.
        """
        self.filepath = filepath
        self.plugin = plugin

    # ------------------------------------------------------------------
    # Core lifecycle – must be implemented by every subclass
    # ------------------------------------------------------------------

    @abstractmethod
    def load(self) -> Dict[str, Any]:
        """Loads and validates data from the storage into memory.

        This is the single read/validation entry point for a target. Implementations
        must verify the source is present and well-formed, populate their in-memory
        state, and raise StorageFileError on any problem. After a successful call,
        ``get_items``, ``get_item_count`` and ``get_faulty_indices`` reflect the data.

        Returns:
            Dict[str, Any]: The parsed data representing tracked items.

        Raises:
            StorageFileError: If the source is missing, unreadable, or malformed.
        """
        pass

    @abstractmethod
    def save(self) -> None:
        """Persists the current in-memory state back to storage.

        Implementations should apply any pending updates cached via
        ``update_item`` and write the result to the underlying store.
        The mechanism (atomic file swap, database transaction, etc.) is
        an implementation detail.
        """
        pass

    # ------------------------------------------------------------------
    # Item access
    # ------------------------------------------------------------------

    @abstractmethod
    def update_item(self, url: str, **updates: Any) -> None:
        """Caches field updates for an item identified by its URL.

        Updates are not written to persistent storage until ``save``
        is called. Any keyword argument is accepted so that each
        scraper can store whatever fields it needs (e.g. ``last_price``,
        ``stock_status``, ``shipping_cost``).

        Args:
            url (str): The URL of the item.
            **updates: Arbitrary field updates to cache for the item.
        """
        pass

    @abstractmethod
    def get_items(self) -> List[Dict[str, Any]]:
        """Returns the list of items as dictionaries from the loaded data.

        Returns:
            List[Dict[str, Any]]: The list of item data dictionaries.
        """
        pass

    def get_item_count(self) -> int:
        """Returns the number of tracked items without materializing the full list.

        The default implementation delegates to ``get_items()``.
        Subclasses backed by a database or API may override this for
        efficiency.

        Returns:
            int: The total number of items.
        """
        return len(self.get_items())

    # ------------------------------------------------------------------
    # Parsing & Validation
    # ------------------------------------------------------------------

    @abstractmethod
    def parse_item(self, data: Dict[str, Any]) -> BaseTrackedItem:
        """Parses a dictionary into a BaseTrackedItem.

        Args:
            data (Dict[str, Any]): The item data.

        Returns:
            BaseTrackedItem: The parsed item.
        """
        pass

    def get_faulty_indices(self) -> list[int]:
        """Returns the 1-based indices of loaded items that fail validation.

        The default implementation derives the result from the already-loaded
        items via ``is_valid_item``; subclasses backed by a database or API may
        override it. Call after ``load`` so the in-memory data is populated.

        Returns:
            list[int]: 1-based indices of items for which ``is_valid_item`` is False.
        """
        return [i + 1 for i, item in enumerate(self.get_items()) if not self.is_valid_item(item)]

    @abstractmethod
    def is_valid_item(self, item: Dict[str, Any]) -> bool:
        """Validates an individual item's data structure and content.

        Args:
            item (Dict[str, Any]): The item data dictionary to validate.

        Returns:
            bool: True if the item is valid, False otherwise.
        """
        pass

    @abstractmethod
    def is_scrappable_item(self, item: Dict[str, Any]) -> bool:
        """Checks if the item has a valid, properly formatted URL.

        Args:
            item (Dict[str, Any]): The item dictionary to check.

        Returns:
            bool: True if the item can be scraped, False otherwise.
        """
        pass

    @abstractmethod
    def clean_storage(self) -> None:
        """Performs pre-scrape cleanup on the storage data (e.g., removing duplicates)."""
        pass

    # ------------------------------------------------------------------
    # Shared concrete helpers
    # ------------------------------------------------------------------

    def has_valid_target_price(self, item: Dict[str, Any], field: str = "target_price") -> bool:
        """Checks if an item has a valid, non-negative price in the given field.

        Args:
            item (Dict[str, Any]): The item dictionary to check.
            field (str): The dictionary key containing the price value.
                Defaults to ``"target_price"``.

        Returns:
            bool: True if the price field exists and is a valid non-negative number.
        """
        if field not in item:
            return False

        price = parse_price(item.get(field))
        if price is None or price < 0:
            return False

        return True

    def _url_on_supported_domain(self, url: str) -> bool:
        """Returns True if the URL's host is one this plugin handles.

        Matches the URL's netloc against ``plugin.get_supported_domains()`` — the
        same single source of truth the registry uses to route URLs — so domain
        matching never drifts between routing and storage. Returns False when no
        plugin was injected or the value is not a usable URL string.

        Args:
            url (str): The URL to check.

        Returns:
            bool: True if the URL is on a supported domain.
        """
        if self.plugin is None or not isinstance(url, str) or not url:
            return False
        domain = urlparse(url).netloc.lower()
        return any(domain.endswith(d) for d in self.plugin.get_supported_domains())


class JsonProductDataManager(BaseDataManager):
    """Generic data manager for a JSON file holding a list of tracked items.

    Implements the entire storage lifecycle shared by every JSON-file-backed
    scraper: load/validate, cache-and-merge updates, atomic save, and
    duplicate cleanup. The file is treated both as configuration (the tracked
    items and their target prices) and as state (the scraper writes back the
    latest price and check timestamp).

    Subclasses only need to declare two class attributes and implement one
    store-specific method:

        class FooDataManager(JsonProductDataManager):
            MODEL = FooItem        # a BaseTrackedItem subclass
            ROOT_KEY = "products"  # top-level JSON key holding the item list

            def _matches_product_path(self, url): ...  # store URL-path rule

    Everything else (parsing, validation, dedup, persistence, and the
    supported-domain check) is inherited.
    """

    #: The :class:`BaseTrackedItem` subclass that ``parse_item`` instantiates.
    MODEL: Type[BaseTrackedItem] = BaseTrackedItem
    #: The top-level JSON key whose value is the list of item dictionaries.
    ROOT_KEY: str = "products"

    def __init__(self, filepath: str, plugin: Optional['BasePlugin'] = None) -> None:
        """Initializes the manager with the JSON file path.

        Args:
            filepath (str): The path to the JSON storage/config file.
            plugin (Optional[BasePlugin]): The owning plugin (see BaseDataManager).
        """
        super().__init__(filepath, plugin)
        self._data: Dict[str, Any] = {}
        self._updates: Dict[str, Dict[str, Any]] = {}

    @property
    def _config_label(self) -> str:
        """Returns a human-readable ``config/<file>`` label for error messages."""
        return f"config/{os.path.basename(self.filepath)}"

    def _save_json_atomically(self, data: Dict[str, Any]) -> None:
        """Writes data to the JSON file atomically using a temp-file swap.

        Writes to a temporary file first, then atomically replaces the target
        file via ``os.replace`` to prevent corruption on crash. This is the sole
        writer for the JSON backend.

        Args:
            data (Dict[str, Any]): The data to serialize as JSON.

        Raises:
            StorageFileError: If the write operation fails.
        """
        temp_path = self.filepath + ".tmp"
        try:
            with open(temp_path, mode='w') as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, self.filepath)
        except OSError as e:
            raise StorageFileError(str(e))

    def load(self) -> Dict[str, Any]:
        """Loads and validates the items data from the JSON file.

        Performs the full pre-scrape validation (directory, existence, permissions
        and JSON structure) and populates the in-memory state in one pass.

        Returns:
            Dict[str, Any]: The parsed JSON data.

        Raises:
            StorageFileError: If the file is missing, has wrong permissions, or
                contains invalid JSON (or lacks the ``ROOT_KEY`` list).
        """
        config_dir = os.path.dirname(self.filepath)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir)

        if not os.path.exists(self.filepath) or not os.path.isfile(self.filepath):
            raise StorageFileError(f"The {self._config_label} file is missing or not a file")

        if not os.access(self.filepath, os.R_OK | os.W_OK):
            raise StorageFileError(f"The {self._config_label} file has wrong permissions")

        try:
            with open(self.filepath, 'r') as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            raise StorageFileError(f"The {self._config_label} file contains invalid JSON format")

        if not isinstance(data, dict) or not isinstance(data.get(self.ROOT_KEY), list):
            raise StorageFileError(f"The {self._config_label} file contains invalid JSON format")

        self._data = data
        return self._data

    def _get_clean_url(self, url: str) -> str:
        """Strips query parameters and fragments to return the clean base URL.

        Args:
            url (str): The raw URL to clean.

        Returns:
            str: The sanitized base URL.
        """
        if not url:
            return ""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def update_item(self, url: str, **updates: Any) -> None:
        """Caches updates for an item based on its clean URL.

        Args:
            url (str): The URL of the item to update.
            **updates: Arbitrary field updates (e.g. ``last_price=12.5``,
                ``last_checked="11-06-2026 01:00:00"``).
        """
        clean_url = self._get_clean_url(url)
        if clean_url in self._updates:
            self._updates[clean_url].update(updates)
        else:
            self._updates[clean_url] = dict(updates)

    def get_items(self) -> List[Dict[str, Any]]:
        """Returns the list of items as dictionaries."""
        return self._data.get(self.ROOT_KEY, [])

    def _clean_products(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Removes duplicates based on URL rules and cleans URLs."""
        groups = defaultdict(list)

        for i, product in enumerate(products):
            if "skip" not in product:
                product["skip"] = False

            url = str(product.get("url", ""))
            # Group by clean URL if scrappable, otherwise fallback to string representation of raw url
            clean_url = self._get_clean_url(url) if self.is_scrappable_item(product) else url
            groups[clean_url].append((i, product))

        items_to_keep = set()
        for clean_url, group in groups.items():
            if len(group) == 1:
                items_to_keep.add(group[0][0])
                continue

            valid_indices = [i for i, p in group if self.is_valid_item(p)]
            if valid_indices:
                items_to_keep.add(valid_indices[0])
            else:
                scrappable_indices = [i for i, p in group if self.is_scrappable_item(p)]
                if scrappable_indices:
                    items_to_keep.add(scrappable_indices[0])
                else:
                    for i, p in group:
                        items_to_keep.add(i)

        cleaned_products = []
        for i, product in enumerate(products):
            if i in items_to_keep:
                if self.is_scrappable_item(product):
                    product["url"] = self._get_clean_url(str(product.get("url", "")))
                cleaned_products.append(product)

        return cleaned_products

    def clean_storage(self) -> None:
        """Normalizes the in-memory item list (dedup + URL cleaning) before scraping.

        Operates only on the in-memory snapshot so the scrape loop iterates a clean,
        de-duplicated list. Persistence is deferred entirely to ``save()`` — the sole
        writer — which re-reads the file and re-cleans it, absorbing any external
        edits made during the run. Keeping this in-memory avoids writing the config
        file twice per run.
        """
        if self.ROOT_KEY in self._data:
            self._data[self.ROOT_KEY] = self._clean_products(self._data[self.ROOT_KEY])

    def save(self) -> None:
        """Applies pending updates and saves the data back to the JSON file atomically.

        Re-reads the file from disk to merge with any external edits made
        during the scraping run, then applies cached updates and performs
        a final duplicate cleanup before writing.
        """
        fresh_data: Dict[str, Any] = {}
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as file:
                    fresh_data = json.load(file)
            except json.JSONDecodeError:
                fresh_data = self._data  # Fallback to in-memory data if corrupted
        else:
            fresh_data = self._data

        if self.ROOT_KEY in fresh_data:
            for product in fresh_data[self.ROOT_KEY]:
                url = str(product.get("url", ""))
                clean_url = self._get_clean_url(url)

                if clean_url in self._updates:
                    for key, value in self._updates[clean_url].items():
                        product[key] = value

            # We also need to clean duplicates when saving to ensure any user edits during scraping are handled.
            fresh_data[self.ROOT_KEY] = self._clean_products(fresh_data[self.ROOT_KEY])

        self._data = fresh_data
        self._save_json_atomically(self._data)

    def parse_item(self, data: Dict[str, Any]) -> BaseTrackedItem:
        """Parses a dictionary into a ``MODEL`` instance."""
        return self.MODEL.from_dict(data)

    def is_valid_item(self, item: Dict[str, Any]) -> bool:
        """Validates an item dictionary.

        Args:
            item (Dict[str, Any]): The item dictionary to validate.

        Returns:
            bool: True if the item has a name, a scrappable URL, and a valid target price.
        """
        if "name" not in item:
            return False

        if not self.is_scrappable_item(item):
            return False

        if not self.has_valid_target_price(item):
            return False

        return True

    def is_scrappable_item(self, item: Dict[str, Any]) -> bool:
        """Checks whether the item has a scrappable product URL.

        Composes the shared supported-domain check (inherited, driven by the
        plugin) with the store-specific path rule (:meth:`_matches_product_path`),
        so a concrete plugin declares only the path shape. Override this method
        entirely only for stores whose scrappability cannot be expressed as
        "supported domain + path shape".

        Args:
            item (Dict[str, Any]): The item dictionary to check.

        Returns:
            bool: True if the URL is on a supported domain and its path matches.
        """
        url = item.get("url", "")
        return self._url_on_supported_domain(url) and self._matches_product_path(url)

    @abstractmethod
    def _matches_product_path(self, url: str) -> bool:
        """Returns True if the URL path matches this store's product-page shape.

        Called only after the domain has been confirmed supported, so the URL is
        guaranteed to be a non-empty string on a supported domain; implementations
        need only inspect the path (e.g. a numeric product-id segment).

        Args:
            url (str): A URL already confirmed to be on a supported domain.

        Returns:
            bool: True if the path matches this store's product-page shape.
        """
        ...
