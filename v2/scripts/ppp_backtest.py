"""Backtest del perfil PPP (Progressive Profit Protection — BTCUSDT) con costos reales del motor.

    python scripts/ppp_backtest.py --data <carpeta con candles/, funding/ y paper.duckdb>

Usa los contextos ya guardados (`python -m eim.paper backtest --local`) y las mismas ideas que ven
los otros perfiles. NO modifica nada: DuckDB se abre en la carpeta indicada (usa una COPIA si la
API está en marcha). Informe en Markdown y JSON bajo `reports/`.

Optimización controlada (sección 14 del encargo): rejilla de umbrales/escalones sobre el MISMO
periodo, partida en desarrollo (primeros `--is-frac`) y validación fuera de muestra (el resto,
con el capital reiniciado). No cambia la configuración del perfil: solo informa.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.paper.book import run_profile
from eim.paper.desk import MMR, PaperDesk
from eim.paper.feedback import Learner
from eim.paper.ladder_book import LadderSim
from eim.paper.params import PPP_ID, PROFILES, ExecParams, LadderParams, ProfileParams
from eim.paper.summary import _max_dd_pct, profile_summary

PPP = next(p for p in PROFILES if p.id == PPP_ID)
GRID = [(10.0, 5.0), (8.0, 3.0), (8.0, 5.0), (10.0, 3.0), (10.0, 7.0), (12.0, 5.0), (12.0, 7.0)]
COST_X = (0.5, 1.0, 2.0, 3.0)


@dataclass
class Row:
    label: str
    n: int
    net: float
    exp: float | None
    pf: float | None
    dd: float
    win: float | None
    sl0: int
    sld: int
    open: int
    gap: float | None


def _with(p: ProfileParams, first: float, step: float) -> ProfileParams:
    return p.model_copy(update={"ladder": LadderParams(first_usdt=first, step_usdt=step)})


def _row(label: str, st, mmr: float, now: int) -> Row:
    s = profile_summary(st, Learner([]), [], now, mmr)
    lad = s["ladder"]
    pnl = [t["pnl"] for t in st.trades]
    gains, losses = sum(x for x in pnl if x > 0), -sum(x for x in pnl if x < 0)
    return Row(label, len(pnl), sum(pnl), sum(pnl) / len(pnl) if pnl else None,
               gains / losses if losses > 0 else None, _max_dd_pct(st.curve),
               sum(1 for x in pnl if x > 0) / len(pnl) if pnl else None,
               lad["closed_initial_sl"], lad["closed_dynamic_sl"], len(s["positions"]),
               lad["avg_gap_max_vs_realized_usd"])


def _run(p, outs, path, ep, mmr):
    sim = LadderSim(path, ep)
    return run_profile(p, outs, Learner(outs), mmr, sim)


def _fmt(x, d=2):
    return "—" if x is None else f"{x:,.{d}f}"


def _table(rows: list[Row]) -> str:
    out = ["| Config | Ops | Neto USDT | Esperanza/op | PF | Acierto | DD máx | "
           "SL ini / SL din | Abiertas | Devuelto vs máx. |",
           "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for r in rows:
        out.append(f"| {r.label} | {r.n} | {_fmt(r.net)} | {_fmt(r.exp)} | {_fmt(r.pf)} | "
                   f"{_fmt(None if r.win is None else r.win * 100, 0)} % | {r.dd * 100:.2f} % | "
                   f"{r.sl0} / {r.sld} | {r.open} | {_fmt(r.gap)} |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--is-frac", type=float, default=0.6)
    ap.add_argument("--out", default="reports/ppp_backtest")
    a = ap.parse_args()
    store, ps = Store(a.data), PaperStore(Path(a.data) / "paper.duckdb")
    desk = PaperDesk(store, ps)
    v = desk.view(a.symbol)
    outs, path = v.outcomes, v.path
    if not outs or path is None:
        print("sin contextos guardados: corre `python -m eim.paper backtest --local` antes")
        return 1
    ep, mmr, now = desk.ep, MMR.get(a.symbol, 0.005), path.end
    ts = sorted(o.idea.t for o in outs)
    cut = ts[int(len(ts) * a.is_frac)]
    train, test = [o for o in outs if o.idea.t < cut], [o for o in outs if o.idea.t >= cut]

    full = _run(PPP, outs, path, ep, mmr)
    detail = profile_summary(full, Learner([]), [], now, mmr)
    grid_is, grid_oos = [], []
    for first, step in GRID:
        p = _with(PPP, first, step)
        tag = f"+{first:g} / +{step:g}" + (" (referencia)" if (first, step) == (10.0, 5.0) else "")
        grid_is.append(_row(tag, _run(p, train, path, ep, mmr), mmr, now))
        grid_oos.append(_row(tag, _run(p, test, path, ep, mmr), mmr, now))
    cost_rows = []
    for k in COST_X:
        cp = ep.costs.model_copy(update={"taker_fee": ep.costs.taker_fee * k,
                                         "maker_fee": ep.costs.maker_fee * k,
                                         "slip_base_bps": ep.costs.slip_base_bps * k})
        e2 = ExecParams.model_validate({**ep.model_dump(), "costs": cp.model_dump()})
        cost_rows.append(_row(f"costos ×{k:g}", _run(PPP, outs, path, e2, mmr), mmr, now))

    first_t, last_t = ts[0], ts[-1]
    def iso(t: int) -> str:
        return datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%d %H:%M")
    lad = detail["ladder"]
    reached = ", ".join(f"+{r['nominal']:g}: {r['reached']}" for r in lad["reached"]) or "ninguno"
    md = [f"# Backtest PPP — {a.symbol}", "",
          f"Datos: `{a.data}` · ideas {iso(first_t)} → {iso(last_t)} UTC · "
          f"{len(outs)} ideas "
          f"simuladas · camino de {ep.path_tf} hasta {iso(path.end)} · SIMULADO, sin dinero "
          "real.", "",
          f"Desarrollo: antes de {iso(cut)} ({len(train)} ideas) · fuera de muestra: desde esa "
          f"fecha ({len(test)} ideas), capital reiniciado a {PPP.initial_equity:,.0f} USDT.", "",
          "## Configuración de referencia (+10 / +5) — todo el periodo", "",
          _table([_row("referencia", full, mmr, now)]), "",
          f"- Escalones alcanzados: {reached}",
          f"- Violaciones de reglas: {lad['violations']} · incidencias: {lad['incidents']} · "
          f"pérdidas seguidas máx.: {lad['max_consecutive_losses']}",
          f"- Máximo flotante medio {_fmt(lad['avg_max_float_usd'])} USDT · realizado medio "
          f"{_fmt(lad['avg_realized_usd'])} USDT · duración media {_fmt(lad['avg_hours'], 1)} h",
          "", "## Rejilla — desarrollo", "", _table(grid_is), "",
          "## Rejilla — fuera de muestra", "", _table(grid_oos), "",
          "## Sensibilidad a comisiones y deslizamiento (configuración de referencia)", "",
          _table(cost_rows), "",
          "## Cómo leerlo", "",
          "- Una muestra pequeña NO demuestra rentabilidad: no se declara rentable el perfil.",
          "- La rejilla es informativa; no cambia la configuración. Elegir por el mayor beneficio "
          "de un periodo sería sobreajuste: se exige estabilidad entre desarrollo y fuera de "
          "muestra.",
          "- Camino de 15 m: dentro de una vela manda el SL vigente y el avance sube el SL desde "
          "la siguiente (conservador)."]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(
        {"detail": detail["ladder"], "is": [r.__dict__ for r in grid_is],
         "oos": [r.__dict__ for r in grid_oos], "costs": [r.__dict__ for r in cost_rows]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
