# Installed libraries
import tls_client
import apprise
from filelock import FileLock, Timeout
from dotenv import load_dotenv

# Standard libraries
import traceback
import datetime
import argparse
import random
import time
import json
import os
import re
from urllib.parse import urlparse
from typing import Dict, Any, Optional

# --- Configuration Constants ---

# Maximum number of times to retry scraping a product if the request fails
MAX_RETRIES: int = 3

# Number of hours after which a product check is considered old, triggering a warning
OLD_ENTRY_HOURS: int = 24

# Base delay in seconds between processing each product to avoid rate limits
MIN_DELAY_SECONDS: int = 20

# Minimum random time in seconds added to the base delay (jitter)
RANDOM_DELAY_MIN: float = 1.0

# Maximum random time in seconds added to the base delay (jitter)
RANDOM_DELAY_MAX: float = 5.0

# Maximum possible startup delay in seconds (used only in non-debug mode)
STARTUP_DELAY_MAX: int = 60

# Timeout in seconds when trying to acquire the file lock (0 means fail immediately if locked)
LOCK_TIMEOUT: int = 0

# Multiplier used to increase the wait time on each retry attempt
RETRY_DELAY_MULTIPLIER: int = 3

# Headers impersonating a real browser to avoid being blocked by anti-bot measures
DEFAULT_HEADERS: Dict[str, str] = {
    'authority': 'www.skroutz.gr',
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9',
    'dnt': '1',
    'referer': 'https://www.skroutz.gr/search?keyphrase=witcher',
    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'x-requested-with': 'XMLHttpRequest',
}

# --- Classes ---

class ErrorHandler:
    @staticmethod
    def save_traceback(script_dir: str) -> None:
        """Saves the current exception traceback to an error log file."""
        log_path = os.path.join(script_dir, "error_log.txt")
        time_now = datetime.datetime.now().strftime("%Y-%m-%d (%H:%M:%S)")
        with open(log_path, "a", newline='') as log_file:
            log_file.write(f"\n\nAn error occurred at {time_now}:\n")
            traceback.print_exc(file=log_file)
            log_file.write(f"\n{'-'*100}")

class Notifier:
    def __init__(self, notification_urls: str):
        self.app_notif = apprise.Apprise()
        if notification_urls:
            for url in notification_urls.split(','):
                url = url.strip()
                if url:
                    self.app_notif.add(url)

    def notify(self, title: str, body: str) -> None:
        """Sends a notification with the given title and body."""
        self.app_notif.notify(title=title, body=body)

    def notify_low_price(self, product_name: str, target_price: float, current_price: float, url: str, currency: str = '€') -> None:
        self.notify(
            title='Skroutz Price Alert - Attention required!',
            body=f'{product_name} found at a price bellow {target_price} {currency}.\nCurrent price = {current_price} {currency}.\nLink: {url}'
        )

    def notify_old_entries(self, hours: int, url: str) -> None:
        self.notify(
            title='Skroutz Price Alert - Attention required!',
            body=f'Link {url} has not been updated for {hours} hours.\nCheck if product page has a problem and error logs.'
        )

    def notify_errors(self) -> None:
        self.notify(
            title='Skroutz Price Alert - Attention required!',
            body='Skroutz Price Alert Script encountered errors on some products. Check error log.'
        )

class ConfigManager:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config_data: Dict[str, Any] = {}

    def load(self) -> Dict[str, Any]:
        """Loads the configuration from the JSON file."""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as file:
                self.config_data = json.load(file)
        return self.config_data

    def save_atomically(self) -> None:
        """Saves the configuration back to the JSON file atomically."""
        temp_file_path = self.config_path + ".tmp"
        with open(temp_file_path, mode='w') as file:
            json.dump(self.config_data, file, indent=2)
        os.replace(temp_file_path, self.config_path)

    def check_for_old_entries(self, hours: int, notifier: Notifier) -> None:
        """Checks if any products haven't been successfully checked in the specified hours."""
        for row in self.config_data.get("products", []):
            url = row.get('url', '')
            product_name = row.get('productName', 'Unknown')
            last_check = row.get('last_successful_check')
            if last_check:
                try:
                    timestamp = datetime.datetime.strptime(last_check, "%d-%m-%Y %H:%M:%S")
                    current_time = datetime.datetime.now()
                    if (current_time - timestamp) > datetime.timedelta(hours=hours):
                        print(f"⚠️ Old entry found for {product_name}: {url} (Last check: {last_check})")
                        notifier.notify_old_entries(hours, url)
                except ValueError:
                    pass

class SkroutzScraper:
    def __init__(self, debug: bool = False):
        self.debug = debug

    def _sleep_with_jitter(self, base_delay: float, attempt: int = 0) -> None:
        """Sleeps for a base time plus some jitter based on the current attempt."""
        jitter = random.uniform(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)
        total_delay = base_delay + (RETRY_DELAY_MULTIPLIER * attempt) + jitter
        time.sleep(total_delay)

    def scrape_product(self, product_url: str, product_name: str) -> Optional[float]:
        """Scrapes the Skroutz product page and returns the minimum price found."""
        parsed_url = urlparse(product_url)
        domain = parsed_url.netloc
        match = re.search(r'/s/(\d+)', parsed_url.path)

        if not match:
            if self.debug:
                print(f"{product_name}: Failed to parse product ID from URL: {product_url}")
            return None

        product_id = match.group(1)
        api_link = f"https://{domain}/s/{product_id}/filter_products.json?"

        session = tls_client.Session(
            client_identifier="chrome120",
            random_tls_extension_order=True
        )

        try:
            headers = DEFAULT_HEADERS.copy()
            headers['authority'] = domain
            headers['referer'] = f"https://{domain}/search?keyphrase=witcher"

            response = session.get(api_link.strip(), headers=headers)
            response_data = response.json()

            if response_data.get("price_min") is None:
                if self.debug:
                    print(f"{product_name}: Not available")
                return None

            price_str = response_data["price_min"]
            # Remove any non-numeric characters except for '.' and ','
            price_str = re.sub(r'[^\d.,]', '', price_str)
            price_str = price_str.replace(",", ".")
            if price_str.count(".") == 2:
                price_str = price_str.replace(".", "", 1)

            return float(price_str)

        finally:
            session.close()

    def process_products(self, config_manager: ConfigManager, notifier: Notifier, script_dir: str) -> None:
        """Orchestrates the scraping of all products in the configuration."""
        products = config_manager.config_data.get("products", [])
        has_errors = False

        if self.debug:
            print(f"Loaded {len(products)} products from configuration.")

        for index, entry in enumerate(products):
            self._sleep_with_jitter(MIN_DELAY_SECONDS)

            product_name = entry.get('productName', 'Unknown')
            if self.debug:
                print(f"Checking product: {product_name}")

            url = entry.get('url', '')
            if not url:
                continue

            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            currency = 'Lei' if domain.endswith('.ro') else '€'

            target_price = float(entry.get('targetPrice', 0.0))

            for attempt in range(MAX_RETRIES):
                try:
                    current_price = self.scrape_product(url, product_name)

                    if current_price is not None:
                        if current_price < target_price:
                            if self.debug:
                                print(f"🚨 {product_name}: {current_price} {currency} (Target: {target_price} {currency})")
                            notifier.notify_low_price(product_name, target_price, current_price, url, currency)
                        else:
                            if self.debug:
                                print(f"✅ {product_name}: {current_price} {currency} (Target: {target_price} {currency})")

                        # Update the timestamp
                        config_manager.config_data["products"][index]['last_successful_check'] = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                        break # Success, move to the next product
                    else:
                        break # Unavailable or invalid URL, move to next

                except json.JSONDecodeError as e:
                    if self.debug:
                        print(f"Attempt {attempt + 1} failed: Received empty response from site.")
                    self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
                except Exception as e:
                    if self.debug:
                        print(f"Attempt {attempt + 1} FAILED ({type(e).__name__}): {e} --> {product_name} --> {url}")

                    if attempt == MAX_RETRIES - 1:
                        ErrorHandler.save_traceback(script_dir)
                        has_errors = True
                        break

                    self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)

        # Save updates
        if self.debug:
            print("Saving configuration and checking for old entries...")
        config_manager.save_atomically()
        config_manager.check_for_old_entries(OLD_ENTRY_HOURS, notifier)

        if has_errors:
            notifier.notify_errors()


# --- Main Execution ---

def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description='Script with debug flag')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_file_path = os.path.join(script_dir, "products.json")

    if args.debug:
        print("Starting Skroutz Price Alert...")

    # Initial Setup & Delay
    random.seed(time.time())
    if not args.debug:
        time.sleep(random.randint(1, STARTUP_DELAY_MAX))

    # Initialize Config and Notifier
    config_manager = ConfigManager(json_file_path)
    config_data = config_manager.load()
    notification_urls = os.environ.get("NOTIFICATION_URLS", "")
    notifier = Notifier(notification_urls)

    # Locking and Execution
    lock_file_path = os.path.join(script_dir, "skroutz_price_alert_running.lock")
    lock = FileLock(lock_file_path, timeout=LOCK_TIMEOUT)

    try:
        with lock:
            scraper = SkroutzScraper(debug=args.debug)
            scraper.process_products(config_manager, notifier, script_dir)

    except Timeout:
        if args.debug:
            print('Skroutz Price Alert script did not start! Another instance is currently running.')
    except Exception:
        ErrorHandler.save_traceback(script_dir)
        notifier.notify(
            title='Skroutz Price Alert - Attention required!',
            body='Skroutz Price Alert Script failed. Check error log.'
        )

if __name__ == "__main__":
    main()

