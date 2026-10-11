"""Offline tests for the Kronos prediction section: guards, withholding, failure paths, PDF text. No torch, no network."""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from outlook import core, runner, text
from outlook.core import Config, EngineError

EVENING = datetime(2026, 10, 10, 20, 0, tzinfo=core.IST)


def prices(n=300, seed=1, start=100.0):
    rng = np.random.default_rng(seed)
    close = start * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    idx = pd.bdate_range(end="2026-10-09", periods=n)
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close, "volume": 1e5}, index=idx)


class Scripted:
    """One path whose close is fixed (as a move from the last close) on given days, straight lines between."""

    def __init__(self, anchors):
        self.anchors, self.calls = anchors, 0

    def load(self):
        pass

    def sample(self, contexts, *, horizon, n_paths, **kw):
        self.calls += 1
        last = float(contexts[0]["close"].iloc[-1])
        days = [0] + sorted(self.anchors)
        closes = last * (1 + np.interp(np.arange(1, horizon + 1), days, [0.0] + [self.anchors[d] for d in sorted(self.anchors)]))
        path = np.stack([closes, closes, closes, closes], axis=1)
        return [np.repeat(path[None], n_paths, axis=0)]


def build(engine, df=None, **kw):
    return core.build("AAA", prices() if df is None else df, engine, cfg=Config(n_paths=16, batch=8), now=EVENING, **kw)


def test_default_runs_kronos_to_30_days_only_and_asks_for_21_steps():
    eng = Scripted({5: 0.01, 21: 0.02, 126: 0.04}); seen = []
    orig = eng.sample
    eng.sample = lambda c, *, horizon, **kw: (seen.append(horizon), orig(c, horizon=horizon, **kw))[1]
    o = build(eng)
    assert set(seen) == {21} and [s.kronos is not None for s in o.steps] == [True, True, False] and o.steps[2].skipped
    assert [r[2] for r in text.table_rows(o)][1:] == [text.rs(o.steps[0].kronos), text.rs(o.steps[1].kronos), "not run"]
    assert "Kronos was not run for 6 months" in " ".join(text.notes(o))


def test_plausible_run_shows_all_three_rows_with_a_range():
    o = core.build("AAA", prices(), Scripted({5: 0.01, 21: 0.02, 126: 0.04}), cfg=Config(n_paths=16, batch=8, max_sessions=126), now=EVENING)
    assert o.status == "ok" and o.paths == 16 and all(s.kronos for s in o.steps)
    assert [s.sessions for s in o.steps] == [5, 21, 126] and all(s.low < o.last_close < s.high for s in o.steps)


def test_broken_first_week_withholds_every_longer_row():
    o = build(Scripted({5: -0.77, 21: -0.2, 126: -0.05}))
    assert [s.kronos for s in o.steps] == [None] * 3 and o.steps[2].skipped and "not believable" in o.steps[0].note
    line = next(n for n in text.notes(o) if n.startswith("Kronos not shown"))
    assert line.startswith("Kronos not shown for 5 days") and "The longer forecast (30 days) is not shown either" in line


def test_a_good_week_does_not_save_a_broken_month():
    o = core.build("AAA", prices(), Scripted({5: 0.01, 21: 0.7, 126: 0.02}), cfg=Config(n_paths=16, batch=8, max_sessions=126), now=EVENING)
    assert o.steps[0].kronos is not None and o.steps[1].kronos is None and o.steps[2].kronos is None


def test_engine_failure_gives_range_only_not_an_exception():
    class Broken(Scripted):
        def load(self):
            raise EngineError("Kronos is not installed here (missing torch)")

    o = build(Broken({}))
    assert o.status == "range_only" and len(o.steps) == 3 and all(s.kronos is None for s in o.steps)
    assert "not installed" in text.notes(o)[0]


def test_checkpoint_is_written_before_kronos_runs():
    seen = []
    build(Scripted({5: 0.0}), checkpoint=lambda o: seen.append(o.status))
    assert seen == ["range_only"]


def test_unadjusted_split_flat_and_short_charts_get_no_kronos():
    df = prices()
    df.iloc[-100:, :4] *= 0.2                                    # a 5:1 split Yahoo did not adjust
    assert build(Scripted({}), df).status == "none"
    flat = prices(); flat[["open", "high", "low", "close"]] = 50.0
    assert build(Scripted({}), flat).status == "none"
    assert build(Scripted({}), prices(60)).status == "range_only"   # enough for a range, too short for Kronos
    assert build(Scripted({}), prices(10)).status == "none"


def test_time_budget_stops_drawing_early_but_keeps_what_it_has():
    class Slow(Scripted):
        def sample(self, *a, **kw):
            import time
            time.sleep(0.05)
            return super().sample(*a, **kw)

    cfg = Config(n_paths=24, batch=8, budget_s=0.12)
    o = core.build("AAA", prices(), Slow({5: 0.0}), cfg=cfg, now=EVENING)
    assert o.status == "ok" and 8 <= o.paths < 24


def test_json_round_trip_and_evidence_text_has_no_invented_numbers():
    o = build(Scripted({5: 0.01, 21: 0.02, 126: 0.04}))
    back = core.from_json(core.to_json(o))
    assert core.to_json(back) == core.to_json(o) and back.steps == o.steps
    line = text.evidence_line(o)
    assert "50% at 5 days, 50% at 30 days and 42% at 6 months" in line and "813, 150 and 38" in line and "not advice" in line


def test_runner_switched_off_and_missing_result(monkeypatch):
    monkeypatch.setenv("KRONOS_ENABLED", "0")
    assert runner.run("AAA").outlook is None
    monkeypatch.setenv("KRONOS_ENABLED", "1")
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(runner.subprocess.TimeoutExpired("x", 1)))
    res = runner.run("AAA", timeout=1)
    assert res.outlook is None and "too long" in res.note


def test_pdf_section_renders_for_ok_and_for_unavailable(tmp_path):
    from fpdf import FPDF
    from report import kronos_section
    from report.pdf import GREY, LGREY, NAVY, TEAL, WHITE, _san

    for res in (runner.Result(build(Scripted({5: 0.01, 21: 0.02, 126: 0.04}))), runner.Result(None, "the Kronos step took too long")):
        pdf = FPDF("P", "mm", "A4"); pdf.add_page()
        kronos_section.draw(pdf, res, _san, (NAVY, GREY, LGREY, WHITE, TEAL))
        out = tmp_path / "k.pdf"; pdf.output(str(out))
        assert out.stat().st_size > 1000
