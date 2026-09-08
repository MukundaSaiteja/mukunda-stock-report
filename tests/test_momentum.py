"""Offline tests for the momentum (A-F) engine: it scores footprints from a
yfinance-style OHLCV frame and never raises."""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd


def _locked_circuit_frame():
    """26 flat days then 2 locked +5% upper-circuit days (O=H=L=C)."""
    rows = []
    base = date(2026, 1, 1)
    for i in range(26):
        rows.append((base + timedelta(days=i), 100.0, 100.5, 99.5, 100.0, 100000))
    rows.append((base + timedelta(days=26), 105.0, 105.0, 105.0, 105.0, 200000))
    rows.append((base + timedelta(days=27), 110.25, 110.25, 110.25, 110.25, 300000))
    idx = pd.DatetimeIndex([r[0] for r in rows], name="Date")
    return pd.DataFrame({
        "Open": [r[1] for r in rows], "High": [r[2] for r in rows],
        "Low": [r[3] for r in rows], "Close": [r[4] for r in rows],
        "Volume": [r[5] for r in rows],
    }, index=idx)


def test_circuit_and_scoring(monkeypatch):
    monkeypatch.setenv("MOMENTUM_NSE", "0")  # no network in tests
    from momentum import engine, fundamentals
    # avoid the real yfinance fundamentals call
    monkeypatch.setattr(fundamentals, "fetch",
                        lambda s: fundamentals.Fundamentals(symbol=s, ok=True))

    r = engine.compute("TESTX", _locked_circuit_frame(), {}, None)
    assert r["ok"] is True
    assert r["tier"] in ("HIGH", "MEDIUM")
    assert r["score"] > 0
    # circuit streak of 2 landed in group B (accumulation footprint)
    assert any("circuit" in ln.lower() for ln in r["groups"]["B"])
    assert r["coverage"]["B"] is True
    # render-ready fields present
    for k in ("scenario", "n_signals", "verify", "group_names", "price"):
        assert k in r


def test_insufficient_history_is_soft_fail():
    from momentum import engine
    r = engine.compute("X", pd.DataFrame({"Close": [1.0, 2.0]}), {}, None)
    assert r["ok"] is False and "error" in r


def test_bad_input_never_raises():
    from momentum import engine
    r = engine.compute("X", None, {}, None)
    assert r["ok"] is False
