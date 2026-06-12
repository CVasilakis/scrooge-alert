from typing import List, Type
from scrapers.base.plugin import BasePlugin
from scrapers.base.client import BaseScraperClient
from scrapers.base.storage import BaseDataManager


class SkroutzPlugin(BasePlugin):
    """Plugin descriptor for the Skroutz price comparison platform.

    This is the single source of truth for all Skroutz-related metadata.
    Both the client and the storage reference this plugin's domain list
    to ensure they stay in sync.
    """

    _SUPPORTED_DOMAINS = ["skroutz.gr", "skroutz.cy", "skroutz.ro", "skroutz.bg", "skroutz.de"]

    @staticmethod
    def get_name() -> str:
        return "skroutz"

    @staticmethod
    def get_display_name() -> str:
        return "Skroutz"

    @staticmethod
    def get_supported_domains() -> List[str]:
        return SkroutzPlugin._SUPPORTED_DOMAINS

    @staticmethod
    def get_config_filename() -> str:
        return "skroutz.json"

    @staticmethod
    def get_client_class() -> Type[BaseScraperClient]:
        from scrapers.skroutz.client import SkroutzClient
        return SkroutzClient

    @staticmethod
    def get_storage_class() -> Type[BaseDataManager]:
        from scrapers.skroutz.storage import SkroutzDataManager
        return SkroutzDataManager
