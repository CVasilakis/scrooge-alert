from dataclasses import dataclass
from typing import Dict, Any
from .base import BaseTrackedItem
from utils import parse_price

@dataclass
class Product(BaseTrackedItem):
    """Represents a product tracked on Skroutz."""
    name: str = "Unknown"
    target_price: float = 0.0
    last_price: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Product':
        """Creates a Product instance from a dictionary.

        Args:
            data (Dict[str, Any]): The dictionary containing product data.

        Returns:
            Product: A new Product instance populated with data from the dictionary.
        """
        target_price = parse_price(data.get('target_price', 0.0))
        if target_price is None:
            target_price = -1.0  # indicating invalid

        return cls(
            name=data.get('name', 'Unknown'),
            url=data.get('url', ''),
            target_price=target_price,
            skip=data.get('skip', False),
            last_price=data.get('last_price', 0.0),
            last_checked=data.get('last_checked', '')
        )

