"""Agente `liquidations`: consume liquidaciones ya presentes en el snapshot (sin I/O).

Si el dato está obsoleto (Binance dejó de publicar en octubre de 2024) devuelve
`status="degraded"` sin sesgo: un mapa histórico no describe el mercado actual.
"""

from __future__ import annotations

from datetime import UTC, datetime

from eim.agents.base import no_data_report
from eim.agents.liquidations.flow import flow_report
from eim.agents.liquidations.params import LiquidationsParams
from eim.core import AgentReport, MarketSnapshot, Overlay

_DAY_MS = 86_400_000


class LiquidationsAgent:
    id = "liquidations"
    version = "2.0.0"
    requires = {"liq_flow", "liquidations"}

    def __init__(self, params: LiquidationsParams | None = None) -> None:
        self.params = params or LiquidationsParams()

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        if snapshot.liq_flow:  # flujo en vivo: fuente vigente (el histórico está retirado)
            return flow_report(self.id, self.version, snapshot, p)
        liq = snapshot.liquidations
        if liq is None or not liq.daily:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  "sin liquidaciones en el snapshot")
        latest = datetime.strptime(liq.most_recent_date, "%Y-%m-%d").replace(tzinfo=UTC)
        age = (snapshot.asof - int(latest.timestamp() * 1000)) // _DAY_MS
        stale = liq.stale or age > p.stale_days
        metrics = {
            "requested_symbol": liq.requested_symbol, "liquidation_symbol": liq.liquidation_symbol,
            "most_recent_date": liq.most_recent_date, "stale": stale,
            "stale_age_days": max(age, liq.stale_age_days) if stale else age,
            "days_with_data": liq.days_with_data, "source": liq.source,
        }
        proxy = (f"{liq.liquidation_symbol} (coin-margined) es un contrato distinto de "
                 f"{liq.requested_symbol}: proxy correlacionado, no idéntico")
        if stale:
            return AgentReport(
                agent_id=self.id, version=self.version, asof=snapshot.asof, bias=0, confidence=0,
                horizon_bars=0, status="degraded", metrics=metrics, warnings=[
                    f"dataset obsoleto: último archivo {liq.most_recent_date} "
                    f"({metrics['stale_age_days']} días); Binance dejó de publicarlo en octubre "
                    f"de 2024 — histórico, NO es el mercado actual; sin sesgo",
                    proxy,
                ],
            )
        window = liq.daily[-p.lookback_days:]
        longs = sum(d.longs_usd for d in window)
        shorts = sum(d.shorts_usd for d in window)
        total = longs + shorts
        metrics |= {"window_days": len(window), "longs_usd": longs, "shorts_usd": shorts}
        warnings = [proxy]
        bias = confidence = 0.0
        evidence = [f"Liquidado en {len(window)} días: longs {longs:,.0f} USD, "
                    f"shorts {shorts:,.0f} USD"]
        if total < p.min_total_usd:
            warnings.append(f"notional liquidado bajo ({total:,.0f} < {p.min_total_usd:,.0f} USD): "
                            "sin sesgo")
        else:
            # Shorts liquidados = compras forzadas (presión alcista); longs = ventas forzadas.
            bias = (shorts - longs) / total
            confidence = min(p.max_confidence, p.max_confidence * len(window) / p.lookback_days)
        t0 = window[0].t
        top = sorted(liq.levels, key=lambda lv: lv.longs_usd + lv.shorts_usd,
                     reverse=True)[:p.top_levels]
        overlays = [
            Overlay(id=f"liquidations:level:{i}", agent_id=self.id, kind="level", t_from=t0,
                    geometry={"p": lv.price, "longs_usd": lv.longs_usd,
                              "shorts_usd": lv.shorts_usd},
                    label=f"Liquidaciones {lv.longs_usd + lv.shorts_usd:,.0f} USD",
                    confidence=confidence,
                    evidence=[f"nivel con más notional liquidado; fuente {liq.source}"])
            for i, lv in enumerate(top)
        ]
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof, bias=bias,
            confidence=confidence, horizon_bars=p.horizon_bars, evidence=evidence,
            metrics=metrics, warnings=warnings, overlays=overlays,
        )
