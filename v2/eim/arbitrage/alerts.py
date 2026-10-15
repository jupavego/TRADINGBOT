"""Alertas del escáner (T39): una oportunidad seleccionada que supera el umbral y sigue
vigente durante `hold_s` segundos seguidos de escaneos.

El umbral es la puntuación del selector (pb/día ajustados por riesgo), comparable entre
estrategias de horizontes distintos: 3 pb/día ≈ 11 % anual antes del ajuste. Sin I/O; el
estado (desde cuándo cumple cada oportunidad) vive en `AlertTracker`, que guarda la API.
"""

from __future__ import annotations

from pydantic import Field

from eim.arbitrage.selector import Selection
from eim.core import Opportunity
from eim.core.market import Frozen


class AlertParams(Frozen):
    min_score: float = 3.0  # pb/día ajustados por riesgo (puntuación del selector)
    hold_s: float = Field(default=60.0, ge=0)  # tiempo seguido cumpliendo antes de avisar
    max_gap_s: float = Field(default=180.0, gt=0)  # hueco entre escaneos que reinicia la cuenta


class ArbAlert(Frozen):
    key: str  # `opp_key`: estable entre escaneos
    strategy: str
    asset: str
    variant: str
    since: int  # primer escaneo seguido que cumplió (ms)
    asof: int  # escaneo actual
    held_s: float
    net_bps: float
    score: float
    annualized: float | None
    active: bool  # cumplió `hold_s`: alerta en firme (si no, en observación)
    new: bool = False  # se activó en este escaneo (para avisar una sola vez)


def opp_key(o: Opportunity) -> str:
    """Identidad de una oportunidad entre escaneos: estrategia · activo · variante ·
    contratos (dos trimestrales del mismo activo comparten variante)."""
    syms = "/".join(dict.fromkeys(lg.symbol for lg in o.legs))
    return f"{o.strategy}·{o.asset}·{o.variant}·{syms}"


class AlertTracker:
    """Cuenta el tiempo seguido que cada oportunidad cumple el umbral (escaneo a escaneo)."""

    def __init__(self, p: AlertParams | None = None) -> None:
        self.p = p or AlertParams()
        self._since: dict[str, int] = {}
        self._active: set[str] = set()
        self.last_asof: int | None = None
        self.last: list[ArbAlert] = []

    def update(self, sel: Selection, asof: int) -> list[ArbAlert]:
        """Procesa un escaneo nuevo; repetir el mismo `asof` devuelve el último resultado."""
        if self.last_asof is not None and asof <= self.last_asof:
            return self.last
        if self.last_asof is not None and (asof - self.last_asof) / 1000 > self.p.max_gap_s:
            self._since.clear()  # escáner detenido: no se sabe si siguió vigente
            self._active.clear()
        ok = {opp_key(r.opportunity): r for r in sel.selected
              if r.score >= self.p.min_score and r.opportunity.valid_until >= asof}
        self._since = {k: t for k, t in self._since.items() if k in ok}
        self._active &= set(ok)
        out: list[ArbAlert] = []
        for k, r in ok.items():
            since = self._since.setdefault(k, asof)
            held = (asof - since) / 1000
            active = held >= self.p.hold_s
            new = active and k not in self._active
            if active:
                self._active.add(k)
            o = r.opportunity
            out.append(ArbAlert(key=k, strategy=o.strategy, asset=o.asset, variant=o.variant,
                                since=since, asof=asof, held_s=held, net_bps=o.net_bps,
                                score=r.score, annualized=o.annualized, active=active, new=new))
        out.sort(key=lambda a: (not a.active, -a.score))
        self.last_asof, self.last = asof, out
        return out
