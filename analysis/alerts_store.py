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

ALERTS_FILE = Path(os.environ.get("ALERTS_FILE", "data/alerts.json"))
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


def _cooldown_elapsed(alert: Alert) -> bool:
    if not alert.last_fired:
        return True
    try:
        last = datetime.fromisoformat(alert.last_fired)
    except ValueError:
        return True
    return (_now() - last).total_seconds() >= COOLDOWN_HOURS * 3600


def evaluate(alert: Alert, price: float) -> bool:
    """Return True if this alert should FIRE now (crossed + armed/cooldown ok).

    Mutates armed/last_fired on fire so it goes quiet for the cooldown, then
    re-arms automatically once the cooldown passes.
    """
    if not _crossed(alert, price):
        # Re-arm when price moves back to the safe side (so it can fire again later).
        if not alert.armed and _cooldown_elapsed(alert):
            alert.armed = True
        return False
    if not alert.armed:
        return False
    # Fire once, then disarm + stamp time (cooldown).
    alert.armed = False
    alert.last_fired = _now().isoformat()
    return True
