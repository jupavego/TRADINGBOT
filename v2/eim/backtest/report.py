"""Informe reproducible del backtest: JSON + Markdown en `reports/backtest/` (sin reloj ni azar)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from eim.backtest.engine import BacktestResult
from eim.backtest.metrics import compute_metrics, cost_breakdown
from eim.backtest.params import BacktestParams
from eim.core import Candle

DEFAULT_DIR = Path("reports/backtest")


def data_hash(candles: list[Candle], funding: list[tuple[int, float]] | None) -> str:
    h = hashlib.sha256()
    for c in candles:
        h.update(f"{c.t},{c.o},{c.h},{c.l},{c.c},{c.v};".encode())
    for t, r in funding or []:
        h.update(f"f{t},{r};".encode())
    return h.hexdigest()[:16]


def pool(results: list[BacktestResult], initial_equity: float) -> BacktestResult:
    """Encadena ventanas disjuntas: los retornos de cada una se componen (sin salto entre ellas)."""
    t: list[int] = []
    eq: list[float] = []
    level = initial_equity
    trades, stats = [], {}
    for r in results:
        if r.equity:
            scale = level / initial_equity
            eq.extend(v * scale for v in r.equity)
            t.extend(r.equity_t)
            level = eq[-1]
        trades.extend(r.trades)
        for k, v in r.stats.items():
            if isinstance(v, bool):
                stats[k] = stats.get(k, False) or v
            elif isinstance(v, int | float) and k != "final_equity":
                stats[k] = stats.get(k, 0) + v
    stats["final_equity"] = eq[-1] if eq else initial_equity
    return BacktestResult(trades=trades, equity_t=t, equity=eq, stats=stats)


def build_report(
    windows: list[tuple[dict, BacktestResult]],
    params: BacktestParams,
    candles: list[Candle],
    funding: list[tuple[int, float]] | None,
    meta: dict,
    seed: int = 0,
) -> dict:
    ie = params.initial_equity
    pooled = pool([r for _, r in windows], ie)
    per_window = []
    for w, r in windows:
        m = compute_metrics(r, ie, params.bars_per_year, seed, n_boot=300)
        per_window.append({"window": w, "metrics": m, "costs": cost_breakdown(r)})
    return {
        "meta": {**meta, "data_hash": data_hash(candles, funding), "n_candles": len(candles),
                 "funding_points": len(funding or []), "seed": seed,
                 "first_t": candles[0].t if candles else None,
                 "last_t": candles[-1].t if candles else None,
                 "mode": "SIMULADO"},
        "params": params.model_dump(),
        "pooled": {"metrics": compute_metrics(pooled, ie, params.bars_per_year, seed),
                   "costs": cost_breakdown(pooled), "stats": pooled.stats},
        "windows": per_window,
        "trades": pooled.trades_dicts(),
        "notes": ["Ejecución en la apertura de la vela siguiente a la señal.",
                  "Si SL y TP caben en la misma vela se asume SL primero.",
                  "Funding cada 8 h con las tasas reales almacenadas; si faltan se asumen 0 "
                  "(ver `costs.warning_funding`).",
                  "Resultado de simulación sobre datos históricos: no garantiza edge futuro."],
    }


def _f(x: object, nd: int = 2) -> str:
    return "—" if x is None else f"{x:,.{nd}f}" if isinstance(x, int | float) else str(x)


def to_markdown(rep: dict) -> str:
    m, c = rep["pooled"]["metrics"], rep["pooled"]["costs"]
    ci = m["ci95"]

    def rng(k: str, nd: int = 2) -> str:
        v = ci.get(k)
        return f"[{_f(v[0], nd)}, {_f(v[1], nd)}]" if v else "—"

    meta = rep["meta"]
    L = [f"# Backtest {meta.get('symbol', '')} {meta.get('timeframe', '')} (SIMULADO)", "",
         f"Datos: {meta['n_candles']} velas, hash `{meta['data_hash']}`, "
         f"{meta['funding_points']} puntos de funding. Ventanas fuera de muestra: "
         f"{len(rep['windows'])}.", "",
         "## Resultado (ventanas encadenadas)", "",
         "| Métrica | Valor | IC 95 % |", "|---|---|---|",
         f"| Retorno total | {_f(m['total_return'] * 100)} % | |",
         f"| Sharpe | {_f(m['sharpe'])} | {rng('sharpe')} |",
         f"| Sortino | {_f(m['sortino'])} | |",
         f"| Drawdown máx. | {_f(m['max_drawdown'] * 100)} % | |",
         f"| R esperado | {_f(m['expectancy_r'], 3)} | {rng('expectancy_r', 3)} |",
         f"| Tasa de acierto | {_f(None if m['win_rate'] is None else m['win_rate'] * 100)} % "
         f"| {rng('win_rate', 3)} |",
         f"| Factor de beneficio | {_f(m['profit_factor'])} | {rng('profit_factor')} |",
         f"| Exposición | {_f(m['exposure'] * 100)} % | |",
         f"| Operaciones | {m['n_trades']} | |", "",
         "## Costos (USDT)", "",
         "| Concepto | Monto |", "|---|---|",
         f"| P&L bruto | {_f(c['gross_pnl'])} |", f"| Comisiones | {_f(-c['fees'])} |",
         f"| Deslizamiento | {_f(-c['slippage'])} |", f"| Funding | {_f(-c['funding'])} |",
         f"| Liquidaciones | {_f(-c['liquidation_fees'])} |", f"| **P&L neto** | "
         f"**{_f(c['net_pnl'])}** |", "",
         f"Liquidaciones de funding: {c['funding_settlements']['observed']} observadas de "
         f"{c['funding_settlements']['expected']} esperadas."]
    for k in ("warning_funding",):
        if k in c:
            L += ["", f"> ⚠ {c[k]}"]
    for k in ("warning_few_trades", "warning_few_bars"):
        if k in m:
            L += ["", f"> ⚠ {m[k]}"]
    L += ["", "## Notas", ""] + [f"- {n}" for n in rep["notes"]]
    return "\n".join(L) + "\n"


def write_report(rep: dict, name: str, out_dir: Path | str = DEFAULT_DIR) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pj, pm = out / f"{name}.json", out / f"{name}.md"
    pj.write_text(json.dumps(rep, indent=2, sort_keys=True, default=float), encoding="utf-8")
    pm.write_text(to_markdown(rep), encoding="utf-8")
    return pj, pm
