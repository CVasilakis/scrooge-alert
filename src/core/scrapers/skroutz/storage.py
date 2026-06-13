import re
from urllib.parse import urlparse

from scrapers.base.storage import JsonProductDataManager
from scrapers.skroutz.model import Product


class SkroutzDataManager(JsonProductDataManager):
    """Data manager for Skroutz products.

    Inherits the entire JSON lifecycle and the supported-domain check from
    :class:`JsonProductDataManager`; only the Skroutz-specific URL-path rule
    (a ``/<product-id>/`` numeric segment) is declared here. The supported
    domains come from the injected plugin, so they are never duplicated.
    """

    MODEL = Product
    ROOT_KEY = "products"

    def _matches_product_path(self, url: str) -> bool:
        """Returns True if the URL path has a Skroutz numeric product-id segment.

        The domain has already been confirmed supported by the base class, so this
        only needs to inspect the path.

        Args:
            url (str): A URL already confirmed to be on a supported Skroutz domain.

        Returns:
            bool: True if the path contains a numeric product-id segment.
        """
        return bool(re.search(r'/\d+/', urlparse(url).path))
