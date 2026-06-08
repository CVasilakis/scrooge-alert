from abc import ABC, abstractmethod
from typing import Dict, Any, List
from models.base import BaseTrackedItem

class BaseDataManager(ABC):
    """Abstract base class for managing data storage and retrieval."""
    def __init__(self, filepath: str) -> None:
        """Initializes the data manager with a file path.

        Args:
            filepath (str): The path to the storage file.
        """
        self.filepath = filepath

    @abstractmethod
    def load(self) -> Dict[str, Any]:
        """Loads data from the storage.

        Returns:
            Dict[str, Any]: The parsed data representing tracked items.
        """
        pass

    @abstractmethod
    def save_atomically(self) -> None:
        """Saves the data back to storage atomically."""
        pass

    @abstractmethod
    def update_item(self, url: str, last_price: float, last_checked: str) -> None:
        """Caches updates for an item based on its URL.

        Args:
            url (str): The URL of the item.
            last_price (float): The most recent scraped price.
            last_checked (str): The formatted timestamp of the last check.
        """
        pass

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
    def get_items(self) -> List[Dict[str, Any]]:
        """Returns the list of items as dictionaries from the loaded data.

        Returns:
            List[Dict[str, Any]]: The list of item data dictionaries.
        """
        pass
