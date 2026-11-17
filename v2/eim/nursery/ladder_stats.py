"""Medidas de una cuenta de la cantera hasta un instante τ (T170). Puras.

Todo lo de aquí recibe solo operaciones cerradas en `exit_t ≤ τ` (o, para la actividad, entradas
llenadas en `fill_t ≤ τ`): el escalafón no puede ver el futuro por construcción.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

from eim.nursery.ladder_rules import ForwardExam, LadderRules

DAY_MS = 86_400_000
H_MS = 3_600_000


@dataclass(frozen=True)
class Closed:
    """Una operación cerrada y contabilizada de una cuenta (no las sombras de la puerta)."""

    t: int                      # cierre de la vela de decisión
    fill_t: int
    exit_t: int
    d: float                    # R − media de sus gemelos aleatorios pareados
    pnl_usd: float
    cost_r: float | None = None
    r: float | None = None
    regime: str | None = None


@dataclass(frozen=True)
class AccountData:
    closed: tuple[Closed, ...] = ()                    # ascendente por exit_t
    fills: tuple[tuple[int, int | None], ...] = ()     # (fill_t, exit_t) de lo llenado

    def upto(self, tau: int) -> AccountData:
        return AccountData(tuple(c for c in self.closed if c.exit_t <= tau),
                           tuple((f, e if e is not None and e <= tau else None)
                                 for f, e in self.fills if f <= tau))


def observations(acc: AccountData, band: str, rules: LadderRules) -> list[float]:
    """Observaciones de la hipótesis primaria: d por operación, o la suma diaria de d si la
    banda se mide por día (los días sin cierre aportan 0 y no mueven el e-proceso)."""
    if band not in rules.primary.day_unit_bands:
        return [c.d for c in acc.closed]
    days: dict[int, float] = {}
    for c in acc.closed:
        days[c.exit_t // DAY_MS] = days.get(c.exit_t // DAY_MS, 0.0) + c.d
    return [days[k] for k in sorted(days)]


def net_pnl(acc: AccountData) -> float:
    return float(sum(c.pnl_usd for c in acc.closed))


def max_dd_pct(acc: AccountData, initial: float) -> float:
    """Drawdown máximo de la curva realizada (al cierre de cada operación), en %."""
    eq, peak, dd = initial, initial, 0.0
    for c in acc.closed:
        eq += c.pnl_usd
        peak = max(peak, eq)
        dd = max(dd, (peak - eq) / peak if peak > 0 else 0.0)
    return dd * 100


def top_share(acc: AccountData) -> float | None:
    """Fracción del beneficio neto que explica la mejor operación (None sin beneficio)."""
    net = net_pnl(acc)
    if net <= 0 or not acc.closed:
        return None
    return max(c.pnl_usd for c in acc.closed) / net


def overlap(spans: Sequence[tuple[int, int]], a: int, b: int) -> int:
    return sum(max(0, min(e, b) - max(s, a)) for s, e in spans)


def inactive_days(acc: AccountData, alta: int, tau: int, closed_spans: Sequence[tuple[int, int]],
                  count_closed: bool) -> float:
    """Días desde la última actividad (alta, entrada o salida; 0 con posición abierta), sin los
    días con el marco cerrado por la puerta de costo si así se pre-registró."""
    last = alta
    for f, e in acc.fills:
        if e is None:
            return 0.0
        last = max(last, f, e)
    span = tau - last
    if not count_closed:
        span -= overlap(closed_spans, last, tau)
    return max(0, span) / DAY_MS


def daily_pnl(acc: AccountData, alta: int, tau: int) -> np.ndarray:
    """P&L realizado por día UTC, del día del alta al de τ (0 los días sin cierre)."""
    d0, d1 = alta // DAY_MS, tau // DAY_MS
    out = np.zeros(int(d1 - d0 + 1))
    for c in acc.closed:
        if alta <= c.exit_t <= tau:          # lo anterior al alta (reentradas) no cuenta
            out[int(c.exit_t // DAY_MS - d0)] += c.pnl_usd
    return out


def clipped(d: Sequence[float], clip_r: float) -> np.ndarray:
    return np.clip(np.asarray(d, float), -clip_r, clip_r)


def beats(d_complex: Sequence[float], d_simple: Sequence[float], rules: LadderRules
          ) -> tuple[bool, float | None]:
    """¿Supera el complejo a su hermano simple? z de Welch unilateral sobre d̃ (a empate, no).

    Con menos de `sibling_min_trades` del hermano se compara con 0, que es su gemelo aleatorio.
    """
    p = rules.promise
    a = clipped(d_complex, rules.primary.clip_r)
    if len(a) < 2:
        return False, None
    b = clipped(d_simple, rules.primary.clip_r)
    var = a.var(ddof=1) / len(a)
    mb = 0.0
    if len(b) >= p.sibling_min_trades:
        mb, var = float(b.mean()), var + b.var(ddof=1) / len(b)
    if var <= 0:
        return bool(a.mean() > mb), None
    z = (float(a.mean()) - mb) / math.sqrt(var)
    return z > NormalDist().inv_cdf(1 - p.sibling_alpha), round(z, 3)


def marginal(own: np.ndarray, other: np.ndarray, rules: LadderRules) -> tuple[bool, dict]:
    """Contribución marginal frente a otra cuenta (hermano o genérico): si su P&L diario tiene
    correlación > umbral, solo vale si aporta por encima (media diaria de la diferencia > 0)."""
    p = rules.promise
    active = int(np.count_nonzero((own != 0) | (other != 0)))
    if active < p.marginal_min_days or own.std() == 0 or other.std() == 0:
        return True, {"corr": None, "days": active}
    rho = float(np.corrcoef(own, other)[0, 1])
    gain = float((own - other).mean())
    ok = rho <= p.marginal_corr or gain > 0
    return ok, {"corr": round(rho, 3), "gain_usd_day": round(gain, 2), "days": active}


def band_of(hold_h: float, fx: ForwardExam) -> str:
    s, i, t = fx.band_max_hours
    if hold_h <= s:
        return "scalping"
    if hold_h < i:
        return "intradia"
    return "tres_dias" if hold_h <= t else "semanal"


def forward_exam(acc: AccountData, declared: str, alta: int, tau: int,
                 closed_spans: Sequence[tuple[int, int]], fx: ForwardExam
                 ) -> tuple[list[str], str]:
    """Examen físico hacia adelante (ficha de T169) de un prospecto sin historia: (motivos, banda).

    Los días con su marco cerrado por la puerta de costo no cuentan en la cadencia.
    """
    days = (tau - alta - overlap(closed_spans, alta, tau)) / DAY_MS
    holds = [(c.exit_t - c.fill_t) / H_MS for c in acc.closed]
    band = band_of(float(np.median(holds)), fx) if len(holds) >= fx.min_closed_for_band \
        else declared
    why: list[str] = []
    if band == "semanal":
        held = set()
        for f, e in acc.fills:
            held.update(range(f // DAY_MS, (e if e is not None else tau) // DAY_MS + 1))
        frac = len(held) / days if days > 0 else 0.0
        if frac < fx.min_pos_days_frac:
            why.append(f"semanal en posición el {round(frac * 100)} % de los días "
                       f"(< {round(fx.min_pos_days_frac * 100)} %)")
    else:
        per_month = len(acc.fills) / days * 30 if days > 0 else 0.0
        need = fx.min_ops_month[band]
        if per_month < need:
            why.append(f"{band}: {per_month:.1f} operaciones al mes (< {need:g})".replace(".", ","))
    costs = [c.cost_r for c in acc.closed if c.cost_r is not None]
    if costs and float(np.mean(costs)) > fx.max_cost_r:
        why.append(f"costo medio {np.mean(costs):.3f} R (> {fx.max_cost_r:g} R)".replace(".", ","))
    return why, band
