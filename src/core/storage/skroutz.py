import json
import os
from urllib.parse import urlparse
from typing import Dict, Any, List
from .base import BaseDataManager
from models.skroutz import Product
from exceptions import StorageFileError
from constants import CONFIG_DIR

class SkroutzDataManager(BaseDataManager):
    """Data manager for handling Skroutz-specific products and configuration."""
    def __init__(self, products_path: str):
        """Initializes the SkroutzDataManager.

        Args:
            products_path (str): The file path to the products JSON file.
        """
        self.products_path = products_path
        self.products_data: Dict[str, Any] = {}
        self.product_updates: Dict[str, Dict[str, Any]] = {}

    def load(self) -> Dict[str, Any]:
        """Loads the products data from the JSON file.

        Returns:
            Dict[str, Any]: The parsed JSON data representing products.
        """
        try:
            with open(self.products_path, 'r') as file:
                self.products_data = json.load(file)
        except (OSError, json.JSONDecodeError):
            self.products_data = {"products": []}

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

    def update_item(self, url: str, last_price: float, last_checked: str) -> None:
        """Caches updates for a product based on its clean URL."""
        clean_url = self._get_clean_url(url)
        self.product_updates[clean_url] = {
            'last_price': last_price,
            'last_checked': last_checked
        }

    def save_atomically(self) -> None:
        """Saves the products data back to the JSON file atomically."""
        fresh_data: Dict[str, Any] = {}
        if os.path.exists(self.products_path):
            try:
                with open(self.products_path, 'r') as file:
                    fresh_data = json.load(file)
            except json.JSONDecodeError:
                fresh_data = self.products_data  # Fallback to in-memory data if corrupted
        else:
            fresh_data = self.products_data

        if "products" in fresh_data:
            seen_urls = set()
            unique_products = []
            for product in fresh_data["products"]:
                url = product.get("url")
                clean_url = self._get_clean_url(url)

                if clean_url in seen_urls:
                    continue
                seen_urls.add(clean_url)

                product["url"] = clean_url

                if clean_url in self.product_updates:
                    updates = self.product_updates[clean_url]
                    product["last_price"] = updates["last_price"]
                    product["last_checked"] = updates["last_checked"]

                if "skip" not in product:
                    product["skip"] = False

                unique_products.append(product)

            fresh_data["products"] = unique_products

        self.products_data = fresh_data

        temp_file_path = self.products_path + ".tmp"
        try:
            with open(temp_file_path, mode='w') as file:
                json.dump(self.products_data, file, indent=2)
            os.replace(temp_file_path, self.products_path)
        except OSError as e:
            raise StorageFileError(str(e))

    def parse_item(self, data: Dict[str, Any]) -> Product:
        """Parses a dictionary into a Product."""
        return Product.from_dict(data)

    def get_items(self) -> List[Dict[str, Any]]:
        """Returns the list of products as dictionaries."""
        return self.products_data.get("products", [])

    def validate_storage(self) -> tuple[int, list[int]]:
        """Validates the skroutz.json file and counts products.

        Returns:
            tuple[int, list[int]]: A tuple containing the total number of products and a list of 1-based indices of faulty products.
        """
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)

        if not os.path.exists(self.products_path) or not os.path.isfile(self.products_path):
            raise StorageFileError("The config/skroutz.json file is missing or not a file")

        if not os.access(self.products_path, os.R_OK | os.W_OK):
            raise StorageFileError("The config/skroutz.json file has wrong permissions")

        try:
            with open(self.products_path, 'r') as f:
                data = json.load(f)
                if not isinstance(data, dict) or not isinstance(data.get("products"), list):
                    raise StorageFileError("The config/skroutz.json file contains invalid JSON format")

                products = data.get("products", [])
                num_products = len(products)
                faulty_indices = [i + 1 for i, p in enumerate(products) if not all(k in p for k in ("name", "url", "target_price"))]
                return num_products, faulty_indices
        except (json.JSONDecodeError, OSError):
            raise StorageFileError("The config/skroutz.json file contains invalid JSON format")
