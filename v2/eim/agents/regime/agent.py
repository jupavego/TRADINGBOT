"""Agente `regime`: cambios de régimen con BOCPD sobre retornos y volatilidad.

Corre BOCPD (Normal-Gamma) sobre el log-retorno y sobre log|retorno| (proxy de volatilidad);
une los puntos de cambio, etiqueta cada tramo (tendencia alcista/bajista, rango, volátil) y
mide la estabilidad del esquema (matriz de transición, permanencia, entropía). El sesgo es
SIEMPRE neutro: el régimen condiciona los pesos de la síntesis, no la dirección.
"""

from __future__ import annotations

import numpy as np

from eim.agents.base import no_data_report
from eim.agents.regime.bocpd import bocpd, change_points, standardize
from eim.agents.regime.labeling import label_bars, segment_starts, stability
from eim.agents.regime.params import RegimeParams
from eim.core import AgentReport, MarketSnapshot, Overlay

_NAMES = {"trend_up": "tendencial alcista", "trend_down": "tendencial bajista",
          "range": "rango", "volatile": "alta volatilidad"}


class RegimeAgent:
    id = "regime"
    version = "1.0.0"
    requires = {"candles"}

    def __init__(self, params: RegimeParams | None = None) -> None:
        self.params = params or RegimeParams()

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        c = snapshot.candles
        if len(c) < p.min_bars:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  f"velas insuficientes ({len(c)}/{p.min_bars})")
        close = np.array([k.c for k in c], dtype=float)
        if np.any(close <= 0):
            return no_data_report(self.id, self.version, snapshot.asof, "precios no positivos")
        rets = np.diff(np.log(close))
        vol = np.log(np.abs(rets) + 1e-8)
        m_r, run_r = bocpd(standardize(rets), p.hazard, p.max_run, p.short_run)
        m_v, run_v = bocpd(standardize(vol), p.hazard, p.max_run, p.short_run)
        found = sorted(change_points(run_r, p.min_drop, p.min_gap)
                       + change_points(run_v, p.min_drop, p.min_gap))
        cps: list[tuple[int, int]] = []
        for loc, det in found:
            if not cps or loc - cps[-1][0] >= p.min_gap:
                cps.append((loc, det))
        starts = segment_starts(len(rets), [loc for loc, _ in cps])
        labels = label_bars(rets, starts, p.min_seg, p.trend_t, p.vol_ratio)
        st = stability(labels)
        current = labels[-1]
        seg_len = len(rets) - int(starts[-1])
        recent = float(max(m_r[-p.recent_bars:].max(), m_v[-p.recent_bars:].max()))

        warnings: list[str] = []
        unstable = st["dwell_overall"] < p.min_dwell or st["entropy"] > p.max_entropy
        if unstable:
            warnings.append(
                f"esquema de regímenes inestable (permanencia media {st['dwell_overall']:.1f} "
                f"velas, entropía {st['entropy']:.2f}): el régimen puede ser ruido")
        evidence = [
            f"Régimen actual: {_NAMES[current]} desde hace {seg_len} velas",
            f"Probabilidad de cambio reciente (últimas {p.recent_bars} velas): {recent:.0%}",
            f"{len(cps)} cambios detectados en {len(rets)} velas; permanencia media "
            f"{st['dwell_overall']:.1f} velas; entropía {st['entropy']:.2f}",
        ]
        # el cambio en retorno i (entre vela i y i+1) se ubica en la vela i+1
        overlays = [
            Overlay(id=f"regime:cp:{c[loc + 1].t}", agent_id=self.id, kind="marker",
                    t_from=c[loc + 1].t,
                    geometry={"t": c[loc + 1].t, "p": c[loc + 1].c, "action": "regime_change"},
                    label="Cambio de régimen", confidence=0.5,
                    evidence=[f"BOCPD lo detectó {det - loc} velas después"])
            for loc, det in cps[-5:]
        ]
        conf = p.max_confidence * (0.5 if unstable else 1.0) * min(1.0, seg_len / p.min_seg)
        metrics = {
            "regime": current, "segment_bars": seg_len, "change_prob_recent": recent,
            "change_points": [{"t": c[loc + 1].t, "detected_after": det - loc}
                              for loc, det in cps],
            "stability": st, "unstable": unstable,
            "sources": dict(snapshot.sources), "coverage": dict(snapshot.coverage),
        }
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof, bias=0.0,
            confidence=conf, horizon_bars=p.horizon_bars, evidence=evidence, metrics=metrics,
            warnings=warnings, overlays=overlays,
        )
