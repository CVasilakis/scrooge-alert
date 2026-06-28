"""Settings data model: the parsed ``settings`` block, resolved values, and status codes.

Pure stdlib dataclasses with no dependency on the rest of the settings package, so this
stays the leaf of the import graph (import-light).
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ScraperSettings:
    """The parsed ``settings`` block of a scraper's config file.

    The base set of settings shared by every scraper. A scraper that needs its own
    knobs subclasses this (adding fields and extending :meth:`from_dict`) and
    returns the subclass from ``BasePlugin.get_settings_class``.

    Attributes:
        execution_interval (Optional[str]): The user's raw cadence string (as
            typed), or ``None`` when unset. It is normalized via
            ``normalize_interval`` only at the point it becomes a systemd schedule, so
            the file keeps the user's original spelling.
        log_retention_days: The user's raw log-retention value (an int or a
            day-duration string), or ``None`` when unset. Validated via
            ``normalize_retention_days`` at the point it becomes a rotating-file
            ``backupCount``; the raw value is kept so the resolver can tell an
            *invalid* value apart from an *unset* one.
        notify_scraping_errors: The user's raw opt-out for the per-run "Scraping
            Errors" notification, or ``None`` when unset. Validated via
            ``normalize_bool`` where it gates the notification; it defaults to *notify*
            (``True``) when unset or unparseable, so only an explicit, valid ``false``
            silences that push (stale-product and crash alerts are unaffected). The raw
            value is kept so an *invalid* value can be told apart from an *unset* one.
    """
    execution_interval: Optional[str] = None
    log_retention_days: Optional[object] = None
    notify_scraping_errors: Optional[object] = None

    @classmethod
    def from_dict(cls, data) -> "ScraperSettings":
        """Builds settings from a raw ``settings`` mapping, tolerating bad input.

        A missing or non-dict ``settings`` block (or a missing key) yields field
        defaults rather than an error; unknown keys are ignored. Each value is stored
        *raw*; validation of its *meaning* (a supported interval, a 1-30 retention)
        happens later, where it is used, so the model stays a pure container.

        Args:
            data: The value of the config's top-level ``settings`` key.

        Returns:
            ScraperSettings: The parsed settings.
        """
        if not isinstance(data, dict):
            return cls()
        interval = data.get("execution_interval")
        return cls(
            execution_interval=interval if isinstance(interval, str) else None,
            log_retention_days=data.get("log_retention_days"),
            notify_scraping_errors=data.get("notify_scraping_errors"),
        )


# Resolution status codes for a scraper's effective setting value.
STATUS_OK = "ok"            # config present with a valid, supported value
STATUS_DEFAULT = "default"  # no value set; the spec's default is in effect
STATUS_INVALID = "invalid"  # config sets an unsupported/unparseable value
STATUS_NOCFG = "nocfg"      # the config file is missing entirely


@dataclass
class ResolvedSetting:
    """The effective value of one setting, plus how it was derived.

    The single result type shared by every setting (interval, retention, flag, and any
    per-scraper setting). For ``execution_interval`` the ``value`` is the systemd
    ``OnCalendar`` expression; for other settings it is the setting's effective value.

    Attributes:
        value: The effective value to apply - the validated user value when OK,
            otherwise the spec's default. Always usable.
        status (str): One of :data:`STATUS_OK`, :data:`STATUS_DEFAULT`,
            :data:`STATUS_INVALID`, :data:`STATUS_NOCFG`; lets callers decide whether
            to warn, footnote, or proceed silently.
        raw: The user's raw value, kept for messages (e.g. the offending input on
            :data:`STATUS_INVALID`); ``None`` unless the status is OK or INVALID.
    """
    value: Any
    status: str
    raw: Any = None


@dataclass
class SettingView:
    """A presentation-ready record of one setting for the settings panel section.

    Built by ``setting_view`` from a ``SettingSpec`` and its :class:`ResolvedSetting`.
    Render sites (the ``--status`` Service Status panel and the interactive Scraping
    panel) map this to their own row/icon idiom, so resolution and rendering stay
    decoupled.

    Attributes:
        label (str): The human-readable setting name (e.g. ``"Execution Interval"``).
        display_value (str): The effective value, formatted for display (e.g. ``"1h"``,
            ``"7 days"``, ``"true"``).
        status (str): The ``STATUS_*`` code (drives the row icon: invalid -> warn).
        footnote (Optional[str]): The invalid-value message when the status is
            :data:`STATUS_INVALID`, otherwise ``None``.
    """
    label: str
    display_value: str
    status: str
    footnote: Optional[str] = None
