from dataclasses import dataclass

@dataclass
class ScrapeResult:
    price: float
    currency: str

@dataclass
class Product:
    name: str
    url: str
    target_price: float
    skip: bool = False
    last_price: float = 0.0
    last_checked: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> 'Product':
        """Creates a Product instance from a dictionary.
        
        Args:
            data (dict): The dictionary containing product data.
            
        Returns:
            Product: A new Product instance populated with data from the dictionary.
        """
        try:
            target_price_raw = data.get('target_price', 0.0)
            if isinstance(target_price_raw, str):
                target_price_raw = target_price_raw.strip('"').strip("'").replace(',', '.')
            target_price = float(target_price_raw)
        except (ValueError, TypeError):
            target_price = -1.0 # indicating invalid
            
        return cls(
            name=data.get('name', 'Unknown'),
            url=data.get('url', ''),
            target_price=target_price,
            skip=data.get('skip', False),
            last_price=data.get('last_price', 0.0),
            last_checked=data.get('last_checked', '')
        )
