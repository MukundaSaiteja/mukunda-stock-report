"""Persistent price-alert store (a small JSON committed to the repo).

Each alert: symbol, direction (above/below), level, chat_id, one-shot + cooldown
state. The per-minute poller loads this, checks live prices, fires crossings, and
saves back. Committed by the workflow so it survives across stateless runs.

Schema (data/alerts.json):
{
  "alerts": [
    {"id":"RELIANCE-below-1250", "symbol":"RELIANCE", "direction":"below",
     "level":1250.0, "chat_id":"-100...", "note":"S1",
     "armed":true, "last_fired":null}
  ]
}
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ALERTS_FILE = Path(os.environ.get("ALERTS_FILE", "data/alerts.json"))
IST = ZoneInfo("Asia/Kolkata")
COOLDOWN_HOURS = float(os.environ.get("ALERT_COOLDOWN_HOURS", "6"))


@dataclass
class Alert:
    id: str
    symbol: str
    direction: str          # "above" | "below"
    level: float
    chat_id: str
    note: str = ""          # e.g. "S1", "R1", or "manual"
    armed: bool = True       # ready to fire (one-shot); re-arms after cooldown
    last_fired: str | None = None   # ISO timestamp of last firing


def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_id(symbol: str, direction: str, level: float) -> str:
    return f"{symbol.upper()}-{direction}-{level:g}"


def load(path: Path = ALERTS_FILE) -> list[Alert]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [Alert(**a) for a in raw.get("alerts", [])]
    except Exception:  # noqa: BLE001
        return []


def save(alerts: list[Alert], path: Path = ALERTS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"alerts": [asdict(a) for a in alerts]}, indent=2), encoding="utf-8")


def upsert(alerts: list[Alert], new: Alert) -> list[Alert]:
    """Add or replace an alert with the same id (re-arms it)."""
    out = [a for a in alerts if a.id != new.id]
    out.append(new)
    return out


def remove(alerts: list[Alert], alert_id: str) -> tuple[list[Alert], bool]:
    kept = [a for a in alerts if a.id != alert_id]
    return kept, len(kept) != len(alerts)


def remove_symbol(alerts: list[Alert], symbol: str) -> tuple[list[Alert], int]:
    sym = symbol.upper()
    kept = [a for a in alerts if a.symbol.upper() != sym]
    return kept, len(alerts) - len(kept)


def _crossed(alert: Alert, price: float) -> bool:
    if alert.direction == "above":
        return price >= alert.level
    return price <= alert.level


def _ist_date(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).astimezone(IST).strftime("%Y-%m-%d")
    except ValueError:
        return None


def evaluate(alert: Alert, price: float) -> bool:
    """Return True if this alert should FIRE now.

    Policy: fire at most ONCE PER IST DAY while the price is past the level. So a
    fresh crossing pings today; if it's still past the level tomorrow you get one
    more ping (a daily reminder), never a per-minute repeat. It also re-arms
    immediately if price returns to the safe side.
    """
    today = datetime.now(timezone.utc).astimezone(IST).strftime("%Y-%m-%d")

    if not _crossed(alert, price):
        # Safe side -> ready for the next crossing.
        alert.armed = True
        return False

    # Past the level. Fire if we haven't already fired today.
    if _ist_date(alert.last_fired) == today:
        return False
    alert.armed = False
    alert.last_fired = datetime.now(timezone.utc).isoformat()
    return True
