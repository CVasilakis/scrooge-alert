import json
import os
from abc import ABC, abstractmethod
from typing import Dict, Any, List

from scrapers.base.model import BaseTrackedItem
from utils import parse_price


class BaseDataManager(ABC):
    """Abstract base class for managing data storage and retrieval.

    Subclasses must call ``super().__init__(filepath)`` in their
    ``__init__`` and use ``self.filepath`` for all file operations so that
    the base-class helpers (e.g. ``_save_json_atomically``) work correctly.
    """
    def __init__(self, filepath: str) -> None:
        """Initializes the data manager with a file path.

        Args:
            filepath (str): The path to the storage file.
        """
        self.filepath = filepath

    # ------------------------------------------------------------------
    # Core lifecycle – must be implemented by every subclass
    # ------------------------------------------------------------------

    @abstractmethod
    def load(self) -> Dict[str, Any]:
        """Loads data from the storage.

        Returns:
            Dict[str, Any]: The parsed data representing tracked items.
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
    # Item CRUD
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

    @abstractmethod
    def add_item(self, data: Dict[str, Any]) -> None:
        """Adds a new item to the storage.

        Args:
            data (Dict[str, Any]): The item data dictionary to add.
        """
        pass

    @abstractmethod
    def remove_item(self, url: str) -> bool:
        """Removes an item from the storage by its URL.

        Args:
            url (str): The URL of the item to remove.

        Returns:
            bool: True if the item was found and removed, False otherwise.
        """
        pass

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

    @abstractmethod
    def validate_storage(self) -> tuple[int, list[int]]:
        """Validates the storage file and counts items.

        Returns:
            tuple[int, list[int]]: A tuple containing the total number of items and a list of 1-based indices of faulty items.

        Raises:
            StorageFileError: If the file is missing, unreadable, or contains invalid data.
        """
        pass

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

    @abstractmethod
    def get_store_name(self) -> str:
        """Returns a human-readable name for the store this manager handles.

        Returns:
            str: The store name (e.g. ``"Skroutz"``).
        """
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

    def _save_json_atomically(self, data: Dict[str, Any]) -> None:
        """Writes data to the JSON file atomically using a temp-file swap.

        This is a shared helper for any JSON-file-backed subclass.
        Writes to a temporary file first, then atomically replaces the
        target file via ``os.replace`` to prevent corruption on crash.

        Args:
            data (Dict[str, Any]): The data to serialize as JSON.

        Raises:
            StorageFileError: If the write operation fails.
        """
        from exceptions import StorageFileError

        temp_path = self.filepath + ".tmp"
        try:
            with open(temp_path, mode='w') as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, self.filepath)
        except OSError as e:
            raise StorageFileError(str(e))
