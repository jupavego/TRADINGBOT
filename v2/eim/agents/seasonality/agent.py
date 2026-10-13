"""Agente `seasonality`: sesgo del mes en curso según el promedio histórico real de ese mes."""

from __future__ import annotations

from datetime import UTC, datetime

from eim.agents.base import no_data_report
from eim.agents.seasonality.compute import MONTH_NAMES, build_matrix, monthly_closes
from eim.agents.seasonality.params import SeasonalityParams
from eim.core import AgentReport, MarketSnapshot


class SeasonalityAgent:
    id = "seasonality"
    version = "1.0.0"
    requires = {"candles"}

    def __init__(self, params: SeasonalityParams | None = None) -> None:
        self.params = params or SeasonalityParams()

    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        monthly = monthly_closes(snapshot.candles, snapshot.timeframe, snapshot.asof)
        if len(monthly) < p.min_months:
            return no_data_report(
                self.id, self.version, snapshot.asof,
                f"cierres mensuales insuficientes: {len(monthly)} < {p.min_months}")
        try:
            matrix = build_matrix(monthly, strict_gaps=p.strict_gaps)
        except ValueError as exc:
            return no_data_report(self.id, self.version, snapshot.asof, str(exc))
        src = snapshot.sources.get("candles", "desconocida")
        month = datetime.fromtimestamp(snapshot.asof / 1000, tz=UTC).month
        name = MONTH_NAMES[month - 1]
        samples = [r[name] for r in matrix["rows"] if r[name] is not None]
        n = len(samples)
        warnings = [
            f"cobertura real {matrix['real_data_range']['start']} → "
            f"{matrix['real_data_range']['end']}; los años sin datos no se rellenan"
        ]
        bias = confidence = 0.0
        evidence = []
        if n < p.min_samples:
            warnings.append(f"solo {n} observaciones de {name} (< {p.min_samples}): sin sesgo")
        else:
            avg = sum(samples) / n
            hit = sum(1 for x in samples if x > 0) / n
            bias = max(-1.0, min(1.0, avg / p.bias_scale_pct))
            confidence = min(p.max_confidence, p.max_confidence * n / 10) * abs(2 * hit - 1)
            evidence.append(f"{name}: retorno medio {avg:+.2f}% en {n} años, "
                            f"{hit:.0%} de meses positivos")
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snapshot.asof, bias=bias,
            confidence=confidence, horizon_bars=p.horizon_bars, evidence=evidence,
            metrics={"matrix": matrix, "month": name, "samples": n, "source": src,
                     "coverage": snapshot.coverage.get("candles")},
            warnings=warnings,
        )
