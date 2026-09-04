"""Snapshot + valuation from yfinance info (best-effort)."""

from __future__ import annotations


def _g(info: dict, *keys):
    for k in keys:
        v = info.get(k)
        if v not in (None, "", 0):
            return v
    return None


def snapshot(info: dict) -> dict:
    return {
        "name": _g(info, "longName", "shortName"),
        "sector": _g(info, "sector"),
        "industry": _g(info, "industry"),
        "price": _g(info, "currentPrice", "regularMarketPrice"),
        "market_cap": _g(info, "marketCap"),
        "pe_trailing": _g(info, "trailingPE"),
        "pe_forward": _g(info, "forwardPE"),
        "pb": _g(info, "priceToBook"),
        "ev_ebitda": _g(info, "enterpriseToEbitda"),
        "div_yield": _g(info, "dividendYield"),
        "roe": _g(info, "returnOnEquity"),
        "profit_margin": _g(info, "profitMargins"),
        "beta": _g(info, "beta"),
        "high_52w": _g(info, "fiftyTwoWeekHigh"),
        "low_52w": _g(info, "fiftyTwoWeekLow"),
        "shares_out": _g(info, "sharesOutstanding"),
        "held_insiders": _g(info, "heldPercentInsiders"),
        "held_institutions": _g(info, "heldPercentInstitutions"),
    }


def analyst(info: dict) -> dict:
    return {
        "target_mean": _g(info, "targetMeanPrice"),
        "target_high": _g(info, "targetHighPrice"),
        "target_low": _g(info, "targetLowPrice"),
        "recommendation": _g(info, "recommendationKey"),
        "num_analysts": _g(info, "numberOfAnalystOpinions"),
    }
