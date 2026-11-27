"""Calidad y resumen de una cadena de opciones de un vencimiento (T100).

Es el agente de prueba de la familia «opciones/IV», en modo ANÁLISIS y sin registrar: recibe
las cotizaciones de un vencimiento y dice (1) si la cadena es utilizable —horquillas, cruces,
arbitraje estático— y (2) lo que el mercado está pagando: volatilidad ATM y pendiente de la
sonrisa. **No hay datos de cadenas aprobados** (◆ de T88): por eso no se conecta a ningún
proveedor; ver `v2/reports/fixed_income_options_viability.md`.

Reglas de arbitraje estático comprobadas sobre los precios medios, por tipo:
calls no crecientes y convexas en K; puts no decrecientes y convexas en K; y, donde hay los dos
lados al mismo K, la paridad put-call dentro de la mitad de las horquillas sumadas.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from eim.options.black_scholes import CALL, PUT, parity_gap
from eim.options.implied_vol import NoImpliedVol, implied_vol

MAX_REL_SPREAD = 0.25      # horquilla/medio por encima de esto: cotización no utilizable
TOL = 1e-9


@dataclass(frozen=True)
class Quote:
    strike: float
    kind: str                  # "call" | "put"
    bid: float | None
    ask: float | None

    @property
    def two_sided(self) -> bool:
        return self.bid is not None and self.ask is not None and self.bid > 0 and self.ask > 0

    @property
    def mid(self) -> float | None:
        return 0.5 * (self.bid + self.ask) if self.two_sided else None

    @property
    def rel_spread(self) -> float | None:
        m = self.mid
        return (self.ask - self.bid) / m if m else None


@dataclass
class ChainReport:
    status: str                                   # "ok" | "degradado" | "no_data"
    n_quotes: int
    n_two_sided: int
    n_crossed: int
    n_wide: int
    median_rel_spread: float | None
    arbitrage: list[str] = field(default_factory=list)
    iv: dict[tuple[float, str], float] = field(default_factory=dict)
    iv_failures: dict[tuple[float, str], str] = field(default_factory=dict)
    atm_iv: float | None = None
    skew_90_110: float | None = None              # IV(0,9·F) − IV(1,1·F), en σ
    warnings: list[str] = field(default_factory=list)


def _violations(rows: list[tuple[float, float]], kind: str) -> list[str]:
    out = []
    for (k0, p0), (k1, p1) in zip(rows, rows[1:], strict=False):
        if kind == CALL and p1 > p0 + TOL:
            out.append(f"call no decreciente entre K={k0:g} y K={k1:g}")
        if kind == PUT and p1 < p0 - TOL:
            out.append(f"put no creciente entre K={k0:g} y K={k1:g}")
    for (k0, p0), (k1, p1), (k2, p2) in zip(rows, rows[1:], rows[2:], strict=False):
        w = (k2 - k1) / (k2 - k0)
        if p1 > w * p0 + (1 - w) * p2 + TOL:
            out.append(f"{kind} no convexa en K={k1:g} (mariposa negativa)")
    return out


def _interp(xs: list[float], ys: list[float], x: float) -> float | None:
    if not xs or x < xs[0] or x > xs[-1]:
        return None
    for i in range(1, len(xs)):
        if x <= xs[i]:
            w = (x - xs[i - 1]) / (xs[i] - xs[i - 1]) if xs[i] > xs[i - 1] else 0.0
            return ys[i - 1] + w * (ys[i] - ys[i - 1])
    return ys[-1]


def analyze(quotes: Sequence[Quote], s: float, t: float, r: float,
            b: float | None = None) -> ChainReport:
    """Calidad y resumen de la cadena de un vencimiento (`t` años, subyacente `s`)."""
    b = r if b is None else b
    two = [q for q in quotes if q.two_sided]
    crossed = [q for q in two if q.bid > q.ask]
    usable = [q for q in two if q.bid <= q.ask and (q.rel_spread or 0) <= MAX_REL_SPREAD]
    spreads = sorted(q.rel_spread for q in two if q.bid <= q.ask)
    rep = ChainReport(status="ok", n_quotes=len(quotes), n_two_sided=len(two),
                      n_crossed=len(crossed), n_wide=len(two) - len(crossed) - len(usable),
                      median_rel_spread=spreads[len(spreads) // 2] if spreads else None)
    if not usable:
        rep.status = "no_data"
        rep.warnings.append("ninguna cotización con dos lados, sin cruzar y horquilla razonable")
        return rep
    by_kind = {kd: sorted((q.strike, q.mid) for q in usable if q.kind == kd) for kd in (CALL, PUT)}
    for kd, rows in by_kind.items():
        rep.arbitrage += _violations(rows, kd)
    calls = {q.strike: q for q in usable if q.kind == CALL}
    for q in usable:
        if q.kind == PUT and q.strike in calls:
            c = calls[q.strike]
            gap = parity_gap(c.mid, q.mid, s, q.strike, t, r, b)
            if abs(gap) > 0.5 * ((c.ask - c.bid) + (q.ask - q.bid)) + TOL:
                rep.arbitrage.append(f"paridad put-call rota en K={q.strike:g} ({gap:+.4g})")
        try:
            rep.iv[(q.strike, q.kind)] = implied_vol(q.mid, s, q.strike, t, r, q.kind, b)
        except NoImpliedVol as exc:
            rep.iv_failures[(q.strike, q.kind)] = str(exc)
    fwd = s * math.exp(b * t)
    # Sonrisa con la opción fuera del dinero en cada K (la más líquida y sin valor intrínseco).
    otm = sorted((k, v) for (k, kd), v in rep.iv.items()
                 if (kd == PUT and k <= fwd) or (kd == CALL and k > fwd))
    ks, vs = [k for k, _ in otm], [v for _, v in otm]
    rep.atm_iv = _interp(ks, vs, fwd)
    lo, hi = _interp(ks, vs, 0.9 * fwd), _interp(ks, vs, 1.1 * fwd)
    rep.skew_90_110 = None if lo is None or hi is None else lo - hi
    if rep.atm_iv is None:
        rep.warnings.append("la cadena no cubre el forward: sin volatilidad ATM")
    if crossed or rep.arbitrage or rep.iv_failures or rep.n_wide:
        rep.status = "degradado"
    return rep
