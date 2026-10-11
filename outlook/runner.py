"""Parent side: run the child with a hard time limit and read back whatever it managed to write. Never raises."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .core import Outlook, from_json

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Result:
    outlook: Outlook | None
    note: str = ""


def enabled() -> bool:
    return os.environ.get("KRONOS_ENABLED", "1") != "0"


def run(symbol: str, timeout: float | None = None) -> Result:
    if not enabled():
        return Result(None, "switched off (KRONOS_ENABLED=0)")
    timeout = timeout or float(os.environ.get("KRONOS_TIMEOUT", "900"))
    out = Path(tempfile.mkdtemp()) / "outlook.json"
    deadline = time.time() + timeout - 20
    env = {k: v for k, v in os.environ.items() if "TOKEN" not in k and "SECRET" not in k}
    env.update(TOKENIZERS_PARALLELISM="false", PIP_DISABLE_PIP_VERSION_CHECK="1", HF_HUB_DISABLE_PROGRESS_BARS="1")
    note = ""
    try:
        r = subprocess.run([sys.executable, "-m", "outlook", symbol, str(out), str(deadline)], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=timeout)
        print((r.stdout or "").strip()[-200:])
        if r.returncode:
            note = "the Kronos step crashed: " + (r.stderr or "").strip().splitlines()[-1][:160] if (r.stderr or "").strip() else "the Kronos step crashed"
    except subprocess.TimeoutExpired:
        note = "the Kronos step took too long and was stopped"
    except OSError as exc:
        note = f"the Kronos step could not start ({exc})"
    try:
        o = from_json(json.loads(out.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError):
        return Result(None, note or "no result was produced")
    if note and o.status == "ok":
        note = ""
    if note and o.status != "ok":
        o = Outlook(**{**o.__dict__, "note": note})
    return Result(o, note)
