import re
import random
from urllib.parse import urlparse
from typing import Optional, Dict

import json
import tls_client

from clients.base import BaseScraperClient
from models.base import ScrapeResult
from exceptions import ScraperError, RateLimitError, ServerError, ScraperParseError, ProductNotFoundError, ProductUnavailableError, InvalidURLError

class SkroutzClient(BaseScraperClient):
    """Client for scraping product information from Skroutz."""

    # Headers impersonating a real browser to avoid being blocked by anti-bot measures.
    # The scraper rotates through these profiles randomly on retries.
    HEADERS_POOL: list[Dict[str, str]] = [
        {
            'authority': 'www.skroutz.gr',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'dnt': '1',
            'referer': 'https://www.skroutz.gr/search?keyphrase=home',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        },
        {
            'authority': 'www.skroutz.gr',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'el-GR,el;q=0.9,en-US;q=0.8,en;q=0.7',
            'dnt': '1',
            'referer': 'https://www.skroutz.gr/search?keyphrase=camera',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        },
        {
            'authority': 'www.skroutz.gr',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7',
            'dnt': '1',
            'referer': 'https://www.skroutz.gr/search?keyphrase=fantasy',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        },
        {
            'authority': 'www.skroutz.gr',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'bg-BG,bg;q=0.9,en-US;q=0.8,en;q=0.7',
            'dnt': '1',
            'referer': 'https://www.skroutz.gr/search?keyphrase=harry+potter',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        },
        {
            'authority': 'www.skroutz.gr',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
            'dnt': '1',
            'referer': 'https://www.skroutz.gr/c/11/home-garden.html',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        }
    ]

    def __init__(self):
        """Initializes the Skroutz client, picking a random header and setting up a TLS session."""
        self.current_headers = random.choice(self.HEADERS_POOL)
        self.session = tls_client.Session(
            client_identifier="chrome120",  # type: ignore
            random_tls_extension_order=True
        )

    def get_current_headers(self) -> Dict[str, str]:
        """Retrieves the current HTTP headers.

        Returns:
            Dict[str, str]: The current headers in use.
        """
        return self.current_headers

    def refresh_identity(self) -> None:
        """Refreshes the client's identity by selecting new headers and recreating the session."""
        self.current_headers = random.choice(self.HEADERS_POOL)
        if hasattr(self, 'session'):
            self.session.close()
        self.session = tls_client.Session(
            client_identifier="chrome120",  # type: ignore
            random_tls_extension_order=True
        )

    def scrape_product(self, product_url: str, product_name: str) -> Optional[ScrapeResult]:
        """Scrapes the Skroutz API for the current price of a product.

        Args:
            product_url (str): The Skroutz URL of the product.
            product_name (str): The name of the product.

        Returns:
            ScrapeResult: The scraped price and currency.

        Raises:
            ProductNotFoundError: If the product is not found.
            ProductUnavailableError: If the product is found but price is unavailable.
            InvalidURLError: If the provided URL is invalid.
            ScraperError: For generic scraping errors (e.g. empty response, unexpected HTTP code).
            RateLimitError: If the server blocks the request or limits the rate.
            ServerError: For server-side HTTP errors (5xx).
            ScraperParseError: If the API response cannot be decoded as JSON.
        """
        parsed_url = urlparse(product_url)
        domain = parsed_url.netloc
        match = re.search(r'/s/(\d+)', parsed_url.path)

        if not match:
            raise InvalidURLError(f"Failed to parse product ID from URL: {product_url}")

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
            raise ProductNotFoundError(f"Product not found or removed (HTTP {response.status_code}).")
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
            raise ProductUnavailableError("Not available")

        price_str = str(response_data["price_min"])
        price_str = re.sub(r'[^\d.,]', '', price_str)
        price_str = price_str.replace(",", ".")
        if price_str.count(".") == 2:
            price_str = price_str.replace(".", "", 1)

        currency = 'Lei' if domain.endswith('.ro') else '€'

        return ScrapeResult(price=float(price_str), currency=currency)

    def close(self) -> None:
        """Closes the underlying TLS session."""
        self.session.close()
