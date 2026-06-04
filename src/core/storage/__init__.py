from .base import BaseDataManager
from .factory import DataManagerFactory
from .skroutz import SkroutzDataManager

# Register data managers for each supported target.
# To add a new target, import its DataManager class and register it here.
DataManagerFactory.register('skroutz', SkroutzDataManager, 'skroutz.json')

__all__ = [
    "BaseDataManager",
    "DataManagerFactory",
    "SkroutzDataManager",
]
