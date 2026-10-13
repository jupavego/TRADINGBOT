"""Agente `derivatives`: lee funding, open interest (y, si hay, long/short y basis).

Reglas (cada una deja su evidencia en el reporte; z = z-score contra la historia disponible
en el snapshot, `change_bars` = ventana del cambio; "alto" = z ≥ `z_high`):

1. Precio↑ + OI↑ + funding alto → apalancamiento largo saturado: sesgo bajista (riesgo de
   *long squeeze*), con advertencia.
2. Precio↑ + OI↑ + funding no alto → tendencia con posiciones nuevas: sesgo alcista moderado.
3. Precio↓ + OI↑ + funding muy negativo (z ≤ −`z_high`) → cortos saturados: sesgo alcista
   (riesgo de *short squeeze*), con advertencia.
4. Precio↓ + OI↑ + funding no extremo → cortos abriendo: sesgo bajista moderado.
5. Precio↓ + OI↓ → cierre de posiciones (liquidación/capitulación): sesgo 0, solo evidencia.
6. Precio↑ + OI↓ → cobertura de cortos: rally débil, sesgo alcista leve.
Ajustes contrarian (±`modifier_bias`): long/short con z alto resta, con z muy bajo suma; basis
con z alto resta, con z muy bajo suma. Sin funding o sin OI → `no_data`; sin L/S o basis
solo se avisa de la cobertura. Función pura: sin red ni disco.
"""

from __future__ import annotations

from statistics import fmean, pstdev

from eim.agents.base import no_data_report
from eim.agents.derivatives.params import DerivativesParams
from eim.core import AgentReport, MarketSnapshot


def _z(value: float, history: list[float]) -> float | None:
    sd = pstdev(history) if len(history) > 1 else 0.0
    return None if sd == 0 else (value - fmean(history)) / sd


def _changes(vals: list[float], k: int) -> list[float]:
    return [vals[i] / vals[i - k] - 1 for i in range(k, len(vals)) if vals[i - k] > 0]


class DerivativesAgent:
    id = "derivatives"
    version = "1.0.0"
    requires = {"candles", "funding", "open_interest"}

    def __init__(self, params: DerivativesParams | None = None) -> None:
        self.params = params or DerivativesParams()

    def _opt_z(self, series, name: str, warnings: list[str]) -> float | None:
        p = self.params
        if not series or len(series) < p.min_series_points:
            warnings.append(f"sin {name} suficiente (cobertura "
                            f"{len(series) if series else 0}/{p.min_series_points}): no se usa")
            return None
        vals = [v for _, v in series]
        return _z(vals[-1], vals[:-1])

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        k = p.change_bars
        if len(snapshot.candles) <= k:
            return no_data_report(self.id, self.version, snapshot.asof, "velas insuficientes")
        if not snapshot.funding or len(snapshot.funding) < p.min_funding_points:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  "funding ausente o insuficiente")
        oi = snapshot.open_interest
        if not oi or len(oi) < p.min_oi_points:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  "open interest ausente o insuficiente")
        oi_changes = _changes([v for _, v in oi], k)
        fvals = [v for _, v in snapshot.funding]
        fz = _z(fvals[-1], fvals[:-1])
        oz = _z(oi_changes[-1], oi_changes[:-1]) if len(oi_changes) > 2 else None
        if fz is None or oz is None:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  "series de derivados sin variación (z-score indefinido)")

        warnings: list[str] = []
        c = snapshot.candles
        step = c[-1].t - c[-2].t
        stale = c[-1].t - oi[-1][0] > p.max_stale_bars * step
        if stale:
            warnings.append("open interest desactualizado respecto a la última vela")
        ret = c[-1].c / c[-1 - k].c - 1
        oi_chg = oi_changes[-1]
        price_up, price_dn = ret >= p.price_move, ret <= -p.price_move
        oi_up, oi_dn = oz >= p.z_oi, oz <= -p.z_oi
        f_hi, f_lo = fz >= p.z_high, fz <= -p.z_high
        evidence = [
            f"Precio {ret:+.2%} en {k} barras; OI {oi_chg:+.2%} (z {oz:+.2f}); "
            f"funding {fvals[-1]:+.5f} (z {fz:+.2f}) "
            f"[fuente {snapshot.sources.get('funding', '?')}]"
        ]
        bias, rule = 0.0, "sin_regla"
        if price_up and oi_up and f_hi:
            bias, rule = -p.crowded_bias, "largos_saturados"
            warnings.append("apalancamiento largo saturado: riesgo de squeeze de largos")
            evidence.append("Precio↑ + OI↑ + funding alto: largos saturados")
        elif price_up and oi_up:
            bias, rule = p.trend_bias, "tendencia_alcista_con_oi"
            evidence.append("Precio↑ + OI↑ con funding no extremo: posiciones nuevas a favor")
        elif price_dn and oi_up and f_lo:
            bias, rule = p.crowded_bias, "cortos_saturados"
            warnings.append("apalancamiento corto saturado: riesgo de squeeze de cortos")
            evidence.append("Precio↓ + OI↑ + funding muy negativo: cortos saturados")
        elif price_dn and oi_up:
            bias, rule = -p.trend_bias, "tendencia_bajista_con_oi"
            evidence.append("Precio↓ + OI↑: cortos abriendo posiciones")
        elif price_dn and oi_dn:
            rule = "cierre_de_posiciones"
            evidence.append("Precio↓ + OI↓: cierre de posiciones (capitulación), sin sesgo")
        elif price_up and oi_dn:
            bias, rule = p.weak_bias, "cobertura_de_cortos"
            evidence.append("Precio↑ + OI↓: cobertura de cortos, rally débil")
        else:
            evidence.append("Combinación precio/OI sin regla activa")

        metrics: dict = {
            "rule": rule, "price_return": ret, "oi_change": oi_chg, "oi_change_z": oz,
            "funding_last": fvals[-1], "funding_z": fz, "oi_points": len(oi),
            "funding_points": len(fvals), "sources": dict(snapshot.sources),
            "coverage": dict(snapshot.coverage),
        }
        lz = self._opt_z(snapshot.long_short_ratio, "long/short", warnings)
        bz = self._opt_z(snapshot.basis, "basis", warnings)
        for name, z in (("long/short", lz), ("basis", bz)):
            if z is None:
                continue
            metrics[f"{name.replace('/', '_')}_z"] = z
            if z >= p.z_high:
                bias -= p.modifier_bias
                evidence.append(f"{name} alto (z {z:+.2f}): ajuste contrarian bajista")
            elif z <= -p.z_high:
                bias += p.modifier_bias
                evidence.append(f"{name} bajo (z {z:+.2f}): ajuste contrarian alcista")
        bias = max(-1.0, min(1.0, bias))
        conf = min(p.max_confidence, 0.2 + 0.15 * max(abs(fz), abs(oz)))
        conf *= min(1.0, len(oi) / (2 * p.min_oi_points))
        if rule == "sin_regla":
            conf = 0.0
        status = "ok"
        if stale:
            status, conf = "degraded", conf / 2
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof, bias=bias,
            confidence=conf, horizon_bars=p.horizon_bars, evidence=evidence, metrics=metrics,
            warnings=warnings, status=status,
        )
