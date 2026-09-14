"""Sector-aware hedge-fund multi-factor valuation scorecard (the PDF's last section).

Self-contained: reuses the report's already-fetched data (info + computed snapshot /
forensic / quant / technicals) and only computes the few extra inputs it needs, so it
adds no second heavy fetch. Six factor families (Value / Quality / Growth / Safety /
Momentum / Payout) -> a 0-100 composite, sector-adapted, with outlier skip-rules,
value/quality gates, an investment archetype and a confidence read.

Educational only - not SEBI-registered advice.
"""

from __future__ import annotations

import re

# ----------------------------------------------------------------- sector config
SECTORS = {
    "bank":        dict(name="Bank", lens="P/B", q="roe", q_good=15, normal_pe=None, pe_like=False,
                        cfo_ok=False, bench="P/B ~1.8x",
                        note="Bank -> judge on P/B, ROA/ROE, GNPA/NNPA, NIM, CASA, CAR. P/E & CFO are not meaningful; asset quality pulled from Screener."),
    "nbfc":        dict(name="NBFC", lens="P/B", q="roe", q_good=15, normal_pe=None, pe_like=False,
                        cfo_ok=False, bench="P/B ~2.5x",
                        note="NBFC -> P/B + NIM/spread, GNPA, credit cost, ALM. CFO not meaningful."),
    "insurance":   dict(name="Insurance", lens="P/B", q="roe", q_good=15, normal_pe=None, pe_like=False,
                        cfo_ok=False, bench="P/EV ~2x",
                        note="Insurer -> use P/EV, VNB margin, persistency, solvency. P/B is a proxy only."),
    "capital_mkts":dict(name="Exchange/RTA/Broker", lens="P/E", q="roce", q_good=25, normal_pe=30, pe_like=True,
                        cfo_ok=True, bench="P/E ~35x",
                        note="Exchange/broker/RTA -> ADT/take-rate & market share. Beware F&O-regulation risk + peak-cycle earnings flattering the P/E."),
    "it":          dict(name="IT services", lens="P/E", q="roce", q_good=25, normal_pe=24, pe_like=True,
                        cfo_ok=True, bench="P/E ~26x",
                        note="IT -> deal TCV/book-to-bill, EBIT margin, attrition, constant-currency growth."),
    "pharma":      dict(name="Pharma", lens="P/E", q="roce", q_good=20, normal_pe=28, pe_like=True,
                        cfo_ok=True, bench="P/E ~30x",
                        note="Pharma -> US/domestic mix, ANDA pipeline, USFDA status, price erosion."),
    "fmcg":        dict(name="FMCG/Consumer", lens="P/E", q="roce", q_good=25, normal_pe=45, pe_like=True,
                        cfo_ok=True, bench="P/E ~48x",
                        note="FMCG -> VOLUME growth (not just value), gross margin, distribution. A high P/E is normal here."),
    "auto":        dict(name="Auto/Ancillary", lens="P/E", q="roce", q_good=18, normal_pe=20, pe_like=True,
                        cfo_ok=True, bench="P/E ~22x",
                        note="Auto -> volumes, EBITDA margin, the CV/PV cycle. CYCLICAL: a low P/E at the peak can be a trap."),
    "cyclical":    dict(name="Metals/Commodity/Cyclical", lens="P/B", q="roce", q_good=15, normal_pe=None, pe_like=False,
                        cfo_ok=True, bench="P/B ~1.8x",
                        note="CYCLICAL -> use EV/EBITDA & P/B, NOT P/E. A low P/E usually = PEAK earnings. Buy at trough (high P/E), sell at peak."),
    "defence":     dict(name="Defence/Capital goods", lens="P/E", q="roce", q_good=18, normal_pe=40, pe_like=True,
                        cfo_ok=True, bench="P/E ~55x",
                        note="Defence/capital-goods -> ORDER BOOK, book-to-bill, working-capital days matter most. A high P/E rides order-book hope."),
    "logistics":   dict(name="Logistics", lens="EV/Sales", q="roce", q_good=12, normal_pe=None, pe_like=False,
                        cfo_ok=True, bench="EV/Sales ~3x",
                        note="Logistics -> EV/Sales + contribution margin, network utilization, path to EBITDA."),
    "realty":      dict(name="Real estate", lens="P/B", q="roce", q_good=12, normal_pe=None, pe_like=False,
                        cfo_ok=True, bench="P/B ~3x",
                        note="Real estate -> pre-sales/bookings, collections, net debt, NAV. Use P/B/NAV, not P/E."),
    "chemical":    dict(name="Chemicals", lens="P/E", q="roce", q_good=18, normal_pe=28, pe_like=True,
                        cfo_ok=True, bench="P/E ~30x",
                        note="Chemicals -> spreads, capacity utilization, capex cycle, end-market mix."),
    "utility":     dict(name="Utility/Power", lens="P/E", q="roce", q_good=12, normal_pe=15, pe_like=True,
                        cfo_ok=True, bench="P/E ~15x",
                        note="Utility -> PLF, regulated RoE, receivable days (discom dues)."),
    "loss_making": dict(name="Pre-profit / loss-making", lens="EV/Sales", q="roce", q_good=10, normal_pe=None, pe_like=False,
                        cfo_ok=True, bench="EV/Sales ~4x",
                        note="Pre-profit -> P/E is meaningless. Judge EV/Sales, contribution margin/unit economics, cash runway."),
    "generic":     dict(name="General", lens="P/E", q="roce", q_good=20, normal_pe=30, pe_like=True,
                        cfo_ok=True, bench="P/E ~25x",
                        note="Judged on the standard P/E lens."),
}
_RTA = {"CAMS", "KFINTECH", "KFINTEC"}


def _classify(info, symbol, pe, net_income, eps):
    ind = (info.get("industry") or "").lower()
    sec = (info.get("sector") or "").lower()
    nm = (info.get("longName") or symbol or "").lower()
    text = f"{ind} {sec} {nm}"
    base = (symbol or "").split(".")[0].upper()
    loss = (pe is None) or (net_income is not None and net_income < 0) or (eps is not None and eps <= 0)
    if base in _RTA:                                   return "capital_mkts", loss
    if "bank" in text:                                 return "bank", loss
    if "insurance" in text:                            return "insurance", loss
    if any(k in text for k in ["stock exchange", "financial data", "capital market", "brokerage"]): return "capital_mkts", loss
    if any(k in text for k in ["asset management", "credit"]): return "nbfc", loss
    if any(k in text for k in ["aerospace", "defense", "defence"]): return "defence", loss
    if any(k in text for k in ["steel", "aluminum", "copper", "mining", "metal", "cement", "commodit"]): return "cyclical", loss
    if any(k in text for k in ["freight", "logistic", "courier", "trucking", "airlines", "marine"]): return "logistics", loss
    if any(k in text for k in ["software", "information technology", "it services", "internet", "communication equipment"]): return "it", loss
    if any(k in text for k in ["drug", "pharma", "biotech", "medical", "healthcare", "diagnostic"]): return "pharma", loss
    if any(k in text for k in ["auto", "vehicle", "tyre", "tire"]): return "auto", loss
    if any(k in text for k in ["food", "beverage", "household", "personal product", "tobacco", "staple", "consumer defensive", "packaged"]): return "fmcg", loss
    if any(k in text for k in ["real estate", "realty"]): return "realty", loss
    if "chemical" in text: return "chemical", loss
    if any(k in text for k in ["utilit", "power", "electric"]): return "utility", loss
    if "financial services" in sec: return "capital_mkts", loss
    return "generic", loss


# ----------------------------------------------------------------- Screener bank KPIs
def _screener_bank(symbol):
    """NIM/GNPA/NNPA/CASA/CRAR/ROE for banks (yfinance lacks these) - same data MC Pro shows."""
    try:
        import requests
    except Exception:  # noqa: BLE001
        return {}
    base = (symbol or "").split(".")[0].upper()
    hdr = {"User-Agent": "Mozilla/5.0 (educational stock research)"}
    for path in (f"https://www.screener.in/company/{base}/consolidated/",
                 f"https://www.screener.in/company/{base}/"):
        try:
            r = requests.get(path, headers=hdr, timeout=12)
            if r.status_code != 200:
                continue
            t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))

            def g(pat):
                m = re.search(pat, t, re.I)
                return float(m.group(1).replace(",", "")) if m else None

            def last_row(label):
                m = re.search(label + r"\s*%\s*((?:[\d.]+%?\s*){2,})", t, re.I)
                if m:
                    nums = re.findall(r"[\d.]+", m.group(1))
                    if nums:
                        return float(nums[-1])
                return None

            out = dict(
                nim=g(r"NIM\)?\s*:?\s*([\d.]+)\s*%"),
                gnpa=g(r"Gross NPA\s*:?\s*([\d.]+)\s*%") or last_row(r"Gross NPA"),
                nnpa=g(r"Net NPA\s*:?\s*([\d.]+)\s*%") or last_row(r"Net NPA"),
                casa=g(r"CASA Ratio\s*:?\s*([\d.]+)\s*%"),
                crar=g(r"(?:CRAR|Capital Adequacy Ratio)\)?\s*:?\s*([\d.]+)\s*%"),
                roe_scr=g(r"ROE\s*([\d.]+)\s*%"),
            )
            if any(out.get(k) is not None for k in ("gnpa", "nim", "casa")):
                return out
        except Exception:  # noqa: BLE001
            continue
    return {}


# ----------------------------------------------------------------- helpers
def _s_lo(x, good, bad):
    if x is None:
        return None
    if x <= good:
        return 1.0
    if x >= bad:
        return 0.0
    return (bad - x) / (bad - good)


def _s_hi(x, good, bad):
    if x is None:
        return None
    if x >= good:
        return 1.0
    if x <= bad:
        return 0.0
    return (x - bad) / (good - bad)


def _avg(xs):
    v = [s for s in xs if s is not None]
    return sum(v) / len(v) if v else None


def _row_vals(df, *names):
    if df is None or getattr(df, "empty", True):
        return []
    idx = {str(i).lower(): i for i in df.index}
    for n in names:
        for lo, orig in idx.items():
            if n.lower() in lo:
                out = []
                for col in df.columns:
                    try:
                        val = float(df.loc[orig, col])
                        out.append(val if val == val else None)
                    except (TypeError, ValueError):
                        out.append(None)
                return out
    return []


def _cagr(vals, years=3):
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return None
    newest = vals[0]
    k = min(years, len(vals) - 1)
    oldest = vals[k]
    if oldest is None or oldest <= 0 or newest <= 0:
        return None
    return (newest / oldest) ** (1 / k) - 1


def _M(label, val, score, fmt, good, ok, weak):
    if val is None or score is None:
        return {"sym": "?", "label": label, "value": "n/a", "note": ""}
    sym = "+" if score >= 0.66 else "~" if score >= 0.33 else "x"
    note = good if score >= 0.66 else ok if score >= 0.33 else weak
    return {"sym": sym, "label": label, "value": fmt(val), "note": note, "_s": score}


def _grade(c):
    if c is None:
        return "n/a"
    return "A" if c >= 72 else "B" if c >= 60 else "C" if c >= 48 else "D" if c >= 36 else "E"


def _verdict(c):
    if c is None:
        return "INSUFFICIENT DATA", "too many metrics missing"
    if c >= 68:
        return "BUY-WORTHY", "strong multi-factor profile at this price"
    if c >= 54:
        return "FAIR / WATCH", "decent profile; buy on dips/confirmation"
    if c >= 40:
        return "EXPENSIVE / MIXED - WATCH", "weak on value or quality; don't chase"
    return "AVOID / POOR", "fails on multiple factor families"


# ----------------------------------------------------------------- main
def compute(info, snap, fore, quant, tech, financials, balance_sheet):
    info = info or {}
    P = lambda x: f"{x:.1f}%"
    X = lambda x: f"{x:.1f}x"
    N = lambda x: f"{x:.2f}"

    # ---- gather metrics (reuse computed layers; compute the few extras) ----
    pe = snap.get("pe_trailing")
    pb = snap.get("pb")
    eve = snap.get("ev_ebitda")
    evs = info.get("enterpriseToRevenue")
    ni_vals = _row_vals(financials, "net income")
    rev_vals = _row_vals(financials, "total revenue", "revenue")
    net_income = ni_vals[0] if ni_vals else None
    eps = info.get("trailingEps")
    g_pat = _cagr(ni_vals)
    g_pat = g_pat * 100 if g_pat is not None else None
    g_rev = _cagr(rev_vals)
    g_rev = g_rev * 100 if g_rev is not None else None
    ey = (100 / pe) if (pe and pe > 0) else None
    peg = (pe / g_pat) if (pe and g_pat and g_pat > 0) else None
    mc = info.get("marketCap")
    fcf = info.get("freeCashflow")
    fcfy = (fcf / mc * 100) if (fcf and mc) else None
    # dividend yield - robust against yfinance fraction/percent ambiguity
    tady = info.get("trailingAnnualDividendYield")
    drate = info.get("dividendRate")
    price = snap.get("price")
    dy = (tady * 100) if tady else ((drate / price * 100) if (drate and price) else None)
    dyv = dy if dy else None
    roe = (snap.get("roe") or 0) * 100 if snap.get("roe") else None
    # ROCE from statements
    ebit = (_row_vals(financials, "ebit", "operating income") or [None])[0]
    ta = (_row_vals(balance_sheet, "total assets") or [None])[0]
    cl = (_row_vals(balance_sheet, "current liabilities") or [None])[0]
    roce = (ebit / (ta - cl) * 100) if (ebit and ta and cl and (ta - cl) > 0) else None
    # gross profitability
    gp = (_row_vals(financials, "gross profit") or [None])[0]
    if gp is None:
        cogs = (_row_vals(financials, "cost of revenue") or [None])[0]
        rev0 = rev_vals[0] if rev_vals else None
        gp = (rev0 - cogs) if (rev0 is not None and cogs is not None) else None
    gpa = (gp / ta) if (gp is not None and ta) else None
    opm = (info.get("operatingMargins") or 0) * 100 if info.get("operatingMargins") else None
    cfo_pat = fore.get("cfo_pat")
    acc = fore.get("sloan_accruals")
    z = fore.get("altman_z")
    td, cash, ebitda = info.get("totalDebt"), info.get("totalCash"), info.get("ebitda")
    nde = ((td - cash) / ebitda) if (td is not None and cash is not None and ebitda and ebitda > 0) else None
    ic = fore.get("interest_coverage")
    cr = info.get("currentRatio")
    mom = quant.get("mom_12_1_pct")
    rs = quant.get("rs_vs_nifty_pct")
    a200 = tech.get("px_vs_200dma_pct")

    sec_key, loss = _classify(info, snap.get("name"), pe, net_income, eps)
    if loss and sec_key not in ("bank", "nbfc", "insurance"):
        cfg = dict(SECTORS["loss_making"])
        cfg["note"] = f"{SECTORS['loss_making']['note']}  (Underlying sector: {SECTORS[sec_key]['name']}.)"
    else:
        cfg = SECTORS[sec_key]
    is_fin = cfg["q"] == "roe"

    bank = _screener_bank(snap.get("symbol") or info.get("symbol")) if is_fin else {}
    gnpa, nnpa, nim, casa, crar = (bank.get(k) for k in ("gnpa", "nnpa", "nim", "casa", "crar"))
    if roe is None and bank.get("roe_scr"):
        roe = bank["roe_scr"]

    years_data = len([v for v in ni_vals if v is not None])
    growth_ok = not (years_data < 3 or (g_pat is not None and g_pat < -40)) and not loss

    # ---- outlier flags ----
    flags = []
    if loss:
        flags.append(("LOSS-MAKING", "P/E meaningless -> judged on EV/Sales + cash runway"))
    if years_data < 3 and not is_fin:
        flags.append(("JUST-LISTED (<3y data)", "growth/history unreliable -> PEG & growth low-confidence"))
    if g_pat is not None and g_pat < -40 and (mc or 0) / 1e7 > 5000:
        flags.append(("POSSIBLE DEMERGER/RESTRUCTURING", "profit CAGR distorted -> growth metrics skipped"))
    if sec_key in ("cyclical", "auto") and pe and pe < 15:
        flags.append(("CYCLICAL @ POSSIBLE PEAK", "a low P/E here can be a trap -> use P/B & EV/EBITDA"))
    if nde is not None and nde > 4 and not is_fin:
        flags.append(("HIGH LEVERAGE", f"net debt/EBITDA {nde:.1f}x -> fragile in a downturn"))
    if acc is not None and acc > 0.10 and not is_fin:
        flags.append(("HIGH ACCRUALS", f"(NI-CFO)/assets {acc*100:.0f}% -> paper-profit / earnings-quality risk"))
    if z is not None and z < 1.8 and not is_fin:
        flags.append(("ALTMAN DISTRESS", f"Z {z} (<1.8) -> bankruptcy-zone; demand a margin of safety"))
    if pe and pe > 60 and g_pat is not None and g_pat > 0 and not loss:
        flags.append(("PRICED FOR PERFECTION", "very high P/E -> needs years of flawless growth; fragile to any miss"))

    # ---- factor families ----
    if is_fin:
        value = [_M("P/B", pb, _s_lo(pb, 1.0, 3.5), X, "cheap vs book", "fair vs book", "expensive vs book"),
                 _M("Earnings yield (1/PE)", ey, _s_hi(ey, 9, 3), P, "high yield = cheap", "moderate", "low yield = pricey")]
    elif loss:
        value = [_M("EV/Sales", evs, _s_lo(evs, 2, 12), X, "cheap on sales", "fair on sales", "expensive on sales")]
    elif sec_key in ("cyclical", "auto"):
        value = [_M("P/B", pb, _s_lo(pb, 1.2, 4), X, "cheap on book", "fair", "rich on book"),
                 _M("EV/EBITDA", eve, _s_lo(eve, 5, 16), X, "cheap (use this, not P/E)", "fair", "expensive"),
                 _M("FCF yield", fcfy, _s_hi(fcfy, 6, -4), P, "strong free cash", "modest", "weak/negative FCF")]
    else:
        value = [_M("Earnings yield (1/PE)", ey, _s_hi(ey, 7, 1.5), P, "cheap on earnings", "moderate", "low yield = expensive"),
                 _M("EV/EBITDA", eve, _s_lo(eve, 9, 28), X, "cheap on cash earnings", "fair", "expensive on EV/EBITDA"),
                 _M("P/B", pb, _s_lo(pb, 2.5, 14), X, "cheap on book", "fair", "rich (OK if asset-light / high-ROE)"),
                 _M("PEG", peg, _s_lo(peg, 1, 3), N, "cheap for its growth", "fair for growth", "expensive even vs growth"),
                 _M("FCF yield", fcfy, _s_hi(fcfy, 6, -3), P, "strong FCF yield", "modest", "low/negative FCF")]
    if is_fin:
        quality = [_M("ROE", roe, _s_hi(roe, 16, 8), P, "strong returns", "adequate", "low returns"),
                   _M("Gross NPA", gnpa, _s_lo(gnpa, 1.5, 6), P, "clean loan book", "some stress", "high bad loans"),
                   _M("Net NPA", nnpa, _s_lo(nnpa, 0.5, 2.5), P, "well provisioned", "some risk", "high net NPAs")]
    else:
        qg = cfg["q_good"]
        quality = [_M("ROCE / ROE", roce or roe, _s_hi(roce or roe, qg * 1.1, qg * 0.4), P, "elite returns on capital", "decent", "low returns on capital"),
                   _M("Gross profitability", gpa, _s_hi(gpa, 0.4, 0.05), N, "very productive assets", "ok", "low gross profitability"),
                   _M("Operating margin", opm, _s_hi(opm, 18, 2), P, "fat margins", "moderate", "thin margins"),
                   _M("CFO / PAT (cash)", cfo_pat, _s_hi(cfo_pat, 1.0, 0.3), N, "profits = real cash", "okay conversion", "weak - profit > cash"),
                   _M("Accruals", (acc * 100 if acc is not None else None), (_s_lo(acc, 0.03, 0.15) if acc is not None else None), P, "clean, cash-backed", "some accruals", "high accruals - paper-profit risk")]
    if growth_ok:
        growth = [_M("PAT CAGR (3y)", g_pat, _s_hi(g_pat, 25, 0), P, "fast profit growth", "moderate growth", "flat/declining profit"),
                  _M("Revenue CAGR (3y)", g_rev, _s_hi(g_rev, 18, 0), P, "strong topline", "moderate topline", "weak topline")]
    else:
        growth = [{"sym": "?", "label": "Growth", "value": "skipped", "note": "distorted by demerger/just-listed - growth NOT scored (outlier rule)"}]
    if is_fin:
        safety = [_M("CRAR (capital)", crar, _s_hi(crar, 16, 11), P, "well capitalised", "adequate", "thin capital"),
                  _M("Gross NPA", gnpa, _s_lo(gnpa, 1.5, 6), P, "clean book", "some stress", "high bad loans")]
    else:
        safety = [_M("Altman-Z (bankruptcy)", z, _s_hi(z, 3, 1.8), N, "safe zone", "grey zone", "distress zone"),
                  _M("Net debt / EBITDA", nde, _s_lo(nde, 1, 5), X, "low leverage", "moderate leverage", "high leverage"),
                  _M("Interest cover", ic, _s_hi(ic, 6, 1.5), X, "comfortable", "adequate", "weak - debt-servicing risk"),
                  _M("Current ratio", cr, _s_hi(cr, 1.5, 0.8), N, "liquid", "adequate", "tight liquidity")]
    momentum = [_M("12-1 momentum", mom, _s_hi(mom, 25, -25), P, "strong uptrend", "sideways", "downtrend"),
                _M("Rel. strength vs Nifty", rs, _s_hi(rs, 8, -20), P, "outperforming index", "in line", "lagging index"),
                _M("Distance above 200-DMA", a200, _s_lo(a200, 15, 110), P, "near trend (calm)", "extended", "parabolic / frothy")]
    payout = [_M("Dividend yield", dyv, _s_hi(dyv, 4, 0), P, "good income", "modest", "little / none"),
              _M("FCF yield", fcfy, _s_hi(fcfy, 7, -2), P, "strong cash-return capacity", "modest", "weak/negative FCF")]

    specs = [("Value", 24, value), ("Quality", 24, quality), ("Growth", 14, growth),
             ("Safety", 14, safety), ("Momentum", 12, momentum), ("Payout", 12, payout)]
    families = []
    for nm, w, rows in specs:
        sc = _avg([r.get("_s") for r in rows])
        families.append({"name": nm, "weight": w, "score": sc,
                         "points": (round(sc * w, 1) if sc is not None else None), "rows": rows})
    active = [(f["weight"], f["score"]) for f in families if f["score"] is not None]
    tw = sum(w for w, _ in active)
    comp = round(sum(w * s for w, s in active) / tw * 100, 1) if tw else None

    # ---- gates ----
    fam = {f["name"]: f["score"] for f in families}
    gate = ""
    if comp is not None:
        if fam.get("Value") is not None and fam["Value"] < 0.20 and comp > 58:
            comp, gate = 58.0, "  (value-gate: too expensive to rate buy)"
        elif fam.get("Quality") is not None and fam["Quality"] < 0.25 and comp > 58:
            comp, gate = 58.0, "  (quality-gate: value-trap risk)"
    hard = gate
    if any(f[0] in ("ALTMAN DISTRESS",) for f in flags):
        hard += "  (DISTRESS - treat score as a ceiling)"

    v, vwhy = _verdict(comp)
    scored = [f for f in families if f["score"] is not None]
    think = ""
    if scored:
        best = max(scored, key=lambda f: f["score"])
        worst = min(scored, key=lambda f: f["score"])
        think = f"strong {best['name'].lower()} ({best['score']*100:.0f}%), weakest {worst['name'].lower()} ({worst['score']*100:.0f}%)"

    # ---- archetype ----
    arche, anote = _archetype(pe, pb, g_pat, roce or roe, cfo_pat, dyv, peg, sec_key, loss, {f[0] for f in flags})
    n_scored = len(scored)
    conf = "HIGH" if n_scored >= 6 and not ({f[0] for f in flags} & {"JUST-LISTED (<3y data)", "POSSIBLE DEMERGER/RESTRUCTURING", "LOSS-MAKING"}) else "MEDIUM" if n_scored >= 4 else "LOW"

    return {
        "sector": cfg["name"], "lens": cfg["lens"], "sector_note": cfg["note"],
        "composite": comp, "grade": _grade(comp), "verdict": v, "verdict_why": vwhy,
        "gate": hard, "what_i_think": think, "archetype": arche, "archetype_note": anote,
        "confidence": conf, "families_scored": n_scored, "families": families,
        "bank_kpis": ({"NIM": nim, "GNPA": gnpa, "NNPA": nnpa, "CASA": casa, "CRAR": crar} if is_fin and (gnpa or nim) else None),
        "flags": flags,
    }


def _archetype(pe, pb, g, roce, cfo, dy, peg, sec_key, loss, fset):
    if loss or "POSSIBLE DEMERGER/RESTRUCTURING" in fset:
        return "Special situation", "story/turnaround bet - value on EV/Sales, runway & catalyst, NOT P/E"
    if sec_key in ("cyclical", "auto"):
        return "Cyclical", "ride the cycle; buy at trough (high P/E), sell at peak (low P/E)"
    if pe and pe < 12 and pb and pb < 1.5:
        return "Deep value", "cheap on assets/earnings - check it's not a value trap (why so cheap?)"
    if dy and dy >= 2.5 and pe and pe < 22:
        return "Dividend / income", "own for yield + stability; watch payout coverage"
    if roce and roce >= 20 and cfo and cfo >= 0.8 and g is not None and 8 <= g <= 28:
        return "Quality compounder", "great business - overpay only a little; let it compound"
    if peg and 0.7 <= peg <= 1.6 and g is not None and g >= 15:
        return "GARP (growth at reasonable price)", "the sweet spot - growth you're not overpaying for"
    if pe and pe > 50 and g is not None and g > 30:
        return "Hyper-growth (priced for perfection)", "market prices years ahead - only if growth is real, cash-backed & durable"
    if g is not None and g < 0 and not loss:
        return "Turnaround / de-rating", "earnings falling - needs a catalyst; cheap-for-a-reason risk"
    return "Core / blend", "no single dominant pattern - judge on the full scorecard"


_SYM = {"+": "\u2713", "~": "~", "x": "\u2717", "?": "?"}


def _short(lbl):
    return re.sub(r"\s*\(.*?\)", "", lbl or "")


def to_telegram(sc: dict, name: str, symbol: str) -> str:
    """Render the scorecard dict as a Telegram HTML message (monospace <pre> block so
    the columns line up, matching the on-screen scorecard)."""
    from html import escape
    if not sc or sc.get("error") or sc.get("composite") is None:
        why = (sc or {}).get("error") or "insufficient data (SME/just-listed names are often not on Yahoo)"
        return (f"\U0001f4ca <b>{escape(name)} ({escape(symbol)})</b>\n"
                f"Valuation scorecard unavailable - {escape(str(why))}.\nTry the exact NSE symbol.")

    comp = sc["composite"]
    L = [f"{name} ({symbol})  -  Valuation Scorecard",
         f"Sector: {sc.get('sector')}  |  Lens: {sc.get('lens')}",
         "",
         f"COMPOSITE {comp}/100   Grade {sc.get('grade')}   -> {sc.get('verdict')}"]
    if sc.get("gate"):
        L.append(f"          {sc['gate'].strip()}")
    if sc.get("what_i_think"):
        L.append(f"Read: {sc['what_i_think']}")
    L.append(f"Archetype: {sc.get('archetype')}")
    L.append(f"Confidence: {sc.get('confidence')} ({sc.get('families_scored')}/6 families)")

    fams = {f["name"]: f for f in sc.get("families", [])}

    def hd(f):
        pts = f"{f['points']:.1f}/{f['weight']}" if f["points"] is not None else f"n/a/{f['weight']}"
        scp = f"{f['score']*100:.0f}%" if f["score"] is not None else "skipped"
        return f"{f['name'].upper():<8}{pts:>8}  ({scp})"

    for nm in ("Value", "Quality"):
        f = fams.get(nm)
        if not f:
            continue
        L.append("")
        L.append(hd(f))
        for r in f["rows"]:
            L.append(f"  {_SYM.get(r.get('sym'), '?')} {_short(r['label']):<18}{r['value']:>8}  {r.get('note', '')}")
    for nm in ("Growth", "Safety", "Momentum", "Payout"):
        f = fams.get(nm)
        if not f:
            continue
        if f["score"] is None:
            note = (f["rows"][0].get("note") if f["rows"] else "") or ""
            L.append(hd(f) + (f"  {note}" if note and note != "skipped" else ""))
        else:
            bits = " \u00b7 ".join(f"{_SYM.get(r.get('sym'), '?')} {_short(r['label'])} {r['value']}" for r in f["rows"])
            L.append(hd(f))
            L.append(f"   {bits}")

    if sc.get("bank_kpis"):
        kp = "  ".join(f"{k} {v}%" for k, v in sc["bank_kpis"].items() if v is not None)
        L += ["", f"Bank KPIs: {kp}"]
    if sc.get("flags"):
        L.append("")
        for n, w in sc["flags"]:
            L.append(f"! {n}: {w}")

    body = escape("\n".join(L))
    return f"<pre>{body}</pre>\n<i>Educational, not advice. Verify on Screener/filings.</i>"
