"""T143 — comparación emparejada de la entrada a mercado (taker) frente a la orden límite (maker).

Funciones puras sobre ideas ya construidas y un camino de precios: no abren red ni disco. El
pre-registro que fija criterio, rejilla y contabilidad es `PLAN/notas/T143_preregistro_maker.md`.

Dos decisiones de contabilidad que el pre-registro no fijaba y que aquí se toman **en contra** del
brazo maker, porque sin ellas la medición se engaña sola:

1. **Denominador común.** El motor divide por el riesgo *realizado* (`|llenado − SL|`). Una límite
   que entra a mejor precio tiene un riesgo menor, así que su R se infla por aritmética y no por
   acertar. Las cifras `_p` dividen por el riesgo **planeado** (`|entry − SL|`), idéntico en los
   dos brazos por construcción. **El veredicto se juzga con `_p`.**
2. **Paso por el nivel.** `_limit_fill` del motor llena si la vela *toca* el precio, que es la
   hipótesis optimista: una orden en reposo necesita que el precio la atraviese o estar al frente
   de la cola (por eso existe T79). `through_bps` exige que el precio pase del nivel antes de dar
   la orden por llenada.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from eim.paper.engine import Outcome, Path, simulate
from eim.paper.ideas import Idea, to_limit  # noqa: F401 - se reexporta: la misma conversión
from eim.paper.params import ExecParams

RESOLVED = ("CERRADA", "CANCELADA", "RECHAZADA")


# `to_limit` se importa de `ideas.py`, donde vive junto a `Idea`: lo que esta medición compara y
# lo que `catalog.generate_ideas` despliega son la misma función, no dos copias. `through_bps` (el
# estrés de cola) solo lo usa esta medición; en producción va a 0.


@dataclass(frozen=True)
class Leg:
    """Lo que aporta una idea a su brazo, en R. Todo 0 si no llegó a haber operación."""

    filled: bool
    reason: str
    net: float = 0.0        # R sobre el riesgo realizado (lo que calcula el motor)
    gross: float = 0.0
    net_p: float = 0.0      # R sobre el riesgo planeado: mismo denominador en los dos brazos
    gross_p: float = 0.0
    cost_p: float = 0.0
    fee_p: float = 0.0
    slip_p: float = 0.0
    fund_p: float = 0.0
    risk: float = 0.0       # riesgo realizado, fracción del precio
    risk_planned: float = 0.0

    @property
    def won(self) -> bool:
        return self.filled and self.net_p > 0


def planned_risk(idea: Idea) -> float:
    """`|entry − SL|` en fracción del precio pedido. Igual en los dos brazos."""
    return abs(idea.entry - idea.sl) / idea.entry if idea.entry else 0.0


def leg_of(o: Outcome, risk_p: float) -> Leg:
    """Traduce un `Outcome` a su aportación en R. Una cancelación aporta 0, no se descarta."""
    if o.status != "CERRADA" or o.r is None or not o.risk or not risk_p:
        return Leg(False, o.reason or o.status)
    return Leg(
        True, o.reason,
        net=float(o.r), gross=float(o.gross / o.risk),
        net_p=float(o.net / risk_p), gross_p=float(o.gross / risk_p),
        cost_p=float((o.fee_in + o.fee_out + o.slip + o.funding) / risk_p),
        fee_p=float((o.fee_in + o.fee_out) / risk_p), slip_p=float(o.slip / risk_p),
        fund_p=float(o.funding / risk_p),
        risk=float(o.risk), risk_planned=float(risk_p),
    )


def pair_up(ideas: Sequence[Idea], path: Path, ep: ExecParams, bars: float,
            through_bps: float = 0.0) -> tuple[list[Leg], list[Leg], list[int], int]:
    """Simula cada idea en los dos brazos, una a una (sin «una viva por estrategia»).

    Devuelve (taker, maker, índices conservados, descartadas). Se descarta la pareja en la que
    algún brazo queda sin resolver al final del camino (ABIERTA o PENDIENTE): no se puede comparar
    lo que aún no ha pasado. Es mecánico, afecta igual a los dos brazos y el informe lo publica.
    """
    tk: list[Leg] = []
    mk: list[Leg] = []
    kept: list[int] = []
    dropped = 0
    for i, idea in enumerate(ideas):
        risk_p = planned_risk(idea)
        a = simulate(idea, path, ep)
        b = simulate(to_limit(idea, bars, through_bps), path, ep)
        if a.status not in RESOLVED or b.status not in RESOLVED:
            dropped += 1
            continue
        tk.append(leg_of(a, risk_p))
        mk.append(leg_of(b, risk_p))
        kept.append(i)
    return tk, mk, kept, dropped


def arm_stats(legs: Sequence[Leg]) -> dict:
    """Las dos lecturas del pre-registro: por intento (decide) y por llenado (descriptiva)."""
    n = len(legs)
    if not n:
        return {"intentos": 0, "llenadas": 0, "llenado_pct": 0.0}
    g = {k: np.array([getattr(x, k) for x in legs], dtype=float)
         for k in ("net", "net_p", "gross_p", "cost_p", "fee_p", "slip_p", "fund_p", "risk")}
    fill = np.array([x.filled for x in legs], dtype=bool)
    nf = int(fill.sum())
    wins = g["net_p"][fill] > 0 if nf else np.zeros(0, dtype=bool)
    gw = float(g["net_p"][fill][wins].sum()) if wins.any() else 0.0
    gl = float(g["net_p"][fill][~wins].sum()) if nf and (~wins).any() else 0.0
    return {
        "intentos": n, "llenadas": nf, "llenado_pct": 100.0 * nf / n,
        "no_llenada": sum(1 for x in legs if x.reason == "NO_LLENADA"),
        "objetivo_sin_llenar": sum(1 for x in legs if x.reason == "OBJETIVO_SIN_LLENAR"),
        # lectura A, por intento, con el denominador común: lo que decide
        "neto_r": float(g["net_p"].mean()), "bruto_r": float(g["gross_p"].mean()),
        "costo_r": float(g["cost_p"].mean()), "comision_r": float(g["fee_p"].mean()),
        "desliz_r": float(g["slip_p"].mean()), "funding_r": float(g["fund_p"].mean()),
        # el mismo neto con el riesgo realizado, para ver cuánto infla el denominador
        "neto_r_realizado": float(g["net"].mean()),
        "riesgo_medio": float(g["risk"][fill].mean()) if nf else 0.0,
        # lectura B, por llenado: descriptiva
        "neto_r_llenada": float(g["net_p"][fill].mean()) if nf else 0.0,
        "costo_r_llenada": float(g["cost_p"][fill].mean()) if nf else 0.0,
        "acierto_pct": 100.0 * float(wins.mean()) if nf else 0.0,
        "pf": (gw / abs(gl)) if gl else None,
        "salidas": _reasons(legs),
    }


def _reasons(legs: Sequence[Leg]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in legs:
        out[x.reason] = out.get(x.reason, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


CELLS = 4_000_000     # celdas por tanda del bootstrap: acota la RAM sin cambiar el resultado


def paired_delta(taker: Sequence[Leg], maker: Sequence[Leg], seed: int = 143,
                 draws: int = 5000) -> dict:
    """ΔE[R] neto por intento (maker − taker) con IC95 % bootstrap **emparejado**.

    Emparejado porque las dos muestras son las mismas decisiones: lo que se remuestrea es la
    diferencia por idea, no cada brazo por su lado. Usa el denominador común (`net_p`).

    Las remuestras salen **por tandas**. La matriz entera (`draws` × `n`) pide 8,4 GiB de
    índices y otros tantos al indexar con n = 224 814: más de lo que tiene el equipo, así que
    pedirla completa clavaba el trabajo contra la guarda de RAM de la cola. Por tandas el pico
    baja a decenas de MB y, como PCG64 llena fila a fila, el flujo de azar es el mismo: las
    cifras no cambian (lo fija `test_paired_delta_por_tandas_da_lo_mismo`).
    """
    d = np.array([m.net_p - t.net_p for t, m in zip(taker, maker, strict=True)], dtype=float)
    n = len(d)
    if n < 2:
        return {"delta": 0.0, "lo": 0.0, "hi": 0.0, "n": n, "se": 0.0}
    rng = np.random.default_rng(seed)
    means = np.empty(draws, dtype=float)
    step = max(1, CELLS // n)
    for i in range(0, draws, step):
        k = min(step, draws - i)
        means[i:i + k] = d[rng.integers(0, n, size=(k, n))].mean(axis=1)
    lo, hi = (float(x) for x in np.percentile(means, [2.5, 97.5]))
    return {"delta": float(d.mean()), "lo": lo, "hi": hi, "n": n,
            "se": float(d.std(ddof=1) / np.sqrt(n))}


def delta_split(taker: dict, maker: dict, delta: dict) -> dict:
    """Parte ΔE[R] en lo que viene de **no operar** y lo que viene de ahorrar ejecución.

    Una orden que no se llena aporta R = 0, y el intento medio pierde dinero: **abstenerse sube
    E[R] por sí solo**, sin ahorrar un céntimo de comisión. Sin separar las dos cosas, un brazo
    maker que se llena menos parece mejor justo por operar menos, y el estrés de cola (que baja el
    llenado a propósito) se leería al revés de como fue diseñado.

    La parte de no operar es `(llenado_taker − llenado_maker) × (−E[R] por llenada del taker)`: las
    decisiones que un brazo ejecutó y el otro no, valoradas a lo que de media cuesta ejecutarlas.
    """
    gap = (taker["llenado_pct"] - maker["llenado_pct"]) / 100.0
    no_trade = gap * (-taker["neto_r_llenada"])
    total = delta["delta"]
    return {"total": total, "no_operar": no_trade, "ejecucion": total - no_trade,
            "no_operar_pct": (100.0 * no_trade / total) if total else None,
            "llenado_menos_pp": 100.0 * gap}


def verdict(taker: dict, maker: dict, delta: dict, stable: bool,
            min_cost_drop: float = 0.04) -> dict:
    """El criterio de §4 del pre-registro, aplicado tal cual y sin margen de interpretación."""
    drop = taker["costo_r"] - maker["costo_r"]
    c1 = drop >= min_cost_drop
    c2 = delta["lo"] >= 0.0
    return {
        "costo_baja_r": drop, "c1_costo": bool(c1), "c2_neto": bool(c2), "c3_estable": bool(stable),
        "adopta": bool(c1 and c2 and stable),
        "motivo": _why(c1, c2, stable, drop, delta),
    }


def _why(c1: bool, c2: bool, c3: bool, drop: float, delta: dict) -> str:
    if c1 and c2 and c3:
        return (f"el costo baja {drop:.4f} R, el neto por intento mejora "
                f"{delta['delta']:+.4f} R con IC95 % [{delta['lo']:+.4f}, {delta['hi']:+.4f}] "
                "y el signo aguanta los tres plazos y los años")
    bits = []
    if not c1:
        bits.append(f"el costo solo baja {drop:.4f} R (hace falta 0,0400)")
    if not c2:
        bits.append(f"ΔE[R] neto por intento {delta['delta']:+.4f} R con IC95 % "
                    f"[{delta['lo']:+.4f}, {delta['hi']:+.4f}]: el límite inferior no llega a 0")
    if not c3:
        bits.append("el signo de ΔE[R] cambia entre plazos o entre años")
    return "no se adopta: " + "; ".join(bits)


def by_year(ideas: Sequence[Idea], taker: Sequence[Leg], maker: Sequence[Leg],
            kept: Sequence[int]) -> dict[str, dict]:
    """ΔE[R] neto por intento, año a año. `kept` son los índices de `ideas` que quedaron."""
    out: dict[str, list[float]] = {}
    for i, t, m in zip(kept, taker, maker, strict=True):
        out.setdefault(_year(ideas[i].t), []).append(m.net_p - t.net_p)
    return {y: {"n": len(v), "delta": float(np.mean(v))} for y, v in sorted(out.items())}


def _year(ms: int) -> str:
    import datetime as dt
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).strftime("%Y")
