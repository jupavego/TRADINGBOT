"""Seguimiento adelante (puro): solo puntúa lo que observamos nosotros.

- `forward_start` = primera foto de posiciones del líder (cuando empezamos a capturarlo).
  Días adelante = tiempo cubierto por fotos consecutivas (el vigilante guarda una al menos
  cada 5 min; un salto mayor es tiempo sin capturar y no cuenta). Una operación es
  «adelante» si su apertura es posterior: la vimos entera, sin reconstrucciones. Lo
  anterior (historial reenviado, `portfolio`) solo preselecciona.
- **¿Sirve el filtro?** Cada cambio de veredicto se registra con su hora; el rendimiento de
  las operaciones abiertas después se asigna al veredicto vigente en su apertura. Si los
  aprobados no rinden más que los descartados, el filtro no aporta.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from eim.copytrading.trades import Trip
from eim.core.market import Frozen

Verdict = Literal["approved", "watch", "rejected"]
VERDICTS: tuple[Verdict, ...] = ("approved", "watch", "rejected")
DAY_MS = 86_400_000


class VerdictMark(Frozen):
    leader_id: str
    t: int
    verdict: Verdict
    quality: float = 0.0


class Cohort(Frozen):
    verdict: Verdict
    leaders: int = 0
    trades: int = 0
    net: float = 0.0
    mean: float | None = None
    mean_bps: float | None = None
    win_rate: float | None = None
    since: int | None = None  # primer veredicto registrado de la cohorte


def forward_trips(trips: list[Trip], start: int | None) -> list[Trip]:
    if start is None:
        return []
    return [t for t in trips if t.complete and t.t_open >= start]


def covered_ms(times: list[int], max_step_ms: int) -> int:
    """Tiempo cubierto por fotos consecutivas: cada salto cuenta hasta `max_step_ms`."""
    ts = sorted(times)
    return sum(min(b - a, max_step_ms) for a, b in zip(ts, ts[1:], strict=False))


def cohorts(marks: list[VerdictMark], fwd: dict[str, list[Trip]]) -> dict[str, Cohort]:
    """Rendimiento adelante por veredicto vigente al abrir cada operación."""
    by_leader: dict[str, list[VerdictMark]] = defaultdict(list)
    for m in sorted(marks, key=lambda m: m.t):
        by_leader[m.leader_id].append(m)
    acc = {v: {"leaders": set(), "xs": [], "notional": 0.0, "since": None} for v in VERDICTS}
    for lid, ms in by_leader.items():
        for m in ms:
            a = acc[m.verdict]
            a["since"] = m.t if a["since"] is None else min(a["since"], m.t)
        for tr in fwd.get(lid, []):
            if not tr.closed:
                continue
            cur = [m for m in ms if m.t <= tr.t_open]
            if not cur:
                continue
            a = acc[cur[-1].verdict]
            a["leaders"].add(lid)
            a["xs"].append(tr.net)
            a["notional"] += tr.notional_max
    out = {}
    for v, a in acc.items():
        xs = a["xs"]
        out[v] = Cohort(verdict=v, leaders=len(a["leaders"]), trades=len(xs), net=sum(xs),
                        mean=sum(xs) / len(xs) if xs else None,
                        mean_bps=sum(xs) / a["notional"] * 1e4 if a["notional"] else None,
                        win_rate=sum(x > 0 for x in xs) / len(xs) if xs else None,
                        since=a["since"])
    return out
