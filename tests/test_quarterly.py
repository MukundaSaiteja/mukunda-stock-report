"""Offline tests: quarterly results parsing, QoQ/YoY maths, loss handling and the staleness note."""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis import quarterly as q

PERIODS = ["Sep 2024", "Dec 2024", "Mar 2025", "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026"]


def html(rows, periods=PERIODS):
    head = "<tr><th></th>" + "".join(f"<th>{p}</th>" for p in periods) + "</tr>"
    body = "".join("<tr><td>" + k + "</td>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>" for k, vals in rows)
    return f'<section id="quarters"><table>{head}{body}</table></section>'


ROWS = [("Sales&nbsp;+", ["364", "347", "380", "412", "381", "448", "599", "550"]),
        ("Operating Profit", ["14", "16", "19", "19", "16", "24", "28", "22"]),
        ("OPM %", ["3.8%", "4.7%", "4.9%", "4.5%", "4.1%", "5%", "4.7%", "4.0%"]),
        ("Net Profit&nbsp;+", ["8", "11", "13", "12", "10", "15", "20", "17"])]


def test_parse_reads_periods_and_rows():
    t = q.parse_table(html(ROWS))
    assert t["periods"] == PERIODS and t["sales"][-1] == 550 and t["np"][-2] == 20 and t["opm"][0] == 3.8
    assert q.parse_table("<html>nothing</html>") is None


def test_bank_labels_are_understood():
    t = q.parse_table(html([("Revenue +", ["10"] * 8), ("Financing Profit", ["2"] * 8), ("Net Profit +", ["1"] * 8)]))
    assert t["sales"][0] == 10 and t["op"][0] == 2


def test_qoq_and_yoy_for_the_latest_quarter():
    res = q.build("X", today=date(2026, 10, 11), fetch=lambda s: (q.parse_table(html(ROWS)), "consolidated"))
    last = res["rows"][0]
    assert res["ok"] and last["label"] == "Jun 2026" and len(res["rows"]) == 5
    assert last["sales_qoq"] == "-8.2%" and last["sales_yoy"] == "+33.5%"          # 550 vs 599, 550 vs 412
    assert res["rows"][1]["sales_qoq"] == "+33.7%"                                  # Mar 2026 vs Dec 2025 (599 vs 448)
    assert res["verdict"].startswith("Strong") and "last 4 quarters" in res["trend"].lower()
    assert res["stale"] == ""


def test_loss_base_is_worded_not_faked_and_missing_history_is_na():
    rows = [("Sales", ["10"] * 8), ("Net Profit", ["-5", "-4", "-3", "-2", "1", "2", "3", "4"])]
    res = q.build("X", today=date(2026, 10, 11), fetch=lambda s: (q.parse_table(html(rows)), "standalone"))
    assert res["rows"][0]["np_yoy"] == "turned profit"
    short = q.parse_table(html([("Sales", ["10", "11"]), ("Net Profit", ["1", "2"])], PERIODS[:2]))
    assert q.build("X", fetch=lambda s: (short, "standalone"))["rows"][0]["sales_yoy"] == "n/a"


def test_stale_note_appears_when_a_newer_quarter_should_exist():
    res = q.build("X", today=date(2026, 12, 1), fetch=lambda s: (q.parse_table(html(ROWS)), "consolidated"))
    assert "newest quarter" in res["stale"]


def test_never_raises_and_yahoo_sharpens_rounded_profit():
    assert q.build("X", fetch=lambda s: (_ for _ in ()).throw(RuntimeError("down")))["ok"] is False
    import pandas as pd
    yf = pd.DataFrame({pd.Timestamp("2026-06-30"): [549.7e7, 17.1e7]}, index=["Total Revenue", "Net Income"])
    t = q.sharpen(q.parse_table(html(ROWS)), yf)
    assert t["sales"][-1] == 549.7 and t["np"][-1] == 17.1 and t["sales"][-2] == 599
