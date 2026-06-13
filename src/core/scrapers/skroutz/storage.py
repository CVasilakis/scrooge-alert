import re
from urllib.parse import urlparse
from typing import Dict, Any

from scrapers.base.storage import JsonProductDataManager
from scrapers.skroutz.model import Product
from scrapers.skroutz.plugin import SkroutzPlugin


class SkroutzDataManager(JsonProductDataManager):
    """Data manager for Skroutz products.

    Inherits the entire JSON load/save/update/clean lifecycle from
    :class:`JsonProductDataManager`; only the Skroutz-specific URL rule
    (a supported domain plus a ``/<product-id>/`` path) is implemented here.
    """

    MODEL = Product
    ROOT_KEY = "products"

    def is_scrappable_item(self, item: Dict[str, Any]) -> bool:
        """Checks if the item has a valid Skroutz product URL.

        Args:
            item (Dict[str, Any]): The item dictionary to check.

        Returns:
            bool: True if the URL is on a supported Skroutz domain and contains
                a numeric product-id path segment.
        """
        url = item.get("url", "")
        if not isinstance(url, str):
            return False

        parsed = urlparse(url)
        if not any(parsed.netloc.endswith(d) for d in SkroutzPlugin.get_supported_domains()):
            return False

        if not re.search(r'/\d+/', parsed.path):
            return False

        return True
