# Installed libraries
import tls_client
import apprise
from filelock import FileLock, Timeout
from dotenv import load_dotenv

# Standard libraries
import signal
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

# --- Script Constants ---

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
    def save_traceback(data_dir: str) -> None:
        """Saves the current exception traceback to an error log file."""
        log_path = os.path.join(data_dir, "error_log.txt")
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
            title='Skroutz Price Drop Alert! 📉',
            body=f'{product_name} found at a price below {target_price} {currency}.\nCurrent price = {current_price} {currency}.\nLink: {url}'
        )

    def notify_old_entries(self, hours: int, url: str) -> None:
        self.notify(
            title='Skroutz Tracking Stale ⚠️',
            body=f'Link {url} has not been updated for {hours} hours.\nCheck if product page has a problem and error logs.'
        )

    def notify_errors(self) -> None:
        self.notify(
            title='Skroutz Scraping Errors ❌',
            body='Skroutz Price Alert Script encountered errors on some products. Check error log.'
        )

class ProductsManager:
    def __init__(self, products_path: str):
        self.products_path = products_path
        self.products_data: Dict[str, Any] = {}
        self.product_updates: Dict[str, Dict[str, Any]] = {}

    def load(self) -> Dict[str, Any]:
        """Loads the products data from the JSON file."""
        if os.path.exists(self.products_path):
            with open(self.products_path, 'r') as file:
                self.products_data = json.load(file)
        return self.products_data

    def _get_clean_url(self, url: str) -> str:
        """Strips query parameters and fragments to return the clean base URL."""
        if not url:
            return ""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def update_product(self, url: str, last_price: float, last_successful_check: str) -> None:
        """Caches updates for a product based on its clean URL."""
        clean_url = self._get_clean_url(url)
        self.product_updates[clean_url] = {
            'last_price': last_price,
            'last_successful_check': last_successful_check
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

        # Merge updates into the fresh data and remove duplicates
        if "products" in fresh_data:
            seen_urls = set()
            unique_products = []
            for product in fresh_data["products"]:
                url = product.get("url")
                clean_url = self._get_clean_url(url)

                if clean_url in seen_urls:
                    continue
                seen_urls.add(clean_url)

                # Overwrite the URL with the cleaned version so the JSON stays clean
                product["url"] = clean_url

                if clean_url in self.product_updates:
                    updates = self.product_updates[clean_url]
                    product["last_price"] = updates["last_price"]
                    product["last_successful_check"] = updates["last_successful_check"]

                unique_products.append(product)

            fresh_data["products"] = unique_products

        # Update the in-memory state for subsequent operations
        self.products_data = fresh_data

        temp_file_path = self.products_path + ".tmp"
        with open(temp_file_path, mode='w') as file:
            json.dump(self.products_data, file, indent=2)
        os.replace(temp_file_path, self.products_path)

    def check_for_old_entries(self, hours: int, notifier: Notifier) -> None:
        """Checks if any products haven't been successfully checked in the specified hours."""
        for row in self.products_data.get("products", []):
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
    def __init__(self, silent: bool = False):
        self.silent = silent
        self.interrupted = False

    def signal_handler(self, signum, frame):
        sig_name = 'SIGINT (Ctrl+C)' if signum == signal.SIGINT else 'SIGTERM (System Shutdown/Termination)' if signum == signal.SIGTERM else signum
        if not self.silent:
            print(f"\nReceived signal {sig_name}. Gracefully shutting down...")
        self.interrupted = True

    def _sleep_with_jitter(self, base_delay: float, attempt: int = 0) -> None:
        """Sleeps for a base time plus some jitter based on the current attempt."""
        jitter = random.uniform(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)
        total_delay = base_delay + (RETRY_DELAY_MULTIPLIER * attempt) + jitter

        if not self.silent:
            print(f"⏳ Sleeping for {total_delay:.2f} seconds...")

        # Break sleep into smaller chunks to remain responsive to interruptions
        start_time = time.time()
        while time.time() - start_time < total_delay:
            if self.interrupted:
                break
            time.sleep(0.5)

    def scrape_product(self, product_url: str, product_name: str) -> Optional[float]:
        """Scrapes the Skroutz product page and returns the minimum price found."""
        parsed_url = urlparse(product_url)
        domain = parsed_url.netloc
        match = re.search(r'/s/(\d+)', parsed_url.path)

        if not match:
            if not self.silent:
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
                if not self.silent:
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

    def process_products(self, products_manager: ProductsManager, notifier: Notifier, data_dir: str) -> None:
        """Orchestrates the scraping of all products in the products data."""
        # Register signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        products = products_manager.products_data.get("products", [])
        has_errors = False

        if not self.silent:
            print(f"Loaded {len(products)} products from products data.")

        for index, entry in enumerate(products):
            if self.interrupted:
                break

            if not self.silent and index >= 0:
                print()

            self._sleep_with_jitter(MIN_DELAY_SECONDS)
            if self.interrupted:
                break

            product_name = entry.get('productName', 'Unknown')

            url = entry.get('url', '')
            if not url:
                if not self.silent:
                    print(f"⚠️ {product_name}: URL is missing, skipping product.")
                continue

            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            currency = 'Lei' if domain.endswith('.ro') else '€'

            if 'targetPrice' not in entry:
                if not self.silent:
                    print(f"⚠️ {product_name}: Target price is missing, defaulting to 0.0.")
            target_price = float(entry.get('targetPrice', 0.0))

            for attempt in range(MAX_RETRIES):
                if self.interrupted:
                    break

                try:
                    current_price = self.scrape_product(url, product_name)

                    if self.interrupted:
                        break

                    if current_price is not None:
                        if current_price < target_price:
                            if not self.silent:
                                print(f"🚨 {product_name}: {current_price} {currency} (Target: {target_price} {currency})")
                            notifier.notify_low_price(product_name, target_price, current_price, url, currency)
                        else:
                            if not self.silent:
                                print(f"✅ {product_name}: {current_price} {currency} (Target: {target_price} {currency})")

                        # Update the timestamp and last price
                        products_manager.update_product(
                            url=url,
                            last_price=current_price,
                            last_successful_check=datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                        )
                        break # Success, move to the next product
                    else:
                        break # Unavailable or invalid URL, move to next

                except json.JSONDecodeError as e:
                    if not self.silent:
                        print(f"Attempt {attempt + 1} failed: Received empty response for {product_name}.")
                    self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
                except Exception as e:
                    if not self.silent:
                        print(f"Attempt {attempt + 1} FAILED ({type(e).__name__}): {e} --> {product_name} --> {url}")

                    if attempt == MAX_RETRIES - 1:
                        ErrorHandler.save_traceback(data_dir)
                        has_errors = True
                        break

                    self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)

        # Save updates
        if not self.silent:
            print()
            if self.interrupted:
                print("Saving products data...")
            else:
                print("Saving products data and checking for old entries...")
        products_manager.save_atomically()

        if not self.interrupted:
            products_manager.check_for_old_entries(OLD_ENTRY_HOURS, notifier)

        if has_errors and not self.interrupted:
            notifier.notify_errors()


# --- Main Execution ---

def main() -> None:
    parser = argparse.ArgumentParser(description='Script with debug flag')
    parser.add_argument('--debug', action='store_true', help='Skip the initial startup delay')
    parser.add_argument('--silent', action='store_true', help='Run script with no console output')
    parser.add_argument('--test-notification', action='store_true', help='Send a test notification via Apprise and exit')
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_data_dir = os.path.join(base_dir, "data")
    data_dir = os.environ.get("DATA_DIR", default_data_dir)

    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    env_path = os.path.join(base_dir, '.env')
    env_loaded = load_dotenv(dotenv_path=env_path)

    products_file_path = os.path.join(data_dir, "products.json")

    if not args.silent:
        print("Starting Skroutz Price Alert...")
        if not env_loaded or not os.path.exists(env_path):
            print("⚠️ No .env file found or loaded.")

    if not os.path.exists(products_file_path):
        if not args.silent:
            print(f"❌ The products.json file is missing! Please create it at {products_file_path} or copy from products.json.example.")
        return

    notification_urls = os.environ.get("NOTIFICATION_URLS", "")

    if not args.silent:
        env_exists = env_loaded or os.path.exists(env_path)
        if not notification_urls and env_exists:
            print("⚠️ No NOTIFICATION_URLS provided in environment.")
        elif notification_urls and ("<bot_token>" in notification_urls or "<chat_id>" in notification_urls or "<webhook_id>" in notification_urls or "<webhook_token>" in notification_urls):
            print("⚠️ NOTIFICATION_URLS contains an unconfigured placeholder. Please update it.")

    notifier = Notifier(notification_urls)

    if args.test_notification:
        if not args.silent:
            print("Sending test notification...")
        notifier.notify(
            title="Skroutz Price Alert Test",
            body="This is a test notification from Skroutz Price Alert."
        )
        if not args.silent:
            print("Test notification sent. Exiting.")
        return

    # Initial Delay
    random.seed(time.time())
    if not args.debug:
        delay = random.randint(1, STARTUP_DELAY_MAX)
        if not args.silent:
            print(f"⏳ Waiting for {delay} seconds before starting. Use the --debug flag to skip this.")
        time.sleep(delay)

    # Initialize ProductsManager
    products_manager = ProductsManager(products_file_path)
    products_data = products_manager.load()

    # Locking and Execution
    lock_file_path = os.path.join(data_dir, "skroutz_price_alert_running.lock")
    lock = FileLock(lock_file_path, timeout=LOCK_TIMEOUT)

    try:
        with lock:
            scraper = SkroutzScraper(silent=args.silent)
            scraper.process_products(products_manager, notifier, data_dir)

    except Timeout:
        if not args.silent:
            print('Skroutz Price Alert script did not start! Another instance is currently running.')
    except Exception:
        ErrorHandler.save_traceback(data_dir)
        notifier.notify(
            title='Skroutz Script Crash 💥',
            body='Skroutz Price Alert Script failed. Check error log.'
        )

if __name__ == "__main__":
    main()

