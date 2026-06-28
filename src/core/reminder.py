"""Per-scraper status reminder: a periodic "still running in the background"
notification that also flags a newer project version when one exists.

Isolated in its own module (imported only by the orchestrator at runtime, never by
``--status`` or ``--help``) so the feature stays modular and the lightweight commands
stay import-light. All cadence parsing lives in :mod:`scrapers.base.settings`; the
persisted state (``last_reminder_sent``) is read/written through the data manager's
settings API, so the timestamp is saved atomically alongside the scrape's write-back.
"""

import datetime
from typing import Optional

from constants import TIMESTAMP_FORMAT
from exceptions import UpdateCheckError
from utils import check_for_updates
from scrapers.base.settings import normalize_reminder_interval, REMINDER_OFF


def _parse_timestamp(raw: Optional[str]) -> Optional[datetime.datetime]:
    """Parses a stored UTC timestamp, or returns ``None`` when absent/unparseable."""
    if not raw:
        return None
    try:
        return datetime.datetime.strptime(raw, TIMESTAMP_FORMAT)
    except (ValueError, TypeError):
        return None


def maybe_send_reminder(manager, notifier, now: datetime.datetime) -> bool:
    """Sends this scraper's periodic "still running" reminder if it is due.

    Reads the cadence + last-sent timestamp from the loaded config
    (``manager.get_settings()``); once the interval has elapsed it best-effort checks
    for a newer version, sends a liveness notification (mentioning the update only
    when one exists), and caches ``last_reminder_sent`` for the manager's next
    ``save()``. The notification is always sent when due — its purpose is to confirm
    the background service is alive — so a failed update check never suppresses it.

    Self-contained and defensive: any unexpected error is swallowed (a reminder must
    never abort a scrape). An ``off``/unset cadence is a silent no-op; an invalid one
    is surfaced on the ``--status`` Service Status panel.

    Args:
        manager: The target's data manager (already loaded).
        notifier: The shared :class:`Notifier`.
        now (datetime.datetime): The current naive-UTC time.

    Returns:
        bool: True if ``last_reminder_sent`` was cached (the caller should save).
    """
    try:
        settings = manager.get_settings()
        interval = normalize_reminder_interval(settings.reminder_interval)
        if interval is None or interval == REMINDER_OFF:
            return False  # unset, off, or invalid (the latter shown in --status)

        last_sent = _parse_timestamp(settings.last_reminder_sent)
        if last_sent is not None and (now - last_sent).total_seconds() < interval * 86400:
            return False  # not due yet

        try:
            update_available = check_for_updates()
        except UpdateCheckError:
            update_available = False  # transient; still send the liveness reminder

        scraper_name = manager.plugin.get_display_name() if manager.plugin else "Scrooge Alert"
        notifier.notify_status_reminder(scraper_name, update_available)
        manager.update_setting("last_reminder_sent", now.strftime(TIMESTAMP_FORMAT))
        return True
    except Exception:
        # A reminder is best-effort and must never abort the scrape.
        return False
