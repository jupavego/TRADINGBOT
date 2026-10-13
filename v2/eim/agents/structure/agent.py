"""Agente `structure`: sesgo y confianza desde el estado estructural (FRM→BRM→IRM)."""

from __future__ import annotations

import pandas as pd

from eim.agents.base import no_data_report
from eim.agents.structure.brm import compute_brm
from eim.agents.structure.frm import compute_frm
from eim.agents.structure.irm import compute_irm, diagnose
from eim.agents.structure.params import StructureParams
from eim.core import AgentReport, MarketSnapshot

_OHLCV = ["timestamp", "open", "high", "low", "close", "volume"]


def snapshot_frame(snapshot: MarketSnapshot) -> pd.DataFrame:
    """Velas cerradas del snapshot como DataFrame OHLCV (timestamp UTC)."""
    c = snapshot.candles
    return pd.DataFrame({
        "timestamp": pd.to_datetime([x.t for x in c], unit="ms", utc=True),
        "open": [x.o for x in c], "high": [x.h for x in c], "low": [x.l for x in c],
        "close": [x.c for x in c], "volume": [x.v for x in c],
    })[_OHLCV]


def structure_frame(ohlcv: pd.DataFrame, params: StructureParams | None = None) -> pd.DataFrame:
    """Pipeline completo FRM → BRM → IRM sobre todo el histórico."""
    p = params or StructureParams()
    return compute_irm(compute_brm(compute_frm(ohlcv, p.frm), p.brm), p.irm)


class StructureAgent:
    id = "structure"
    version = "1.0.0"
    requires = {"candles"}

    def __init__(self, params: StructureParams | None = None) -> None:
        self.params = params or StructureParams()

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        n = len(snapshot.candles)
        if n < p.min_bars:
            return no_data_report(
                self.id, self.version, snapshot.asof, f"velas insuficientes: {n} < {p.min_bars}"
            )
        df = compute_brm(compute_frm(snapshot_frame(snapshot), p.frm), p.brm)
        row = df.iloc[-1].to_dict()
        diag = diagnose(row, p.irm)
        conv = diag["conviction"]
        warnings: list[str] = []
        status = "ok"
        if n < p.warmup_bars:
            status = "degraded"
            warnings.append(f"solo {n} velas (< {p.warmup_bars}): warmup de EMA-200 incompleto")
        if row["COMBINATION_STATUS"] != "NORMAL":
            warnings.append(f"combinación de estados {row['COMBINATION_STATUS']}")
        if row["TRANSITION_STATUS"] == "INVALID":
            warnings.append("transición estructural inválida respecto de la vela previa")
        evidence = [
            f"Estado estructural {row['STRUCTURAL_STATE']}, momentum {row['MOMENTUM_STATE']}, "
            f"energía {row['ENERGY_STATE']}",
            f"Escenario {diag['scenario']} (convicción {conv:.1f}, "
            f"confianza {diag['confidence']:.1f})",
            *diag["rules"],
            *diag["modifiers"],
        ]
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof,
            bias=max(-1.0, min(1.0, (conv - 50) / 50)),
            confidence=diag["confidence"] / 100,
            horizon_bars=p.irm.horizon_bars,
            evidence=evidence,
            metrics={
                "structural_state": row["STRUCTURAL_STATE"],
                "momentum_state": row["MOMENTUM_STATE"],
                "energy_state": row["ENERGY_STATE"],
                "scenario": diag["scenario"],
                "conviction": conv,
                "coherence": float(row["COHERENCE_SCORE"]),
                "friction": float(row["FRICTION_INDEX"]),
                "bars": n,
                "source": snapshot.sources.get("candles", "desconocida"),
                "coverage": snapshot.coverage.get("candles"),
                "explanation": diag["explanation"],
            },
            warnings=warnings,
            status=status,  # type: ignore[arg-type]
        )
