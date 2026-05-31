import os
import logging
import sys
import apprise
from dotenv import load_dotenv

from constants import BASE_DIR, EXIT_CODE_ENV_ERROR, APPRISE_PLACEHOLDERS
from exceptions import EnvFileError

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

def print_env_status(fatal_on_error: bool = False, show_invalid_details: bool = False) -> None:
    """Validates the .env file and prints the status to the log.

    Args:
        fatal_on_error (bool): If True, exits the program when an error is encountered.
        show_invalid_details (bool): If True, logs details of invalid notification URLs.
    """
    try:
        check_env_file()
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
