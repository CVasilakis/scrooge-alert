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

Read-only by design:
    The ``settings`` block is **authored by the user and never written back by the
    application**. Settings are read - at config/schedule time through the
    ``resolve_*`` helpers, and at scrape time through
    ``JsonProductDataManager.get_settings`` - but there is deliberately no
    ``update_setting``/settings write path. Machine-owned runtime state (the latest
    price, a check timestamp) is persisted on *item rows* via ``update_item``, not in
    ``settings`` (see :class:`scrapers.base.model.BaseTrackedItem`). Keep new settings
    plain user inputs; do not introduce stateful settings.

Adding a setting:
    * give :class:`ScraperSettings` a new field (and parse it in ``from_dict``);
    * add a ``resolve_<setting>`` wrapper that delegates to :func:`_resolve_setting`
      with the field name, a normalizer and a default (the file read, the
      unset/invalid/ok status machine and the fallback are all handled there);
    * a scraper that needs a store-specific setting subclasses
      :class:`ScraperSettings` and returns it from ``BasePlugin.get_settings_class``
      (mirroring how ``MODEL``/``ROOT_KEY`` specialize the data manager).
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple, Type


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
    """
    execution_interval: Optional[str] = None
    log_retention_days: Optional[object] = None

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
        )


# Resolution status codes for a scraper's effective execution interval.
STATUS_OK = "ok"            # config present with a valid, supported interval
STATUS_DEFAULT = "default"  # no interval set; the plugin default is in effect
STATUS_INVALID = "invalid"  # config sets an unsupported/unparseable interval
STATUS_NOCFG = "nocfg"      # the config file is missing entirely


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


def _load_config_settings(
    config_path: str,
    settings_cls: Type[ScraperSettings],
) -> Tuple[Optional[ScraperSettings], Optional[str]]:
    """Reads a scraper config file and parses its ``settings`` block, once.

    The shared file stage of every ``resolve_*`` helper, factored out so each
    setting's resolver only declares its field, normalizer and default. Reads the
    JSON directly (import-light - never the storage stack), so it stays safe to call
    from the shell one-liners and ``--status``.

    Returns:
        Tuple[Optional[ScraperSettings], Optional[str]]: ``(settings, None)`` on a
            clean read; ``(None, STATUS_NOCFG)`` when the file is missing;
            ``(None, "readerror")`` when it is unreadable or not valid JSON (the
            corrupt config is surfaced elsewhere - here it degrades to the default).
    """
    if not os.path.isfile(config_path):
        return None, STATUS_NOCFG
    try:
        with open(config_path, "r") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None, "readerror"
    return settings_cls.from_dict(data.get("settings") if isinstance(data, dict) else None), None


def _resolve_setting(
    config_path: str,
    settings_cls: Type[ScraperSettings],
    field_name: str,
    normalize: Callable[[Any], Optional[Any]],
    default_value: Any,
    is_unset: Callable[[Any], bool] = lambda value: value is None,
) -> Tuple[Any, str, Any]:
    """Resolves one ``settings`` field to ``(value, status, raw)``, generically.

    The single home for the resolve state machine shared by every setting: missing
    config -> NOCFG; unreadable/corrupt -> DEFAULT; unset -> DEFAULT; a value that
    ``normalize`` rejects (returns ``None``) -> INVALID; otherwise OK. Every non-OK
    branch yields ``default_value`` so the caller always has a usable value. Adding a
    new setting is one call to this with its field name, normalizer and default.

    Args:
        config_path (str): Absolute path to the scraper's JSON config file.
        settings_cls (Type[ScraperSettings]): The settings class to parse with.
        field_name (str): The :class:`ScraperSettings` attribute to read.
        normalize (Callable): Maps the raw value to its effective value, or ``None``
            when the value is unsupported.
        default_value (Any): The fallback returned for every non-OK status.
        is_unset (Callable): Predicate for "the user did not set this" (default:
            ``is None``). ``execution_interval`` passes ``not value`` so an empty
            string counts as unset (default) rather than invalid.

    Returns:
        Tuple[Any, str, Any]: ``(value, status, raw)`` where status is one of the
            ``STATUS_*`` codes and ``raw`` is the user's value (``None`` unless the
            status is OK or INVALID).
    """
    settings, load_status = _load_config_settings(config_path, settings_cls)
    if load_status is not None:
        # nocfg -> NOCFG so the caller can footnote a missing file; a read/parse
        # error degrades to DEFAULT (the corrupt config is surfaced by the load path).
        return default_value, STATUS_NOCFG if load_status == STATUS_NOCFG else STATUS_DEFAULT, None

    raw = getattr(settings, field_name)
    if is_unset(raw):
        return default_value, STATUS_DEFAULT, None

    value = normalize(raw)
    if value is None:
        return default_value, STATUS_INVALID, raw
    return value, STATUS_OK, raw


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
    oncalendar, status, raw = _resolve_setting(
        config_path, settings_cls, "execution_interval",
        normalize=lambda r: oncalendar_for(c) if (c := normalize_interval(r)) else None,
        default_value=default_oncalendar,
        is_unset=lambda r: not r,  # an empty/blank interval is unset, not invalid
    )
    return ResolvedInterval(oncalendar, status, raw)


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
    days, status, raw = _resolve_setting(
        config_path, settings_cls, "log_retention_days",
        normalize=normalize_retention_days,
        default_value=DEFAULT_LOG_RETENTION_DAYS,
    )
    return ResolvedRetention(days, status, raw)


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
