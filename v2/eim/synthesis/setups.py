"""Operaciones intradía sugeridas (entrada límite, SL, TP) a partir del análisis de los agentes.

Funciones puras. Insumos: niveles que dibujan los agentes (zonas y niveles), la síntesis
(dirección y confianza) y la volatilidad reciente. Modelo: el precio como paseo aleatorio con
la deriva de la síntesis (`drift_of`, la misma que inclina la proyección de T17). Con él se
estiman, para cada candidata, la probabilidad de que se llene la orden límite, la de tocar el
TP antes que el SL y el tiempo esperado de resolución.

Orden (heurístico, explícito): alineación con la síntesis × prob. de llenado × confluencia
(cuántos agentes marcan un nivel en la entrada) × (1 + valor esperado en R) × √P(TP).
Las probabilidades son ESTIMACIONES de un modelo, no frecuencias calibradas. Siempre ANALISIS.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from eim.core import AgentReport, Synthesis
from eim.synthesis.params import SynthesisParams
from eim.synthesis.synth import drift_of


class SetupParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_hours: float = 4.0          # horizonte intradía: resolución esperada entre 4 h …
    max_hours: float = 36.0         # … y día y medio
    fill_hours: float = 12.0        # ventana para que se llene la orden límite
    pullbacks_atr: tuple[float, ...] = (0.25, 0.5, 1.0)  # entradas por retroceso
    max_entry_atr: float = 3.0      # niveles más lejos que esto no sirven de entrada
    sl_buffer_atr: float = 0.3      # colchón más allá del nivel de invalidación
    min_sl_atr: float = 0.6
    max_sl_atr: float = 2.5
    fallback_sl_atr: float = 1.2    # SL por volatilidad si no hay nivel estructural útil
    r_targets: tuple[float, ...] = (1.5, 2.0, 3.0)  # TP por múltiplos de riesgo
    tp_front_atr: float = 0.1       # el TP se adelanta a la zona objetivo
    min_rr: float = 1.2
    fee_rate: float = 0.0007        # comisión ida y vuelta supuesta (taker+maker, Binance VIP 0)
    dedupe_atr: float = 0.5         # dos sugerencias del mismo lado deben separarse esto
    confluence_atr: float = 0.25    # un nivel confirma la entrada si está a menos de esto
    confluence_w: float = 0.5       # peso de cada agente que confirma (máx. `confluence_cap`)
    confluence_cap: int = 4
    align_k: float = 2.0            # cuánto pesa ir a favor del sesgo·confianza de la síntesis
    min_align: float = 0.1
    top: int = 3


class Setup(BaseModel):
    model_config = ConfigDict(frozen=True)

    side: Literal["long", "short"]
    entry: float
    sl: float
    tp: float
    rr: float
    p_fill: float           # prob. estimada de llenar la límite en `fill_hours`
    p_tp: float             # prob. estimada de tocar TP antes que SL (una vez dentro)
    ev_r: float             # valor esperado en R (neto de comisiones), una vez dentro
    confluence: int         # agentes con un nivel en la entrada
    score: float            # criterio de orden (ver docstring del módulo)
    hours: float            # tiempo esperado de resolución (h)
    entry_basis: str
    sl_basis: str
    tp_basis: str
    aligned: bool           # va a favor del sesgo de la síntesis


@dataclass(frozen=True)
class Level:
    low: float
    high: float
    label: str
    agent: str


def levels_of(reports: list[AgentReport]) -> list[Level]:
    """Zonas y niveles horizontales que dibujan todos los agentes."""
    out: list[Level] = []
    for r in reports:
        for o in r.overlays:
            g = o.geometry
            if o.kind == "zone" and "p_low" in g and "p_high" in g:
                out.append(Level(float(g["p_low"]), float(g["p_high"]),
                                 f"{r.agent_id}: {o.label}", r.agent_id))
            elif o.kind == "level" and "p" in g:
                out.append(Level(float(g["p"]), float(g["p"]), f"{r.agent_id}: {o.label}",
                                 r.agent_id))
    return out


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def touch_prob(dist: float, mu: float, sigma: float, hours: float) -> float:
    """P(recorrer `dist` (>0) en `hours`) con deriva `mu` a favor y vol. `sigma` por hora."""
    if dist <= 0:
        return 1.0
    s = sigma * math.sqrt(hours)
    a = _phi((-dist + mu * hours) / s)
    k = 2 * mu * dist / sigma**2
    b = math.exp(k) * _phi((-dist - mu * hours) / s) if k < 50 else 0.0
    return min(1.0, a + b)


def hit_first(up: float, down: float, mu: float, sigma: float) -> float:
    """P(tocar +up antes que −down) con deriva `mu` (hacia +) y vol. `sigma` (mismas unidades)."""
    k = 2 * mu / sigma**2
    if abs(k * (up + down)) < 1e-9:
        return down / (up + down)
    return (1 - math.exp(-k * down)) / (1 - math.exp(-k * (up + down)))


def confluence(price: float, levels: list[Level], tol: float) -> int:
    """Agentes distintos con un nivel a menos de `tol` del precio."""
    return len({lv.agent for lv in levels if lv.low - tol <= price <= lv.high + tol})


def _cands(side: int, close: float, a: float, levels: list[Level], p: SetupParams):
    """(entrada, base) candidatas para un lado: retrocesos por ATR y bordes de nivel."""
    out = [(close - side * k * a, f"retroceso {k:g} ATR") for k in p.pullbacks_atr]
    for lv in levels:
        edge = lv.high if side > 0 else lv.low
        d = (close - edge) * side
        if 0.1 * a < d <= p.max_entry_atr * a:
            out.append((edge, lv.label))
    return out


def _stops(side: int, entry: float, a: float, levels: list[Level], p: SetupParams):
    out = []
    for lv in levels:
        far = lv.low if side > 0 else lv.high
        sl = far - side * p.sl_buffer_atr * a
        if p.min_sl_atr * a <= (entry - sl) * side <= p.max_sl_atr * a:
            out.append((sl, f"tras {lv.label}"))
    out.append((entry - side * p.fallback_sl_atr * a, f"{p.fallback_sl_atr:g} ATR"))
    return out


def _targets(side: int, entry: float, risk: float, a: float, levels: list[Level], p: SetupParams):
    out = [(entry + side * k * risk, f"{k:g} R") for k in p.r_targets]
    for lv in levels:
        near = lv.low if side > 0 else lv.high
        tp = near - side * p.tp_front_atr * a
        if (tp - entry) * side >= p.min_rr * risk:
            out.append((tp, f"antes de {lv.label}"))
    return out


def suggest(close: float, sigma_h: float, a: float, levels: list[Level], syn: Synthesis | None,
            p: SetupParams | None = None, sp: SynthesisParams | None = None,
            bar_hours: float = 1.0) -> list[Setup]:
    """Mejores `p.top` operaciones intradía. `sigma_h`: desviación del precio por hora (USDT);
    `a`: ATR del marco; `bar_hours`: horas por vela (para pasar la deriva a horas)."""
    p = p or SetupParams()
    if close <= 0 or sigma_h <= 0 or a <= 0:
        return []
    # deriva de la síntesis (log-retorno por vela) → USDT por hora
    sig_bar = sigma_h * math.sqrt(bar_hours) / close
    mu_h = (drift_of(syn, sig_bar, sp) or 0.0) * close / bar_hours
    found: list[dict] = []
    for side in (1, -1):
        mu = mu_h * side  # deriva a favor de la operación
        lean = syn.bias * syn.confidence * side if syn else 0.0
        align = max(p.min_align, 1 + p.align_k * lean)
        for entry, eb in _cands(side, close, a, levels, p):
            p_fill = touch_prob((close - entry) * side, -mu, sigma_h, p.fill_hours)
            conf = confluence(entry, levels, p.confluence_atr * a)
            weight = align * p_fill * (1 + p.confluence_w * min(conf, p.confluence_cap))
            for sl, sb in _stops(side, entry, a, levels, p):
                risk = (entry - sl) * side
                for tp, tb in _targets(side, entry, risk, a, levels, p):
                    reward = (tp - entry) * side
                    rr = reward / risk
                    hours = reward * risk / sigma_h**2
                    if rr < p.min_rr or not p.min_hours <= hours <= p.max_hours:
                        continue
                    p_tp = hit_first(reward, risk, mu, sigma_h)
                    fee_r = p.fee_rate * entry / risk
                    ev = p_tp * rr - (1 - p_tp) - fee_r
                    found.append(dict(
                        side="long" if side > 0 else "short", entry=entry, sl=sl, tp=tp, rr=rr,
                        p_fill=p_fill, p_tp=p_tp, ev_r=ev, confluence=conf,
                        score=weight * max(0.0, 1 + ev) * math.sqrt(p_tp), hours=hours,
                        entry_basis=eb, sl_basis=sb, tp_basis=tb,
                        aligned=syn is not None and syn.bias * side > 0))
    found.sort(key=lambda s: s["score"], reverse=True)
    picked: list[dict] = []
    for s in found:
        if all(s["side"] != q["side"] or abs(s["entry"] - q["entry"]) >= p.dedupe_atr * a
               for q in picked):
            picked.append(s)
        if len(picked) == p.top:
            break
    return [Setup(**s) for s in picked]
