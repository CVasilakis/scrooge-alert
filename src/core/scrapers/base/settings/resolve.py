"""The generic resolve state machine, the :class:`SettingSpec`, and the built-in specs.

This is the heart of the settings layer: a single state machine (:func:`_resolve_setting`)
and a single result type (:class:`scrapers.base.settings.model.ResolvedSetting`) serve
every setting, declared as :class:`SettingSpec` objects in :data:`BASE_SETTING_SPECS`.
Adding a setting is one spec; a per-scraper setting is ``BASE_SETTING_SPECS + [extra]``
returned from ``BasePlugin.get_setting_specs`` - no new ``Resolved*`` type, registry
passthrough or config-check block.

Import-light: reads the config JSON directly (stdlib ``json``/``os``), never the storage
stack, so it is safe to call from the shell one-liners and ``--status``.
"""

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple, Type

from scrapers.base.settings.model import (
    ScraperSettings, ResolvedSetting, SettingView,
    STATUS_OK, STATUS_DEFAULT, STATUS_INVALID, STATUS_NOCFG,
)
from scrapers.base.settings.normalizers import (
    normalize_retention_days, normalize_bool, DEFAULT_LOG_RETENTION_DAYS,
)
from scrapers.base.settings.intervals import (
    normalize_interval, oncalendar_for, canonical_for_oncalendar,
)
from scrapers.base.settings.messages import (
    interval_warning_message, retention_warning_message, notify_errors_warning_message,
)


@dataclass(frozen=True)
class SettingSpec:
    """A declarative description of one ``settings`` field.

    One spec fully describes how a setting is resolved, validated and displayed, so the
    generic machinery (:func:`resolve_setting`, :func:`setting_view`) needs no
    per-setting code. The built-in settings live in :data:`BASE_SETTING_SPECS`; a
    plugin adds its own by returning ``BASE_SETTING_SPECS + [extra]`` from
    ``BasePlugin.get_setting_specs``.

    Attributes:
        field (str): The :class:`ScraperSettings` attribute this spec reads.
        label (str): The human-readable name shown in the settings panel.
        normalize (Callable): Maps the raw value to its effective value, or ``None``
            when the value is unsupported (which yields :data:`STATUS_INVALID`).
        display (Callable): Formats an effective value into a display string.
        warning (str): The footnote shown when the value is invalid.
        default (Any): The effective fallback when the value is unset/invalid/missing.
        default_factory (Optional[Callable]): A plugin-aware default, used instead of
            ``default`` when set (e.g. ``execution_interval`` defaults to the plugin's
            own ``OnCalendar``). Receives the owning ``BasePlugin``.
        is_unset (Callable): Predicate for "the user did not set this" (default:
            ``is None``). ``execution_interval`` uses ``not value`` so an empty string
            counts as unset (default) rather than invalid.
    """
    field: str
    label: str
    normalize: Callable[[Any], Optional[Any]]
    display: Callable[[Any], str]
    warning: str
    default: Any = None
    default_factory: Optional[Callable[[Any], Any]] = None
    is_unset: Callable[[Any], bool] = lambda value: value is None

    def default_for(self, plugin: Any = None) -> Any:
        """Returns the effective default, using the plugin-aware factory when present."""
        if self.default_factory is not None:
            return self.default_factory(plugin)
        return self.default


def _load_config_settings(
    config_path: str,
    settings_cls: Type[ScraperSettings],
) -> Tuple[Optional[ScraperSettings], Optional[str]]:
    """Reads a scraper config file and parses its ``settings`` block, once.

    The shared file stage of :func:`resolve_setting`, factored out so each setting's
    spec only declares its field, normalizer and default. Reads the JSON directly
    (import-light - never the storage stack), so it stays safe to call from the shell
    one-liners and ``--status``.

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
    branch yields ``default_value`` so the caller always has a usable value.

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


def resolve_setting(
    spec: SettingSpec,
    config_path: str,
    settings_cls: Type[ScraperSettings] = ScraperSettings,
    plugin: Any = None,
) -> ResolvedSetting:
    """Resolves one :class:`SettingSpec` against a scraper's config file.

    The single generic resolver: it folds the spec's field, normalizer, default
    (plugin-aware via :meth:`SettingSpec.default_for`) and unset-predicate through the
    shared state machine (:func:`_resolve_setting`). Import-light - reads the config
    JSON directly, never the storage class - so it is safe from the shell one-liners
    and ``--status``. Any problem degrades gracefully to the spec's default with a
    status the caller can act on.

    Args:
        spec (SettingSpec): The setting to resolve.
        config_path (str): Absolute path to the scraper's JSON config file.
        settings_cls (Type[ScraperSettings]): The settings class to parse with.
        plugin (Any): The owning plugin, for a spec whose default is plugin-aware
            (e.g. ``execution_interval``).

    Returns:
        ResolvedSetting: The effective value and how it was derived.
    """
    value, status, raw = _resolve_setting(
        config_path, settings_cls, spec.field,
        normalize=spec.normalize,
        default_value=spec.default_for(plugin),
        is_unset=spec.is_unset,
    )
    return ResolvedSetting(value, status, raw)


def setting_view(spec: SettingSpec, resolved: ResolvedSetting) -> SettingView:
    """Combines a spec and its resolved value into a presentation-ready view.

    Args:
        spec (SettingSpec): The setting's spec (supplies the label, display formatter
            and invalid-value message).
        resolved (ResolvedSetting): The resolved value and status.

    Returns:
        SettingView: The row to render in the settings panel section.
    """
    return SettingView(
        label=spec.label,
        display_value=spec.display(resolved.value),
        status=resolved.status,
        footnote=spec.warning if resolved.status == STATUS_INVALID else None,
    )


# The built-in settings shared by every scraper, in display order. A plugin returns
# this (optionally extended) from ``BasePlugin.get_setting_specs``; the registry and
# the settings panel iterate whatever it returns, so a per-scraper setting needs no
# framework change.
SPEC_INTERVAL = SettingSpec(
    field="execution_interval",
    label="Execution Interval",
    # The effective value is the systemd OnCalendar; display folds it back to the
    # canonical key the user recognizes (falling back to the raw expression).
    normalize=lambda raw: oncalendar_for(c) if (c := normalize_interval(raw)) else None,
    display=lambda oncalendar: canonical_for_oncalendar(oncalendar) or oncalendar,
    warning=interval_warning_message(),
    default_factory=lambda plugin: plugin.get_timer_directives().get("OnCalendar", ""),
    is_unset=lambda raw: not raw,  # an empty/blank interval is unset, not invalid
)

SPEC_RETENTION = SettingSpec(
    field="log_retention_days",
    label="Log Retention",
    normalize=normalize_retention_days,
    display=lambda days: f"{days} day{'s' if days != 1 else ''}",
    warning=retention_warning_message(),
    default=DEFAULT_LOG_RETENTION_DAYS,
)

SPEC_NOTIFY = SettingSpec(
    field="notify_scraping_errors",
    label="Notify On Errors",
    normalize=normalize_bool,
    display=lambda value: "true" if value else "false",
    warning=notify_errors_warning_message(),
    default=True,  # default ON: notifications enabled unless explicitly disabled
)

BASE_SETTING_SPECS: List[SettingSpec] = [SPEC_INTERVAL, SPEC_RETENTION, SPEC_NOTIFY]
