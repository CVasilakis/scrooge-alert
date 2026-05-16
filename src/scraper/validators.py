import os
import json
import logging
import subprocess
import sys
import apprise
from dotenv import load_dotenv

from config import BASE_DIR, DATA_DIR, PRODUCTS_FILE_PATH, EXIT_CODE_ENV_ERROR, EXIT_CODE_PRODUCTS_ERROR, APPRISE_PLACEHOLDERS
from exceptions import EnvFileError, ProductFileError, UpdateCheckError

class ConfigValidator:
    @staticmethod
    def check_env_file() -> None:
        env_path = os.path.join(BASE_DIR, '.env')
        env_loaded = load_dotenv(dotenv_path=env_path)
        env_exists = env_loaded or os.path.exists(env_path)

        if not env_exists or not os.access(env_path, os.R_OK):
            raise EnvFileError("No .env file found or unreadable")

        notification_urls = os.environ.get("NOTIFICATION_URLS", "").strip()
        if not notification_urls:
            raise EnvFileError("No NOTIFICATION_URLS provided in .env file")

        urls = [u.strip() for u in notification_urls.split(',') if u.strip()]

        valid_urls = [u for u in urls if not any(p in u for p in APPRISE_PLACEHOLDERS) and apprise.Apprise.instantiate(u)]
        if not valid_urls:
            raise EnvFileError("NOTIFICATION_URLS contains no valid notification URL(s)")

    @staticmethod
    def check_products_file() -> None:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

        if not os.path.exists(PRODUCTS_FILE_PATH) or not os.path.isfile(PRODUCTS_FILE_PATH):
            raise ProductFileError("The data/products.json file is missing or not a file")

        if not os.access(PRODUCTS_FILE_PATH, os.R_OK | os.W_OK):
            raise ProductFileError("The data/products.json file has wrong permissions")

        try:
            with open(PRODUCTS_FILE_PATH, 'r') as f:
                data = json.load(f)
                if not isinstance(data, dict) or not isinstance(data.get("products"), list):
                    raise ProductFileError("The data/products.json file contains invalid JSON format")
        except (json.JSONDecodeError, OSError):
            raise ProductFileError("The data/products.json file contains invalid JSON format")

    @staticmethod
    def check_for_updates() -> bool:
        try:
            remote_url = subprocess.check_output(['git', 'config', '--get', 'remote.origin.url'], cwd=BASE_DIR, stderr=subprocess.DEVNULL).decode('utf-8').strip()

            if remote_url.startswith('git@github.com:'):
                remote_url = remote_url.replace('git@github.com:', 'https://github.com/')

            local_hash = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=BASE_DIR, stderr=subprocess.DEVNULL).decode('utf-8').strip()
            remote_output = subprocess.check_output(['git', 'ls-remote', remote_url, 'HEAD'], cwd=BASE_DIR, stderr=subprocess.DEVNULL).decode('utf-8').strip()
            if remote_output:
                remote_hash = remote_output.split()[0]
                return local_hash != remote_hash
            else:
                raise UpdateCheckError("No remote output received")
        except Exception as e:
            raise UpdateCheckError(f"Could not check for updates: {e}")

    @staticmethod
    def print_update_status() -> None:
        is_info = logging.getLogger().isEnabledFor(logging.INFO)
        if not is_info:
            return

        print("⏳ Checking for updates...", end="", flush=True)

        try:
            has_update = ConfigValidator.check_for_updates()
            print("\r" + " " * 30 + "\r", end="", flush=True)
            if has_update:
                logging.info("✨ A new version is available! Run ./update.sh to update.\n")
            else:
                logging.info("✅ You are running the latest version.")
        except UpdateCheckError:
            print("\r" + " " * 30 + "\r", end="", flush=True)
            logging.info("❗ Could not check for script updates.\n")

    @staticmethod
    def print_env_status(fatal_on_error: bool = False, show_invalid_details: bool = False) -> None:
        try:
            ConfigValidator.check_env_file()
            notification_urls = os.environ.get("NOTIFICATION_URLS", "")
            valid_urls = []
            invalid_urls = []
            for u in notification_urls.split(','):
                u = u.strip()
                if u:
                    if not any(p in u for p in APPRISE_PLACEHOLDERS) and apprise.Apprise.instantiate(u):
                        valid_urls.append(u)
                    else:
                        invalid_urls.append(u)

            if show_invalid_details and invalid_urls:
                logging.warning(f"❗ Found {len(invalid_urls)} invalid notification URL(s) in .env")
                for iu in invalid_urls:
                    schema_end = iu.find('://')
                    if schema_end != -1:
                        scheme = iu[:schema_end + 3]
                        rest = iu[schema_end + 3:]
                    else:
                        scheme = ""
                        rest = iu

                    first_slash = rest.find('/')

                    if first_slash != -1:
                        token = rest[:first_slash]
                        path = '/...'
                    else:
                        token = rest
                        path = ''

                    if len(token) > 2:
                        obfuscated_token = f"{token[0]}...{token[-1]}"
                    elif len(token) > 0:
                        obfuscated_token = f"{token[0]}..."
                    else:
                        obfuscated_token = ""

                    if not scheme and not obfuscated_token:
                        obfuscated_iu = "***"
                    else:
                        obfuscated_iu = f"{scheme}{obfuscated_token}{path}"

                    logging.warning(f"    ↳ 🔕 {obfuscated_iu}")
                logging.info("")
                logging.info(f"✅ Loaded {len(valid_urls)} valid notification URL(s) from .env")
            else:
                logging.info(f"✅ Loaded {len(valid_urls)} valid notification URL(s) from .env")
                if invalid_urls:
                    logging.warning(f"    ↳ ❗ Also found {len(invalid_urls)} invalid notification URL(s) in .env")
        except EnvFileError as e:
            icon = "🛑" if fatal_on_error else "❗"
            suffix = "!\n" if fatal_on_error else "!"
            logging.warning(f"{icon} {e}{suffix}")
            if fatal_on_error:
                sys.exit(EXIT_CODE_ENV_ERROR)

    @staticmethod
    def print_prod_status(fatal_on_error: bool = False) -> None:
        try:
            ConfigValidator.check_products_file()
        except ProductFileError as e:
            icon = "🛑" if fatal_on_error else "❗"
            suffix = "!\n" if fatal_on_error else "!"
            logging.warning(f"{icon} {e}{suffix}")
            if fatal_on_error:
                sys.exit(EXIT_CODE_PRODUCTS_ERROR)
