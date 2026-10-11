"""Kronos runtime: install on demand (CI only), fetch the pinned upstream code, load the weights, draw sampled futures."""

from __future__ import annotations

import importlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .core import EngineError, future_days

KRONOS_REPO = "https://github.com/shiyu-coder/Kronos.git"
KRONOS_COMMIT = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"  # upstream master, MIT licence
MODELS = {"small": ("NeoQuasar/Kronos-small", "901c26c1332695a2a8f243eb2f37243a37bea320",
                    "NeoQuasar/Kronos-Tokenizer-base", "0e0117387f39004a9016484a186a908917e22426", 512)}
NEEDED = {"torch": "torch", "einops": "einops", "safetensors": "safetensors", "huggingface_hub": "huggingface_hub", "tqdm": "tqdm"}
KRONOS_DIR = Path(os.environ.get("KRONOS_DIR", Path(__file__).resolve().parent.parent / ".kronos" / "Kronos"))


def _run(cmd: list[str], timeout: int) -> None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise EngineError(f"{cmd[0]} step failed: {exc}") from exc
    if r.returncode:
        raise EngineError(f"{' '.join(cmd[:3])} failed: {(r.stderr or r.stdout).strip()[-200:]}")


def ensure_runtime() -> None:
    missing = [m for m in NEEDED if importlib.util.find_spec(m) is None]
    if missing:
        if os.environ.get("KRONOS_AUTOINSTALL") != "1":
            raise EngineError(f"Kronos is not installed here (missing {', '.join(missing)})")
        if "torch" in missing:
            _run([sys.executable, "-m", "pip", "install", "-q", "torch", "--index-url", "https://download.pytorch.org/whl/cpu"], 900)
        rest = [NEEDED[m] for m in missing if m != "torch"]
        if rest:
            _run([sys.executable, "-m", "pip", "install", "-q", *rest], 600)
        importlib.invalidate_caches()
        still = [m for m in NEEDED if importlib.util.find_spec(m) is None]
        if still:
            raise EngineError(f"could not install {', '.join(still)}")
    if (KRONOS_DIR / "model" / "kronos.py").exists():
        return
    if os.environ.get("KRONOS_AUTOINSTALL") != "1":
        raise EngineError(f"Kronos code not found at {KRONOS_DIR}")
    KRONOS_DIR.mkdir(parents=True, exist_ok=True)
    git = ["git", "-C", str(KRONOS_DIR)]
    if not (KRONOS_DIR / ".git").exists():
        _run(git + ["init", "-q"], 60)
        _run(git + ["remote", "add", "origin", KRONOS_REPO], 60)
    _run(git + ["fetch", "-q", "--depth", "1", "origin", KRONOS_COMMIT], 300)
    _run(git + ["checkout", "-q", KRONOS_COMMIT], 120)


class KronosEngine:
    def __init__(self, model: str = "small", seed: int = 7, device: str | None = None):
        self.model, self.seed, self.device, self._predictor = model, seed, device, None

    def load(self):
        if self._predictor is not None:
            return
        ensure_runtime()
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        sys.path.insert(0, str(KRONOS_DIR))
        try:
            import torch
            from model import Kronos, KronosPredictor, KronosTokenizer
            repo, rev, tok, tok_rev, ctx = MODELS[self.model]
            torch.manual_seed(self.seed)
            self._predictor = KronosPredictor(Kronos.from_pretrained(repo, revision=rev), KronosTokenizer.from_pretrained(tok, revision=tok_rev),
                                              device=self.device, max_context=ctx)
        except Exception as exc:  # noqa: BLE001 - import, download or load errors all mean "no Kronos this run"
            raise EngineError(f"Kronos could not be loaded ({type(exc).__name__}: {str(exc)[:120]})") from exc

    def sample(self, contexts, *, horizon: int, n_paths: int, temperature: float = 1.0, top_p: float = 0.9) -> list[np.ndarray]:
        """One array per context, shaped (n_paths, horizon, 4): open, high, low, close."""
        self.load()
        out = []
        for ctx in contexts:
            frames = [ctx[["open", "high", "low", "close", "volume"]].reset_index(drop=True)] * n_paths
            past = [pd.Series(ctx.index)] * n_paths
            future = [pd.Series(future_days(ctx.index[-1], horizon))] * n_paths
            try:
                res = self._predictor.predict_batch(df_list=frames, x_timestamp_list=past, y_timestamp_list=future, pred_len=horizon,
                                                    T=temperature, top_p=top_p, sample_count=1, verbose=False)
            except Exception as exc:  # noqa: BLE001
                raise EngineError(f"Kronos run failed ({type(exc).__name__}: {str(exc)[:120]})") from exc
            out.append(np.stack([p[["open", "high", "low", "close"]].to_numpy(dtype=float) for p in res]))
        return out
