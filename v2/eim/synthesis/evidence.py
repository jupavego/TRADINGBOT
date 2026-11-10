"""T150 — cobertura en vivo, correlación vigente y votos efectivos (funciones puras).

La síntesis que publica el panel no puede decir más de lo que sabe:

- **Cobertura** (entregable 1 y 2): por agente, `ok` / `degraded` / `no_data` en las últimas
  `coverage_bars` velas guardadas. Un agente ausente en una vela cuenta como `no_data`. Si lo
  malo pasa de `max_bad`, el agente no vota.
- **Correlación** (entregable 3): ρ de Pearson del sesgo entre votantes en las últimas
  `corr_bars` velas con datos en ambos, recortada a [0, 1] (una ρ negativa inflaría los votos).
- **Votos efectivos** (entregable 4): N_eff = (Σ wᵢ)² / Σᵢ Σⱼ wᵢ wⱼ ρᵢⱼ (ρᵢᵢ = 1), el número de
  votos independientes con la misma información. Con pesos iguales es N / (1 + (N − 1) ρ̄):
  cinco votantes con ρ 0,6 son ~1,5 votos; con ρ 0,44 (el mínimo medido en T44), ~1,8.

Sin red ni disco: el historial lo trae quien llama (`eim/api/synthesis_live.py`).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from eim.synthesis.params import EvidenceParams

# Una fila del historial: (asof, agent_id, sesgo, confianza, estado).
Row = tuple[int, str, float, float, str]


@dataclass(frozen=True)
class Coverage:
    """Cobertura de un agente en la ventana: cuentas, estado resumido y si vota."""

    agent_id: str
    window_bars: int
    ok: int
    degraded: int
    no_data: int
    votes: bool
    short: bool = False        # ventana con menos de `min_bars` velas: decide la vela actual

    @property
    def bad_fraction(self) -> float:
        return (self.degraded + self.no_data) / self.window_bars if self.window_bars else 0.0

    @property
    def state(self) -> str:
        """Lo que domina en la ventana (empate → lo peor). Si vota o no lo dice `votes`."""
        if self.ok > max(self.degraded, self.no_data):
            return "ok"
        return "no_data" if self.no_data >= self.degraded else "degraded"

    def reason(self, p: EvidenceParams) -> str:
        n = self.window_bars
        if self.short:
            return f"ventana corta ({n}/{p.min_bars} velas): vota según la vela actual"
        txt = (f"{self.ok}/{n} velas con datos, {self.degraded} degradadas y {self.no_data} sin "
               f"datos en las últimas {n}")
        if self.votes:
            return txt
        return f"{txt}: más del {p.max_bad:.0%} sin datos útiles, no vota"


@dataclass(frozen=True)
class Evidence:
    """Lo que la síntesis v2 sabe del pasado reciente de cada agente."""

    coverage: dict[str, Coverage]
    rho: dict[tuple[str, str], float]          # par ordenado (a < b) → ρ ∈ [0, 1]
    measured: frozenset[tuple[str, str]] = field(default_factory=frozenset)  # sin `rho_prior`
    first_asof: int | None = None
    last_asof: int | None = None
    corr_window: int = 0

    def rho_of(self, a: str, b: str, prior: float) -> float:
        if a == b:
            return 1.0
        return self.rho.get((a, b) if a < b else (b, a), prior)


def _usable(status: str, conf: float) -> bool:
    return status != "no_data" and conf > 0


def coverage_of(rows: Iterable[Row], agents: Iterable[str], p: EvidenceParams,
                corr_agents: Iterable[str] | None = None) -> Evidence:
    """Cobertura de `agents` y ρ entre `corr_agents` (por omisión, los mismos) con el historial
    `rows` (cualquier orden). Solo se correlaciona a quien puede votar y tiene cobertura."""
    by_asof: dict[int, dict[str, tuple[float, float, str]]] = {}
    for asof, aid, bias, conf, status in rows:
        by_asof.setdefault(asof, {})[aid] = (bias, conf, status)
    asofs = sorted(by_asof)
    agents = sorted(set(agents))
    cov_win = asofs[-p.coverage_bars:]
    cov: dict[str, Coverage] = {}
    for a in agents:
        ok = deg = nod = 0
        for t in cov_win:
            got = by_asof[t].get(a)
            if got is None or got[2] == "no_data":
                nod += 1
            elif got[2] == "degraded":
                deg += 1
            else:
                ok += 1
        n = len(cov_win)
        short = n < p.min_bars
        votes = short or (deg + nod) / n <= p.max_bad
        cov[a] = Coverage(a, n, ok, deg, nod, votes, short)
    corr_win = asofs[-p.corr_bars:]
    pool = agents if corr_agents is None else sorted(set(corr_agents) & set(agents))
    agents = [a for a in pool if cov[a].votes]
    series = {a: [by_asof[t].get(a) for t in corr_win] for a in agents}
    rho: dict[tuple[str, str], float] = {}
    measured: set[tuple[str, str]] = set()
    for i, a in enumerate(agents):
        for b in agents[i + 1:]:
            pairs = [(x[0], y[0]) for x, y in zip(series[a], series[b], strict=True)
                     if x is not None and y is not None and _usable(x[2], x[1])
                     and _usable(y[2], y[1])]
            r = pearson(pairs) if len(pairs) >= p.corr_min_overlap else None
            if r is None:
                rho[(a, b)] = p.rho_prior
            else:
                rho[(a, b)] = min(1.0, max(0.0, r))
                measured.add((a, b))
    return Evidence(cov, rho, frozenset(measured), asofs[0] if asofs else None,
                    asofs[-1] if asofs else None, len(corr_win))


def pearson(pairs: Sequence[tuple[float, float]]) -> float | None:
    """ρ de Pearson; None si alguna serie no varía."""
    n = len(pairs)
    if n < 2:
        return None
    mx = sum(x for x, _ in pairs) / n
    my = sum(y for _, y in pairs) / n
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    syy = sum((y - my) ** 2 for _, y in pairs)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def effective_votes(weights: Mapping[str, float], ev: Evidence, prior: float) -> float:
    """N_eff = (Σ w)² / Σ Σ wᵢ wⱼ ρᵢⱼ sobre los agentes con peso > 0 (0 si no hay)."""
    w = {a: x for a, x in weights.items() if x > 0}
    if not w:
        return 0.0
    num = sum(w.values()) ** 2
    den = sum(w[a] * w[b] * ev.rho_of(a, b, prior) for a in w for b in w)
    return num / den if den > 0 else 0.0


def mean_rho(agents: Sequence[str], ev: Evidence, prior: float) -> float | None:
    """ρ medio entre pares de `agents` (None con menos de dos)."""
    ids = sorted(agents)
    pairs = [ev.rho_of(a, b, prior) for i, a in enumerate(ids) for b in ids[i + 1:]]
    return sum(pairs) / len(pairs) if pairs else None
