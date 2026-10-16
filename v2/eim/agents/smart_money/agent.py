"""Agente `smart_money` (T41): posición neta de los líderes aprobados en la moneda del snapshot.

Solo vota quien pasó el scorecard (`snapshot.leader_weights`, verificado adelante y copiable).
Cada líder aporta su postura `tanh(exposición / escala)` (exposición = nocional neto en la
moneda / valor de su cuenta) con peso = su calidad, normalizado y **limitado** a
`max_leader_share`: un líder no domina (solo, mueve el sesgo como mucho ±0,4). Un aprobado
sin posición en la moneda vota neutral. Confianza = calidad media × acuerdo × cobertura
(líderes / `full_leaders`) × frescura de las fotos. No entra en la síntesis hasta T44.
"""

from __future__ import annotations

import math
from statistics import median

from eim.agents.base import no_data_report
from eim.agents.smart_money.params import SmartMoneyParams
from eim.core import AgentReport, LeaderPosition, LeaderWeight, MarketSnapshot

NO_BOARD = ("sin tablero de líderes vigente (≤ 10 min): el vigilante `python -m eim.leaders "
            "run` está apagado o aún no evaluó")
NO_APPROVED = ("ningún líder aprobado por el scorecard (T41): sin señal; ver pestaña «Líderes» "
               "para los motivos")
_UNIT_MS = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}


def _tf_ms(tf: str) -> int | None:
    try:
        return int(tf[:-1]) * _UNIT_MS[tf[-1]]
    except (KeyError, ValueError, IndexError):
        return None


def _usd(x: float, sign: bool = True) -> str:
    """Miles con espacio y sin decimales (la coma es el separador decimal en la interfaz)."""
    return (f"{x:+,.0f}" if sign else f"{x:,.0f}").replace(",", " ")


def _d(x: float, nd: int = 2, sign: bool = False) -> str:
    return (f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}").replace(".", ",")


def _signed(x: LeaderPosition) -> float:
    return x.size if x.side == "long" else -x.size


class SmartMoneyAgent:
    id = "smart_money"
    version = "0.1.0"
    requires = {"leaders"}

    def __init__(self, params: SmartMoneyParams | None = None) -> None:
        self.params = params or SmartMoneyParams()

    def coin(self, symbol: str) -> str:
        for suf in self.params.quote_suffixes:
            if symbol.endswith(suf) and len(symbol) > len(suf):
                return symbol[: -len(suf)]
        return symbol

    def _row(self, w: LeaderWeight, pos: list[LeaderPosition], coin: str,
             price: float | None, age: int) -> dict:
        p = self.params
        mine = [x for x in pos if x.leader_id == w.leader_id]
        here = [x for x in mine if x.symbol == coin]
        px = price or (here[0].entry if here else None)
        size = sum(_signed(x) for x in here)
        notional = size * px if px else 0.0
        if w.account_value:
            base, basis = w.account_value, "cuenta"
        else:
            base = sum(x.size * (px if x.symbol == coin and px else x.entry) for x in mine)
            basis = "cartera"
        exposure = notional / base if base else 0.0
        fresh = 1.0 if age <= p.fresh_ms else max(0.0, 1 - (age - p.fresh_ms) / (
            p.stale_ms - p.fresh_ms or 1))
        return {"leader_id": w.leader_id, "label": w.label, "quality": w.quality,
                "side": "long" if size > 0 else "short" if size < 0 else "plano",
                "size": size, "notional_usd": round(notional, 2),
                "entry": here[0].entry if len(here) == 1 else None,
                "leverage": here[0].leverage if len(here) == 1 else None,
                "unrealized_pnl": sum(x.unrealized_pnl or 0.0 for x in here) if here else None,
                "exposure": round(exposure, 4), "exposure_basis": basis,
                "stance": round(math.tanh(exposure / p.exposure_scale), 4),
                "age_s": round(age / 1000, 1), "fresh": round(fresh, 3), "hold_ms": w.hold_ms,
                "changes": [{"window_h": c.window_h, "from": c.from_size, "to": c.to_size,
                             "delta": c.delta} for c in w.changes if c.symbol == coin]}

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p, asof = self.params, snapshot.asof
        if snapshot.leaders is None or snapshot.leader_weights is None:
            return no_data_report(self.id, self.version, asof, NO_BOARD)
        if not snapshot.leader_weights:
            return no_data_report(self.id, self.version, asof, NO_APPROVED)
        coin = self.coin(snapshot.symbol)
        price = snapshot.candles[-1].c if snapshot.candles else None
        rows, stale = [], []
        for w in snapshot.leader_weights:
            age = asof - w.positions_at if w.positions_at is not None else None
            if age is None or age > p.stale_ms:
                stale.append(w.leader_id)
                continue
            rows.append(self._row(w, snapshot.leaders, coin, price, max(age, 0)))
        if not rows:
            return no_data_report(self.id, self.version, asof,
                                  f"fotos de posiciones de {len(stale)} aprobados con más de "
                                  f"{p.stale_ms // 60_000} min: no votan")
        total_q = sum(r["quality"] for r in rows) or 1.0
        for r in rows:
            r["weight"] = round(min(r["quality"] / total_q, p.max_leader_share), 4)
        wsum = sum(r["weight"] for r in rows)
        bias = max(-1.0, min(1.0, sum(r["weight"] * r["stance"] for r in rows)))
        spread = sum(r["weight"] * abs(r["stance"]) for r in rows)
        agreement = abs(bias) / spread if spread > 0 else 0.0
        quality = sum(r["weight"] * r["quality"] for r in rows) / wsum
        freshness = sum(r["weight"] * r["fresh"] for r in rows) / wsum
        coverage = min(1.0, len(rows) / p.full_leaders)
        confidence = quality * agreement * coverage * freshness
        holds = [r["hold_ms"] for r in rows if r["hold_ms"]]
        bar = _tf_ms(snapshot.timeframe) or p.default_hold_ms
        horizon = round((median(holds) if holds else p.default_hold_ms) / bar)
        horizon = max(p.horizon_min_bars, min(p.horizon_max_bars, horizon))
        longs = sum(r["notional_usd"] for r in rows if r["notional_usd"] > 0)
        shorts = -sum(r["notional_usd"] for r in rows if r["notional_usd"] < 0)
        in_coin = [r for r in rows if r["side"] != "plano"]
        warnings = ([f"{len(stale)} aprobados sin foto vigente (> {p.stale_ms // 60_000} min): "
                     "no votan"] if stale else [])
        if coverage < 1:
            warnings.append(f"solo {len(rows)} líder(es) aprobado(s) de {p.full_leaders} para "
                            f"cobertura plena: peso máximo por líder {p.max_leader_share:.0%}")
        evidence = [
            f"{len(rows)} líderes aprobados votan; {len(in_coin)} con posición en {coin}",
            f"exposición neta {_usd(longs - shorts)} USD (long {_usd(longs, False)} / short "
            f"{_usd(shorts, False)})",
            f"acuerdo {agreement:.0%}, calidad media {_d(quality)}, peso máx. por líder "
            f"{max(r['weight'] for r in rows):.0%}",
        ] + [f"{r['label'] or r['leader_id'][-8:]}: {r['side']} {_usd(r['notional_usd'])} USD "
             f"(exposición {_d(r['exposure'], sign=True)} de la {r['exposure_basis']}, peso "
             f"{r['weight']:.0%})" for r in in_coin[:5]]
        metrics = {
            "mode": "ANALISIS", "coin": coin, "price": price, "n_approved": len(rows),
            "n_stale": len(stale), "n_in_coin": len(in_coin),
            "net_exposure_usd": round(longs - shorts, 2), "long_usd": round(longs, 2),
            "short_usd": round(shorts, 2), "agreement": round(agreement, 4),
            "quality": round(quality, 4), "coverage": round(coverage, 4),
            "freshness": round(freshness, 4), "max_leader_share": p.max_leader_share,
            "leaders": rows,
            "changes": [dict(c, leader_id=r["leader_id"]) for r in rows for c in r["changes"]],
            "source": snapshot.sources.get("leaders", "desconocida"),
            "coverage_t": snapshot.coverage.get("leaders"),
        }
        return AgentReport(
            agent_id=self.id, version=self.version, asof=asof, bias=round(bias, 4),
            confidence=round(max(0.0, min(1.0, confidence)), 4), horizon_bars=horizon,
            evidence=evidence, metrics=metrics, warnings=warnings,
            status="degraded" if stale else "ok")
