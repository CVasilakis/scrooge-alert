import os
import json
import logging
import sys
import apprise
from dotenv import load_dotenv

from constants import BASE_DIR, CONFIG_DIR, SKROUTZ_FILE_PATH, EXIT_CODE_ENV_ERROR, EXIT_CODE_PRODUCTS_ERROR, APPRISE_PLACEHOLDERS
from exceptions import EnvFileError, ProductFileError

class ConfigValidator:
    @staticmethod
    def check_env_file() -> None:
        """Validates the existence and contents of the .env file.

        Raises:
            EnvFileError: If the .env file is missing, unreadable, or missing valid NOTIFICATION_URLS.
        """
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
    def check_products_file() -> tuple[int, int]:
        """Validates the skroutz.json file and counts products.

        Returns:
            tuple[int, int]: A tuple containing the total number of products and the number of faulty products.

        Raises:
            ProductFileError: If the file is missing, unreadable, or contains invalid JSON.
        """
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR)

        if not os.path.exists(SKROUTZ_FILE_PATH) or not os.path.isfile(SKROUTZ_FILE_PATH):
            raise ProductFileError("The config/skroutz.json file is missing or not a file")

        if not os.access(SKROUTZ_FILE_PATH, os.R_OK | os.W_OK):
            raise ProductFileError("The config/skroutz.json file has wrong permissions")

        try:
            with open(SKROUTZ_FILE_PATH, 'r') as f:
                data = json.load(f)
                if not isinstance(data, dict) or not isinstance(data.get("products"), list):
                    raise ProductFileError("The config/skroutz.json file contains invalid JSON format")

                products = data.get("products", [])
                num_products = len(products)
                faulty_count = sum(1 for p in products if not all(k in p for k in ("name", "url", "target_price")))
                return num_products, faulty_count
        except (json.JSONDecodeError, OSError):
            raise ProductFileError("The config/skroutz.json file contains invalid JSON format")

    @staticmethod
    def print_env_status(fatal_on_error: bool = False, show_invalid_details: bool = False) -> None:
        """Validates the .env file and prints the status to the log.

        Args:
            fatal_on_error (bool): If True, exits the program when an error is encountered.
            show_invalid_details (bool): If True, logs details of invalid notification URLs.
        """
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
            if fatal_on_error:
                logging.error(f"🛑 {e}!")
                logging.info("")
                sys.exit(EXIT_CODE_ENV_ERROR)
            else:
                logging.warning(f"❗ {e}!")

    @staticmethod
    def print_prod_status(fatal_on_error: bool = False) -> None:
        """Validates the products file and prints the status to the log.

        Args:
            fatal_on_error (bool): If True, exits the program when an error is encountered.
        """
        try:
            num_products, faulty_count = ConfigValidator.check_products_file()
            logging.info(f"✅ Loaded {num_products} products from config/skroutz.json")
            if faulty_count > 0:
                logging.warning(f"    ↳ ❗ Detected {faulty_count} misconfigured product(s) in config/skroutz.json")
        except ProductFileError as e:
            if fatal_on_error:
                logging.error(f"🛑 {e}!")
                logging.info("")
                sys.exit(EXIT_CODE_PRODUCTS_ERROR)
            else:
                logging.warning(f"❗ {e}!")
