"""Scraper plugin packages.

Plugins are discovered and registered explicitly via
``ScraperRegistry.discover()``, which the registry's own lookup methods call
lazily and idempotently. Importing this package therefore has no registration
side effects, and a populated registry never depends on a caller remembering to
import it first.

Each plugin sub-package must expose a module-level ``plugin`` attribute (a
:class:`BasePlugin` instance) in its ``__init__.py``.
"""
