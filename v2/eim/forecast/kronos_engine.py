"""Motor Kronos (opcional): modelo fundacional de velas, vía wrapper de muestreo múltiple.

Dependencias pesadas como extra (`pip install .[kronos]`: torch, einops, huggingface_hub,
safetensors). Solo repo oficial `shiyu-coder/Kronos` (paquete `model/`, sin `examples/` ni
`finetune/`) y pesos `NeoQuasar/Kronos-*` fijados por SHA (T04). Si no están instalados, el
motor se omite: `KronosEngine.available()` devuelve False y no se lanza error.
Su salida es un muestreo más: pasa por el mismo agrupamiento en escenarios (T17).
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from eim.core import MarketSnapshot
from eim.data.timeframes import tf_ms
from eim.forecast.engine import check_horizon

DEFAULT_MODEL = "NeoQuasar/Kronos-small"
DEFAULT_TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"
# Revisión (SHA) de los pesos: fijar tras auditar la descarga; None = rama por defecto.
PINNED_REVISION: str | None = None
MAX_SAMPLES = 100  # el plan pide 50–100 trayectorias


class KronosEngine:
    """Muestrea trayectorias con Kronos; `predictor` inyectable para tests sin red/torch."""

    name = "kronos"

    def __init__(
        self,
        *,
        temperature: float = 1.0,
        top_p: float = 0.9,
        context: int = 400,
        predictor: Callable[..., Any] | None = None,
    ) -> None:
        self.temperature, self.top_p, self.context = temperature, top_p, context
        self._predictor = predictor

    @staticmethod
    def available() -> bool:
        """True si las dependencias opcionales están instaladas."""
        mods = ("torch", "einops", "huggingface_hub", "model")
        return all(importlib.util.find_spec(m) for m in mods)

    def _load(self) -> Callable[..., Any]:
        if self._predictor is not None:
            return self._predictor
        if not self.available():
            raise RuntimeError("Kronos no instalado: pip install .[kronos]")
        from model import Kronos, KronosPredictor, KronosTokenizer  # pragma: no cover

        kw = {"revision": PINNED_REVISION} if PINNED_REVISION else {}  # pragma: no cover
        tok = KronosTokenizer.from_pretrained(DEFAULT_TOKENIZER, **kw)  # pragma: no cover
        mdl = Kronos.from_pretrained(DEFAULT_MODEL, **kw)  # pragma: no cover
        self._predictor = KronosPredictor(mdl, tok, max_context=512).predict  # pragma: no cover
        return self._predictor  # pragma: no cover

    def sample(self, snapshot: MarketSnapshot, horizon: int, n: int = 50) -> np.ndarray:
        check_horizon(horizon)
        n = min(n, MAX_SAMPLES)
        step = tf_ms(snapshot.timeframe)
        hist = snapshot.candles[-self.context :]
        df = pd.DataFrame(
            {
                "open": [c.o for c in hist],
                "high": [c.h for c in hist],
                "low": [c.l for c in hist],
                "close": [c.c for c in hist],
                "volume": [c.v for c in hist],
            }
        )
        last = hist[-1].t
        x_ts = pd.Series(pd.to_datetime([c.t for c in hist], unit="ms"))
        y_ts = pd.Series(pd.to_datetime([last + step * (i + 1) for i in range(horizon)], unit="ms"))
        predict = self._load()
        paths = np.empty((n, horizon, 4))
        for k in range(n):
            out = predict(
                df=df, x_timestamp=x_ts, y_timestamp=y_ts, pred_len=horizon,
                T=self.temperature, top_p=self.top_p, sample_count=1,
            )
            cols = ("open", "high", "low", "close")
            o, h, lo, c = (out[col].to_numpy(dtype=float) for col in cols)
            hi = np.maximum.reduce([h, o, c])
            lw = np.minimum.reduce([lo, o, c])
            paths[k] = np.stack([o, hi, lw, c], axis=1)
        return paths
