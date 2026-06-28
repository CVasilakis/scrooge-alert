"""Tests for the generic settings resolver and its status state machine.

Covers each STATUS_* branch (ok/default/invalid/nocfg) and the unset-vs-invalid
distinction, driven through real temp config files.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src", "core")))

from scrapers.base.settings import (  # noqa: E402
    resolve_setting, oncalendar_for,
    SPEC_RETENTION, SPEC_NOTIFY, SPEC_INTERVAL,
    STATUS_OK, STATUS_DEFAULT, STATUS_INVALID, STATUS_NOCFG,
    DEFAULT_LOG_RETENTION_DAYS,
)


class _FakePlugin:
    """Minimal stand-in supplying the plugin-aware interval default."""
    def get_timer_directives(self):
        return {"OnCalendar": "hourly"}


def _write_config(settings):
    """Writes a temp config file with the given ``settings`` block; returns its path."""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "x.json")
    with open(path, "w") as f:
        json.dump({"settings": settings, "products": []}, f)
    return path


class TestResolveRetention(unittest.TestCase):
    def test_ok(self):
        r = resolve_setting(SPEC_RETENTION, _write_config({"log_retention_days": 4}))
        self.assertEqual((r.value, r.status, r.raw), (4, STATUS_OK, 4))

    def test_default_when_unset(self):
        r = resolve_setting(SPEC_RETENTION, _write_config({}))
        self.assertEqual((r.value, r.status), (DEFAULT_LOG_RETENTION_DAYS, STATUS_DEFAULT))

    def test_invalid_keeps_default_and_raw(self):
        r = resolve_setting(SPEC_RETENTION, _write_config({"log_retention_days": 99}))
        self.assertEqual((r.value, r.status, r.raw), (DEFAULT_LOG_RETENTION_DAYS, STATUS_INVALID, 99))

    def test_nocfg(self):
        r = resolve_setting(SPEC_RETENTION, "/no/such/file.json")
        self.assertEqual((r.value, r.status), (DEFAULT_LOG_RETENTION_DAYS, STATUS_NOCFG))


class TestResolveNotify(unittest.TestCase):
    def test_explicit_false_is_ok_not_invalid(self):
        # A valid `false` must resolve OK (the resolver tests normalize() is None,
        # not falsiness) so it actually silences the push.
        r = resolve_setting(SPEC_NOTIFY, _write_config({"notify_scraping_errors": False}))
        self.assertEqual((r.value, r.status), (False, STATUS_OK))

    def test_default_true_when_unset(self):
        r = resolve_setting(SPEC_NOTIFY, _write_config({}))
        self.assertEqual((r.value, r.status), (True, STATUS_DEFAULT))

    def test_invalid_defaults_to_true(self):
        r = resolve_setting(SPEC_NOTIFY, _write_config({"notify_scraping_errors": "maybe"}))
        self.assertEqual((r.value, r.status, r.raw), (True, STATUS_INVALID, "maybe"))


class TestResolveInterval(unittest.TestCase):
    PLUGIN = _FakePlugin()

    def test_ok_maps_to_oncalendar(self):
        r = resolve_setting(SPEC_INTERVAL, _write_config({"execution_interval": "2h"}),
                            plugin=self.PLUGIN)
        self.assertEqual((r.value, r.status), (oncalendar_for("2h"), STATUS_OK))

    def test_default_uses_plugin_oncalendar(self):
        r = resolve_setting(SPEC_INTERVAL, _write_config({}), plugin=self.PLUGIN)
        self.assertEqual((r.value, r.status), ("hourly", STATUS_DEFAULT))

    def test_empty_string_is_unset_not_invalid(self):
        r = resolve_setting(SPEC_INTERVAL, _write_config({"execution_interval": ""}),
                            plugin=self.PLUGIN)
        self.assertEqual((r.value, r.status), ("hourly", STATUS_DEFAULT))

    def test_unsupported_value_is_invalid(self):
        r = resolve_setting(SPEC_INTERVAL, _write_config({"execution_interval": "3h"}),
                            plugin=self.PLUGIN)
        self.assertEqual((r.value, r.status, r.raw), ("hourly", STATUS_INVALID, "3h"))


if __name__ == "__main__":
    unittest.main()
