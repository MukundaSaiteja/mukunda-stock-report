"""Matplotlib charts saved as PNGs for embedding in the PDF."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

NAVY = "#172a4d"
TEAL = "#008080"
RED = "#aa1e1e"
GREEN = "#00783c"


def price_chart(price: pd.DataFrame, tech: dict, path: str) -> str:
    """1y price with 50/200-DMA and S/R levels drawn as horizontal lines."""
    df = price.tail(252)
    c = df["Close"]
    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=110)
    ax.plot(df.index, c, color=NAVY, lw=1.3, label="Close")
    ax.plot(df.index, c.rolling(50).mean(), color=TEAL, lw=1, label="50-DMA")
    if len(price) >= 200:
        ax.plot(df.index, price["Close"].rolling(200).mean().tail(252), color="#c08a00", lw=1, label="200-DMA")

    sr = tech.get("support_resistance", {})
    for key, col, ls in [("R1", RED, "--"), ("R2", RED, ":"), ("S1", GREEN, "--"), ("S2", GREEN, ":")]:
        lvl = sr.get(key)
        if lvl:
            ax.axhline(lvl, color=col, lw=0.8, ls=ls, alpha=0.7)
            ax.text(df.index[0], lvl, f" {key} {lvl:,.0f}", color=col, fontsize=7, va="bottom")

    ax.set_title("Price (1Y) with 50/200-DMA and Support/Resistance", fontsize=10, color=NAVY)
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(alpha=0.25)
    ax.tick_params(labelsize=7)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def rsi_macd_chart(price: pd.DataFrame, path: str) -> str:
    df = price.tail(180)
    c = df["Close"]
    d = c.diff()
    up = d.clip(lower=0).rolling(14).mean()
    dn = (-d.clip(upper=0)).rolling(14).mean()
    rsi = 100 - 100 / (1 + up / dn)
    e12, e26 = c.ewm(span=12).mean(), c.ewm(span=26).mean()
    macd = e12 - e26
    sig = macd.ewm(span=9).mean()

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 3.6), dpi=110, sharex=True)
    a1.plot(df.index, rsi, color=NAVY, lw=1)
    a1.axhline(70, color=RED, lw=0.7, ls="--"); a1.axhline(30, color=GREEN, lw=0.7, ls="--")
    a1.set_ylabel("RSI(14)", fontsize=7); a1.set_ylim(0, 100); a1.grid(alpha=0.25); a1.tick_params(labelsize=7)
    a2.plot(df.index, macd, color=TEAL, lw=1, label="MACD")
    a2.plot(df.index, sig, color=RED, lw=1, label="signal")
    a2.bar(df.index, macd - sig, color="#999", alpha=0.5, width=1)
    a2.set_ylabel("MACD", fontsize=7); a2.legend(fontsize=6); a2.grid(alpha=0.25); a2.tick_params(labelsize=7)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
