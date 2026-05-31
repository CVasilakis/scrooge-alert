import json
import os
import logging
from urllib.parse import urlparse
from typing import Dict, Any

class ProductsManager:
    def __init__(self, products_path: str):
        """Initializes the ProductsManager.

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

    def update_product(self, url: str, last_price: float, last_checked: str) -> None:
        """Caches updates for a product based on its clean URL.

        Args:
            url (str): The URL of the product.
            last_price (float): The most recent scraped price.
            last_checked (str): The formatted timestamp of the last check.
        """
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
            logging.info("")
            logging.error("🛑 Failed to update config/skroutz.json file!")
            logging.error(f"    ↳  {e}")
            logging.info("")
