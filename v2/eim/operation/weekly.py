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

from eim.data.machine import machine_id
from eim.execution.service import CLOSED, LiveTrade
from eim.forecast.calibration import evaluate_forecast, summarize
from eim.operation.alerts import DIVERGENCE, Alert
from eim.operation.distortions import overlapping
from eim.paper import accounting, universe
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
    # declara su universo (T144): esto es el carril de operación, no la cifra oficial
    out: dict = {"n": len(trades), "n_with_result": n, "universe": universe.OPERATION_VIEW,
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
                  "source": "reports/edge/edge_results.json (T27, ventanas fuera de muestra); "
                  + _repro(edge or {}, a)}
    return out


def _repro(edge: dict, asset: dict) -> str:
    """T124: si las ventanas fijaron sus datos, y si no, decirlo."""
    snap = (asset.get("snapshot") or {}).get("id")
    if edge.get("meta", {}).get("reproducible") and snap:
        return f"reproducible (T124): instantánea {snap}"
    return "no reproducible (T124): sin instantánea de datos"


def deviations(live: dict, base: dict, weeks: float, off: dict | None = None) -> list[str]:
    out: list[str] = []
    if off and off.get("n"):
        out.append(_official_deviation(off, base))
    for s, b in base.items():
        st = live.get(s, {})
        n, mean = st.get("n_with_result", 0), st.get("mean_r")
        freq = st.get("n", 0) / weeks if weeks else 0.0
        if b.get("trades_per_week") and weeks >= 1 / 7:
            out.append(f"vista (corrida de operación) {s}: {freq:.1f} operaciones/semana vs "
                       f"{b['trades_per_week']:.1f} en backtest "
                       f"({freq / b['trades_per_week']:.0%}).")
        if mean is None:
            out.append(f"vista (corrida de operación) {s}: sin operaciones cerradas: no hay R "
                       "que comparar.")
            continue
        ci = st.get("ci95")
        inside = ci is not None and ci[0] <= b["expectancy_r"] <= ci[1]
        tag = (f"no concluyente (n < {MIN_TRADES})" if n < MIN_TRADES else
               "compatible con el backtest" if inside else "DIFERENTE del backtest")
        out.append(f"vista (corrida de operación) {s}: R medio {mean:+.2f} (n={n}) vs "
                   f"{b['expectancy_r']:+.2f} en backtest → {tag}.")
    return out


def _official_deviation(off: dict, base: dict) -> str:
    """La comparación que decide: universo oficial frente al backtest, sin mezclar símbolos.

    El universo oficial es el LIBRO, que puede cubrir varios símbolos, mientras el backtest de
    T27 tiene una esperanza por símbolo. Comparar un agregado de dos símbolos contra la línea de
    uno sería inventar la comparación: cuando hay más de uno, se dice y no se compara.
    """
    syms = [s for s in off.get("symbols") or [] if s]
    head = (f"UNIVERSO OFICIAL ({', '.join(syms) or 'sin símbolo'}): R medio "
            f"{off['mean_r']:+.2f} (n={off['n']} de {off['tally']['n_total']} operaciones del "
            f"libro en el tramo)")
    if len(syms) != 1:
        return (f"{head}; cubre {len(syms)} símbolos y el backtest de T27 tiene una esperanza por "
                "símbolo: no se compara para no mezclar líneas base.")
    b = base.get(syms[0])
    if not b or b.get("expectancy_r") is None:
        return f"{head}; sin backtest de {syms[0]} con el que comparar."
    exp, ci = b["expectancy_r"], off.get("ci95")
    inside = ci is not None and ci[0] <= exp <= ci[1]
    tag = (f"no concluyente (n < {MIN_TRADES})" if off["n"] < MIN_TRADES else
           "compatible con el backtest" if inside else "DIFERENTE del backtest")
    return f"{head} vs {exp:+.2f} en backtest de {syms[0]} → {tag}."


def official(book_rows: Iterable[dict] | None, t0: int, t1: int) -> dict:
    """Las cifras OFICIALES del tramo (T144): el libro de los cuatro perfiles bajo el universo
    declarado, con su recuento y las `retro` aparte.

    Recibe el libro completo y recorta aquí la ventana `[t0, t1)`, de modo que el recorte y el
    filtro queden en un solo sitio: es lo que compara la prueba de cuadre
    (`tests/paper/test_cuadre_w43_w46.py`) contra el mismo libro leído por fuera.
    """
    rows = accounting.window(list(book_rows or []), t0, t1)
    return {**accounting.figures(rows), "window": {"from": t0, "to": t1},
            "available": book_rows is not None,
            "note": ("" if book_rows is not None else
                     "libro no disponible al componer el informe: sin cifra oficial (no se "
                     "sustituye por la del carril de operación)")}


def operation_view(live: dict, all_trades: dict) -> dict:
    """El carril de ejecución del servicio, declarado como VISTA y nunca como cifra oficial.

    Hasta T144 esta era la única tabla del informe, y con 1 operación por semana decidía la puerta
    al dinero real mientras el libro cerraba 118. Se sigue publicando porque es la única medida
    del carril que reconcilia contra el exchange, pero diciendo qué es.
    """
    return {"universe": universe.OPERATION_VIEW,
            "label": "corrida de operación del servicio (carril propio, reconciliado): vista "
                     "declarada dentro del universo oficial, NO la cifra que decide",
            "n": all_trades.get("n", 0), "n_with_result": all_trades.get("n_with_result", 0),
            "by_symbol": {s: st.get("n_with_result", 0) for s, st in live.items()}}


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
            hft_qc: dict[str, dict] | None = None, usage: list[dict] | None = None,
            data_dir: Path | None = None, book_rows: Iterable[dict] | None = None) -> dict:
    closed = [t for t in trades if t.status == CLOSED and t.closed_at is not None
              and t0 <= t.closed_at < t1]
    weeks = (t1 - max(t0, started_at or t0)) / WEEK_MS
    live = {s: trade_stats([t for t in closed if t.symbol == s], fee_rate) for s in symbols}
    base = backtest_baseline(edge, symbols)
    inc = incidents(alerts, active_alerts)
    all_trades = trade_stats(closed, fee_rate)
    off = official(book_rows, t0, t1)
    return {
        "period": {"from": t0, "to": t1, "label": week_label(t0) + (
            "" if t1 - t0 == WEEK_MS else " (parcial)"), "weeks_operated": round(weeks, 2)},
        "mode": mode, "generated_at": int(time.time() * 1000),
        # T144: la cifra que decide es `official` (libro de los cuatro perfiles, sin `retro`);
        # `trades`/`all_trades` son el carril de operación, declarado como vista en
        # `operation_view`. Antes esta era la única tabla y en ningún sitio decía qué contaba.
        "universe": universe.declaration(), "official": off,
        "operation_view": operation_view(live, all_trades),
        "trades": live, "all_trades": all_trades,
        "equity": equity_stats(equity), "backtest": base,
        "deviations": deviations(live, base, weeks, off), "calibration": calib,
        "incidents": inc, "risk": vetoes(decisions), "hft_qc": hft_qc or {},
        "distortions": overlapping(t0, t1, machine_id(data_dir) if data_dir else None),
        "usage": usage or [],
        "acceptance": {"recon_unresolved": len(inc["recon_unresolved"]),
                       "weeks_operated": round(weeks, 2),
                       "universe": universe.OFFICIAL,
                       "n_counted": off.get("n", 0),
                       "n_total_book": off.get("tally", {}).get("n_total", 0),
                       "note": "T31 exige ≥ 4 semanas continuas sin incidentes de "
                               "reconciliación sin resolver. La decisión de capital real la "
                               "toma el usuario por escrito; este informe no la habilita. "
                               "La cifra que decide es la del universo oficial (T144): el libro "
                               "de los cuatro perfiles, sin las operaciones `retro`."},
    }


def load_edge(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
