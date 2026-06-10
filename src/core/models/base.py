from dataclasses import dataclass, field
from typing import Any, Dict, Type, TypeVar

from utils import parse_price

T = TypeVar('T', bound='BaseTrackedItem')


@dataclass
class ScrapeResult:
    """Represents the result of a successful price scrape.

    Attributes:
        price: The scraped price as a float.
        currency: The currency symbol (e.g. ``"€"``, ``"Lei"``).
        metadata: Optional extra data returned by the scraper (e.g.
            ``{"stock": "in_stock", "seller": "StoreName"}``).  Consumers
            that only need ``price`` and ``currency`` can ignore this.
    """
    price: float
    currency: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BaseTrackedItem:
    """Base class for any item tracked by the scraper.

    Every tracked item — regardless of which store it comes from — has a
    human-readable name, a URL, a target price for alerting, the most
    recently scraped price, a skip flag, and a last-checked timestamp.

    Subclasses may add store-specific fields (e.g. an SKU or category)
    and should override ``from_dict`` / ``to_dict`` accordingly.
    """
    name: str = "Unknown"
    url: str = ""
    target_price: float = 0.0
    last_price: float = 0.0
    skip: bool = False
    last_checked: str = ""

    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        """Creates an instance from a dictionary.

        Error-handling contract:
            * Missing keys fall back to the field defaults declared above.
            * Invalid ``target_price`` values (non-numeric strings, None)
              are stored as ``-1.0`` to signal invalidity.  The caller
              (typically the orchestrator) is responsible for detecting the
              sentinel and deciding how to proceed.

        Args:
            data (Dict[str, Any]): The item data dictionary.

        Returns:
            BaseTrackedItem: A new instance populated with data from the
            dictionary.
        """
        target_price = parse_price(data.get('target_price', 0.0))
        if target_price is None:
            target_price = -1.0  # sentinel: invalid value

        return cls(
            name=data.get('name', 'Unknown'),
            url=data.get('url', ''),
            target_price=target_price,
            last_price=data.get('last_price', 0.0),
            skip=data.get('skip', False),
            last_checked=data.get('last_checked', ''),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the item back to a dictionary.

        The output is compatible with ``from_dict`` for round-tripping.
        Subclasses that add fields should override this method and merge
        with ``super().to_dict()``.

        Returns:
            Dict[str, Any]: A dictionary representation of the item.
        """
        return {
            'name': self.name,
            'url': self.url,
            'target_price': self.target_price,
            'last_price': self.last_price,
            'skip': self.skip,
            'last_checked': self.last_checked,
        }
