import subprocess

from constants import BASE_DIR
from exceptions import UpdateCheckError

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
            raise UpdateCheckError("No remote output received")
    except Exception as e:
        raise UpdateCheckError(f"Could not check for updates: {e}")
