"""Informe del backtest por instrumento (T92): métricas con la anualización de SU calendario
y el desglose de costos de su clase (comisión, deslizamiento, financiación, dividendos, roll).

`bars_per_year` deja de ser 8766 fijo fuera de cripto: sale de `eim.instruments.timebase`
(la NYSE en diario ≈ 252). Sin `exchange_calendars` no se adivina: el Sharpe y el Sortino
salen vacíos con el motivo, en vez de anualizar con un número que inflaría la cifra ×5,9 (T87).
"""

from __future__ import annotations

from eim.backtest.engine import BacktestResult
from eim.backtest.metrics import compute_metrics
from eim.backtest.params import BacktestParams
from eim.data.timeframes import tf_ms
from eim.instruments.calendar_specs import CalendarUnavailable
from eim.instruments.models import Instrument
from eim.instruments.timebase import bars_per_year


def annualization(inst: Instrument, timeframe: str) -> tuple[float | None, str]:
    """(velas por año, procedencia) del calendario del contrato; None con el motivo si falta
    la librería de calendarios."""
    try:
        return bars_per_year(inst, tf_ms(timeframe)), f"calendario {inst.calendar_id}"
    except CalendarUnavailable as e:
        return None, f"sin anualizar: {e}"


def class_cost_breakdown(res: BacktestResult) -> dict:
    """bruto − comisiones − deslizamiento − financiación + dividendos − roll = neto (cuenta)."""
    ts = res.trades
    d = {k: sum(getattr(t, k, 0.0) for t in ts)
         for k in ("gross_pnl", "fees", "slippage", "financing", "dividends", "roll_costs",
                   "net_pnl")}
    d["total_costs"] = d["fees"] + d["slippage"] + d["financing"] + d["roll_costs"]
    d["rolls"] = sum(getattr(t, "rolls", 0) for t in ts)
    d["reasons"] = {r: sum(1 for t in ts if t.reason == r) for r in sorted({t.reason for t in ts})}
    return d


def build_class_report(res: BacktestResult, inst: Instrument, params: BacktestParams,
                       timeframe: str, model, data_source: str) -> dict:
    """Informe reproducible: meta (instrumento, modelo y sus supuestos), métricas y costos."""
    bpy, bpy_src = annualization(inst, timeframe)
    met = compute_metrics(res, params.initial_equity, bpy or 1.0)
    if bpy is None:
        met["sharpe"] = met["sortino"] = None
        met["ci95"].pop("sharpe", None)
        met["warning_annualization"] = bpy_src
    return {
        "meta": {"mode": "SIMULADO", "instrument": inst.id, "symbol": inst.symbol,
                 "asset_class": inst.asset_class.value, "timeframe": timeframe,
                 "calendar": inst.calendar_id, "multiplier": inst.multiplier,
                 "cost_model": model.version, "kind": model.kind.value,
                 "fingerprint": model.fingerprint(), "bars_per_year": bpy,
                 "bars_per_year_source": bpy_src, "data_source": data_source,
                 "assumptions": model.assumptions()},
        "metrics": met,
        "costs": class_cost_breakdown(res),
        "stats": {k: v for k, v in res.stats.items() if k != "cost_model"},
        "trades": [{"side": t.side, "reason": t.reason, "qty": t.qty, "bars": t.bars,
                    "gross": t.gross_pnl, "net": t.net_pnl, "r": t.r_multiple}
                   for t in res.trades],
    }


def _money(x: float) -> str:
    return f"{x:,.2f}"


def to_markdown(reports: list[dict], title: str) -> str:
    """Tabla de costos por clase y detalle de supuestos de cada modelo."""
    lines = [f"# {title}", "", "| Instrumento | Modelo | Operaciones | Bruto | Comisiones | "
             "Deslizamiento | Financiación | Dividendos | Roll | Neto |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in reports:
        c, m = r["costs"], r["meta"]
        lines.append(f"| {m['instrument']} | {m['cost_model']} | {r['metrics']['n_trades']} | "
                     f"{_money(c['gross_pnl'])} | {_money(c['fees'])} | "
                     f"{_money(c['slippage'])} | {_money(c['financing'])} | "
                     f"{_money(c['dividends'])} | {_money(c['roll_costs'])} | "
                     f"{_money(c['net_pnl'])} |")
    for r in reports:
        m = r["meta"]
        lines += ["", f"## {m['symbol']} ({m['asset_class']}, {m['timeframe']})", "",
                  f"- Datos: {m['data_source']}; modo {m['mode']}.",
                  f"- Modelo `{m['cost_model']}` (huella `{m['fingerprint']}`), "
                  f"multiplicador {m['multiplier']:g}.",
                  f"- Anualización: {m['bars_per_year'] or '—'} velas/año "
                  f"({m['bars_per_year_source']}).",
                  f"- Salidas: {r['costs']['reasons']}; empalmes: {r['costs']['rolls']}; "
                  f"eventos: splits {r['stats'].get('splits', 0)}, dividendos "
                  f"{r['stats'].get('dividends', 0)}; órdenes que esperaron al mercado abierto: "
                  f"{r['stats'].get('waited_closed', 0)}.", "",
                  "Supuestos (sin verificar en la fuente):"]
        lines += [f"- `{k}`: {v}" for k, v in m["assumptions"].items()] or ["- ninguno"]
    return "\n".join(lines) + "\n"
