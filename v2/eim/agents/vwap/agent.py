"""Agente `vwap`: posición del precio respecto a los VWAP diario/semanal/quincenal/mensual."""

from __future__ import annotations

import pandas as pd

from eim.agents.base import no_data_report
from eim.agents.structure.agent import snapshot_frame
from eim.agents.vwap.compute import compute_vwap, interpret
from eim.agents.vwap.params import LABEL, PERIODS, POSITION_NOTES, PREFIX, VWAPParams
from eim.core import AgentReport, MarketSnapshot, Overlay


def _ms(ts: pd.Timestamp) -> int:
    return int(ts.timestamp() * 1000)


def _overlays(row: pd.Series, first_ts: pd.Timestamp, p: VWAPParams, conf: float,
              src: str) -> list[Overlay]:
    out: list[Overlay] = []
    for period in PERIODS:
        pre = PREFIX[period]
        start = row[f"{pre}_PERIOD"]
        ev = [f"VWAP {LABEL[period]} desde {start.isoformat()}; fuente {src}"]
        if start < first_ts:
            ev.append("período parcial: la ventana cargada no cubre su inicio")
        lines = [(row[pre], "VWAP")]
        for k in p.overlay_bands:
            lines += [(row[f"{pre}_UPPER_{k}"], f"+{k}σ"), (row[f"{pre}_LOWER_{k}"], f"-{k}σ")]
        for price, name in lines:
            if pd.isna(price):
                continue
            out.append(Overlay(
                id=f"vwap:{period}:{name}", agent_id="vwap", kind="level",
                t_from=_ms(max(start, first_ts)),
                geometry={"p": float(price), "period": period, "band": name},
                label=f"{name} {LABEL[period]}", confidence=conf, evidence=ev,
            ))
    return out


class VWAPAgent:
    id = "vwap"
    version = "1.0.0"
    requires = {"candles"}

    def __init__(self, params: VWAPParams | None = None) -> None:
        self.params = params or VWAPParams()

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        n = len(snapshot.candles)
        if n < p.min_bars:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  f"velas insuficientes: {n} < {p.min_bars}")
        src = snapshot.sources.get("candles", "desconocida")
        df = compute_vwap(snapshot_frame(snapshot))
        row, first_ts = df.iloc[-1], df["timestamp"].iloc[0]

        metrics: dict = {"bars": n, "source": src, "coverage": snapshot.coverage.get("candles"),
                         "close": float(row["close"]), "periods": {}}
        evidence: list[str] = []
        warnings: list[str] = []
        votes: list[tuple[float, float]] = []  # (sesgo, peso)
        for period in PERIODS:
            pre = PREFIX[period]
            pos, slope = row[f"{pre}_POSITION"], row[f"{pre}_SLOPE"]
            prob_up = interpret(pos, slope, p)
            partial = bool(row[f"{pre}_PERIOD"] < first_ts)
            metrics["periods"][period] = {
                "vwap": None if pd.isna(row[pre]) else float(row[pre]),
                "std": None if pd.isna(row[f"{pre}_STD"]) else float(row[f"{pre}_STD"]),
                "position": pos, "slope_pct": None if pd.isna(slope) else float(slope),
                "prob_up_pct": round(prob_up, 1), "partial": partial,
            }
            evidence.append(f"VWAP {LABEL[period]}: {pos} — {POSITION_NOTES[pos]}")
            if partial:
                warnings.append(f"VWAP {LABEL[period]} parcial: la ventana no cubre el período")
            if pos != "SIN_DATOS":
                votes.append(((prob_up - 50) / 50, p.period_weights.get(period, 1.0)))
        if not votes:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  "sin volumen acumulado para ningún VWAP")
        wsum = sum(w for _, w in votes)
        bias = max(-1.0, min(1.0, sum(b * w for b, w in votes) / wsum))
        agree = sum(w for b, w in votes if b * bias > 0) / wsum if bias else 0.0
        confidence = min(p.max_confidence, agree * len(votes) / len(PERIODS))
        metrics["anchored_vwap"] = float(row["VWAP_ANCHOR"])
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof, bias=bias,
            confidence=confidence, horizon_bars=p.horizon_bars, evidence=evidence,
            metrics=metrics, warnings=warnings,
            overlays=_overlays(row, first_ts, p, confidence, src),
            status="degraded" if warnings else "ok",
        )
