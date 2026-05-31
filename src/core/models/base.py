from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class ScrapeResult:
    price: float
    currency: str

@dataclass
class BaseTrackedItem:
    url: str = ""
    skip: bool = False
    last_checked: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseTrackedItem':
        """Creates a BaseTrackedItem instance from a dictionary."""
        return cls(
            url=data.get('url', ''),
            skip=data.get('skip', False),
            last_checked=data.get('last_checked', '')
        )
