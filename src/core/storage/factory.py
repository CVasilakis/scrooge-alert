import os
from typing import Dict, List, Tuple, Type
from .base import BaseDataManager


class DataManagerFactory:
    """Factory for creating and managing DataManager instances.

    Uses a class-level registry so new data managers can be added without
    modifying this file. To add a new data manager, implement BaseDataManager
    and register it via the package's __init__.py.
    """
    _registry: Dict[str, Tuple[Type[BaseDataManager], str]] = {}

    @classmethod
    def register(cls, target_name: str, manager_class: Type[BaseDataManager], config_filename: str) -> None:
        """Registers a data manager class for the given target.

        Args:
            target_name (str): The target identifier (e.g., 'skroutz').
            manager_class (Type[BaseDataManager]): The data manager class to instantiate.
            config_filename (str): The configuration filename (e.g., 'skroutz.json').
        """
        cls._registry[target_name] = (manager_class, config_filename)

    @classmethod
    def registered_targets(cls) -> List[str]:
        """Returns a list of all registered data manager target identifiers.

        Returns:
            List[str]: The registered target names.
        """
        return list(cls._registry.keys())

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
            if target not in self._registry:
                raise ValueError(f"Unsupported storage target: {target}")

            manager_class, config_filename = self._registry[target]
            path = os.path.join(self.config_dir, config_filename)
            self._managers[target] = manager_class(path)

        return self._managers[target]
