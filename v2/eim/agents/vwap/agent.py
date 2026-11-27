"""Agente `vwap`: posición del precio respecto a los VWAP diario/semanal/quincenal/mensual."""

from __future__ import annotations

import pandas as pd

from eim.agents.base import no_data_report
from eim.agents.structure.agent import snapshot_frame
from eim.agents.vwap.compute import compute_vwap, interpret
from eim.agents.vwap.params import LABEL, PERIODS, POSITION_NOTES, PREFIX, VWAPParams
from eim.core import AgentReport, MarketSnapshot, Overlay

_DAY_MS = 86_400_000
#: Duración mínima de cada período: con velas de esa duración o más, el ancla tiene una sola
#: vela (σ = 0) y no informa de nada (T87: ancla diaria con velas de 1 d).
_PERIOD_MIN_MS = {"daily": _DAY_MS, "weekly": 7 * _DAY_MS, "quincenal": 13 * _DAY_MS,
                  "monthly": 28 * _DAY_MS}
_VOLUME_NOTE = {"tick": "volumen de ticks (cuenta de cotizaciones, no volumen negociado): el VWAP "
                        "pondera por actividad, no por volumen"}


def _ms(ts: pd.Timestamp) -> int:
    return int(ts.timestamp() * 1000)


def dead_anchors(snapshot: MarketSnapshot) -> list[str]:
    """Anclas que no aplican al marco del snapshot: período ≤ duración de la vela (T91)."""
    c = snapshot.candles
    step = min((b.t - a.t for a, b in zip(c, c[1:], strict=False)), default=0)
    return [k for k in PERIODS if step >= _PERIOD_MIN_MS[k]]


def _overlays(row: pd.Series, first_ts: pd.Timestamp, p: VWAPParams, conf: float,
              src: str, skip: tuple[str, ...] = ()) -> list[Overlay]:
    out: list[Overlay] = []
    for period in PERIODS:
        if period in skip:
            continue
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
        if p.volume_kind == "none":
            return no_data_report(self.id, self.version, snapshot.asof,
                                  "el instrumento no tiene volumen negociado: sin VWAP (no se "
                                  "inventa un volumen)")
        src = snapshot.sources.get("candles", "desconocida")
        df = compute_vwap(snapshot_frame(snapshot), tz=p.anchor_tz)
        dead = tuple(dead_anchors(snapshot)) if p.explicit_dead_anchors else ()
        row, first_ts = df.iloc[-1], df["timestamp"].iloc[0]

        metrics: dict = {"bars": n, "source": src, "coverage": snapshot.coverage.get("candles"),
                         "close": float(row["close"]), "periods": {}}
        evidence: list[str] = []
        warnings: list[str] = [_VOLUME_NOTE[p.volume_kind]] if p.volume_kind in _VOLUME_NOTE else []
        if p.anchor_tz != "UTC":
            metrics["anchor_tz"] = p.anchor_tz
        votes: list[tuple[float, float]] = []  # (sesgo, peso)
        for period in PERIODS:
            if period in dead:
                metrics["periods"][period] = {"applicable": False}
                warnings.append(f"ancla {LABEL[period]} no aplica con velas de "
                                f"{snapshot.timeframe}: excluida del voto y de la confianza")
                continue
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
        if p.explicit_dead_anchors:   # T91: perder un ancla cuesta confianza, también con tope
            confidence = min(p.max_confidence, agree) * len(votes) / len(PERIODS)
        else:
            confidence = min(p.max_confidence, agree * len(votes) / len(PERIODS))
        metrics["anchored_vwap"] = float(row["VWAP_ANCHOR"])
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof, bias=bias,
            confidence=confidence, horizon_bars=p.horizon_bars, evidence=evidence,
            metrics=metrics, warnings=warnings,
            overlays=_overlays(row, first_ts, p, confidence, src, dead),
            status="degraded" if warnings else "ok",
        )
