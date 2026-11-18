"""Agente `intermarket` (T183): contexto de otros mercados para la cripto. Informante, sin I/O.

Lee del snapshot las velas diarias de los índices de EE. UU. (Nasdaq, S&P 500), del oro y de la
propia cripto. Dice si hay apetito o aversión al riesgo (impulso de 20 sesiones normalizado por la
volatilidad y tendencia sobre la media de 50) y cuánto se mueve hoy la cripto con los índices
(correlación de 60 sesiones). El sesgo = correlación positiva × impulso de los índices: con
correlación nula o negativa no hay nada que trasladar.

Nunca devuelve `degraded`: sin datos, viejos o insuficientes es `no_data` con el motivo. Así el
motor de riesgo (`max_degraded_agents`) y las alertas de agentes no lo cuentan, y la corrida de T31
no cambia. En la síntesis pesa 0 (`INFORMER_WEIGHTS`) hasta que la prueba de aporte marginal lo
mida, como cualquier agente nuevo desde T44.
"""

from __future__ import annotations

from eim.agents.base import no_data_report
from eim.agents.intermarket.compute import (
    DAY_MS,
    aligned_returns,
    closes_by_day,
    momentum,
    pearson,
    regime,
)
from eim.agents.intermarket.params import IntermarketParams
from eim.core import AgentReport, MarketSnapshot

NAMES = {"NASDAQ": "Nasdaq", "SP500": "S&P 500", "XAUUSDT": "Oro", "BTCUSDT": "BTC",
         "ETHUSDT": "ETH"}
ROLE_NOTE = ("Informante (T183): pesa 0 en la síntesis hasta que la prueba de aporte marginal "
             "lo mida; se muestra, no vota.")


def _fmt(x: float, d: int = 2) -> str:
    return f"{x:+.{d}f}".replace(".", ",")


class IntermarketAgent:
    id = "intermarket"
    version = "0.1.0"
    requires = {"intermarket"}

    def __init__(self, params: IntermarketParams | None = None) -> None:
        self.params = params or IntermarketParams()

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p, asof = self.params, snapshot.asof
        im = snapshot.intermarket or {}
        if not im:
            return no_data_report(self.id, self.version, asof,
                                  "sin velas de intermercado en el snapshot (aún no se "
                                  "sincronizó o EIM_INTERMARKET=0)")
        own = im.get(snapshot.symbol)
        if not own:
            return no_data_report(self.id, self.version, asof,
                                  f"sin velas diarias de {snapshot.symbol} para correlacionar")
        crypto = closes_by_day(own)
        eq: dict[str, dict] = {}
        corr: dict[str, float] = {}
        corr_n: dict[str, int] = {}
        missing: list[str] = []
        for key in p.equities:
            cs = im.get(key) or []
            if not cs or (asof - cs[-1].t) > p.stale_days * DAY_MS:
                missing.append(NAMES.get(key, key))
                continue
            m = momentum(cs, p.mom_days, p.vol_days, p.sma_days, p.z_scale)
            xs, ys = aligned_returns(cs[-(p.corr_days + 1) * 2:], crypto)
            xs, ys = xs[-p.corr_days:], ys[-p.corr_days:]
            r = pearson(xs, ys)
            if m is None or r is None or len(xs) < p.min_common:
                missing.append(NAMES.get(key, key))
                continue
            eq[key], corr[key], corr_n[key] = m, round(r, 4), len(xs)
        if not eq:
            return no_data_report(self.id, self.version, asof,
                                  "sin índices con datos recientes y sesiones suficientes "
                                  f"({', '.join(missing) or 'ninguno'})")
        haven_cs = im.get(p.haven) or []
        haven = (momentum(haven_cs, p.mom_days, p.vol_days, p.sma_days, p.z_scale)
                 if haven_cs and (asof - haven_cs[-1].t) <= p.stale_days * DAY_MS else None)
        eq_score = sum(m["score"] for m in eq.values()) / len(eq)
        ref = max(corr, key=lambda k: corr_n[k])          # el índice con más sesiones comunes
        rho = corr[ref]
        bias = max(-1.0, min(1.0, max(rho, 0.0) * eq_score))
        cover = min(1.0, corr_n[ref] / p.corr_days)
        conf = min(p.max_confidence, abs(rho) * cover)
        label = regime(eq_score, haven["score"] if haven else None, p.regime_band)
        step = (snapshot.candles[-1].t - snapshot.candles[-2].t
                if len(snapshot.candles) >= 2 else DAY_MS)
        name = NAMES.get(snapshot.symbol, snapshot.symbol)
        evidence = [f"{NAMES.get(k, k)} {p.mom_days} sesiones: {_fmt(m['ret_pct'], 1)} % "
                    f"(z {_fmt(m['z'])}, {'sobre' if m['above_sma'] else 'bajo'} su media de "
                    f"{p.sma_days})" for k, m in eq.items()]
        evidence.append(f"Correlación {name}–{NAMES.get(ref, ref)} ({corr_n[ref]} sesiones): "
                        f"{_fmt(rho)}")
        if haven:
            evidence.append(f"Oro {p.mom_days} sesiones: {_fmt(haven['ret_pct'], 1)} % "
                            f"(z {_fmt(haven['z'])})")
        evidence.append(f"Lectura: {label}" + ("; con correlación positiva el contexto se "
                                               "traslada a la cripto." if rho > 0 else
                                               "; sin correlación positiva no se traslada."))
        warnings = [ROLE_NOTE] + ([f"sin datos recientes de: {', '.join(missing)}"]
                                  if missing else [])
        if haven is None:
            warnings.append("sin velas recientes del oro: no se distingue la huida a refugio")
        assets = {**eq, **({p.haven: haven} if haven else {})}
        return AgentReport(
            agent_id=self.id, version=self.version, asof=asof, bias=round(bias, 4),
            confidence=round(conf, 4),
            horizon_bars=max(1, round(p.horizon_days * DAY_MS / max(step, 1))),
            evidence=evidence, warnings=warnings,
            metrics={"role": "informante", "regime": label, "equity_score": round(eq_score, 4),
                     "haven_score": haven["score"] if haven else None, "corr": corr,
                     "corr_sessions": corr_n, "corr_ref": ref, "assets": assets,
                     "sources": {k: v for k, v in snapshot.sources.items()
                                 if k.startswith("intermarket:")}},
        )
