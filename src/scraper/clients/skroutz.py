import re
import logging
import random
from urllib.parse import urlparse
from typing import Optional, Dict

import json
import tls_client

from clients.base import BaseScraperClient
from models import ScrapeResult
from exceptions import ScraperError, RateLimitError, ServerError, ScraperParseError
from config import DEFAULT_HEADERS_POOL

class SkroutzClient(BaseScraperClient):
    def __init__(self):
        self.current_headers = random.choice(DEFAULT_HEADERS_POOL)
        self.session = tls_client.Session(
            client_identifier="chrome120",  # type: ignore
            random_tls_extension_order=True
        )

    def get_current_headers(self) -> Dict[str, str]:
        return self.current_headers

    def refresh_identity(self) -> None:
        self.current_headers = random.choice(DEFAULT_HEADERS_POOL)
        if hasattr(self, 'session'):
            self.session.close()
        self.session = tls_client.Session(
            client_identifier="chrome120",  # type: ignore
            random_tls_extension_order=True
        )

    def scrape_product(self, product_url: str, product_name: str) -> Optional[ScrapeResult]:
        parsed_url = urlparse(product_url)
        domain = parsed_url.netloc
        match = re.search(r'/s/(\d+)', parsed_url.path)

        if not match:
            logging.warning(f"❗️ {product_name}: Failed to parse product ID from URL: {product_url}")
            return None

        product_id = match.group(1)
        api_link = f"https://{domain}/s/{product_id}/filter_products.json?"

        headers = self.current_headers.copy()
        headers['authority'] = domain

        parsed_referer = urlparse(headers.get('referer', 'https://www.skroutz.gr/'))
        headers['referer'] = parsed_referer._replace(netloc=domain).geturl()

        response = self.session.get(api_link.strip(), headers=headers)

        if response.status_code is None:
            raise ScraperError("Empty response or no status code received from server")

        if response.status_code in (404, 410):
            logging.warning(f"❗ {product_name}: Product not found or removed (HTTP {response.status_code}).")
            return None
        elif response.status_code in (401, 403, 429):
            raise RateLimitError(f"Blocked or rate limited (HTTP {response.status_code})")
        elif 500 <= response.status_code < 600:
            raise ServerError(f"Skroutz server error (HTTP {response.status_code}), retrying...")
        elif response.status_code != 200:
            raise ScraperError(f"HTTP request failed with status code {response.status_code}")

        try:
            response_data = response.json()
        except json.JSONDecodeError as e:
            raise ScraperParseError(f"No JSON response: {e}")

        if response_data.get("price_min") is None:
            logging.warning(f"❗️ {product_name}: Not available")
            return None

        price_str = str(response_data["price_min"])
        price_str = re.sub(r'[^\d.,]', '', price_str)
        price_str = price_str.replace(",", ".")
        if price_str.count(".") == 2:
            price_str = price_str.replace(".", "", 1)

        currency = 'Lei' if domain.endswith('.ro') else '€'

        return ScrapeResult(price=float(price_str), currency=currency)

    def close(self) -> None:
        self.session.close()
