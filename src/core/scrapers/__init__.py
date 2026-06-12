import importlib
import pkgutil
from pathlib import Path
from scrapers.registry import ScraperRegistry

# Auto-discover all plugin packages under scrapers/.
# Each plugin sub-package must expose a module-level `plugin` attribute
# (an instance of BasePlugin) in its __init__.py.
_package_dir = Path(__file__).parent
for _importer, _modname, _ispkg in pkgutil.iter_modules([str(_package_dir)]):
    if _ispkg and _modname not in ("base",):
        _mod = importlib.import_module(f"scrapers.{_modname}")
        if hasattr(_mod, "plugin"):
            ScraperRegistry.register(_mod.plugin)
