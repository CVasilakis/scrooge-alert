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
import sys
import subprocess
from urllib.parse import urlparse
from typing import Dict, Any, Optional, List

# --- Script Constants ---

# Base directory paths
BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR: str = os.path.join(BASE_DIR, "data")
PRODUCTS_FILE_PATH: str = os.path.join(DATA_DIR, "products.json")
LOCK_FILE_PATH: str = os.path.join(DATA_DIR, "skroutz_price_alert_running.lock")

# Unconfigured Apprise placeholders to ignore
APPRISE_PLACEHOLDERS: List[str] = ['<token>', '<bot_token>', '<chat_id>', '<webhook_id>', '<webhook_token>']

# Maximum number of times to retry scraping a product if the request fails
MAX_RETRIES: int = 3

# Number of hours after which a product check is considered old, triggering a warning
OLD_ENTRY_HOURS: int = 48

# Base delay in seconds between processing each product to avoid rate limits
MIN_DELAY_SECONDS: int = 20

# Minimum random time in seconds added to the base delay (jitter)
RANDOM_DELAY_MIN: float = 1.0

# Maximum random time in seconds added to the base delay (jitter)
RANDOM_DELAY_MAX: float = 5.0

# Timeout in seconds when trying to acquire the file lock (0 means fail immediately if locked)
LOCK_TIMEOUT: int = 0

# Multiplier used to increase the wait time on each retry attempt
RETRY_DELAY_MULTIPLIER: int = 3

# Headers impersonating a real browser to avoid being blocked by anti-bot measures
DEFAULT_HEADERS_POOL: List[Dict[str, str]] = [
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

# --- Classes ---

class ErrorHandler:
    @staticmethod
    def save_traceback(data_dir: str, url: Optional[str] = None, headers: Optional[Dict[str, str]] = None) -> None:
        """Saves the current exception traceback to an error log file."""
        log_path = os.path.join(data_dir, "error_log.txt")
        time_now = datetime.datetime.now().strftime("%Y-%m-%d (%H:%M:%S)")
        with open(log_path, "a", newline='') as log_file:
            log_file.write(f"\n\nAn error occurred at {time_now}:\n")
            if url:
                log_file.write(f"URL: {url}\n")
            if headers:
                header_id = f"Platform: {headers.get('sec-ch-ua-platform', 'Unknown')}, Lang: {headers.get('accept-language', 'Unknown')}"
                log_file.write(f"Header ID: {header_id}\n")
            traceback.print_exc(file=log_file)
            log_file.write(f"\n{'-'*100}")

class Notifier:
    def __init__(self, notification_urls: str):
        self.app_notif = apprise.Apprise()
        self.has_services = False
        if notification_urls:
            for url in notification_urls.split(','):
                url = url.strip()
                if url and not any(p in url for p in APPRISE_PLACEHOLDERS):
                    self.app_notif.add(url)
                    self.has_services = True

    def notify(self, title: str, body: str) -> None:
        """Sends a notification with the given title and body."""
        self.app_notif.notify(title=title, body=body)

    def notify_low_price(self, product_name: str, target_price: float, current_price: float, url: str, currency: str = '€') -> None:
        self.notify(
            title='Skroutz Price Drop Alert!',
            body=f'{product_name} is now available for {current_price}{currency}, which is below your target of {target_price}{currency}.\nView it here: {url}'
        )

    def notify_old_entries(self, product_name: str, hours: int, url: str) -> None:
        self.notify(
            title='Skroutz Tracking Stale',
            body=f'The scraping for "{product_name}" hasn\'t been successfully completed in over {hours} hours. Please check the error logs or verify if the URL is still valid.\nProduct URL: {url}'
        )

    def notify_errors(self) -> None:
        self.notify(
            title='Skroutz Scraping Errors',
            body='The Skroutz Price Alert script encountered errors while checking some of your products. Please review the error logs for more details.'
        )

    def notify_crash(self) -> None:
        self.notify(
            title='Skroutz Script Crash',
            body='The Skroutz Price Alert script failed unexpectedly. Please review the error logs for more details on the crash.'
        )

    def notify_test(self) -> None:
        self.notify(
            title='Skroutz Test Notification',
            body='This is a test message to confirm that your Skroutz Price Alert notifications are configured correctly!'
        )

class ProductsManager:
    def __init__(self, products_path: str):
        self.products_path = products_path
        self.products_data: Dict[str, Any] = {}
        self.product_updates: Dict[str, Dict[str, Any]] = {}

    def load(self, exit_on_error: bool = True) -> Dict[str, Any]:
        """Loads the products data from the JSON file."""
        if os.path.exists(self.products_path):
            try:
                with open(self.products_path, 'r') as file:
                    self.products_data = json.load(file)
            except json.JSONDecodeError as e:
                print(f"🛑 Failed to load {os.path.basename(self.products_path)}: Invalid JSON format.")
                print(f"    ↳  {e}\n")
                if exit_on_error:
                    sys.exit(1)
        return self.products_data

    def _get_clean_url(self, url: str) -> str:
        """Strips query parameters and fragments to return the clean base URL."""
        if not url:
            return ""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    def update_product(self, url: str, last_price: float, last_checked: str) -> None:
        """Caches updates for a product based on its clean URL."""
        clean_url = self._get_clean_url(url)
        self.product_updates[clean_url] = {
            'last_price': last_price,
            'last_checked': last_checked
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
                    product["last_checked"] = updates["last_checked"]

                if "skip" not in product:
                    product["skip"] = False

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
            if row.get('skip', False):
                continue

            url = row.get('url', '')
            product_name = row.get('name', 'Unknown')
            last_check = row.get('last_checked')
            if last_check:
                try:
                    timestamp = datetime.datetime.strptime(last_check, "%d-%m-%Y %H:%M:%S")
                    current_time = datetime.datetime.now()
                    if (current_time - timestamp) > datetime.timedelta(hours=hours):
                        print(f"❗ Old entry found for {product_name}: {url} (Last check: {last_check})")
                        notifier.notify_old_entries(product_name, hours, url)
                except ValueError:
                    pass

class SkroutzScraper:
    def __init__(self, quiet: bool = False):
        self.quiet = quiet
        self.interrupted = False
        self.current_headers = random.choice(DEFAULT_HEADERS_POOL)

    def signal_handler(self, signum, _frame):
        sig_name = 'SIGINT (Ctrl+C)' if signum == signal.SIGINT else 'SIGTERM (System Shutdown/Termination)' if signum == signal.SIGTERM else signum
        if not self.quiet:
            print(f"\n\nReceived signal {sig_name}. Gracefully shutting down...")
        self.interrupted = True

    def _sleep_with_jitter(self, base_delay: float, attempt: int = 0) -> None:
        """Sleeps for a base time plus some jitter based on the current attempt."""
        jitter = random.uniform(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)
        total_delay = base_delay + (RETRY_DELAY_MULTIPLIER * attempt) + jitter

        # Break sleep into smaller chunks to remain responsive to interruptions
        start_time = time.time()
        while time.time() - start_time < total_delay:
            if self.interrupted:
                break
            if not self.quiet:
                remaining = max(0.0, total_delay - (time.time() - start_time))
                print(f"\r⏳ Sleeping for {remaining:.1f} seconds...   ", end="", flush=True)
            time.sleep(0.1)

        if not self.quiet and not self.interrupted:
            actual_delay = time.time() - start_time
            print(f"\r⏳ Slept for {actual_delay:.1f} seconds.       ")

    def scrape_product(self, product_url: str, product_name: str) -> Optional[float]:
        """Scrapes the Skroutz product page and returns the minimum price found."""
        parsed_url = urlparse(product_url)
        domain = parsed_url.netloc
        match = re.search(r'/s/(\d+)', parsed_url.path)

        if not match:
            if not self.quiet:
                print(f"{product_name}: Failed to parse product ID from URL: {product_url}")
            return None

        product_id = match.group(1)
        api_link = f"https://{domain}/s/{product_id}/filter_products.json?"

        session = tls_client.Session(
            client_identifier="chrome120",  # type: ignore
            random_tls_extension_order=True
        )

        try:
            headers = self.current_headers.copy()
            headers['authority'] = domain

            parsed_referer = urlparse(headers.get('referer', 'https://www.skroutz.gr/'))
            headers['referer'] = parsed_referer._replace(netloc=domain).geturl()

            response = session.get(api_link.strip(), headers=headers)

            if response.status_code is None:
                raise Exception("Empty response or no status code received from server")

            if response.status_code in (404, 410):
                if not self.quiet:
                    print(f"❗ {product_name}: Product not found or removed (HTTP {response.status_code}).")
                return None
            elif response.status_code in (401, 403, 429):
                raise Exception(f"Blocked or rate limited (HTTP {response.status_code})")
            elif 500 <= response.status_code < 600:
                raise Exception(f"Skroutz server error (HTTP {response.status_code}), retrying...")
            elif response.status_code != 200:
                raise Exception(f"HTTP request failed with status code {response.status_code}")

            response_data = response.json()

            if response_data.get("price_min") is None:
                if not self.quiet:
                    print(f"{product_name}: Not available")
                return None

            price_str = str(response_data["price_min"])
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

        for index, entry in enumerate(products):
            if self.interrupted:
                break

            product_name = entry.get('name', 'Unknown')

            if entry.get('skip', False):
                if not self.quiet:
                    print(f"\n🔕 {product_name}: Skipped (skip field set to true)")
                continue

            if not self.quiet and index >= 0:
                print()

            self._sleep_with_jitter(MIN_DELAY_SECONDS)
            if self.interrupted:
                break

            url = entry.get('url', '')
            if not url:
                if not self.quiet:
                    print(f"❗ {product_name}: URL is missing, skipping product.")
                continue

            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            currency = 'Lei' if domain.endswith('.ro') else '€'

            if 'target_price' not in entry:
                if not self.quiet:
                    print(f"❗ {product_name}: Target price is missing, defaulting to 0.0.")

            try:
                target_price_raw = entry.get('target_price', 0.0)
                if isinstance(target_price_raw, str):
                    # Handle string prices, including comma decimals and literal quotes
                    target_price_raw = target_price_raw.strip('"').strip("'").replace(',', '.')
                target_price = float(target_price_raw)
            except (ValueError, TypeError):
                if not self.quiet:
                    print(f"❗ {product_name}: Invalid target price '{entry.get('target_price')}', skipping product.")
                continue

            for attempt in range(MAX_RETRIES):
                if self.interrupted:
                    break

                try:
                    current_price = self.scrape_product(url, product_name)

                    if self.interrupted:
                        break

                    if current_price is not None:
                        if current_price < target_price:
                            if not self.quiet:
                                print(f"🎉 {product_name}: {current_price} {currency} (Target: {target_price} {currency})")
                                if notifier.has_services:
                                    print("    ↳ 📨 Notification sent to configured services.")
                                else:
                                    print("    ↳ 🔕 No notification sent (no services configured in .env).")
                            notifier.notify_low_price(product_name, target_price, current_price, url, currency)
                        else:
                            if not self.quiet:
                                print(f"✅ {product_name}: {current_price} {currency} (Target: {target_price} {currency})")

                        # Update the timestamp and last price
                        products_manager.update_product(
                            url=url,
                            last_price=current_price,
                            last_checked=datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                        )
                        break # Success, move to the next product
                    else:
                        break # Unavailable or invalid URL, move to next

                except json.JSONDecodeError:
                    if not self.quiet:
                        print(f"Attempt {attempt + 1} failed: Received empty response for {product_name}.")
                    self.current_headers = random.choice(DEFAULT_HEADERS_POOL)
                    self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)
                except Exception as e:
                    if not self.quiet:
                        print(f"🛑 {product_name}: Attempt {attempt + 1} FAILED ({type(e).__name__})!\n    ↳ ❗ {e}\n")

                    if attempt == MAX_RETRIES - 1:
                        ErrorHandler.save_traceback(data_dir, url=url, headers=self.current_headers)
                        has_errors = True
                        break

                    self.current_headers = random.choice(DEFAULT_HEADERS_POOL)
                    self._sleep_with_jitter(MIN_DELAY_SECONDS, attempt)

        # Save updates
        if not self.quiet:
            if self.interrupted:
                print("Saving products data...\n")
            else:
                print("\nSaving products data and checking for old entries...\n")
        products_manager.save_atomically()

        if not self.interrupted:
            products_manager.check_for_old_entries(OLD_ENTRY_HOURS, notifier)

        if has_errors and not self.interrupted:
            notifier.notify_errors()


# --- Shared Helpers ---

def check_env_file() -> int:
    """Loads .env and checks if it exists and contains NOTIFICATION_URLS.
    Returns:
        0: OK
        1: No .env file found or unreadable
        2: No NOTIFICATION_URLS provided
        3: Only unconfigured placeholders provided
    """
    env_path = os.path.join(BASE_DIR, '.env')
    env_loaded = load_dotenv(dotenv_path=env_path)
    env_exists = env_loaded or os.path.exists(env_path)

    if not env_exists or not os.access(env_path, os.R_OK):
        return 1

    notification_urls = os.environ.get("NOTIFICATION_URLS", "").strip()
    if not notification_urls:
        return 2

    valid_urls = [u for u in notification_urls.split(',') if u.strip() and not any(p in u for p in APPRISE_PLACEHOLDERS)]
    if not valid_urls:
        return 3

    return 0

def check_products_file() -> int:
    """Checks for products.json file.
    Returns:
        0: OK
        1: File missing or not a file
        2: Permission denied
        3: Invalid JSON format or missing 'products' list
    """
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    if not os.path.exists(PRODUCTS_FILE_PATH) or not os.path.isfile(PRODUCTS_FILE_PATH):
        return 1

    if not os.access(PRODUCTS_FILE_PATH, os.R_OK | os.W_OK):
        return 2

    try:
        with open(PRODUCTS_FILE_PATH, 'r') as f:
            data = json.load(f)
            if not isinstance(data, dict) or not isinstance(data.get("products"), list):
                return 3
    except (json.JSONDecodeError, OSError):
        return 3

    return 0

def check_for_updates() -> int:
    """Checks the remote git repository to see if a newer version is available.
    Returns:
        0: Running the latest version
        1: A new version is available
       -1: Could not check for updates
    """
    try:
        # Get the remote URL
        remote_url = subprocess.check_output(['git', 'config', '--get', 'remote.origin.url'], cwd=BASE_DIR, stderr=subprocess.DEVNULL).decode('utf-8').strip()

        # If it's an SSH URL, convert it to HTTPS to avoid passphrase prompts
        if remote_url.startswith('git@github.com:'):
            remote_url = remote_url.replace('git@github.com:', 'https://github.com/')

        local_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=BASE_DIR, stderr=subprocess.DEVNULL).decode('utf-8').strip()
        remote_output = subprocess.check_output(['git', 'ls-remote', remote_url, 'HEAD'], cwd=BASE_DIR, stderr=subprocess.DEVNULL).decode('utf-8').strip()
        if remote_output:
            remote_hash = remote_output.split()[0]
            if local_hash != remote_hash:
                return 1
            else:
                return 0
        else:
            return -1
    except Exception:
        return -1

def print_update_status(quiet: bool) -> None:
    if quiet:
        return
    print("⏳ Checking for updates...", end="", flush=True)
    update_status = check_for_updates()
    if update_status == 1:
        print("\r✨ A new version is available! Run ./update.sh to update.\n")
    elif update_status == 0:
        print("\r✅ You are running the latest version.")
    else:
        print("\r❗ Could not check for script updates.\n")

def print_env_status(env_status: int, quiet: bool, fatal_on_error: bool = False) -> None:
    notification_urls = os.environ.get("NOTIFICATION_URLS", "")
    icon = "🛑" if fatal_on_error else "❗"
    suffix = "!\n" if fatal_on_error else "!"

    if env_status == 1:
        if not quiet:
            print(f"{icon} No .env file found or unreadable{suffix}")
        if fatal_on_error:
            sys.exit(1)
    elif env_status == 2:
        if not quiet:
            print(f"{icon} No NOTIFICATION_URLS provided in .env file{suffix}")
        if fatal_on_error:
            sys.exit(1)
    elif env_status == 3:
        if not quiet:
            print(f"{icon} NOTIFICATION_URLS contains only unconfigured placeholders{suffix}")
        if fatal_on_error:
            sys.exit(1)
    elif env_status == 0 and not quiet:
        valid_urls = [u for u in notification_urls.split(',') if u.strip() and not any(p in u for p in APPRISE_PLACEHOLDERS)]
        print(f"✅ Found {len(valid_urls)} notification service(s) in .env")

        if notification_urls and any(p in notification_urls for p in APPRISE_PLACEHOLDERS):
            print("    ↳ ❗ NOTIFICATION_URLS contains unconfigured placeholder(s).")

def print_prod_status(prod_status: int, quiet: bool, fatal_on_error: bool = False) -> None:
    icon = "🛑" if fatal_on_error else "❗"
    suffix = "!\n" if fatal_on_error else "!"

    if prod_status == 1:
        if not quiet:
            print(f"{icon} The data/products.json file is missing or not a file{suffix}")
        if fatal_on_error:
            sys.exit(15)
    elif prod_status == 2:
        if not quiet:
            print(f"{icon} The data/products.json file has wrong permissions{suffix}")
        if fatal_on_error:
            sys.exit(15)
    elif prod_status == 3:
        if not quiet:
            print(f"{icon} The data/products.json file contains invalid JSON format{suffix}")
        if fatal_on_error:
            sys.exit(15)


# --- Main Execution ---

def handle_test_notification() -> None:
    print("\nSending Skroutz Price Alert Test Notification...\n")

    env_status = check_env_file()
    print_env_status(env_status, quiet=False, fatal_on_error=True)

    notification_urls = os.environ.get("NOTIFICATION_URLS", "")
    notifier = Notifier(notification_urls)

    try:
        notifier.notify_test()
        print("\n📨 Test notification sent!\n")
    except Exception as e:
        print(f"An error occurred while sending test notification: {e}\n")

def handle_status() -> None:
    NC = '\033[0m'
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[0;33m'

    def get_systemd_properties(unit: str, properties: str) -> dict:
        service_file_path = os.path.expanduser(f'~/.config/systemd/user/{unit}')
        if not os.path.exists(service_file_path) or os.path.getsize(service_file_path) == 0:
            return {}

        try:
            output = subprocess.check_output(
                ['systemctl', '--user', 'show', unit, f'--property={properties}'],
                stderr=subprocess.DEVNULL
            ).decode('utf-8').strip()
            if not output:
                return {}
            return dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
        except (subprocess.CalledProcessError, ValueError):
            return {}

    def is_linger_enabled() -> bool:
        try:
            user_id = os.environ.get("USER") or os.environ.get("LOGNAME") or "nobody"
            output = subprocess.check_output(
                ['loginctl', 'show-user', user_id, '--property=Linger'],
                stderr=subprocess.DEVNULL
            ).decode('utf-8').strip()
            return "Linger=yes" in output
        except subprocess.CalledProcessError:
            return False

    print("\nChecking Skroutz Price Alert Status...\n")

    prod_status = check_products_file()
    env_status = check_env_file()

    print_update_status(quiet=False)
    print_prod_status(prod_status, quiet=False, fatal_on_error=False)

    if prod_status == 0:
        products_manager = ProductsManager(PRODUCTS_FILE_PATH)
        products_data = products_manager.load(exit_on_error=False)
        if products_data:
            num_products = len(products_data.get("products", []))
            print(f"✅ Found {num_products} products in data/products.json")

    print_env_status(env_status, quiet=False, fatal_on_error=False)

    # --- Data Fetching ---
    timer_props = get_systemd_properties('skroutz-price-alert.timer', 'ActiveState,NextElapseUSecRealtime')
    service_props = get_systemd_properties('skroutz-price-alert.service', 'ActiveState,Result,ExecMainStartTimestamp,ExecMainStatus')
    linger_enabled_val = is_linger_enabled()

    # --- Data Formatting ---

    # Linger Status
    linger_icon = "✅" if linger_enabled_val else "❗"
    linger_enabled = f"{GREEN}Yes{NC}" if linger_enabled_val else f"{RED}No{NC}"

    # Timer Status
    timer_active_val = timer_props.get("ActiveState") == "active"
    timer_icon = "✅" if timer_active_val else "❗"
    timer_active = f"{GREEN}Yes{NC}" if timer_active_val else f"{RED}No{NC}"

    # Service / Last Execution Status
    result = service_props.get("Result", "")
    exec_status = service_props.get("ExecMainStatus", "")
    last_exec_time = service_props.get("ExecMainStartTimestamp", "")
    service_active = service_props.get("ActiveState", "")

    no_errors = (result == "success" and exec_status == "0")
    skipped = (exec_status == "42")
    products_error = (exec_status == "15")
    is_currently_running = service_active in ("active", "activating")
    is_pending_first_execution = timer_active_val and not last_exec_time

    next_exec = timer_props.get("NextElapseUSecRealtime", "")
    if is_currently_running:
        next_exec = f"{GREEN}Running Now{NC}"
        next_exec_icon = "✅"
    elif not next_exec or next_exec in ("n/a", "0"):
        next_exec = f"{RED}Not Scheduled{NC}"
        next_exec_icon = "❗"
    else:
        next_exec_icon = "✅"

    if not last_exec_time:
        last_exec_time = f"{RED}Never{NC}"
        completed_str = f"{RED}Not executed yet{NC}"
        last_exec_icon = "❗"
        completed_icon = "❗"
    else:
        last_exec_icon = "✅"
        error_details = "None" if no_errors else f"Result: {result or 'Unknown'}, Exit Code: {exec_status or 'Unknown'}"
        if no_errors:
            completed_icon = "✅"
            completed_str = f"{GREEN}OK{NC}"
        elif skipped:
            completed_icon = "🟡"
            completed_str = f"{YELLOW}Skipped{NC} (Another instance was running)"
        elif products_error:
            completed_icon = "❗"
            completed_str = f"{RED}Failed{NC} (Issue with data/products.json file)"
        else:
            completed_icon = "❗"
            completed_str = f"{RED}Failed{NC} ({error_details})"

    # --- Terminal Output ---
    print(f"\n{linger_icon} Linger Enabled:              {linger_enabled}")
    print(f"{timer_icon} Systemd Timer Active:        {timer_active}")
    if last_exec_time != f"{RED}Never{NC}":
        print(f"{last_exec_icon} Last Execution Time:         {last_exec_time}")
        print(f"{completed_icon} Last Execution Status:       {completed_str}")
    print(f"{next_exec_icon} Next Scheduled Execution:    {next_exec}")

    if is_currently_running:
        print("    ↳ Script is currently running in the background. Re-check in a few minutes.")
    elif is_pending_first_execution:
        print("    ↳ Timer pending first execution. Waiting for the scheduled time.")
    print("")


def run_main_program(quiet: bool) -> None:
    if not quiet:
        print("\nStarting Skroutz Price Alert...\n")

    env_status = check_env_file()
    prod_status = check_products_file()

    print_update_status(quiet)
    print_prod_status(prod_status, quiet, fatal_on_error=True)

    products_manager = ProductsManager(PRODUCTS_FILE_PATH)
    products_data = products_manager.load(exit_on_error=True)

    if not quiet and products_data is not None:
        num_products = len(products_data.get("products", []))
        print(f"✅ Loaded {num_products} products from data/products.json")

    print_env_status(env_status, quiet, fatal_on_error=False)

    notification_urls = os.environ.get("NOTIFICATION_URLS", "")
    notifier = Notifier(notification_urls)

    # Locking and Execution
    lock = FileLock(LOCK_FILE_PATH, timeout=LOCK_TIMEOUT)

    try:
        with lock:
            scraper = SkroutzScraper(quiet=quiet)
            scraper.process_products(products_manager, notifier, DATA_DIR)

    except Timeout:
        if not quiet:
            print('\n🛑 Skroutz Price Alert script did not start! Another instance is currently running.\n')
        sys.exit(42)
    except Exception:
        ErrorHandler.save_traceback(DATA_DIR)
        notifier.notify_crash()


def main() -> None:
    parser = argparse.ArgumentParser(description='Skroutz Price Alert scraper')
    parser.add_argument('--quiet', action='store_true', help='Run script with no console output')
    parser.add_argument('--status', action='store_true', help='Perform a health check of the background service and show execution status (skips main scraper)')
    parser.add_argument('--ping', action='store_true', help='Send a test notification via Apprise (skips main scraper)')
    args = parser.parse_args()

    if args.ping:
        handle_test_notification()

    if args.status:
        handle_status()

    if not args.ping and not args.status:
        run_main_program(args.quiet)

if __name__ == "__main__":
    main()
