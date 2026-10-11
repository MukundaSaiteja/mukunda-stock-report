"""Quarterly results: latest declared quarter with QoQ (vs previous quarter) and YoY (vs same quarter last year) growth.

Source: Screener.in quarterly table (consolidated, else standalone), sales and net profit sharpened with Yahoo's unrounded
quarterly statement when the two agree. Best-effort: ``build`` never raises. Educational, not advice.
"""

from __future__ import annotations

import re
from datetime import date

MONTHS = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
LABELS = {"sales": ("sales", "revenue"), "op": ("operating profit", "financing profit"), "opm": ("opm", "financing margin"),
          "np": ("net profit",), "eps": ("eps",)}


def num(cell: str):
    c = re.sub(r"[,%\s]", "", cell or "")
    try:
        return float(c)
    except ValueError:
        return None


def parse_table(html: str) -> dict | None:
    m = re.search(r'<section id="quarters".*?</section>', html, re.S)
    if not m:
        return None
    periods, rows = [], {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), re.S):
        cells = [re.sub(r"<[^>]+>|&nbsp;", " ", c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        cells = [re.sub(r"\s+", " ", c).strip() for c in cells]
        if not cells:
            continue
        if not periods and all(re.fullmatch(r"[A-Za-z]{3} \d{4}", c) for c in cells[1:] if c) and len(cells) > 2:
            periods = [c for c in cells[1:] if c]
            continue
        head = re.sub(r"[+\s]+$", "", cells[0]).lower()
        for key, names in LABELS.items():
            if key not in rows and any(head.startswith(n) for n in names):
                rows[key] = [num(c) for c in cells[1:len(periods) + 1]]
    if not periods or "sales" not in rows or "np" not in rows:
        return None
    return dict(periods=periods, **rows)


def fetch_screener(symbol: str) -> tuple[dict | None, str]:
    try:
        import requests
    except Exception:  # noqa: BLE001
        return None, ""
    base = symbol.split(".")[0].upper()
    for suffix, basis in (("consolidated/", "consolidated"), ("", "standalone")):
        try:
            r = requests.get(f"https://www.screener.in/company/{base}/{suffix}", timeout=12,
                             headers={"User-Agent": "Mozilla/5.0 (educational stock research)"})
            t = parse_table(r.text) if r.status_code == 200 else None
        except Exception:  # noqa: BLE001
            t = None
        if t:
            return t, basis
    return None, ""


def _key(label: str) -> tuple[int, int]:
    mon, yr = label.split()
    return int(yr), MONTHS[mon]


def sharpen(table: dict, yf_q) -> dict:
    """Replace Screener's whole-crore rounding with Yahoo's figure for the same quarter when they agree within 8%."""
    if yf_q is None or getattr(yf_q, "empty", True):
        return table
    out = {k: (list(v) if isinstance(v, list) else v) for k, v in table.items()}
    for col in yf_q.columns:
        try:
            idx = [_key(p) for p in table["periods"]].index((col.year, col.month))
        except (ValueError, AttributeError):
            continue
        for key, name in (("sales", "Total Revenue"), ("np", "Net Income")):
            if name not in yf_q.index:
                continue
            y, s = yf_q.loc[name, col], table[key][idx]
            if y == y and s is not None and y > 0 and s > 0 and abs(y / 1e7 / s - 1) < 0.08:
                out[key][idx] = round(y / 1e7, 1)
    return out


def change(a, b):
    """% change a vs b, or a word when it is not a plain percentage (loss involved)."""
    if a is None or b is None:
        return None, "n/a"
    if b > 0:
        p = (a / b - 1) * 100
        return p, f"{p:+.1f}%"
    return None, "turned profit" if a > 0 and b <= 0 else "loss" if a <= 0 else "n/a"


def _quarter_end(label: str) -> date:
    y, m = _key(label)
    return date(y, m, {3: 31, 6: 30, 9: 30, 12: 31}.get(m, 28))


def build(symbol: str, yf_q=None, today: date | None = None, fetch=fetch_screener) -> dict:
    try:
        table, basis = fetch(symbol)
        if not table:
            return dict(ok=False, error="quarterly table not available for this stock")
        table = sharpen(table, yf_q)
        n, ps = len(table["periods"]), table["periods"]
        rows = []
        for i in range(n):
            s, np_, opm = table["sales"][i], table["np"][i], (table.get("opm") or [None] * n)[i]
            row = dict(label=ps[i], sales=s, np=np_, opm=opm)
            for name, vals in (("sales", table["sales"]), ("np", table["np"])):
                row[f"{name}_qoq_v"], row[f"{name}_qoq"] = change(vals[i], vals[i - 1] if i >= 1 else None)
                row[f"{name}_yoy_v"], row[f"{name}_yoy"] = change(vals[i], vals[i - 4] if i >= 4 else None)
            rows.append(row)
        last = rows[-1]
        yoys = [r["sales_yoy_v"] for r in rows[-4:] if r["sales_yoy_v"] is not None]
        ttm = prior = None
        if n >= 8 and all(v is not None for v in table["sales"][-8:]):
            ttm, prior = sum(table["sales"][-4:]), sum(table["sales"][-8:-4])
        sy, ny = last["sales_yoy_v"], last["np_yoy_v"]
        if sy is not None and ny is not None:
            verdict = ("Strong: sales and profit both growing fast year on year" if sy > 15 and ny > 15 else
                       "Healthy: sales and profit both up year on year" if sy > 0 and ny > 0 else
                       "Margin squeeze: sales up but profit down year on year" if sy > 0 else
                       "Weak: sales down year on year")
        else:
            verdict = "Not enough history for a year-on-year read"
        today = today or date.today()
        stale = ""
        if (today - _quarter_end(last["label"])).days > 135:
            stale = f"The data source may not have the newest quarter yet (latest shown: {last['label']}); check the company's results filing."
        headline = (f"Latest declared quarter {last['label']}: sales Rs {last['sales']:,.0f} Cr "
                    f"({last['sales_qoq']} vs previous quarter, {last['sales_yoy']} vs same quarter last year); "
                    f"net profit Rs {last['np']:,.1f} Cr ({last['np_qoq']} QoQ, {last['np_yoy']} YoY)."
                    if last["sales"] is not None and last["np"] is not None else f"Latest quarter {last['label']}.")
        trend = ("Sales growth YoY over the last quarters: " + ", ".join(f"{v:+.0f}%" for v in yoys) + "." if yoys else "")
        if ttm and prior:
            trend += f" Last 4 quarters' sales Rs {ttm:,.0f} Cr vs Rs {prior:,.0f} Cr the 4 before ({(ttm / prior - 1) * 100:+.0f}%)."
        return dict(ok=True, basis=basis, rows=rows[-5:][::-1], headline=headline, trend=trend.strip(), verdict=verdict, stale=stale)
    except Exception as exc:  # noqa: BLE001 - never break the report
        return dict(ok=False, error=str(exc)[:120])
