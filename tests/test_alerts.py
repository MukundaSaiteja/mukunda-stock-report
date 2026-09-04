"""Tests for price-level alerts (store + one-shot/cooldown + commands)."""

import os

import pytest

os.environ.setdefault("ALERTS_FILE", "/tmp/pytest_alerts.json")

from analysis import alerts_store as S
from analysis.alerts_store import Alert, make_id


def _alert(direction="below", level=1250.0):
    return Alert(id=make_id("RELIANCE", direction, level), symbol="RELIANCE",
                 direction=direction, level=level, chat_id="-100", note="manual")


def test_below_fires_once_then_quiet_same_day():
    a = _alert("below", 1250)
    assert S.evaluate(a, 1200.0) is True       # crossed below -> fire
    assert S.evaluate(a, 1200.0) is False      # still below same day -> no repeat
    assert S.evaluate(a, 1100.0) is False      # deeper same day -> still no repeat


def test_fires_again_next_day_while_past_level():
    from datetime import datetime, timezone, timedelta
    a = _alert("below", 1250)
    assert S.evaluate(a, 1200.0) is True
    a.last_fired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()  # pretend yesterday
    assert S.evaluate(a, 1200.0) is True        # new day, still below -> one more ping
    assert S.evaluate(a, 1200.0) is False       # same (new) day again -> quiet


def test_above_fires_on_cross():
    a = _alert("above", 1400)
    assert S.evaluate(a, 1450.0) is True
    assert S.evaluate(a, 1450.0) is False


def test_no_fire_when_not_crossed_and_rearms():
    a = _alert("below", 1250)
    assert S.evaluate(a, 1300.0) is False      # above the level, not crossed
    assert a.armed is True


def test_store_roundtrip(tmp_path):
    p = tmp_path / "a.json"
    alerts = S.upsert([], _alert("below", 1250))
    S.save(alerts, p)
    loaded = S.load(p)
    assert len(loaded) == 1 and loaded[0].level == 1250.0
    kept, removed = S.remove_symbol(loaded, "RELIANCE")
    assert removed == 1 and kept == []
