"""Techo y piso por escenario (T19+): niveles estadísticos confirmados por estructura.

Para cada escenario se calcula primero la envolvente estadística de sus trayectorias (techo = p90
del máximo, piso = p10 del mínimo). Luego se buscan niveles estructurales cercanos (±0.75 ATR):
retrocesos/extensiones de Fibonacci del último tramo, proyecciones de onda tipo Elliott
(igualdad y 1.618 del tramo previo medidas desde el último retroceso) y pivotes recientes. Si hay
estructura cerca, el nivel se ajusta a ella y se reporta la confluencia (nº de métodos); si no,
queda el nivel estadístico y se dice. Son referencias probabilísticas, no garantías.
"""

from __future__ import annotations

import numpy as np

from eim.agents.elliott.compute import zigzag
from eim.agents.levels.pivots import find_pivots
from eim.core import MarketSnapshot

FIB_RETR = (0.382, 0.5, 0.618)
FIB_EXT = (1.272, 1.618)
ELLIOTT_PROJ = (1.0, 1.618)
TOL_ATR = 0.75


def structural_levels(snapshot: MarketSnapshot, atr_abs: float) -> list[tuple[float, str]]:
    """Niveles (precio, método) de Fibonacci, Elliott y pivotes sobre las últimas 300 velas."""
    cs = snapshot.candles[-300:]
    t = [c.t for c in cs]
    hi = [c.h for c in cs]
    lo = [c.l for c in cs]
    last = cs[-1].c
    out: list[tuple[float, str]] = []
    pct = max(1.0, 3.0 * atr_abs / last * 100)
    piv = zigzag(t, hi, lo, pct)
    if len(piv) >= 3:
        # último tramo completo p0→p1 y su retroceso hasta p2 (p2 puede ser aún provisional)
        p0, p1, p2 = piv[-3]["price"], piv[-2]["price"], piv[-1]["price"]
        leg = p1 - p0
        for r in FIB_RETR:
            out.append((p1 - leg * r, f"Fib {r:g}"))
        for e in FIB_EXT:
            out.append((p0 + leg * e, f"Fib ext {e:g}"))
        for k in ELLIOTT_PROJ:
            out.append((p2 + leg * k, f"Elliott onda ×{k:g}"))
    v = np.array([c.v for c in cs], dtype=float)
    for p in find_pivots(np.array(hi), np.array(lo), v, 5)[-12:]:
        out.append((p.price, "pivote"))
    return [(p, m) for p, m in out if p > 0]


def _pick(target: float, cands: list[tuple[float, str]], atr_abs: float) -> dict | None:
    near = [(p, m) for p, m in cands if abs(p - target) <= TOL_ATR * atr_abs]
    if not near:
        return None
    best = min(near, key=lambda x: abs(x[0] - target))
    methods = sorted({m for p, m in near if abs(p - best[0]) <= 0.25 * atr_abs} | {best[1]})
    return {"price": float(best[0]), "methods": methods}


def scenario_levels(
    group_paths: np.ndarray, cands: list[tuple[float, str]], atr_abs: float
) -> list[dict]:
    """Techo y piso de un escenario a partir de sus trayectorias (m, h, 4)."""
    ceil_stat = float(np.quantile(group_paths[:, :, 1].max(axis=1), 0.9))
    floor_stat = float(np.quantile(group_paths[:, :, 2].min(axis=1), 0.1))
    out = []
    for role, stat in (("techo", ceil_stat), ("piso", floor_stat)):
        s = _pick(stat, cands, atr_abs)
        if s:
            out.append({"role": role, "price": s["price"], "source": "estructural",
                        "methods": s["methods"], "confluence": len(s["methods"]),
                        "stat_price": stat,
                        "note": f"{role} ajustado a {', '.join(s['methods'])} "
                                f"(envolvente estadística {stat:.2f})"})
        else:
            out.append({"role": role, "price": stat, "source": "estadístico", "methods": [],
                        "confluence": 0, "stat_price": stat,
                        "note": f"{role} estadístico (p{'90' if role == 'techo' else '10'} de "
                                "las trayectorias); sin estructura cercana"})
    return out
