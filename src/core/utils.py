import os
import subprocess
import apprise
from dotenv import load_dotenv

from constants import BASE_DIR, APPRISE_PLACEHOLDERS
from exceptions import EnvFileError, UpdateCheckError

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

def check_for_updates() -> bool:
    """Checks if there are new commits in the remote repository.

    Returns:
        bool: True if a new version is available, False otherwise.

    Raises:
        UpdateCheckError: If there's an error communicating with the remote repository.
    """
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
            raise UpdateCheckError("Failed to retrieve remote repository version information")
    except Exception as e:
        raise UpdateCheckError(f"Could not check for updates: {e}")
