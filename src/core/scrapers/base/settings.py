"""Scraper configuration settings: the user-tunable ``settings`` block.

Each scraper's JSON config file may carry a top-level ``settings`` object, a
sibling of its item list (e.g. ``products``)::

    {
      "settings": { "execution_interval": "1h" },
      "products": [ ... ]
    }

This module is the single home for the settings *model* and for the
``execution_interval`` -> systemd ``OnCalendar`` semantics. It is imported by the
plugin descriptors (and, transitively, by the lightweight shell one-liners and
``--status``), so it must stay **import-light** - stdlib only, never a
transport/parsing library - in line with the BasePlugin import-light contract.

Adding a setting:
    * give :class:`ScraperSettings` a new field (and parse it in ``from_dict``);
    * a scraper that needs a store-specific setting subclasses
      :class:`ScraperSettings` and returns it from ``BasePlugin.get_settings_class``
      (mirroring how ``MODEL``/``ROOT_KEY`` specialize the data manager).
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, Optional, Type


# Canonical execution intervals, in first-seen order, each mapped to the systemd
# OnCalendar expression it generates. This is the authoritative set of supported
# cadences: a normalized user value must resolve to one of these keys.
SUPPORTED_INTERVALS: Dict[str, str] = {
    "15m": "*:0/15",
    "30m": "*:0/30",
    "1h": "hourly",
    "2h": "*-*-* 00/2:00:00",
    "4h": "*-*-* 00/4:00:00",
    "8h": "*-*-* 00/8:00:00",
    "12h": "*-*-* 00/12:00:00",
    "24h": "daily",
}

# Canonical key -> total minutes. Any broad user spelling that resolves to a
# supported number of minutes maps back to its canonical key through this table.
_CANONICAL_MINUTES: Dict[str, int] = {
    "15m": 15, "30m": 30, "1h": 60, "2h": 120,
    "4h": 240, "8h": 480, "12h": 720, "24h": 1440,
}
_MINUTES_TO_CANONICAL: Dict[int, str] = {m: k for k, m in _CANONICAL_MINUTES.items()}

# Named cadences the user may type instead of a number+unit (whitespace, case,
# hyphens and underscores are stripped before this lookup).
_NAMED_ALIASES: Dict[str, int] = {
    "hourly": 60,
    "daily": 1440,
    "halfhourly": 30,
    "halfhour": 30,
}

# Unit token -> minutes-per-unit. A bare number (no unit) is read as minutes.
_UNIT_MINUTES = (
    (("", "m", "min", "mins", "minute", "minutes"), 1),
    (("h", "hr", "hrs", "hour", "hours"), 60),
    (("d", "day", "days"), 1440),
)


def normalize_interval(raw: str) -> Optional[str]:
    """Normalizes a broad user interval string to a canonical key, or ``None``.

    Folds the many ways a user might write a cadence onto one of the
    :data:`SUPPORTED_INTERVALS` keys: e.g. ``"1h"``, ``"1 h"``, ``"1Hour"``,
    ``"1 hour"``, ``"60m"`` and ``"hourly"`` all return ``"1h"``; ``"daily"``,
    ``"1d"`` and ``"1440m"`` return ``"24h"``. Whitespace and case are ignored.

    Args:
        raw (str): The user-supplied interval value.

    Returns:
        Optional[str]: The canonical key (e.g. ``"1h"``), or ``None`` if the value
            is unrecognized or resolves to an unsupported cadence.
    """
    if not isinstance(raw, str):
        return None

    # Collapse case and strip *all* whitespace so "1 Hour" == "1hour".
    token = re.sub(r"\s+", "", raw).lower()
    if not token:
        return None

    # Hyphens/underscores only appear in word aliases ("half-hourly"); drop them
    # for the alias lookup so both "half-hourly" and "halfhourly" resolve.
    alias_key = token.replace("-", "").replace("_", "")
    if alias_key in _NAMED_ALIASES:
        return _MINUTES_TO_CANONICAL.get(_NAMED_ALIASES[alias_key])

    match = re.fullmatch(r"(\d+)([a-z]*)", token)
    if not match:
        return None

    minutes_total = int(match.group(1))
    unit = match.group(2)
    for unit_tokens, per_unit in _UNIT_MINUTES:
        if unit in unit_tokens:
            return _MINUTES_TO_CANONICAL.get(minutes_total * per_unit)
    return None


def oncalendar_for(canonical: str) -> str:
    """Returns the systemd ``OnCalendar`` expression for a canonical interval key."""
    return SUPPORTED_INTERVALS[canonical]


# Log retention: how many daily log files each scraper keeps (the rotating file
# handler's backupCount). A user value is an integer day-count or a day-duration
# string ("4", "4d", "4 days"); only days are supported (no hours/weeks/months).
DEFAULT_LOG_RETENTION_DAYS = 7
MIN_LOG_RETENTION_DAYS = 1
MAX_LOG_RETENTION_DAYS = 30


def normalize_retention_days(raw) -> Optional[int]:
    """Validates a log-retention value to a day-count in 1-30, or ``None``.

    Accepts a JSON integer (``7``) or a day-duration string - ``"4"``, ``"4d"``,
    ``"4 d"``, ``"4day"``, ``"4 days"`` (case-insensitive, whitespace-tolerant); a
    bare number is read as days. Only days are supported. Returns the day count when
    it is within 1-30, otherwise ``None`` - so ``0``, an out-of-range number, a
    non-day unit (``"4h"``, ``"4 months"``), a float, a bool, or junk are rejected.

    Args:
        raw: The user's raw ``log_retention_days`` value (any type).

    Returns:
        Optional[int]: The day count in 1-30, or ``None`` if unsupported.
    """
    # bool is a subclass of int; reject it explicitly (True/False are not day counts).
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        token = re.sub(r"\s+", "", raw).lower()
        match = re.fullmatch(r"(\d+)(d|day|days)?", token)
        if not match:
            return None
        value = int(match.group(1))
    else:
        return None
    if MIN_LOG_RETENTION_DAYS <= value <= MAX_LOG_RETENTION_DAYS:
        return value
    return None


@dataclass
class ScraperSettings:
    """The parsed ``settings`` block of a scraper's config file.

    The base set of settings shared by every scraper. A scraper that needs its own
    knobs subclasses this (adding fields and extending :meth:`from_dict`) and
    returns the subclass from ``BasePlugin.get_settings_class``.

    Attributes:
        execution_interval (Optional[str]): The user's raw cadence string (as
            typed), or ``None`` when unset. It is normalized via
            :func:`normalize_interval` only at the point it becomes a systemd
            schedule, so the file keeps the user's original spelling.
        log_retention_days: The user's raw log-retention value (an int or a
            day-duration string), or ``None`` when unset. Validated via
            :func:`normalize_retention_days` at the point it becomes a rotating-file
            ``backupCount``; the raw value is kept so the resolver can tell an
            *invalid* value apart from an *unset* one.
        reminder_interval: The user's raw status-reminder cadence (e.g. ``"1 month"``
            or ``"off"``), or ``None`` when unset. Validated via
            :func:`normalize_reminder_interval` where it is used.
        last_reminder_sent (Optional[str]): Machine-owned state — the UTC timestamp
            (``TIMESTAMP_FORMAT``) of the last status reminder, written back by the
            scraper. ``None`` until the first reminder is sent.
    """
    execution_interval: Optional[str] = None
    log_retention_days: Optional[object] = None
    reminder_interval: Optional[object] = None
    last_reminder_sent: Optional[str] = None

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
        last_sent = data.get("last_reminder_sent")
        return cls(
            execution_interval=interval if isinstance(interval, str) else None,
            log_retention_days=data.get("log_retention_days"),
            reminder_interval=data.get("reminder_interval"),
            last_reminder_sent=last_sent if isinstance(last_sent, str) else None,
        )


# Resolution status codes for a scraper's effective execution interval.
STATUS_OK = "ok"            # config present with a valid, supported interval
STATUS_DEFAULT = "default"  # no interval set; the plugin default is in effect
STATUS_INVALID = "invalid"  # config sets an unsupported/unparseable interval
STATUS_NOCFG = "nocfg"      # the config file is missing entirely
STATUS_OFF = "off"          # setting explicitly off or unset (a valid disabled state)


@dataclass
class ResolvedInterval:
    """The effective schedule for one scraper, plus how it was derived.

    Attributes:
        oncalendar (str): The systemd ``OnCalendar`` value to apply - the mapped
            user value when valid, otherwise the plugin's default.
        status (str): One of :data:`STATUS_OK`, :data:`STATUS_DEFAULT`,
            :data:`STATUS_INVALID`, :data:`STATUS_NOCFG`; lets callers decide
            whether to warn (``schedule.sh``) or footnote (``--status``).
        raw (Optional[str]): The user's raw value, kept for messages (e.g. the
            offending input on :data:`STATUS_INVALID`).
    """
    oncalendar: str
    status: str
    raw: Optional[str] = None


def resolve_interval(
    default_oncalendar: str,
    config_path: str,
    settings_cls: Type[ScraperSettings] = ScraperSettings,
) -> ResolvedInterval:
    """Resolves a scraper's effective ``OnCalendar`` from its config file.

    The single place the ``execution_interval`` setting becomes a schedule. It
    reads the config JSON directly (never importing the scraper's storage class or
    its transport stack), so it is safe to call from the lightweight shell
    one-liners and from ``--status``. Any problem degrades gracefully to the plugin
    default with a status the caller can act on.

    Args:
        default_oncalendar (str): The plugin's default ``OnCalendar`` (the fallback).
        config_path (str): Absolute path to the scraper's JSON config file.
        settings_cls (Type[ScraperSettings]): The settings class to parse with.

    Returns:
        ResolvedInterval: The effective schedule and how it was derived.
    """
    if not os.path.isfile(config_path):
        return ResolvedInterval(default_oncalendar, STATUS_NOCFG)

    try:
        with open(config_path, "r") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        # An unreadable/corrupt config is surfaced elsewhere (the data manager's
        # load reports it in --status); for scheduling, fall back to the default.
        return ResolvedInterval(default_oncalendar, STATUS_DEFAULT)

    settings = settings_cls.from_dict(data.get("settings") if isinstance(data, dict) else None)
    raw = settings.execution_interval
    if not raw:
        return ResolvedInterval(default_oncalendar, STATUS_DEFAULT)

    canonical = normalize_interval(raw)
    if canonical is None:
        return ResolvedInterval(default_oncalendar, STATUS_INVALID, raw=raw)

    return ResolvedInterval(oncalendar_for(canonical), STATUS_OK, raw=raw)


@dataclass
class ResolvedRetention:
    """The effective log retention for one scraper, plus how it was derived.

    Attributes:
        days (int): The number of daily log files to keep - the validated value, or
            :data:`DEFAULT_LOG_RETENTION_DAYS` as the fallback. Always usable.
        status (str): One of :data:`STATUS_OK`, :data:`STATUS_DEFAULT`,
            :data:`STATUS_INVALID`, :data:`STATUS_NOCFG`; lets callers decide whether
            to warn (the logger / ``--status``).
        raw: The user's raw value, kept for messages.
    """
    days: int
    status: str
    raw: object = None


def resolve_retention(
    config_path: str,
    settings_cls: Type[ScraperSettings] = ScraperSettings,
) -> ResolvedRetention:
    """Resolves a scraper's effective log retention from its config file.

    Mirrors :func:`resolve_interval`: reads the config JSON directly (import-light,
    no storage class), so it is usable from the logger and from ``--status``. Any
    problem degrades gracefully to :data:`DEFAULT_LOG_RETENTION_DAYS` with a status
    the caller can act on; the returned ``days`` is always safe to apply.

    Args:
        config_path (str): Absolute path to the scraper's JSON config file.
        settings_cls (Type[ScraperSettings]): The settings class to parse with.

    Returns:
        ResolvedRetention: The effective retention and how it was derived.
    """
    if not os.path.isfile(config_path):
        return ResolvedRetention(DEFAULT_LOG_RETENTION_DAYS, STATUS_NOCFG)

    try:
        with open(config_path, "r") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return ResolvedRetention(DEFAULT_LOG_RETENTION_DAYS, STATUS_DEFAULT)

    settings = settings_cls.from_dict(data.get("settings") if isinstance(data, dict) else None)
    raw = settings.log_retention_days
    if raw is None:
        return ResolvedRetention(DEFAULT_LOG_RETENTION_DAYS, STATUS_DEFAULT)

    days = normalize_retention_days(raw)
    if days is None:
        return ResolvedRetention(DEFAULT_LOG_RETENTION_DAYS, STATUS_INVALID, raw=raw)

    return ResolvedRetention(days, STATUS_OK, raw=raw)


def retention_warning_message() -> str:
    """The single user-facing message for an invalid ``log_retention_days``.

    Shared by the logger (run-log warning) and ``--status`` (config footnote) so the
    wording and the 1/30/7 bounds live in one place. Kept short to fit the status
    panel's footnote width.
    """
    return (
        f"log_retention_days must be {MIN_LOG_RETENTION_DAYS}-{MAX_LOG_RETENTION_DAYS}. "
        f"Using default {DEFAULT_LOG_RETENTION_DAYS}."
    )


# ---------------------------------------------------------------------------
# Status reminder (per-scraper "still running" liveness notification)
# ---------------------------------------------------------------------------

#: Sentinel for a disabled reminder (the default).
REMINDER_OFF = "off"

#: Canonical reminder cadences (the fixed menu): normalized value -> display label.
_REMINDER_LABELS = {
    REMINDER_OFF: "Off",
    7: "1 week",
    30: "1 month",
    90: "3 months",
    365: "1 year",
}

# Accepted spellings -> canonical value (REMINDER_OFF or a day-count). Keys are
# whitespace-free and lowercase; a raw value is folded to that form before lookup.
_REMINDER_ALIASES = {
    "off": REMINDER_OFF, "none": REMINDER_OFF, "disabled": REMINDER_OFF, "never": REMINDER_OFF,
    # 1 week
    "1week": 7, "1weeks": 7, "1w": 7, "1wk": 7, "7d": 7, "7day": 7, "7days": 7, "7": 7, "weekly": 7,
    # 1 month
    "1month": 30, "1months": 30, "1mo": 30, "30d": 30, "30day": 30, "30days": 30, "30": 30, "monthly": 30,
    # 3 months
    "3month": 90, "3months": 90, "3mo": 90, "90d": 90, "90day": 90, "90days": 90, "90": 90, "quarterly": 90,
    # 1 year
    "1year": 365, "1years": 365, "1y": 365, "1yr": 365, "12month": 365, "12months": 365, "12mo": 365,
    "365d": 365, "365day": 365, "365days": 365, "365": 365, "yearly": 365, "annually": 365,
}


def normalize_reminder_interval(raw) -> Optional[object]:
    """Normalizes a reminder cadence to ``REMINDER_OFF``, a day-count, or ``None``.

    Accepts the fixed menu - off, 1 week, 1 month, 3 months, 1 year - and their
    alternate spellings (``7d``/``1w``/``weekly``, ``30d``/``monthly``, ``90d``,
    ``365d``/``12 months``/``yearly``, plus bare ints). Case-insensitive and
    whitespace-tolerant. Returns ``REMINDER_OFF`` for a disabled reminder, the day
    count (7/30/90/365) for a valid cadence, or ``None`` for an unsupported value.

    Args:
        raw: The user's raw ``reminder_interval`` value (any type).

    Returns:
        Optional[object]: ``REMINDER_OFF``, an int day-count, or ``None`` if invalid.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw in (7, 30, 90, 365) else None
    if not isinstance(raw, str):
        return None
    token = re.sub(r"\s+", "", raw).lower()
    if not token:
        return None
    return _REMINDER_ALIASES.get(token)


def reminder_label(value) -> str:
    """Returns the human-readable label for a normalized reminder value."""
    return _REMINDER_LABELS.get(value, "Invalid")


@dataclass
class ResolvedReminder:
    """The effective status-reminder cadence for one scraper, and how it derived.

    Attributes:
        value: ``REMINDER_OFF`` or a day-count (7/30/90/365). Any non-``ok`` status
            yields ``REMINDER_OFF`` so callers always have a safe value.
        status (str): One of :data:`STATUS_OK`, :data:`STATUS_OFF`,
            :data:`STATUS_INVALID`, :data:`STATUS_NOCFG`.
        label (str): A display label for ``--status`` (e.g. ``"1 month"``, ``"Off"``,
            ``"Invalid"``).
        raw: The user's raw value, kept for messages.
    """
    value: object
    status: str
    label: str
    raw: object = None


def resolve_reminder(
    config_path: str,
    settings_cls: Type[ScraperSettings] = ScraperSettings,
) -> ResolvedReminder:
    """Resolves a scraper's status-reminder cadence from its config file.

    Mirrors :func:`resolve_retention`: reads the config JSON directly (import-light,
    no storage class), so ``--status`` can use it cheaply. An unset key (or a missing
    config) is the default disabled state; an unsupported value is flagged invalid.

    Args:
        config_path (str): Absolute path to the scraper's JSON config file.
        settings_cls (Type[ScraperSettings]): The settings class to parse with.

    Returns:
        ResolvedReminder: The effective cadence and how it was derived.
    """
    off_label = _REMINDER_LABELS[REMINDER_OFF]
    if not os.path.isfile(config_path):
        return ResolvedReminder(REMINDER_OFF, STATUS_NOCFG, off_label)

    try:
        with open(config_path, "r") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return ResolvedReminder(REMINDER_OFF, STATUS_OFF, off_label)

    settings = settings_cls.from_dict(data.get("settings") if isinstance(data, dict) else None)
    raw = settings.reminder_interval
    if raw is None:
        return ResolvedReminder(REMINDER_OFF, STATUS_OFF, off_label)

    value = normalize_reminder_interval(raw)
    if value is None:
        return ResolvedReminder(REMINDER_OFF, STATUS_INVALID, "Invalid", raw=raw)
    if value == REMINDER_OFF:
        return ResolvedReminder(REMINDER_OFF, STATUS_OFF, off_label, raw=raw)

    return ResolvedReminder(value, STATUS_OK, reminder_label(value), raw=raw)


def reminder_invalid_message() -> str:
    """The single user-facing footnote for an invalid ``reminder_interval``."""
    return "reminder_interval is invalid; defaults to off"
