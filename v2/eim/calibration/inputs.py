"""Insumos memoizados del agente de plan: structure/levels por vela, sobre ventana móvil.

Los reportes de `structure` y `levels` (y los niveles derivados) NO dependen de los parámetros
que se calibran (síntesis y plan), así que se calculan una sola vez por vela y se reutilizan en
todos los trials. Cada insumo de la vela `j` usa solo `candles[j-lookback+1 .. j]` (sin futuro).

Diferencia declarada frente al agente en vivo: allí la ventana de los insumos reproducidos
empieza en el inicio del snapshot de la decisión; aquí es una ventana móvil de `lookback` velas
que termina en `j`. Se mide la concordancia en el informe (`fidelity`).
"""

from __future__ import annotations

import pickle
from pathlib import Path

from eim.agents.plan import PlanAgent
from eim.agents.plan.agent import RawInputs
from eim.core import Candle, MarketSnapshot


def _slim(rep):
    """Solo lo que usa la síntesis (sesgo, confianza, estado, id): el caché pesa poco."""
    return rep.model_copy(update={"overlays": [], "metrics": {}, "evidence": [], "warnings": []})


class InputCache:
    """Memo `t → RawInputs` calculado sobre `candles` completos con ventana `lookback`."""

    def __init__(self, candles: list[Candle], symbol: str, timeframe: str,
                 lookback: int = 500) -> None:
        self.candles = candles
        self.symbol, self.timeframe, self.lookback = symbol, timeframe, lookback
        self._idx = {c.t: i for i, c in enumerate(candles)}
        self._step = candles[1].t - candles[0].t if len(candles) > 1 else 0
        self._memo: dict[int, RawInputs | None] = {}
        self._agent = PlanAgent()
        self.misses = 0

    def compute(self, j: int) -> RawInputs | None:
        """Insumos de la vela `j` (índice global), calculados si faltan."""
        t = self.candles[j].t
        if t not in self._memo:
            self.misses += 1
            cs = self.candles[max(0, j + 1 - self.lookback):j + 1]
            snap = MarketSnapshot(symbol=self.symbol, timeframe=self.timeframe, candles=cs,
                                  asof=t + self._step)
            raw = self._agent.raw_inputs(snap, cs[-1].c, t)
            self._memo[t] = None if raw is None else ([_slim(r) for r in raw[0]], raw[1], raw[2])
        return self._memo[t]

    def __call__(self, snap: MarketSnapshot, close: float, t: int) -> RawInputs | None:
        """Firma `RawFn` de `PlanAgent`: busca la vela por su tiempo en la serie global."""
        j = self._idx.get(t)
        if j is None:  # vela ajena a la serie: se calcula sobre el propio snapshot
            return PlanAgent().raw_inputs(snap, close, t)
        return self.compute(j)

    def warm(self, start: int, end: int, every: int = 1) -> None:
        """Precalcula las velas `start..end-1` alineadas a múltiplos de `every`."""
        for j in range(start - start % every + (every if start % every else 0), end, every):
            self.compute(j)

    def save(self, path: Path | str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self._memo, f)

    def load(self, path: Path | str) -> bool:
        """Carga un caché previo (archivo propio, generado por `save`); False si no existe."""
        p = Path(path)
        if not p.exists():
            return False
        with open(p, "rb") as f:
            self._memo.update(pickle.load(f))  # solo archivos propios (save)
        return True
