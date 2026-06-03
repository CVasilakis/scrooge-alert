import os
from typing import Dict
from .base import BaseDataManager
from .skroutz import SkroutzDataManager

class DataManagerFactory:
    """Factory for creating and managing DataManager instances."""
    def __init__(self, config_dir: str):
        """Initializes the DataManagerFactory with a configuration directory.

        Args:
            config_dir (str): The directory containing configuration files.
        """
        self._managers: Dict[str, BaseDataManager] = {}
        self.config_dir = config_dir

    def get_manager(self, target: str) -> BaseDataManager:
        """Retrieves or creates an appropriate data manager for the given target.

        Args:
            target (str): The target identifier (e.g., 'skroutz').

        Returns:
            BaseDataManager: The instantiated data manager.

        Raises:
            ValueError: If the target is unsupported.
        """
        if target not in self._managers:
            if target == 'skroutz':
                path = os.path.join(self.config_dir, "skroutz.json")
                self._managers[target] = SkroutzDataManager(path)
            else:
                raise ValueError(f"Unsupported storage target: {target}")

        return self._managers[target]
