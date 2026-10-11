"""The Kronos prediction for ONE stock: 5 days, 30 days and 6 months ahead, with the stock's own normal range beside it.

One Kronos run (as long as the longest horizon) feeds every row. A row is withheld when Kronos's answer is more than
Z_LIMIT times the stock's own normal move for that distance, and then every longer row is withheld too (same run).
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

IST = ZoneInfo("Asia/Kolkata")
HORIZONS = ((5, "5 days"), (21, "30 days"), (126, "6 months"))
LOOKBACK, MIN_BARS, MIN_VOL_BARS, VOL_WINDOW = 400, 120, 21, 60
BAND_Z, Z_LIMIT, JUMP_LIMIT = 1.2816, 3.0, 0.25
COLUMNS = ["open", "high", "low", "close", "volume"]


class EngineError(RuntimeError):
    """Kronos or its dependencies are not available."""


@dataclass(frozen=True)
class Config:
    model: str = "small"
    lookback: int = LOOKBACK
    n_paths: int = 16
    batch: int = 8
    budget_s: float = 150.0
    # Longest horizon Kronos is run for. The 126-step 6-month rollout costs 6x the 21-step one and is too slow on a free CI
    # runner (6-7 min measured); set KRONOS_MAX_SESSIONS=126 to run it anyway.
    max_sessions: int = int(os.environ.get("KRONOS_MAX_SESSIONS", "21"))
    seed: int = 7
    z_limit: float = Z_LIMIT


@dataclass(frozen=True)
class Step:
    label: str
    sessions: int
    day: date
    low: float
    high: float
    kronos: float | None = None
    note: str = ""
    skipped: bool = False  # Kronos was not run for this horizon (too slow here), only the normal range is shown

    def stretched(self) -> bool:
        return self.kronos is not None and not self.low <= self.kronos <= self.high


@dataclass(frozen=True)
class Outlook:
    symbol: str
    exchange: str
    asof: date
    last_close: float
    bars: int
    status: str  # ok | range_only | none
    cfg: Config = field(default_factory=Config)
    note: str = ""
    steps: tuple[Step, ...] = ()
    paths: int = 0


def pct(x: float) -> str:
    return "n/a" if x != x else f"{x * 100:+.1f}%"


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    """Lower-case OHLCV, tz-naive session dates, no NaN or non-positive prices, no phantom zero-volume holiday bars."""
    df = raw.rename(columns=str.lower)[COLUMNS].astype(float)
    index = pd.DatetimeIndex(df.index)
    df.index = (index.tz_localize(None) if index.tz is not None else index).normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index().dropna()
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    return df[~((df["volume"] <= 0) & (df["high"] == df["low"]))]


def complete_bars(df: pd.DataFrame, now: datetime | None = None) -> pd.DataFrame:
    """Drop today's bar while the NSE session is open (before 16:00 IST)."""
    now = now or datetime.now(IST)
    if len(df) and df.index[-1].date() == now.date() and (now.hour, now.minute) < (16, 0):
        return df.iloc[:-1]
    return df


def jump_issue(df: pd.DataFrame, lookback: int) -> str:
    """A one-day move beyond circuit limits is almost always an unadjusted split/bonus: Kronos would forecast a chart that never existed."""
    window = df.tail(lookback)
    moves = np.log(window["close"]).diff()
    worst = moves.abs().idxmax()
    if abs(moves[worst]) > JUMP_LIMIT:
        return f"the chart has a {np.expm1(moves[worst]):+.0%} one-day move on {worst.date()}, likely an unadjusted split or bonus"
    return "bad price bars" if (window["high"] < window["low"]).any() else ""


def future_days(last: pd.Timestamp, n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(pd.Timestamp(last) + pd.Timedelta(days=1), periods=n)


def draw_paths(engine, df: pd.DataFrame, cfg: Config, horizon: int, deadline: float | None):
    """Sample futures in small batches until n_paths or the time budget (or the parent's deadline) runs out."""
    t0, got, ctx = time.monotonic(), [], df.tail(cfg.lookback)
    limit = cfg.budget_s if deadline is None else min(cfg.budget_s, deadline - time.time())
    while sum(len(g) for g in got) < cfg.n_paths:
        spent = time.monotonic() - t0
        if got and spent / len(got) * (len(got) + 1) > limit:
            break
        block = engine.sample([ctx], horizon=horizon, n_paths=cfg.batch)[0]
        got.append(block[np.isfinite(block).all(axis=(1, 2))])
    return np.concatenate(got) if got else np.empty((0, horizon, 4))


def build(symbol: str, df: pd.DataFrame, engine, *, exchange: str = "NSE", cfg: Config | None = None,
          now: datetime | None = None, horizons=HORIZONS, checkpoint=None, deadline: float | None = None) -> Outlook:
    cfg = cfg or Config()
    horizons = tuple(sorted(horizons))
    df = complete_bars(df, now)
    if df.empty:
        return Outlook(symbol, exchange, date.today(), math.nan, 0, "none", cfg, "no completed daily bars")
    close, last = df["close"], float(df["close"].iloc[-1])
    base = dict(symbol=symbol, exchange=exchange, asof=df.index[-1].date(), last_close=last, bars=len(df), cfg=cfg)
    if len(df) < MIN_VOL_BARS:
        return Outlook(status="none", note=f"only {len(df)} daily bars of price history, too few to size a normal move", **base)
    bad = jump_issue(df, cfg.lookback)
    vol = float(np.log(close).diff().dropna().tail(VOL_WINDOW).std(ddof=1))
    if bad or not vol > 0:
        return Outlook(status="none", note=(bad + ", so no honest range can be drawn") if bad else "the price did not move recently", **base)
    longest = max(s for s, _ in horizons)
    run = [h for h in horizons if h[0] <= cfg.max_sessions] or horizons[:1]
    days = future_days(df.index[-1], longest)

    def step(label, sessions, **kw) -> Step:
        half = BAND_Z * vol * math.sqrt(sessions)
        return Step(label, sessions, days[sessions - 1].date(), max(last * (1 - half), 0.0), last * (1 + half), **kw)

    plain = tuple(step(label, s) for s, label in horizons)

    def range_only(note: str) -> Outlook:
        return Outlook(status="range_only", steps=plain, note=note, **base)

    if len(df) < MIN_BARS:
        return range_only(f"only {len(df)} daily bars of history (it needs at least {MIN_BARS})")
    if checkpoint:
        checkpoint(range_only("the Kronos run did not finish in time"))
    try:
        engine.load()
        paths = draw_paths(engine, df, cfg, max(s for s, _ in run), deadline)
    except EngineError as exc:
        return range_only(str(exc))
    if len(paths) < max(3, cfg.n_paths // 3):
        return range_only(f"only {len(paths)} usable futures fit in the time allowed")
    steps, broken = [], ""
    for s, label in horizons:
        if (s, label) not in run:
            steps.append(step(label, s, skipped=True, note="not run"))
            continue
        moves = paths[:, s - 1, 3] / last - 1
        median = float(np.median(moves))
        z = median / (vol * math.sqrt(s))
        if broken:
            steps.append(step(label, s, note=broken))
        elif abs(z) > cfg.z_limit:
            broken = "a shorter forecast from the same run was not believable"
            steps.append(step(label, s, note=f"it said {pct(median)} ({abs(z):.1f} times this stock's normal move over that time), which is not believable"))
        else:
            steps.append(step(label, s, kronos=last * (1 + median)))
    return Outlook(status="ok", steps=tuple(steps), paths=len(paths), **base)


def to_json(o: Outlook) -> dict:
    return dict(symbol=o.symbol, exchange=o.exchange, asof=o.asof.isoformat(), last_close=o.last_close, bars=o.bars, status=o.status,
                note=o.note, paths=o.paths, cfg=dict(model=o.cfg.model, lookback=o.cfg.lookback, seed=o.cfg.seed),
                steps=[dict(label=s.label, sessions=s.sessions, day=s.day.isoformat(), low=s.low, high=s.high, kronos=s.kronos, note=s.note, skipped=s.skipped)
                       for s in o.steps])


def from_json(d: dict) -> Outlook:
    cfg = Config(**d["cfg"])
    steps = tuple(Step(s["label"], s["sessions"], date.fromisoformat(s["day"]), s["low"], s["high"], s["kronos"], s["note"], s.get("skipped", False)) for s in d["steps"])
    return Outlook(d["symbol"], d["exchange"], date.fromisoformat(d["asof"]), d["last_close"], d["bars"], d["status"], cfg, d["note"], steps, d["paths"])
