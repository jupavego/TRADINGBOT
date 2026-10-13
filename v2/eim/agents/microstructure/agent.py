"""Agente `microstructure`: sesgo de corto plazo desde el flujo de órdenes.

Señales (ventana = últimas `window` velas con recolección; z contra todas las velas con datos):
OFI (order flow imbalance del mejor nivel), delta de volumen agresor (su suma acumulada es el
CVD), desequilibrio de profundidad top-10 y divergencia precio/CVD (precio sube con delta
vendedor → bajista; baja con delta comprador → alcista). La volatilidad realizada
(Parkinson y Garman-Klass) va en métricas; si se expande frente a su referencia larga se
advierte y se reduce la confianza. Sin recolección (`snapshot.micro`) → `no_data`.
Función pura: sin red ni disco.
"""

from __future__ import annotations

import math
from statistics import fmean, pstdev

from eim.agents.base import no_data_report
from eim.agents.microstructure.params import MicrostructureParams
from eim.core import AgentReport, Candle, MarketSnapshot

_LN2_4 = 4 * math.log(2)


def parkinson(candles: list[Candle]) -> float | None:
    """Volatilidad de Parkinson por barra (desviación, no anualizada)."""
    xs = [math.log(c.h / c.l) ** 2 for c in candles if c.h > 0 and c.l > 0]
    return math.sqrt(sum(xs) / (len(xs) * _LN2_4)) if xs else None


def garman_klass(candles: list[Candle]) -> float | None:
    """Volatilidad de Garman-Klass por barra (desviación, no anualizada)."""
    xs = [0.5 * math.log(c.h / c.l) ** 2 - (2 * math.log(2) - 1) * math.log(c.c / c.o) ** 2
          for c in candles if min(c.h, c.l, c.o, c.c) > 0]
    return math.sqrt(max(sum(xs) / len(xs), 0.0)) if xs else None


class MicrostructureAgent:
    id = "microstructure"
    version = "1.0.0"
    requires = {"candles", "micro"}

    def __init__(self, params: MicrostructureParams | None = None) -> None:
        self.params = params or MicrostructureParams()

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        bars = snapshot.micro
        if not bars:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  "sin recolección de microestructura (colector no corre)")
        if len(bars) < p.min_bars:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  f"recolección insuficiente ({len(bars)}/{p.min_bars} velas)")
        candles = snapshot.candles
        win = candles[-p.window:]
        win_t = {c.t for c in win}
        recent = [b for b in bars if b.t in win_t]
        if len(recent) < p.min_window_bars:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  "sin datos de recolección en las velas recientes")
        k = len(recent)
        sd_o = pstdev([b.ofi for b in bars])
        sd_d = pstdev([b.delta for b in bars])
        if sd_o == 0 or sd_d == 0:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  "flujo sin variación (z-score indefinido)")
        zo = sum(b.ofi for b in recent) / (sd_o * math.sqrt(k))
        zd = sum(b.delta for b in recent) / (sd_d * math.sqrt(k))

        def sat(z: float) -> float:
            return math.tanh(z / p.z_scale)

        cvd, run = 0.0, 0.0
        for b in bars:
            run += b.delta
        cvd = run
        imbs = [b.depth_imb for b in recent if b.depth_imb is not None]
        imb = fmean(imbs) if imbs else None
        book = snapshot.orderbook
        book_imb = None
        if book and book.bids and book.asks:
            bq, aq = sum(q for _, q in book.bids), sum(q for _, q in book.asks)
            book_imb = (bq - aq) / (bq + aq) if bq + aq else None

        ret = candles[-1].c / win[0].o - 1
        delta_sum = sum(b.delta for b in recent)
        div = 0.0
        evidence = [f"OFI z {zo:+.2f} y delta agresor z {zd:+.2f} en {k} velas "
                    f"[fuente {snapshot.sources.get('micro', 'binance_ws')}]"]
        if ret >= p.price_move and delta_sum < 0:
            div = -1.0
            evidence.append(f"Divergencia bajista: precio {ret:+.2%} con CVD vendedor")
        elif ret <= -p.price_move and delta_sum > 0:
            div = 1.0
            evidence.append(f"Divergencia alcista: precio {ret:+.2%} con CVD comprador")
        if imb is not None:
            evidence.append(f"Desequilibrio de profundidad top-10 {imb:+.2f} (promedio)")
        bias = (p.w_ofi * sat(zo) + p.w_delta * sat(zd)
                + (p.w_depth * imb if imb is not None else 0.0) + p.w_divergence * div)
        bias = max(-1.0, min(1.0, bias))

        warnings: list[str] = []
        pk, gk = parkinson(candles[-p.vol_window:]), garman_klass(candles[-p.vol_window:])
        pk_long = parkinson(candles[-p.vol_long_window:])
        conf = min(p.max_confidence, 0.15 + 0.12 * max(abs(zo), abs(zd)))
        conf *= min(1.0, len(bars) / (2 * p.min_bars)) * (k / len(win))
        if pk and pk_long and pk / pk_long >= p.vol_expansion:
            warnings.append(f"volatilidad realizada en expansión ({pk / pk_long:.1f}× la de "
                            "referencia): el flujo es menos fiable")
            conf *= 0.6
        incomplete = sum(1 for b in bars if not b.complete) / len(bars)
        status = "ok"
        if incomplete > p.max_incomplete:
            status, conf = "degraded", conf / 2
        if incomplete:
            warnings.append(f"{incomplete:.0%} de las velas con huecos de secuencia")
        if len(bars) < len(candles):
            warnings.append(f"recolección cubre {len(bars)}/{len(candles)} velas del snapshot")
        metrics = {
            "ofi_z": zo, "delta_z": zd, "cvd": cvd, "delta_window": delta_sum,
            "depth_imbalance": imb, "book_imbalance": book_imb, "price_return": ret,
            "parkinson": pk, "garman_klass": gk, "parkinson_ref": pk_long,
            "bars_with_data": len(bars), "bars_window": k, "incomplete_fraction": incomplete,
            "sources": dict(snapshot.sources), "coverage": dict(snapshot.coverage),
        }
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof, bias=bias,
            confidence=conf, horizon_bars=p.horizon_bars, evidence=evidence, metrics=metrics,
            warnings=warnings, status=status,
        )
