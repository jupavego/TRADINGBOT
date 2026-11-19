"""Boleta de dirección (T190): cada voto guardado frente a lo que hizo el precio después. Puro.

Entrada: las columnas de `ReportStore.history` (asof, agente, sesgo, confianza, estado) y las
velas del almacén como arreglos. No recalcula ningún agente ni reconstruye historia: califica lo
que cada informante dijo en su momento. La síntesis v1 se recalcula con la función pura
`synthesize` sobre esos mismos reportes (su signo no depende de las métricas que no se guardan en
columnas: el calendario y el escuadrón solo mueven la confianza o tienen peso 0).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np

from eim.direction.params import REGIMES, SYNTH_ID, DirectionParams

HistoryRow = tuple[int, str, float, float, str]          # (asof, agente, sesgo, confianza, estado)
SynthFn = Callable[[int, list[tuple[str, float, float, str]]], float | None]


@dataclass(frozen=True)
class Vote:
    asof: int
    agent: str
    sign: int                                   # +1 alcista, −1 bajista
    strength: float                             # |sesgo| · confianza (informativo)
    regime: str | None
    outcome: dict[int, int]                     # horizonte → signo (+1/−1/0); falta = pendiente


@dataclass
class Instant:
    """Un instante con todos sus votos: lo que usan las sombras (T192, T193)."""

    asof: int
    regime: str | None
    votes: dict[str, int] = field(default_factory=dict)
    synth: int = 0
    outcome: int | None = None                  # signo al horizonte principal (None = pendiente)


def ref_index(t: np.ndarray, asof: int, step: int) -> int | None:
    """Índice de la última vela cerrada en `asof` (abre en `asof − step` o antes, sin hueco)."""
    i = int(np.searchsorted(t, asof - step, side="right")) - 1
    if i < 0 or t[i] < asof - 2 * step:
        return None
    return i


def regime_at(c: np.ndarray, i: int, p: DirectionParams) -> str | None:
    """Tercil de la volatilidad realizada de las últimas `regime_bars` velas frente a la de las
    `regime_lookback` anteriores. Solo velas cerradas hasta `i`; None sin historia suficiente."""
    need = p.regime_bars + p.regime_lookback
    if i < need:
        return None
    lr = np.diff(np.log(c[i - need:i + 1]))
    win = np.lib.stride_tricks.sliding_window_view(lr, p.regime_bars).std(axis=1)
    now, past = win[-1], win[:-1][-p.regime_lookback:]
    rank = float((past < now).mean())
    return REGIMES[0] if rank < 1 / 3 else (REGIMES[1] if rank < 2 / 3 else REGIMES[2])


def outcomes_at(t: np.ndarray, c: np.ndarray, i: int, step: int,
                horizons: Iterable[int]) -> dict[int, int]:
    """Signo del retorno a cada horizonte ya ocurrido (sin huecos en el camino)."""
    out: dict[int, int] = {}
    for h in horizons:
        j = i + h
        if j < len(t) and t[j] == t[i] + h * step:
            d = c[j] - c[i]
            out[h] = 0 if d == 0 else (1 if d > 0 else -1)
    return out


def default_synth(params=None) -> SynthFn:
    """Signo de la síntesis v1 (la que usa el bróker) sobre los reportes guardados."""
    from eim.core import AgentReport
    from eim.synthesis import synthesize

    def fn(asof: int, rows: list[tuple[str, float, float, str]]) -> float | None:
        reps = [AgentReport(agent_id=a, version="guardado", asof=asof, bias=b, confidence=cf,
                            horizon_bars=0, status=st) for a, b, cf, st in rows]
        syn = synthesize(reps, params=params) if params is not None else synthesize(reps)
        return None if syn is None else syn.bias
    return fn


def _vote_sign(bias: float, conf: float, status: str, p: DirectionParams) -> int:
    if status == "no_data" or conf <= 0 or abs(bias) < p.bias_min or math.isnan(bias):
        return 0
    return 1 if bias > 0 else -1


def build(history: Sequence[HistoryRow], t: np.ndarray, c: np.ndarray, step: int,
          p: DirectionParams, synth: SynthFn | None = None) -> tuple[list[Vote], list[Instant]]:
    """Votos calificables e instantes, en orden de `asof`. `synth=None` no califica la síntesis."""
    by_asof: dict[int, list[tuple[str, float, float, str]]] = defaultdict(list)
    for asof, agent, bias, conf, status in history:
        by_asof[int(asof)].append((str(agent), float(bias), float(conf), str(status)))
    votes: list[Vote] = []
    instants: list[Instant] = []
    regime_cache: dict[int, str | None] = {}
    for asof in sorted(by_asof):
        i = ref_index(t, asof, step)
        if i is None:
            continue
        if i not in regime_cache:
            regime_cache[i] = regime_at(c, i, p)
        reg = regime_cache[i]
        outs = outcomes_at(t, c, i, step, p.horizons)
        inst = Instant(asof=asof, regime=reg, outcome=outs.get(p.primary))
        rows = by_asof[asof]
        for agent, bias, conf, status in rows:
            if agent in p.excluded:
                continue
            s = _vote_sign(bias, conf, status, p)
            if s:
                inst.votes[agent] = s
                votes.append(Vote(asof, agent, s, abs(bias) * conf, reg, outs))
        if synth is not None:
            sb = synth(asof, rows)
            if sb is not None and abs(sb) >= p.bias_min:
                inst.synth = 1 if sb > 0 else -1
                votes.append(Vote(asof, SYNTH_ID, inst.synth, abs(sb), reg, outs))
        instants.append(inst)
    return votes, instants
