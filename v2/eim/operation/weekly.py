"""Informe semanal (y final) de la operación continua: resultados vs backtest, desviaciones,
calibración de escenarios e incidentes. Función pura de sus entradas; el I/O está en `build`.

La comparación con el backtest usa las ventanas fuera de muestra de la puerta de edge (T27,
`reports/edge/edge_results.json`): esperanza neta en R por operación y operaciones/semana.
El R en vivo se mide neto de la comisión estimada (sin funding); con pocas operaciones el
informe lo dice y no saca conclusiones.
"""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from eim.execution.service import CLOSED, LiveTrade
from eim.forecast.calibration import evaluate_forecast, summarize
from eim.operation.alerts import DIVERGENCE, Alert
from eim.risk.inputs import _week0
from eim.risk.models import RiskDecision

WEEK_MS = 7 * 86_400_000
MIN_TRADES = 20                     # por debajo, la comparación no es concluyente


def week_bounds(now: int) -> tuple[int, int]:
    """Semana UTC (lunes 00:00) que contiene `now`."""
    w0 = _week0(now)
    return w0, w0 + WEEK_MS


def week_label(t0: int) -> str:
    iso = datetime.fromtimestamp(t0 / 1000, tz=UTC).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def net_r(t: LiveTrade, fee_rate: float) -> float | None:
    """R neto de comisión (entrada + salida); sin funding."""
    if t.pnl is None or t.avg_entry is None or t.exit_price is None:
        return None
    risk = abs(t.avg_entry - t.sl) * t.filled
    fees = fee_rate * (t.avg_entry + t.exit_price) * t.filled
    return None if risk <= 0 else (t.pnl - fees) / risk


def trade_stats(trades: list[LiveTrade], fee_rate: float) -> dict:
    rs = [r for t in trades if (r := net_r(t, fee_rate)) is not None]
    n = len(rs)
    out: dict = {"n": len(trades), "n_with_result": n,
                 "by_exit": dict(Counter(t.exit_reason.split(":")[0] for t in trades))}
    if not n:
        return out
    mean = sum(rs) / n
    sd = math.sqrt(sum((r - mean) ** 2 for r in rs) / (n - 1)) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else None
    out.update(mean_r=mean, sd_r=sd, ci95=[mean - half, mean + half] if half else None,
               win_rate=sum(r > 0 for r in rs) / n, total_r=sum(rs),
               pnl_gross=sum(t.pnl or 0.0 for t in trades))
    return out


def equity_stats(series: list[tuple[int, float]]) -> dict:
    if not series:
        return {"n": 0}
    eqs = [e for _, e in series]
    peak, mdd = eqs[0], 0.0
    for e in eqs:
        peak = max(peak, e)
        mdd = max(mdd, (peak - e) / peak if peak > 0 else 0.0)
    return {"n": len(eqs), "start": eqs[0], "end": eqs[-1],
            "return": eqs[-1] / eqs[0] - 1 if eqs[0] else None, "max_drawdown": mdd}


def backtest_baseline(edge: dict | None, symbols: Iterable[str]) -> dict:
    """Esperanza neta (R) ponderada por operaciones y frecuencia semanal, por símbolo."""
    out: dict = {}
    for s in symbols:
        a = (edge or {}).get("assets", {}).get(s)
        if not a:
            continue
        ws = a["windows"]
        n = sum(w["n_trades"] for w in ws)
        weeks = sum((w["to_t"] - w["from_t"]) for w in ws) / WEEK_MS
        out[s] = {"n_trades": n, "weeks": weeks,
                  "expectancy_r": sum(w["expectancy_r"] * w["n_trades"] for w in ws) / n
                  if n else None,
                  "trades_per_week": n / weeks if weeks else None,
                  "max_drawdown": max(w["max_drawdown"] for w in ws),
                  "source": "reports/edge/edge_results.json (T27, ventanas fuera de muestra)"}
    return out


def deviations(live: dict, base: dict, weeks: float) -> list[str]:
    out: list[str] = []
    for s, b in base.items():
        st = live.get(s, {})
        n, mean = st.get("n_with_result", 0), st.get("mean_r")
        freq = st.get("n", 0) / weeks if weeks else 0.0
        if b.get("trades_per_week") and weeks >= 1 / 7:
            out.append(f"{s}: {freq:.1f} operaciones/semana vs {b['trades_per_week']:.1f} en "
                       f"backtest ({freq / b['trades_per_week']:.0%}).")
        if mean is None:
            out.append(f"{s}: sin operaciones cerradas: no hay R que comparar.")
            continue
        ci = st.get("ci95")
        inside = ci is not None and ci[0] <= b["expectancy_r"] <= ci[1]
        tag = (f"no concluyente (n < {MIN_TRADES})" if n < MIN_TRADES else
               "compatible con el backtest" if inside else "DIFERENTE del backtest")
        out.append(f"{s}: R medio {mean:+.2f} (n={n}) vs {b['expectancy_r']:+.2f} en backtest "
                   f"→ {tag}.")
    return out


def incidents(alerts: list[Alert], active: list[str]) -> dict:
    opened = [a for a in alerts if not a.resolved]
    last: dict[str, Alert] = {}
    for a in sorted(alerts, key=lambda a: a.t):
        if a.kind == DIVERGENCE:
            last[a.key] = a
    unresolved = sorted({k for k, a in last.items() if not a.resolved} |
                        {k for k in active if k.startswith(DIVERGENCE)})
    return {"n": len(opened), "by_kind": dict(Counter(a.kind for a in opened)),
            "recon_unresolved": unresolved,
            "list": [a.to_json() for a in sorted(opened, key=lambda a: a.t)][:100]}


def vetoes(decisions: list[RiskDecision]) -> dict:
    vet = [d for d in decisions if not d.approved]
    reasons = Counter(r.split(":")[0] for d in vet for r in d.reasons)
    return {"n_decisions": len(decisions), "n_vetoed": len(vet),
            "top_reasons": reasons.most_common(8)}


def calibration(forecasts: list, closes: dict[int, float], horizon: int) -> dict:
    outs, pending = [], 0
    for fs in forecasts:
        o = evaluate_forecast(fs, closes)
        if o is None:
            pending += 1
        else:
            outs.append(o)
    rep = summarize(outs, horizon, pending)
    rep.pop("curve", None)
    return rep


def compose(*, t0: int, t1: int, mode: str, symbols: tuple[str, ...], trades: list[LiveTrade],
            fee_rate: float, equity: list[tuple[int, float]], alerts: list[Alert],
            active_alerts: list[str], decisions: list[RiskDecision], edge: dict | None,
            calib: dict[str, dict], started_at: int | None,
            hft_qc: dict[str, dict] | None = None) -> dict:
    closed = [t for t in trades if t.status == CLOSED and t.closed_at is not None
              and t0 <= t.closed_at < t1]
    weeks = (t1 - max(t0, started_at or t0)) / WEEK_MS
    live = {s: trade_stats([t for t in closed if t.symbol == s], fee_rate) for s in symbols}
    base = backtest_baseline(edge, symbols)
    inc = incidents(alerts, active_alerts)
    return {
        "period": {"from": t0, "to": t1, "label": week_label(t0) + (
            "" if t1 - t0 == WEEK_MS else " (parcial)"), "weeks_operated": round(weeks, 2)},
        "mode": mode, "generated_at": int(time.time() * 1000),
        "trades": live, "all_trades": trade_stats(closed, fee_rate),
        "equity": equity_stats(equity), "backtest": base,
        "deviations": deviations(live, base, weeks), "calibration": calib,
        "incidents": inc, "risk": vetoes(decisions), "hft_qc": hft_qc or {},
        "acceptance": {"recon_unresolved": len(inc["recon_unresolved"]),
                       "weeks_operated": round(weeks, 2),
                       "note": "T31 exige ≥ 4 semanas continuas sin incidentes de "
                               "reconciliación sin resolver. La decisión de capital real la "
                               "toma el usuario por escrito; este informe no la habilita."},
    }


def load_edge(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
