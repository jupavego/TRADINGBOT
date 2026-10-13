"""Agente `ema`: sesgo y confianza desde el stack de EMAs; expone las 44 variables FRM."""

from __future__ import annotations

import math

import numpy as np

from eim.agents.base import no_data_report
from eim.agents.ema.params import CROSS_PAIRS, GROUPS, VARIABLES, EMAParams
from eim.agents.structure.agent import snapshot_frame
from eim.agents.structure.frm import compute_frm
from eim.core import AgentReport, MarketSnapshot, Overlay


def _plain(v):
    """Valor JSON-seguro (numpy→python, NaN→None)."""
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer, int)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if math.isnan(v) else float(v)
    return v


class EMAAgent:
    id = "ema"
    version = "1.0.0"
    requires = {"candles"}

    def __init__(self, params: EMAParams | None = None) -> None:
        self.params = params or EMAParams()

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        n = len(snapshot.candles)
        if n < p.min_bars:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  f"velas insuficientes: {n} < {p.min_bars}")
        src = snapshot.sources.get("candles", "desconocida")
        df = compute_frm(snapshot_frame(snapshot), p.frm)
        row = df.iloc[-1]
        variables = {k: _plain(row[k]) for k in VARIABLES}
        groups = {g: {k: variables[k] for k in ks} for g, ks in GROUPS.items()}

        stack = (row["STACK_SCORE"] - 5) / 5
        price = (row["PRICE_VS_STACK"] - 2.5) / 2.5
        direction = {"UP": 1.0, "DOWN": -1.0}.get(row["SLOPE_DIRECTION"], 0.0)
        slope = direction * float(row["SLOPE_SYNC"]) / 100
        w = p.weights
        bias = max(-1.0, min(1.0, w[0] * stack + w[1] * price + w[2] * slope))
        confidence = max(0.0, min(1.0, float(row["COHERENCE_SCORE"]) / 10))

        warnings: list[str] = []
        status = "ok"
        if n < p.warmup_bars:
            status = "degraded"
            warnings.append(f"solo {n} velas (< {p.warmup_bars}): warmup de EMA-200 incompleto")
        evidence = [
            f"Stack {row['STACK_ORDER']} (score {row['STACK_SCORE']:.1f}); precio sobre "
            f"{int(row['PRICE_VS_STACK'])}/5 EMAs",
            f"Pendientes {row['SLOPE_DIRECTION']}, sincronía {row['SLOPE_SYNC']:.0f}%",
            f"Compresión {row['COMPRESSION_INDEX']:.3f} "
            f"({int(row['COMPRESSION_DURATION'])} velas), "
            f"elasticidad vs EMA-200 {row['ELASTICITY']:.2f}%",
        ]
        t = [int(x.timestamp() * 1000) for x in df["timestamp"].iloc[-p.cross_lookback:]]
        overlays = [
            Overlay(id=f"ema:{span}", agent_id=self.id, kind="level", t_from=t[-1],
                    geometry={"p": float(row[f"EMA_{span}"]), "span": span},
                    label=f"EMA {span}", confidence=confidence,
                    evidence=[f"EMA-{span} de la última vela; fuente {src}"])
            for span in (9, 21, 55, 100, 200) if not math.isnan(row[f"EMA_{span}"])
        ]
        recent = df.iloc[-p.cross_lookback:]
        for fast, slow in CROSS_PAIRS:
            pre = f"CROSS_{fast}_{slow}"
            for idx in recent.index[recent[f"{pre}_occurred"].astype(bool)]:
                d = df.at[idx, f"{pre}_direction"]
                ts = int(df.at[idx, "timestamp"].timestamp() * 1000)
                evidence.append(f"Cruce {fast}/{slow} {d} en la vela {idx}")
                overlays.append(Overlay(
                    id=f"ema:cross:{fast}_{slow}:{ts}", agent_id=self.id, kind="marker",
                    t_from=ts, t_to=ts,
                    geometry={"t": ts, "p": float(df.at[idx, "close"]), "action": d},
                    label=f"Cruce {fast}/{slow} {d}", confidence=confidence,
                    evidence=[f"magnitud {df.at[idx, f'{pre}_magnitude']:.3f}%"],
                ))
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof, bias=bias,
            confidence=confidence, horizon_bars=p.horizon_bars, evidence=evidence,
            metrics={"variables": variables, "groups": groups, "n_variables": len(variables),
                     "bars": n, "source": src, "coverage": snapshot.coverage.get("candles")},
            warnings=warnings, overlays=overlays, status=status,  # type: ignore[arg-type]
        )
