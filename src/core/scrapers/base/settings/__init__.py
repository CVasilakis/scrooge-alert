"""Scraper configuration settings: the user-tunable ``settings`` block.

Each scraper's JSON config file may carry a top-level ``settings`` object, a
sibling of its item list (e.g. ``products``)::

    {
      "settings": { "execution_interval": "1h" },
      "products": [ ... ]
    }

This package is the single home for the settings *model* and for the
``execution_interval`` -> systemd ``OnCalendar`` semantics. It is imported by the
plugin descriptors (and, transitively, by the lightweight shell one-liners and
``--status``), so it must stay **import-light** - stdlib only, never a
transport/parsing library - in line with the BasePlugin import-light contract.

Layout (all submodules stdlib-only):
    * :mod:`~scrapers.base.settings.model` - ``ScraperSettings``, ``ResolvedSetting``,
      ``SettingView`` and the ``STATUS_*`` codes;
    * :mod:`~scrapers.base.settings.normalizers` - retention/bool normalizers;
    * :mod:`~scrapers.base.settings.intervals` - interval vocabulary + OnCalendar map;
    * :mod:`~scrapers.base.settings.messages` - invalid-value messages;
    * :mod:`~scrapers.base.settings.resolve` - the resolve state machine, ``SettingSpec``
      and the built-in ``BASE_SETTING_SPECS``.

    The public names below are re-exported here, so ``from scrapers.base.settings import
    X`` keeps working unchanged.

Read-only by design:
    The ``settings`` block is **authored by the user and never written back by the
    application**. Settings are read - at config/schedule time through
    ``resolve_setting``, and at scrape/status time through the registry's
    ``resolve_settings`` - but there is deliberately no ``update_setting``/settings
    write path. Machine-owned runtime state (the latest price, a check timestamp) is
    persisted on *item rows* via ``update_item``, not in ``settings`` (see
    :class:`scrapers.base.model.BaseTrackedItem`). Keep new settings plain user inputs;
    do not introduce stateful settings.

Adding a setting:
    A setting is one declarative :class:`SettingSpec` in :data:`BASE_SETTING_SPECS`:

    * give :class:`ScraperSettings` a new field (and parse it in ``from_dict``);
    * add a normalizer (raw value -> effective value, or ``None`` when unsupported);
    * append a :class:`SettingSpec` binding the field name, label, normalizer,
      default, a display formatter and an invalid-value message.

    The resolve state machine, the per-setting result (:class:`ResolvedSetting`) and
    the panel view (:class:`SettingView`) are all generic, so no new ``Resolved*``
    type, registry passthrough or config-check block is needed. A scraper that needs a
    store-specific setting subclasses :class:`ScraperSettings` (returned from
    ``BasePlugin.get_settings_class``) and returns ``BASE_SETTING_SPECS + [its specs]``
    from ``BasePlugin.get_setting_specs`` - the single extension point for per-scraper
    settings.
"""

from scrapers.base.settings.model import (
    ScraperSettings,
    ResolvedSetting,
    SettingView,
    STATUS_OK,
    STATUS_DEFAULT,
    STATUS_INVALID,
    STATUS_NOCFG,
)
from scrapers.base.settings.normalizers import (
    normalize_retention_days,
    normalize_bool,
    DEFAULT_LOG_RETENTION_DAYS,
    MIN_LOG_RETENTION_DAYS,
    MAX_LOG_RETENTION_DAYS,
)
from scrapers.base.settings.intervals import (
    SUPPORTED_INTERVALS,
    normalize_interval,
    oncalendar_for,
    canonical_for_oncalendar,
)
from scrapers.base.settings.messages import (
    interval_warning_message,
    retention_warning_message,
    notify_errors_warning_message,
)
from scrapers.base.settings.resolve import (
    SettingSpec,
    resolve_setting,
    setting_view,
    SPEC_INTERVAL,
    SPEC_RETENTION,
    SPEC_NOTIFY,
    BASE_SETTING_SPECS,
)

__all__ = [
    # model
    "ScraperSettings", "ResolvedSetting", "SettingView",
    "STATUS_OK", "STATUS_DEFAULT", "STATUS_INVALID", "STATUS_NOCFG",
    # normalizers
    "normalize_retention_days", "normalize_bool",
    "DEFAULT_LOG_RETENTION_DAYS", "MIN_LOG_RETENTION_DAYS", "MAX_LOG_RETENTION_DAYS",
    # intervals
    "SUPPORTED_INTERVALS", "normalize_interval", "oncalendar_for", "canonical_for_oncalendar",
    # messages
    "interval_warning_message", "retention_warning_message", "notify_errors_warning_message",
    # resolve
    "SettingSpec", "resolve_setting", "setting_view",
    "SPEC_INTERVAL", "SPEC_RETENTION", "SPEC_NOTIFY", "BASE_SETTING_SPECS",
]
