"""Agente `price_action`: sesgo desde estructura de mercado y patrones de vela recientes."""

from __future__ import annotations

from eim.agents.base import no_data_report
from eim.agents.price_action.compute import compute_price_action
from eim.agents.price_action.params import PriceActionParams
from eim.agents.structure.agent import snapshot_frame
from eim.core import AgentReport, MarketSnapshot, Overlay

_BULL = ("BULLISH_ENGULFING", "HAMMER")
_BEAR = ("BEARISH_ENGULFING", "SHOOTING_STAR")
_STATE_SIGN = {"BULLISH": 1.0, "BEARISH": -1.0, "UNDEFINED": 0.0}


class PriceActionAgent:
    id = "price_action"
    version = "1.0.0"
    requires = {"candles"}

    def __init__(self, params: PriceActionParams | None = None) -> None:
        self.params = params or PriceActionParams()

    def _zones(self, zones: list[dict], close: float, t0: int, src: str) -> list[Overlay]:
        p = self.params
        keep = [z for z in zones if z["touches"] >= p.zone_min_touches]
        keep = sorted(keep, key=lambda z: abs(z["price"] - close))[: p.max_zones]
        half = p.sr_tolerance_pct / 200
        out = []
        for z in sorted(keep, key=lambda z: z["price"]):
            role = "resistencia" if z["price"] > close else "soporte"
            out.append(Overlay(
                id=f"price_action:zone:{z['price']:.2f}", agent_id=self.id, kind="zone",
                t_from=t0, geometry={"p_low": z["price"] * (1 - half),
                                     "p_high": z["price"] * (1 + half),
                                     "touches": z["touches"], "role": role},
                label=f"{role} ({z['touches']} toques)",
                confidence=z["touches"] / (z["touches"] + 3),
                evidence=[f"clustering de pivotes ±{p.sr_tolerance_pct}%; fuente {src}"],
            ))
        return out

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        n = len(snapshot.candles)
        if n < p.min_bars:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  f"velas insuficientes: {n} < {p.min_bars}")
        src = snapshot.sources.get("candles", "desconocida")
        df, zones, (hl, ll) = compute_price_action(
            snapshot_frame(snapshot), p.fractal_n, p.sr_tolerance_pct)
        state = df["STRUCTURE_STATE"].iloc[-1]
        events = df["STRUCTURE_EVENT"].to_numpy()
        last_idx = next((i for i in range(n - 1, -1, -1) if events[i] != "NONE"), None)
        age = None if last_idx is None else n - 1 - last_idx

        recent = df.iloc[-p.pattern_lookback:]
        bulls = int(recent[list(_BULL)].to_numpy().sum())
        bears = int(recent[list(_BEAR)].to_numpy().sum())
        pat = (bulls - bears) / max(1, bulls + bears)
        w = p.structure_weight
        bias = max(-1.0, min(1.0, w * _STATE_SIGN[state] + (1 - w) * pat))

        fresh = age is not None and age <= p.event_lookback
        confidence = 0.0
        if state != "UNDEFINED":
            confidence = 0.3 + (0.2 if fresh else 0.0) + (0.1 if bulls + bears else 0.0)
        confidence = min(p.max_confidence, confidence)

        evidence = [f"Estructura {state}; último swing alto {hl or 'n/d'}, bajo {ll or 'n/d'}"]
        if last_idx is not None:
            evidence.append(f"Último evento {events[last_idx]} hace {age} velas")
        evidence.append(f"Patrones en las últimas {p.pattern_lookback} velas: "
                        f"{bulls} alcistas, {bears} bajistas")
        warnings = [] if state != "UNDEFINED" else ["estructura indefinida: sin swings rotos"]
        t0 = int(df["timestamp"].iloc[0].timestamp() * 1000)
        close = float(df["close"].iloc[-1])
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof, bias=bias,
            confidence=confidence, horizon_bars=p.horizon_bars, evidence=evidence,
            metrics={
                "structure_state": state,
                "last_event": None if last_idx is None else events[last_idx],
                "last_event_age": age, "last_swing_high": hl, "last_swing_low": ll,
                "bullish_patterns": bulls, "bearish_patterns": bears,
                "sr_zones": zones, "bars": n, "source": src,
                "coverage": snapshot.coverage.get("candles"),
            },
            warnings=warnings, overlays=self._zones(zones, close, t0, src),
            status="ok" if state != "UNDEFINED" else "degraded",
        )
