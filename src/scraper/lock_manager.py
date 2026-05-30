import os
from contextlib import contextmanager
from filelock import FileLock, Timeout
from constants import LOGS_DIR, LOCK_TIMEOUT
from exceptions import LockAcquisitionError

class ScraperLockManager:
    """Manages concurrent execution locks for different scraper targets.

    This class abstracts the underlying locking mechanism (currently file-based),
    providing a clean interface for acquiring locks without exposing
    implementation-specific exceptions or configuration details.
    """

    @staticmethod
    @contextmanager
    def acquire(target_name: str):
        """Attempts to acquire an exclusive execution lock for the given target.

        Args:
            target_name (str): The identifier for the scraper (e.g., 'skroutz').

        Yields:
            None: If the lock is successfully acquired.

        Raises:
            LockAcquisitionError: If the target is currently locked by another process.
        """
        lock_filename = f"{target_name}_scraper_running.lock"
        lock_path = os.path.join(LOGS_DIR, lock_filename)
        lock = FileLock(lock_path, timeout=LOCK_TIMEOUT)

        try:
            with lock:
                yield
        except Timeout:
            raise LockAcquisitionError
