"""Agente `levels`: zonas S/R, canal/rango y posición del precio respecto a ellos."""

from __future__ import annotations

import math

import numpy as np

from eim.agents.base import no_data_report
from eim.agents.levels.channel import Channel, fit_channel
from eim.agents.levels.params import LevelsParams
from eim.agents.levels.pivots import (
    Zone,
    atr,
    build_zones,
    find_pivots,
    select_zones,
)
from eim.core import AgentReport, MarketSnapshot, Overlay


def _px(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 1000 else f"{x:.2f}"


def _clamp(x: float, lim: float = 1.0) -> float:
    return max(-lim, min(lim, x))


class LevelsAgent:
    id = "levels"
    version = "1.0.0"
    requires = {"candles"}

    def __init__(self, params: LevelsParams | None = None) -> None:
        self.params = params or LevelsParams()

    # --- overlays -------------------------------------------------------
    def _zone_overlay(self, z: Zone, close: float, t: np.ndarray, src: str) -> Overlay:
        role = "resistencia" if z.mid >= close else "soporte"
        return Overlay(
            id=f"levels:zone:{z.mid:.2f}", agent_id=self.id, kind="zone",
            t_from=int(t[z.first_i]),
            geometry={"p_low": z.p_low, "p_high": z.p_high, "touches": z.touches,
                      "role": role},
            label=f"{role} ({z.touches} toques)",
            confidence=z.score / (z.score + 2),
            evidence=[f"{z.touches} toques en {_px(z.p_low)}–{_px(z.p_high)}; fuente {src}"],
        )

    def _channel_overlay(self, ch: Channel, t: np.ndarray, bar_ms: int, src: str) -> Overlay:
        n = len(t)
        i0, i1 = ch.start_i, n - 1 + self.params.extend_bars
        t1 = int(t[-1]) + self.params.extend_bars * bar_ms
        broken = ch.state != "INSIDE"
        name = "rango" if ch.kind == "range" else "canal"
        label = f"{name} roto" if broken else name
        conf = self._channel_conf(ch) * (0.5 if broken else 1.0)
        return Overlay(
            id=f"levels:{ch.kind}", agent_id=self.id, kind=ch.kind,  # type: ignore[arg-type]
            t_from=int(t[i0]), t_to=None,
            geometry={
                "upper": [(int(t[i0]), ch.upper(i0)), (t1, ch.upper(i1))],
                "lower": [(int(t[i0]), ch.lower(i0)), (t1, ch.lower(i1))],
                "slope_per_bar": ch.slope, "state": ch.state,
                "projected": "extendido hacia adelante (simulado)",
            },
            label=label, confidence=conf,
            evidence=[f"{label}: {ch.touches} toques, R² {ch.r2:.2f}; fuente {src}"],
        )

    @staticmethod
    def _channel_conf(ch: Channel) -> float:
        return 0.5 * ch.r2 + 0.5 * ch.touches / (ch.touches + 3)

    # --- sesgo ----------------------------------------------------------
    def _bias(self, ch: Channel | None, zones: list[Zone], close: float, a: float,
              n: int) -> tuple[float, float, dict]:
        pos = None
        chan_bias = 0.0
        if ch is not None:
            lo, up = ch.lower(n - 1), ch.upper(n - 1)
            pos = (close - lo) / (up - lo)
            if ch.state == "BROKEN_UP":
                chan_bias = 0.8
            elif ch.state == "BROKEN_DOWN":
                chan_bias = -0.8
            else:
                mr = -_clamp(2 * pos - 1) * (0.8 if ch.kind == "range" else 0.4)
                trend = 0.0 if ch.kind == "range" else 0.4 * (1 if ch.slope > 0 else -1)
                chan_bias = mr + trend
        sup = [z for z in zones if z.mid < close]
        res = [z for z in zones if z.mid >= close]
        d_sup = min((close - z.p_high for z in sup), default=None)
        d_res = min((z.p_low - close for z in res), default=None)
        prox = lambda d: 0.0 if d is None else math.exp(-max(0.0, d) / (2 * a))  # noqa: E731
        zone_bias = prox(d_sup) - prox(d_res)
        bias = _clamp(0.6 * chan_bias + 0.4 * zone_bias) if ch else _clamp(0.8 * zone_bias)
        parts: list[float] = []
        if ch is not None:
            parts.append(self._channel_conf(ch) * (0.5 if ch.state != "INSIDE" else 1.0))
        if zones:
            parts.append(max(z.score / (z.score + 2) for z in zones))
        conf = min(self.params.max_confidence, sum(parts) / max(1, len(parts)) * 0.9)
        info = {"channel_pos": pos, "dist_support": d_sup, "dist_resistance": d_res}
        return bias, conf, info

    # --- run ------------------------------------------------------------
    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        n = len(snapshot.candles)
        if n < p.min_bars:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  f"velas insuficientes: {n} < {p.min_bars}")
        src = snapshot.sources.get("candles", "desconocida")
        cs = snapshot.candles
        t = np.array([c.t for c in cs], dtype=np.int64)
        h = np.array([c.h for c in cs])
        lo = np.array([c.l for c in cs])
        c = np.array([c.c for c in cs])
        v = np.array([x.v for x in cs])
        a = atr(h, lo, c, p.atr_period)
        close = float(c[-1])
        bar_ms = int(np.median(np.diff(t))) if n > 1 else 0
        if a <= 0:
            return no_data_report(self.id, self.version, snapshot.asof, "ATR nulo: serie plana")

        pivots = find_pivots(h, lo, v, p.pivot_n)
        zones = select_zones(
            build_zones(pivots, n, a, float(np.median(v)), p), close, p)
        ch = fit_channel(pivots, c, a, p)
        bias, conf, info = self._bias(ch, zones, close, a, n)

        evidence = [f"{z.touches} toques en {_px(z.p_low)}–{_px(z.p_high)} "
                    f"({'resistencia' if z.mid >= close else 'soporte'})" for z in zones]
        if ch is None:
            evidence.append("Sin canal ni rango definido en la ventana reciente")
        else:
            name = "Rango lateral" if ch.kind == "range" else (
                f"Canal {'alcista' if ch.slope > 0 else 'bajista'}")
            evidence.append(f"{name}: {ch.touches} toques, R² {ch.r2:.2f}")
            if info["channel_pos"] is not None and ch.state == "INSIDE":
                evidence.append(f"Precio al {info['channel_pos'] * 100:.0f}% del "
                                f"{'rango' if ch.kind == 'range' else 'canal'} (0%=piso)")
            if ch.state != "INSIDE":
                side = "arriba" if ch.state == "BROKEN_UP" else "abajo"
                evidence.append(f"{name} roto: {p.break_bars} cierres fuera por {side}")
        for k, lab in (("dist_support", "soporte"), ("dist_resistance", "resistencia")):
            if info[k] is not None:
                evidence.append(f"A {info[k] / a:.1f} ATR de la {lab} más cercana")

        overlays = [self._zone_overlay(z, close, t, src) for z in zones]
        if ch is not None:
            overlays.append(self._channel_overlay(ch, t, bar_ms, src))
        warnings = []
        if not zones:
            warnings.append("sin zonas con ≥2 toques")
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof, bias=bias,
            confidence=conf if (zones or ch) else 0.0, horizon_bars=p.horizon_bars,
            evidence=evidence,
            metrics={
                "atr": a, "zones": [
                    {"p_low": z.p_low, "p_high": z.p_high, "touches": z.touches,
                     "score": z.score} for z in zones],
                "channel": None if ch is None else {
                    "kind": ch.kind, "slope_per_bar": ch.slope, "r2": ch.r2,
                    "touches": ch.touches, "state": ch.state},
                **info, "bars": n, "source": src,
                "coverage": snapshot.coverage.get("candles"),
            },
            warnings=warnings, overlays=overlays,
            status="ok" if (zones or ch) else "degraded",
        )
