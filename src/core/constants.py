import os
from typing import List, Dict

# --- Exit Codes ---
# Used to indicate failure states when running as a background service.
EXIT_CODE_SUCCESS: int = 0
EXIT_CODE_ERROR: int = 1
EXIT_CODE_INTERRUPT: int = 130        # Script was interrupted (user or system termination)
EXIT_CODE_PRODUCTS_ERROR: int = 15    # Issue with the config/skroutz.json file
EXIT_CODE_ENV_ERROR: int = 16         # Issue with the .env file
EXIT_CODE_RATE_LIMIT_ERROR: int = 17  # Blocked by server due to rate limits
EXIT_CODE_SKIPPED: int = 42           # Skipped execution (another instance running)

# --- Base Directory Paths ---
BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR: str = os.path.join(BASE_DIR, "config")
LOGS_DIR: str = os.path.join(BASE_DIR, "logs")
SKROUTZ_FILE_PATH: str = os.path.join(CONFIG_DIR, "skroutz.json")

# --- Scraping Configuration ---

# Unconfigured Apprise placeholders to ignore during URL validation
APPRISE_PLACEHOLDERS: List[str] = ['<token>', '<bot_token>', '<chat_id>', '<webhook_id>', '<webhook_token>']

# Maximum number of times to retry scraping a product if the request fails
MAX_RETRIES: int = 3

# Number of hours after which a product check is considered old, triggering a stale warning
OLD_ENTRY_HOURS: int = 48

# Base delay in seconds between processing each product to avoid rate limits
MIN_DELAY_SECONDS: int = 20

# Minimum random time in seconds added to the base delay (jitter) to simulate human behavior
RANDOM_DELAY_MIN: float = 1.0

# Maximum random time in seconds added to the base delay (jitter) to simulate human behavior
RANDOM_DELAY_MAX: float = 5.0

# Timeout in seconds when trying to acquire the file lock (0 means fail immediately if locked)
LOCK_TIMEOUT: int = 0

# Multiplier used to increase the wait time exponentially on each retry attempt
RETRY_DELAY_MULTIPLIER: int = 3

# Headers impersonating a real browser to avoid being blocked by anti-bot measures.
# The scraper rotates through these profiles randomly on retries.
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
