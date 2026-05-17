import logging
import subprocess
from abc import ABC, abstractmethod

from config import BASE_DIR
from exceptions import UpdateCheckError

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

class UpdateCheckerStrategy(ABC):
    @abstractmethod
    def check(self) -> None:
        pass

class InteractiveUpdateChecker(UpdateCheckerStrategy):
    def check(self) -> None:
        print("⏳ Checking for updates...", end="", flush=True)

        try:
            has_update = check_for_updates()
            print("\r" + " " * 30 + "\r", end="", flush=True)
            if has_update:
                logging.info("✨ A new version is available! Run ./update.sh to update.\n")
            else:
                logging.info("✅ You are running the latest version.")
        except UpdateCheckError:
            print("\r" + " " * 30 + "\r", end="", flush=True)
            logging.info("❗ Could not check for script updates.\n")

class SilentUpdateChecker(UpdateCheckerStrategy):
    def check(self) -> None:
        pass
