"""Assemble the single-stock research PDF (fpdf2 + embedded matplotlib charts)."""

from __future__ import annotations

import os
import tempfile

from fpdf import FPDF

from report import charts

NAVY = (23, 42, 77)
TEAL = (0, 128, 128)
GREY = (110, 110, 110)
LGREY = (238, 240, 244)
GREEN = (0, 120, 60)
RED = (170, 30, 30)
WHITE = (255, 255, 255)


def _san(x) -> str:
    if x is None:
        return "n/a"
    s = str(x)
    repl = [("₹", "Rs "), ("—", "-"), ("–", "-"), ("→", "->"), ("−", "-"), ("×", "x"),
            ("≈", "~"), ("≥", ">="), ("≤", "<="), ("’", "'"), ("“", '"'), ("”", '"'), ("•", "-")]
    for a, b in repl:
        s = s.replace(a, b)
    return "".join(ch for ch in s if ord(ch) < 0x250)


def _num(x, d=1, suf="", pre=""):
    try:
        return f"{pre}{float(x):,.{d}f}{suf}"
    except (TypeError, ValueError):
        return "n/a"


def _cr(x):
    """Format a large rupee figure into Cr."""
    try:
        return f"Rs {float(x)/1e7:,.0f} Cr"
    except (TypeError, ValueError):
        return "n/a"


def _empty_reason(g: str, mom: dict) -> str:
    """Why an A-F group has no signal, so a blank never looks like a bug."""
    if g in ("D", "E", "F") and not mom.get("nse_used"):
        return "NSE live feed unavailable this run"
    return {
        "A": "no strong results signal (profit / turnaround)",
        "B": "no accumulation footprint (circuit / volume / breakout / RS)",
        "C": "no forward-PE re-rating",
        "D": "no high-impact filing matched today",
        "E": ("not in F&O - no open interest" if not mom.get("in_fno")
              else "no OI buildup / spurt"),
        "F": "no SAST >5% stake or bulk/block BUY disclosed",
    }.get(g, "")


class PDF(FPDF):
    title = "Stock Research"

    def header(self):
        if self.page_no() == 1:
            return
        self.set_fill_color(*NAVY)
        self.rect(0, 0, self.w, 9, "F")
        self.set_xy(8, 2.2); self.set_font("Helvetica", "B", 8); self.set_text_color(*WHITE)
        self.cell(0, 4.5, _san(self.title))
        self.set_text_color(0, 0, 0); self.set_y(12)

    def footer(self):
        self.set_y(-8); self.set_font("Helvetica", "", 6.5); self.set_text_color(*GREY)
        self.cell(0, 4, f"Page {self.page_no()} - Educational quant snapshot, not SEBI-registered advice; verify live",
                  align="C")
        self.set_text_color(0, 0, 0)


def build(result: dict, out_path: str) -> str:
    snap = result["snapshot"]
    tech = result["technicals"]
    forensic = result["forensic"]
    quant = result["quant"]
    val_analyst = result["analyst"]
    verdict = result["verdict"]
    fin = result["financials_table"]
    mom = result.get("momentum")
    sym = result["symbol"]
    name = snap.get("name") or sym

    pdf = PDF("P", "mm", "A4")
    pdf.title = f"{name} ({sym}) - Research Snapshot"
    pdf.set_auto_page_break(True, margin=12)
    EPW = pdf.w - 2 * pdf.l_margin

    def sec(t):
        pdf.ln(1); pdf.set_x(pdf.l_margin); pdf.set_font("Helvetica", "B", 10); pdf.set_text_color(*TEAL)
        pdf.multi_cell(EPW, 5, _san(t)); pdf.set_text_color(0, 0, 0)

    def kv(pairs, ncol=2):
        pdf.set_font("Helvetica", "", 8.4); w = EPW / ncol
        for i in range(0, len(pairs), ncol):
            pdf.set_x(pdf.l_margin)
            for k, v in pairs[i:i + ncol]:
                pdf.set_font("Helvetica", "B", 8.4); pdf.cell(34, 4.6, _san(k))
                pdf.set_font("Helvetica", "", 8.4); pdf.cell(w - 34, 4.6, _san(v))
            pdf.ln(4.6)

    def para(t, size=8.2, style=""):
        pdf.set_x(pdf.l_margin); pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(EPW, 4.2, _san(t))

    # ---- Cover ----
    pdf.add_page()
    pdf.set_fill_color(*NAVY); pdf.rect(0, 0, pdf.w, 46, "F")
    pdf.set_xy(0, 14); pdf.set_font("Helvetica", "B", 20); pdf.set_text_color(*WHITE)
    pdf.cell(0, 10, _san(name), align="C", ln=1)
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 7, _san(f"{sym}  |  NSE  |  as of {result['as_of']}"), align="C")
    pdf.set_text_color(0, 0, 0); pdf.set_y(52)
    para(f"{snap.get('sector') or 'n/a'} / {snap.get('industry') or 'n/a'}", 10, "B")
    pdf.ln(2)

    # Verdict box
    pdf.set_fill_color(*LGREY); pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "B", 11)
    pdf.multi_cell(EPW, 6, _san(f"Quant lean: {verdict['lean']}  (score {verdict['score']})"), fill=True)
    para("Why: " + ", ".join(verdict["reasons"][:8]), 8)
    z = verdict["zones"]
    para(f"Buy zone {z['buy_zone']}  |  CMP {z['cmp']}  |  Upside {z['upside_zone']}  |  Invalidation {z['invalidation']}", 8, "B")

    # ---- 1. Snapshot ----
    sec("1. Snapshot")
    kv([
        ("Price", _num(snap.get("price"), 1, pre="Rs ")),
        ("Market cap", _cr(snap.get("market_cap"))),
        ("PE (TTM)", _num(snap.get("pe_trailing"))),
        ("PE (fwd)", _num(snap.get("pe_forward"))),
        ("P/B", _num(snap.get("pb"))),
        ("EV/EBITDA", _num(snap.get("ev_ebitda"))),
        ("Div yield", _num(snap.get("div_yield"), 2, "%") if snap.get("div_yield") else "n/a"),
        ("ROE", _num((snap.get("roe") or 0) * 100, 1, "%") if snap.get("roe") else "n/a"),
        ("52W high", _num(snap.get("high_52w"), 1)),
        ("52W low", _num(snap.get("low_52w"), 1)),
        ("Beta", _num(snap.get("beta"), 2)),
        ("Insiders/Instit.", f"{_num((snap.get('held_insiders') or 0)*100,1,'%')} / {_num((snap.get('held_institutions') or 0)*100,1,'%')}"),
    ])

    # Price chart
    tmp = tempfile.mkdtemp()
    try:
        p1 = charts.price_chart(result["price"], tech, os.path.join(tmp, "price.png"))
        pdf.image(p1, x=pdf.l_margin, w=EPW)
    except Exception:  # noqa: BLE001
        para("(price chart unavailable)", 7, "I")

    # ---- 2. 5Y financials ----
    sec("2. Financials (annual, latest first)")
    if fin:
        pdf.set_font("Helvetica", "B", 7.6); pdf.set_x(pdf.l_margin)
        cols = ["Metric"] + fin["years"]
        cw = EPW / len(cols)
        for cval in cols:
            pdf.cell(cw, 4.4, _san(cval), border=1, align="C")
        pdf.ln(4.4)
        pdf.set_font("Helvetica", "", 7.6)
        for row in fin["rows"]:
            pdf.set_x(pdf.l_margin)
            for j, cell in enumerate(row):
                pdf.cell(cw, 4.4, _san(cell), border=1, align="L" if j == 0 else "R")
            pdf.ln(4.4)
    else:
        para("Financial statements unavailable from source (n/a).", 8, "I")

    # ---- 3. Cash-flow quality & forensic ----
    sec("3. Cash-flow quality & forensic scores")
    kv([
        ("CFO / PAT", _num(forensic.get("cfo_pat"), 2)),
        ("Sloan accruals", _num(forensic.get("sloan_accruals"), 3)),
        ("Altman Z", f"{_num(forensic.get('altman_z'),2)} ({forensic.get('altman_z_zone') or 'n/a'})"),
        ("Piotroski (partial)", f"{forensic.get('piotroski_partial')}/{forensic.get('piotroski_checks')}"),
        ("Debt / Equity", _num(forensic.get("debt_to_equity"), 2)),
        ("Interest coverage", _num(forensic.get("interest_coverage"), 1, "x")),
    ])
    para("Beneish M-Score: n/a (needs full statement inputs). Forensic values are approximations from public statements.", 7, "I")

    # ---- 4. Quant factors ----
    sec("4. Quant factors")
    kv([
        ("12-1 momentum", _num(quant.get("mom_12_1_pct"), 1, "%")),
        ("RS vs Nifty (1Y)", f"{_num(quant.get('rs_vs_nifty_pct'),1,'%')} ({quant.get('rs_state') or 'n/a'})"),
        ("1M / 3M return", f"{_num(quant.get('ret_1m_pct'),1,'%')} / {_num(quant.get('ret_3m_pct'),1,'%')}"),
        ("6M / 1Y return", f"{_num(quant.get('ret_6m_pct'),1,'%')} / {_num(quant.get('ret_1y_pct'),1,'%')}"),
        ("5Y CAGR", _num(quant.get("cagr_pct"), 1, "%")),
        ("Max drawdown", _num(quant.get("max_drawdown_pct"), 1, "%")),
    ])

    # ---- 5. Technicals ----
    sec("5. Technicals")
    kv([
        ("Last close", _num(tech.get("last_close"), 1)),
        ("50 / 200 DMA", f"{_num(tech.get('sma50'),1)} / {_num(tech.get('sma200'),1)}"),
        ("vs 50 / 200 DMA", f"{_num(tech.get('px_vs_50dma_pct'),1,'%')} / {_num(tech.get('px_vs_200dma_pct'),1,'%')}"),
        ("MA cross", tech.get("ma_cross") or "n/a"),
        ("RSI(14)", _num(tech.get("rsi14"), 1)),
        ("MACD", f"{_num(tech.get('macd'),2)} ({tech.get('macd_state')})"),
        ("ADX(14)", f"{_num(tech.get('adx14'),1)} ({tech.get('di_state') or ''})"),
        ("Stochastic K/D", f"{_num(tech.get('stoch_k'),1)} / {_num(tech.get('stoch_d'),1)}"),
        ("Bollinger %B", _num(tech.get("boll_pctB"), 1, "%")),
        ("ATR(14)", f"{_num(tech.get('atr14'),1)} ({_num(tech.get('atr_pct'),1,'%')})"),
        ("Volume vs 20d", _num(tech.get("vol_vs_avg_pct"), 0, "%")),
        ("52W position", _num(tech.get("pos_52w_pct"), 0, "%")),
    ])
    try:
        p2 = charts.rsi_macd_chart(result["price"], os.path.join(tmp, "ind.png"))
        pdf.image(p2, x=pdf.l_margin, w=EPW)
    except Exception:  # noqa: BLE001
        pass

    # ---- 6. Support / Resistance ----
    sec("6. Support / Resistance")
    sr = tech.get("support_resistance", {})
    kv([
        ("Pivot", _num(sr.get("pivot"), 1)),
        ("Nearest support", _num(sr.get("nearest_support"), 1)),
        ("R1 / R2 / R3", f"{_num(sr.get('R1'),1)} / {_num(sr.get('R2'),1)} / {_num(sr.get('R3'),1)}"),
        ("S1 / S2 / S3", f"{_num(sr.get('S1'),1)} / {_num(sr.get('S2'),1)} / {_num(sr.get('S3'),1)}"),
        ("Nearest resistance", _num(sr.get("nearest_resistance"), 1)),
        ("Swing hi / lo (60d)", f"{_num(sr.get('swing_high_60d'),1)} / {_num(sr.get('swing_low_60d'),1)}"),
    ])

    # ---- 7. Analyst ----
    sec("7. Analyst view")
    kv([
        ("Recommendation", val_analyst.get("recommendation") or "n/a"),
        ("# analysts", _num(val_analyst.get("num_analysts"), 0)),
        ("Target mean", _num(val_analyst.get("target_mean"), 1)),
        ("Target low / high", f"{_num(val_analyst.get('target_low'),1)} / {_num(val_analyst.get('target_high'),1)}"),
    ])

    # ---- 8. Not covered ----
    sec("8. Layers needing deep review (n/a here)")
    para("Deep dated-news timeline & sentiment arc, management concall tone/credibility, "
         "governance/promoter-pledge deep-dive, and the variant-view verdict require an "
         "analyst/LLM pass and are NOT in this automated quant snapshot.", 8)

    # ---- 9. Momentum footprints (A-F) ----
    sec("9. Momentum footprints (A-F)  -  why it may be moving")
    if not mom or not mom.get("ok"):
        para("Momentum footprints unavailable for this stock (n/a).", 8, "I")
    else:
        seg = f"  |  {mom['segment']}" if mom.get("segment") else ""
        para(f"Signal: {mom.get('tier','')} - {mom.get('scenario','')}   |   "
             f"score {mom.get('score',0)}   |   {mom.get('n_signals',0)} signals{seg}", 9.5, "B")
        pos = mom.get("pos_52w")
        para(f"CMP Rs {_num(mom.get('price'), 1)}  ({_num(mom.get('day_pct'), 1, '%')} today)   |   "
             f"52W Rs {_num(mom.get('w52_low'), 0)} - {_num(mom.get('w52_high'), 0)}"
             + (f"   (position {pos:.0f}%)" if pos is not None else ""), 8)
        cov = mom.get("coverage", {})
        para("A-F coverage:   " + "    ".join(f"{g} {'yes' if cov.get(g) else '-'}" for g in "ABCDEF"), 8, "B")
        gn = mom.get("group_names", {})
        groups = mom.get("groups", {})
        # Always show all six groups; an empty one prints its reason (never omitted,
        # so a blank never looks like a bug).
        for g in "ABCDEF":
            lines = groups.get(g) or []
            pdf.set_x(pdf.l_margin); pdf.set_font("Helvetica", "B", 8.2)
            pdf.multi_cell(EPW, 4.6, _san(f"{g}. {gn.get(g, '')}"))
            if lines:
                for ln in lines:
                    pdf.set_x(pdf.l_margin + 4); pdf.set_font("Helvetica", "", 8.2)
                    pdf.multi_cell(EPW - 4, 4.2, _san(f"- {ln}"))
            else:
                pdf.set_x(pdf.l_margin + 4); pdf.set_font("Helvetica", "I", 7.6)
                pdf.set_text_color(*GREY)
                pdf.multi_cell(EPW - 4, 4.2, _san(f"- none - {_empty_reason(g, mom)}"))
                pdf.set_text_color(0, 0, 0)
        if mom.get("verify"):
            pdf.ln(0.5); para("Verify next: " + "  ".join(mom["verify"]), 7.4, "I")
        if not mom.get("nse_used"):
            para("Note: NSE live feeds (D news / E open-interest / F stake+bulk) were unreachable "
                 "this run - those groups reflect no data, not necessarily no event.", 7, "I")
        para("Legend: A results  B accumulation  C valuation  D news  E derivatives/OI  F stake/bulk. "
             "E exists only for F&O stocks; F needs a filed disclosure.", 6.8, "I")
        para("Footprints, not advice - a move can be genuine news, an index event, or a pump.", 6.8, "I")

    pdf.output(out_path)
    return out_path
