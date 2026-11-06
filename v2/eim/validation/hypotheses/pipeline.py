"""Corrida de T139: sombra de cada clave y puntuación con la puerta de T49 tal cual. Puro.

La puntuación es `gate.measure` + `gate.validate_all` sin cambiar nada. La lectura descriptiva solo
les pasa otras ventanas (`entry_versions.complement`), así que no hay una segunda definición de
«fuera de muestra». Todas las lecturas usan la misma familia de Holm, con todas las claves dentro,
tengan o no operaciones.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

import numpy as np

from eim.agents.regime.agent import RegimeAgent
from eim.core import Candle, MarketSnapshot
from eim.paper.engine import Path, run_shadow, simulate
from eim.paper.ideas import Idea
from eim.paper.params import ExecParams
from eim.validation.criteria import Criteria
from eim.validation.entry_versions import complement
from eim.validation.evidence import Trade, flip_idea, ref_price, select, trade_of
from eim.validation.gate import Verdict, measure, validate_all
from eim.validation.hypotheses.prereg import Reading
from eim.validation.lineage import Version, Window

REGIME_BARS = 500                # = `generate.AGENT_BARS`: las que ve el agente en los contextos


class RegimeLabels:
    """Etiqueta de régimen en la vela de decisión, con el agente de siempre y solo con el pasado.

    Se calcula solo para las operaciones que cerraron: cada llamada son unos 0,1 s, y V1 no necesita
    más. Cachea por instante, porque una operación y su réplica comparten decisión.
    """

    def __init__(self, candles: Sequence[Candle], tf: str, symbol: str, bar_ms: int) -> None:
        self.candles, self.tf, self.symbol, self.bar_ms = candles, tf, symbol, bar_ms
        self.close_t = np.array([c.t + bar_ms for c in candles], dtype=np.int64)
        self.agent = RegimeAgent()
        self.cache: dict[int, str | None] = {}

    def at(self, t: int) -> str | None:
        if t not in self.cache:
            self.cache[t] = self._label(t)
        return self.cache[t]

    def _label(self, t: int) -> str | None:
        k = int(np.searchsorted(self.close_t, t, "right"))       # velas cerradas en `t` o antes
        if k == 0:
            return None
        snap = MarketSnapshot(symbol=self.symbol, timeframe=self.tf, asof=t,
                              candles=list(self.candles[max(0, k - REGIME_BARS):k]))
        rep = self.agent.run(snap)
        return rep.metrics.get("regime") if rep.status == "ok" else None


def trades_of(ideas: Sequence[Idea], path: Path, ep: ExecParams,
              regime_at: Callable[[int], str | None]) -> list[Trade]:
    """La sombra de una clave: una idea viva a la vez, y el lado contrario de cada cerrada (V3)."""
    out = []
    for o in run_shadow(ideas, path, ep):
        if o.status != "CERRADA":
            continue
        flip = simulate(flip_idea(o.idea, ref_price(o, path)), path, ep)
        t = trade_of(o, flip)
        if t is not None:
            out.append(replace(t, regime=regime_at(o.idea.t) or "sin dato"))
    return out


def family_of(prior: Mapping[str, float | None], symbol: str, versions: Iterable[Version]
              ) -> dict[str, float | None]:
    """La familia completa: lo ya registrado + todas las claves de T139, midan algo o no."""
    out = dict(prior)
    for v in versions:
        out.setdefault(f"{symbol}|{v.label}", None)
    return out


def windows_of(r: Reading, v: Version) -> tuple[Window, ...]:
    """Lo que una lectura excluye: en la oficial, la ventana de ajuste; en otra, lo de fuera."""
    return v.windows if r.verdict else complement(r.ranges)


def score_reading(r: Reading, versions: Sequence[Version], trades: Mapping[str, list[Trade]],
                  family: Mapping[str, float | None], crit: Criteria, symbol: str, asof: int,
                  prices: tuple[np.ndarray, np.ndarray] | None) -> list[Verdict]:
    """Veredictos de una lectura con la puerta tal cual."""
    items = []
    for v in versions:
        wins = windows_of(r, v)
        m = measure(f"{symbol}|{v.label}", trades.get(v.sid, []), wins, symbol, asof, crit,
                    len(family), prices)
        items.append((v, m, wins))
    return validate_all(items, family, crit)


@dataclass(frozen=True)
class SideStats:
    """Lo que la regla de lectura pide además de la puerta. Bruto = R neto + costo en R."""

    n: int
    gross: float | None
    cost: float | None
    n_long: int
    n_short: int
    gross_long: float | None
    gross_short: float | None
    balanced: float | None
    stressed: float | None

    def to_json(self) -> dict:
        return dict(self.__dict__)


def side_stats(ts: Sequence[Trade], min_side: int, stress: float) -> SideStats:
    """Bruto por lado, bruto equilibrado (cancela la deriva) y R neto con los costos × `stress`.

    El equilibrado es la media simple de los dos lados, y solo existe con `min_side` operaciones por
    lado: con un lado casi vacío no se puede cancelar nada.
    """
    if not ts:
        return SideStats(0, None, None, 0, 0, None, None, None, None)
    r = np.array([x.r for x in ts], dtype=float)
    c = np.array([x.cost_r for x in ts], dtype=float)
    side = np.array([x.side for x in ts])
    g = r + c
    long_, short = g[side > 0], g[side < 0]
    gl = float(long_.mean()) if len(long_) else None
    gs = float(short.mean()) if len(short) else None
    bal = (gl + gs) / 2 if len(long_) >= min_side and len(short) >= min_side else None
    return SideStats(len(ts), float(g.mean()), float(c.mean()), len(long_), len(short), gl, gs, bal,
                     float((r - (stress - 1.0) * c).mean()))


def selected(r: Reading, v: Version, trades: Sequence[Trade], symbol: str, asof: int
             ) -> list[Trade]:
    """Las operaciones de una versión que cuentan en una lectura."""
    return select(trades, windows_of(r, v), symbol, asof).oos


def truncate_path(path: Path, asof: int) -> Path:
    """El mismo camino, solo con las velas cerradas en `asof` o antes (regresión contra T137)."""
    keep = path.t + path.step <= asof
    p = Path([], (), path.step)
    p.t, p.o, p.h, p.l, p.c = path.t[keep], path.o[keep], path.h[keep], path.l[keep], path.c[keep]
    p.ft, p.fr = path.ft, path.fr
    return p
