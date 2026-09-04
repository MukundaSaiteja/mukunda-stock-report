"""Tests for price-level alerts (store + one-shot/cooldown + commands)."""

import os

import pytest

os.environ.setdefault("ALERTS_FILE", "/tmp/pytest_alerts.json")

from analysis import alerts_store as S
from analysis.alerts_store import Alert, make_id


def _alert(direction="below", level=1250.0):
    return Alert(id=make_id("RELIANCE", direction, level), symbol="RELIANCE",
                 direction=direction, level=level, chat_id="-100", note="manual")


def test_below_fires_once_then_cooldown():
    a = _alert("below", 1250)
    assert S.evaluate(a, 1200.0) is True       # crossed below -> fire
    assert a.armed is False
    assert S.evaluate(a, 1200.0) is False      # still below, disarmed -> no re-fire


def test_above_fires_on_cross():
    a = _alert("above", 1400)
    assert S.evaluate(a, 1450.0) is True
    assert S.evaluate(a, 1450.0) is False


def test_no_fire_when_not_crossed():
    a = _alert("below", 1250)
    assert S.evaluate(a, 1300.0) is False      # above the level, not crossed
    assert a.armed is True


def test_rearm_when_price_returns(tmp_path, monkeypatch):
    # Disable cooldown wait by making last_fired old / cooldown 0.
    monkeypatch.setenv("ALERT_COOLDOWN_HOURS", "0")
    import importlib
    importlib.reload(S)
    a = Alert(id="x", symbol="X", direction="below", level=100.0, chat_id="-1")
    assert S.evaluate(a, 90.0) is True          # fire
    assert a.armed is False
    assert S.evaluate(a, 110.0) is False         # back to safe side -> re-arms
    assert a.armed is True
    assert S.evaluate(a, 90.0) is True           # can fire again


def test_store_roundtrip(tmp_path):
    p = tmp_path / "a.json"
    alerts = S.upsert([], _alert("below", 1250))
    S.save(alerts, p)
    loaded = S.load(p)
    assert len(loaded) == 1 and loaded[0].level == 1250.0
    kept, removed = S.remove_symbol(loaded, "RELIANCE")
    assert removed == 1 and kept == []
