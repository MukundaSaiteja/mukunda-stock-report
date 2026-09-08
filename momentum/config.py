"""Tunable thresholds for the momentum (A-F) engine. Env-overridable (UA_*).

Vendored from unusual-activity/config.py — kept in sync intentionally so the
PDF's momentum section uses the exact same rules as the Telegram digest.
"""

from __future__ import annotations

import os


def _f(name, default):
    return float(os.environ.get(name, default))


def _i(name, default):
    return int(os.environ.get(name, default))


# --- Noise filters ----------------------------------------------------------
MIN_MCAP_CR = _f("UA_MIN_MCAP_CR", 500)          # market cap floor (Rs crore)
MIN_TURNOVER_CR = _f("UA_MIN_TURNOVER_CR", 5)    # avg daily turnover floor (Rs crore)
MCAP_UNKNOWN_TURNOVER_CR = _f("UA_MCAP_UNKNOWN_TURNOVER_CR", 25)

# --- Group B: accumulation footprint ---------------------------------------
DELIV_PCT_MIN = _f("UA_DELIV_PCT_MIN", 60)       # delivery % absolute floor
DELIV_MULT = _f("UA_DELIV_MULT", 1.5)            # delivery vs its 20d average
VOL_MULT = _f("UA_VOL_MULT", 3.0)               # volume vs 20d average
TURNOVER_MULT = _f("UA_TURNOVER_MULT", 3.0)      # turnover vs 20d average
CIRCUIT_STREAK_STRONG = _i("UA_CIRCUIT_STREAK", 2)  # consecutive upper circuits = strong
BIG_MOVE_PCT = _f("UA_BIG_MOVE_PCT", 5.0)        # single-day up move to note

# --- Group A: results ------------------------------------------------------
PROFIT_EXCEPTIONAL = _f("UA_PROFIT_EXC", 150)    # YoY profit growth % (headline)
PROFIT_STRONG = _f("UA_PROFIT_STRONG", 50)       # YoY profit growth % (secondary)
PROFIT_FLOOR_CR = _f("UA_PROFIT_FLOOR_CR", 10)   # min latest-Q net profit (Rs crore)
REVENUE_CONFIRM = _f("UA_REV_CONFIRM", 15)       # min YoY revenue growth % to confirm

# --- Group E: derivatives --------------------------------------------------
OI_SPURT_PCT = _f("UA_OI_SPURT", 30)             # change in OI vs avg to flag

# --- Averages / history ----------------------------------------------------
AVG_WINDOW = _i("UA_AVG_WINDOW", 20)             # sessions for averages
HISTORY_DAYS = _i("UA_HISTORY_DAYS", 25)         # price sessions to analyse

# --- Surfacing -------------------------------------------------------------
MIN_SIGNALS = _i("UA_MIN_SIGNALS", 2)            # min signals to call it "surfaced"
