import json
import os
import re
from collections import defaultdict
from urllib.parse import urlparse
from typing import Dict, Any, List

from .base import BaseDataManager
from models.skroutz import Product
from exceptions import StorageFileError


class SkroutzDataManager(BaseDataManager):
    """Data manager for handling Skroutz-specific products and configuration."""
    def __init__(self, filepath: str):
        """Initializes the SkroutzDataManager.

        Args:
            filepath (str): The file path to the products JSON file.
        """
        super().__init__(filepath)
        self.products_data: Dict[str, Any] = {}
        self.product_updates: Dict[str, Dict[str, Any]] = {}

    def get_store_name(self) -> str:
        """Returns the human-readable store name.

        Returns:
            str: ``"Skroutz"``.
        """
        return "Skroutz"

    def load(self) -> Dict[str, Any]:
        """Loads the products data from the JSON file.

        Returns:
            Dict[str, Any]: The parsed JSON data representing products.

        Raises:
            StorageFileError: If the file cannot be read or contains invalid JSON.
        """
        try:
            with open(self.filepath, 'r') as file:
                self.products_data = json.load(file)
        except (OSError, json.JSONDecodeError) as e:
            raise StorageFileError(f"Failed to load {self.filepath}: {e}")

        return self.products_data

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
        """Caches updates for a product based on its clean URL.

        Args:
            url (str): The URL of the product to update.
            **updates: Arbitrary field updates (e.g. ``last_price=12.5``,
                ``last_checked="11-06-2026 01:00:00"``).
        """
        clean_url = self._get_clean_url(url)
        if clean_url in self.product_updates:
            self.product_updates[clean_url].update(updates)
        else:
            self.product_updates[clean_url] = dict(updates)

    def get_items(self) -> List[Dict[str, Any]]:
        """Returns the list of products as dictionaries."""
        return self.products_data.get("products", [])

    def add_item(self, data: Dict[str, Any]) -> None:
        """Adds a new product to the in-memory storage.

        The item is appended to the products list. Call ``save``
        afterwards to persist the change.

        Args:
            data (Dict[str, Any]): The product data dictionary to add.
        """
        if "products" not in self.products_data:
            self.products_data["products"] = []
        self.products_data["products"].append(data)

    def remove_item(self, url: str) -> bool:
        """Removes a product from the in-memory storage by its URL.

        Matches against the cleaned (query-stripped) URL. Call ``save``
        afterwards to persist the change.

        Args:
            url (str): The URL of the product to remove.

        Returns:
            bool: True if the product was found and removed, False otherwise.
        """
        clean_target = self._get_clean_url(url)
        products = self.products_data.get("products", [])
        original_len = len(products)
        self.products_data["products"] = [
            p for p in products
            if self._get_clean_url(str(p.get("url", ""))) != clean_target
        ]
        return len(self.products_data["products"]) < original_len

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
        """Cleans up the configuration file before scraping."""
        if "products" in self.products_data:
            original_count = len(self.products_data["products"])
            cleaned = self._clean_products(self.products_data["products"])
            if len(cleaned) < original_count:
                self.products_data["products"] = cleaned
                self._save_json_atomically(self.products_data)

    def save(self) -> None:
        """Applies pending updates and saves the products data back to the JSON file atomically.

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
                fresh_data = self.products_data  # Fallback to in-memory data if corrupted
        else:
            fresh_data = self.products_data

        if "products" in fresh_data:
            for product in fresh_data["products"]:
                url = str(product.get("url", ""))
                clean_url = self._get_clean_url(url)

                if clean_url in self.product_updates:
                    for key, value in self.product_updates[clean_url].items():
                        product[key] = value

            # We also need to clean duplicates when saving to ensure any user edits during scraping are handled.
            fresh_data["products"] = self._clean_products(fresh_data["products"])

        self.products_data = fresh_data
        self._save_json_atomically(self.products_data)

    def parse_item(self, data: Dict[str, Any]) -> Product:
        """Parses a dictionary into a Product."""
        return Product.from_dict(data)

    def is_scrappable_item(self, item: Dict[str, Any]) -> bool:
        """Checks if the item has a valid, properly formatted URL."""
        url = item.get("url", "")
        if not isinstance(url, str):
            return False

        parsed = urlparse(url)
        if "skroutz.gr" not in parsed.netloc:
            return False

        if not re.search(r'/\d+/', parsed.path):
            return False

        return True

    def is_valid_item(self, item: Dict[str, Any]) -> bool:
        """Validates a product item dictionary.

        Args:
            item (Dict[str, Any]): The item dictionary to validate.

        Returns:
            bool: True if the item contains required fields, valid URL, and valid price.
        """
        if "name" not in item:
            return False

        if not self.is_scrappable_item(item):
            return False

        if not self.has_valid_target_price(item):
            return False

        return True

    def validate_storage(self) -> tuple[int, list[int]]:
        """Validates the skroutz.json file and counts products.

        Returns:
            tuple[int, list[int]]: A tuple containing the total number of products and a list of 1-based indices of faulty products.
        """
        config_dir = os.path.dirname(self.filepath)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)

        if not os.path.exists(self.filepath) or not os.path.isfile(self.filepath):
            raise StorageFileError("The config/skroutz.json file is missing or not a file")

        if not os.access(self.filepath, os.R_OK | os.W_OK):
            raise StorageFileError("The config/skroutz.json file has wrong permissions")

        try:
            with open(self.filepath, 'r') as f:
                data = json.load(f)
                if not isinstance(data, dict) or not isinstance(data.get("products"), list):
                    raise StorageFileError("The config/skroutz.json file contains invalid JSON format")

                products = data.get("products", [])
                num_products = len(products)
                faulty_indices = [i + 1 for i, p in enumerate(products) if not self.is_valid_item(p)]
                return num_products, faulty_indices
        except (json.JSONDecodeError, OSError):
            raise StorageFileError("The config/skroutz.json file contains invalid JSON format")
