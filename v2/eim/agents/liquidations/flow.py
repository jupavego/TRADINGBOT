"""Lectura del flujo de liquidaciones EN VIVO (Binance + Bybit + OKX) como sesgo y confianza.

Todo en relativo a lo normal del propio activo (z del log-notional por vela), porque Binance solo
publica la última liquidación de cada segundo (cota inferior) y las bolsas pesan distinto:
- cascada ACTIVA: el flujo forzado empuja en su dirección (longs liquidados → presión bajista).
- cascada AGOTADA (hubo pico y la vela actual ya está en calma): sesgo contrario, más débil.
- sin cascada: sesgo 0. La confianza baja con huecos de captura y sube si las bolsas coinciden.
Los pesos (`momentum_gain`, `reversal_gain`) son hipótesis: la puerta T49 decide su aporte.
"""

from __future__ import annotations

import math
import statistics as st

from eim.agents.base import no_data_report
from eim.agents.liquidations.params import LiquidationsParams
from eim.core import AgentReport, LiqBar, MarketSnapshot

LOWER_BOUND = ("Binance publica solo la última liquidación de cada segundo: su notional es una "
               "cota inferior; por eso se usa en relativo a lo normal, no como cifra absoluta")
UNCALIBRATED = "mapeo a sesgo sin calibrar: la puerta de edge (T49) decide el peso de esta señal"


def _z(values: list[float], base: list[float]) -> float:
    lb = [math.log1p(v) for v in base]
    sd = max(st.pstdev(lb), 0.5)
    return (math.log1p(sum(values) / len(values)) - st.fmean(lb)) / sd


def _imb(bars: list[LiqBar]) -> float:
    s, lg = sum(b.short_usd for b in bars), sum(b.long_usd for b in bars)
    return (s - lg) / (s + lg) if s + lg > 0 else 0.0


def _active_venues(bars: list[LiqBar], p: LiquidationsParams) -> int:
    """Bolsas con notional relevante en la ventana (confirmación cruzada)."""
    tot: dict[str, float] = {}
    for b in bars:
        for v, usd in b.by_venue.items():
            tot[v] = tot.get(v, 0.0) + usd
    return sum(usd >= p.min_venue_usd for usd in tot.values())


def flow_report(agent_id: str, version: str, snapshot: MarketSnapshot,
                p: LiquidationsParams) -> AgentReport:
    bars = snapshot.liq_flow or []
    asof = snapshot.asof
    if len(bars) < p.min_flow_bars:
        return no_data_report(agent_id, version, asof,
                              f"recolección de liquidaciones insuficiente "
                              f"({len(bars)}/{p.min_flow_bars} velas con el recolector vivo)")
    recent = bars[-p.recent_bars:]
    base = bars[:-p.recent_bars][-p.baseline_bars:]
    last_t = bars[-1].t
    window = [b for b in bars if b.t > last_t - 24 * (bars[-1].t - bars[-2].t)] or bars
    coverage = sum(b.complete for b in window) / len(window)
    tot = lambda bs: [b.long_usd + b.short_usd for b in bs]  # noqa: E731
    z = _z(tot(recent), tot(base))
    usd = sum(tot(recent))
    imb = _imb(recent)
    venues = sorted({v for b in recent for v in b.by_venue})
    metrics = {"state": "quiet", "z": round(z, 2), "imbalance": round(imb, 3),
               "recent_usd": usd, "long_usd": sum(b.long_usd for b in recent),
               "short_usd": sum(b.short_usd for b in recent), "venues": venues,
               "flow_bars": len(bars), "coverage": round(coverage, 3),
               "source": snapshot.sources.get("liq_flow", "liq_flow")}
    warnings = [LOWER_BOUND, UNCALIBRATED]
    if coverage < p.min_coverage:
        return AgentReport(agent_id=agent_id, version=version, asof=asof, bias=0, confidence=0,
                           horizon_bars=0, status="degraded", metrics=metrics,
                           warnings=[f"captura con huecos (cobertura {coverage:.0%} < "
                                     f"{p.min_coverage:.0%}): sin sesgo", *warnings])
    bias = conf = 0.0
    evidence = [f"Últimas {len(recent)} velas: {usd:,.0f} USD liquidados "
                f"(longs {metrics['long_usd']:,.0f} · shorts {metrics['short_usd']:,.0f}), "
                f"z={z:.1f} sobre lo normal de {len(base)} velas"]
    intensity = min(1.0, max(z, 0.0) / p.z_full)
    hist = bars[:-1]
    peak_recent = [b for b in bars[-p.exhaust_bars:-1]]
    peak_z = _z(tot(peak_recent), tot(hist[:-p.exhaust_bars][-p.baseline_bars:] or base)) \
        if peak_recent else 0.0
    if z >= p.z_active and usd >= p.min_flow_usd:
        metrics["state"] = "active"
        bias, conf = imb * p.momentum_gain * intensity, intensity
        evidence.append("cascada ACTIVA: el flujo forzado empuja en su dirección")
    elif (peak_recent and peak_z >= p.z_active and z <= p.z_calm
          and sum(tot(peak_recent)) >= p.min_flow_usd):
        metrics["state"] = "exhausted"
        bias, conf = -_imb(peak_recent) * p.reversal_gain, min(1.0, peak_z / p.z_full) * 0.6
        evidence.append("cascada AGOTADA: pico reciente y calma actual; sesgo contrario")
    else:
        evidence.append("sin cascada: liquidación dentro de lo normal")
    n_ven = _active_venues(recent, p)
    if conf and n_ven < 2:
        warnings.append("solo una bolsa con actividad relevante: confianza reducida")
    conf = conf * p.max_confidence * coverage * (1.0 if n_ven >= 2 else 0.6)
    bias = max(-1.0, min(1.0, bias))
    return AgentReport(agent_id=agent_id, version=version, asof=asof, bias=bias,
                       confidence=conf, horizon_bars=p.flow_horizon_bars if conf else 0,
                       evidence=evidence, metrics=metrics, warnings=warnings)
