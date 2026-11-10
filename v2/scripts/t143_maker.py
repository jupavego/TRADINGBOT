"""T143 — medición emparejada de la entrada maker frente a la taker (entregable 1).

    python scripts/t143_maker.py --data <banco> [--ledger <ledger.csv>] [--limit N]

Aplica `PLAN/notas/T143_preregistro_maker.md` tal cual y escribe `reports/t143_maker.{md,json,csv}`.
Abre una COPIA temporal del `paper.duckdb` del banco: no toca el almacén vivo, no abre red y no
habilita dinero real. Nada de lo que hace cambia un perfil.
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path as FsPath

ROOT = FsPath(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))   # con `python -I` desde un worktree: su `eim`, no el instalado

from eim.data.paper_store import PaperStore  # noqa: E402
from eim.data.store import Store  # noqa: E402
from eim.data.timeframes import tf_ms  # noqa: E402
from eim.paper import maker_ab as ab  # noqa: E402
from eim.paper import maker_ab_report as rep  # noqa: E402
from eim.paper.catalog import generate_ideas  # noqa: E402
from eim.paper.desk import WARMUP_BARS, PaperDesk  # noqa: E402
from eim.paper.engine import FUNDING_MS, run_shadow  # noqa: E402
from eim.paper.engine import Path as PricePath  # noqa: E402

PREREG = "PLAN/notas/T143_preregistro_maker.md"
PREREG_COMMIT = "97f8174"
BARS = (0.5, 1.0, 2.0)      # rejilla fijada; decide 1,0
DECIDES = 1.0
THROUGH_BPS = (1.0, 5.0)    # estrés de cola, posterior al pre-registro (solo puede empeorar)


def log(t0: float, msg: str) -> None:
    print(f"[{time.perf_counter() - t0:7.0f} s] {msg}", flush=True)


def load_world(store: Store, ps: PaperStore, desk: PaperDesk, sym: str):
    """Las ideas de todas las reglas vigentes y el camino de precios (como `PaperDesk._compute`)."""
    ideas, firsts = [], []
    for tf in desk.tfs:
        ctxs = ps.load(sym, tf)
        if not ctxs:
            continue
        firsts.append(ctxs[0]["t"])
        bar = tf_ms(tf)
        candles = store.read_candles(sym, tf, start=ctxs[0]["t"] - WARMUP_BARS * bar)
        ideas += generate_ideas(ctxs, candles, sym, bar, timeframe=tf,
                                htf=desk._htf(sym, tf, ctxs[0]["t"]), exec_params=desk.ep)
        del ctxs, candles
        gc.collect()
    if not firsts:
        raise SystemExit("el banco no tiene contextos")
    t0 = min(firsts)
    pc = store.read_candles(sym, desk.ep.path_tf, start=t0 - tf_ms("4h"))
    funding = store.read_series("funding", sym, start=t0 - FUNDING_MS)
    return ideas, PricePath(pc, funding, tf_ms(desk.ep.path_tf))


def shadow_arm(ideas, path, ep, bars: float | None) -> dict:
    """Lectura secundaria y descriptiva: con «una viva por estrategia», que rompe la pareja."""
    use = ideas if bars is None else [ab.to_limit(i, bars) for i in ideas]
    risk = {i.id: ab.planned_risk(i) for i in ideas}
    legs = [ab.leg_of(o, risk.get(o.idea.id, 0.0)) for o in run_shadow(use, path, ep)]
    return ab.arm_stats(legs)


def live_cross(ledger: FsPath) -> dict:
    """Control de realidad sobre el libro vivo. **Confundido**: cada estrategia elige su tipo."""
    rows = list(csv.DictReader(ledger.open(encoding="utf-8")))
    out: dict[str, dict] = {}
    for kind in ("market", "limit"):
        sel = [r for r in rows
               if r["kind"] == kind and r["scope"] == "perfil"
               and str(r["retro"]).lower() != "true" and r["r"]]
        if not sel:
            continue
        rs = [float(r["r"]) for r in sel]
        cost = [(float(r["fees"] or 0) + float(r["slip"] or 0) + float(r["funding"] or 0))
                / (abs(float(r["pnl_usdt"])) / abs(float(r["r"])))
                for r in sel if float(r["r"]) and float(r["pnl_usdt"])]
        out[kind] = {"n": len(sel), "neto_r": sum(rs) / len(rs),
                     "acierto_pct": 100.0 * sum(1 for x in rs if x > 0) / len(rs),
                     "costo_r": (sum(cost) / len(cost)) if cost else None}
    return out


def render_only(out: FsPath) -> int:
    """Rehace el informe desde el `.json` guardado: las cifras son las mismas, sin recalcular."""
    res = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    out.with_suffix(".md").write_text(rep.render(res), encoding="utf-8")
    rep.write_csv(out.with_suffix(".csv"), res)
    print(f"reescrito {out.with_suffix('.md')} desde {out.with_suffix('.json')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="", help="banco a medir (no hace falta con --render-only)")
    ap.add_argument("--out", default="reports/t143_maker")
    ap.add_argument("--ledger", default="")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--limit", type=int, default=0, help="solo las N primeras ideas (humo)")
    ap.add_argument("--render-only", action="store_true",
                    help="rehace el .md y el .csv desde el .json ya calculado, sin simular")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.render_only:
        return render_only(FsPath(a.out))
    if not a.data:
        print("hace falta --data (el banco a medir)")
        return 2
    data = FsPath(a.data)
    if data.resolve() == FsPath("data").resolve():
        print("no se corre sobre el almacen vivo")
        return 2
    t0 = time.perf_counter()
    tmp = FsPath(tempfile.mkdtemp(prefix="t143_"))
    try:
        shutil.copy2(data / "paper.duckdb", tmp / "paper.duckdb")
        ps = PaperStore(tmp / "paper.duckdb")
        try:
            return run_all(a, FsPath(a.out), Store(data), ps, t0)
        finally:
            ps.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_all(a, out: FsPath, store: Store, ps: PaperStore, t0: float) -> int:
    sym = a.symbol
    desk = PaperDesk(store, ps, profiles=())
    ep = desk.ep
    allideas, path = load_world(store, ps, desk, sym)
    market = [i for i in allideas if i.kind == "market"]
    native = len(allideas) - len(market)
    if a.limit:
        market = market[:a.limit]
    log(t0, f"{len(allideas)} ideas; {len(market)} a mercado (comparables), "
            f"{native} ya límite de nacimiento; camino de {len(path.t)} velas")

    grid: dict[str, dict] = {}
    kept_ref: list[int] = []
    legs_ref: tuple[list, list] | None = None
    for bars in BARS:
        tk, mk, kept, dropped = ab.pair_up(market, path, ep, bars)
        d = ab.paired_delta(tk, mk)
        grid[f"{bars:g}"] = {"bars": bars, "taker": ab.arm_stats(tk), "maker": ab.arm_stats(mk),
                             "delta": d, "descartadas": dropped}
        if bars == DECIDES:
            kept_ref, legs_ref = kept, (tk, mk)
        log(t0, f"fill_h={bars:g} vela(s): {len(tk)} parejas, {dropped} descartadas, "
                f"llenado {ab.arm_stats(mk)['llenado_pct']:.1f} %, ΔE[R] {d['delta']:+.4f} "
                f"[{d['lo']:+.4f}, {d['hi']:+.4f}]")
        gc.collect()

    assert legs_ref is not None
    years = ab.by_year(market, legs_ref[0], legs_ref[1], kept_ref)
    signs = {x["delta"]["delta"] > 0 for x in grid.values()} | {v["delta"] > 0
                                                                for v in years.values()}
    stable = len(signs) == 1
    dec = grid[f"{DECIDES:g}"]
    v = ab.verdict(dec["taker"], dec["maker"], dec["delta"], stable)
    log(t0, f"veredicto: {'ADOPTAR' if v['adopta'] else 'NO ADOPTAR'} — {v['motivo']}")

    # Estrés de cola, añadido después de ver el llenado del 99 %: el motor llena si la vela TOCA
    # el nivel, y una orden en reposo necesita que el precio la atraviese (T79). Solo puede
    # empeorar al maker: por eso se añade aunque no estuviera en el pre-registro.
    stress: dict[str, dict] = {}
    for bps in THROUGH_BPS:
        tk, mk, _, dropped = ab.pair_up(market, path, ep, DECIDES, through_bps=bps)
        d = ab.paired_delta(tk, mk)
        sv = ab.verdict(ab.arm_stats(tk), ab.arm_stats(mk), d, stable)
        stress[f"{bps:g}"] = {"through_bps": bps, "maker": ab.arm_stats(mk), "delta": d,
                              "descartadas": dropped, "veredicto": sv}
        log(t0, f"estrés {bps:g} pb de paso: llenado {ab.arm_stats(mk)['llenado_pct']:.1f} %, "
                f"ΔE[R] {d['delta']:+.4f} [{d['lo']:+.4f}, {d['hi']:+.4f}] → "
                f"{'ADOPTAR' if sv['adopta'] else 'NO ADOPTAR'}")
        gc.collect()

    res = {
        "prereg": PREREG, "prereg_commit": PREREG_COMMIT, "symbol": sym,
        "generado": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "segundos": round(time.perf_counter() - t0, 1),
        "ideas_total": len(allideas), "ideas_mercado": len(market), "ideas_limite_nativas": native,
        "marcos": list(ep.timeframes), "banco": str(a.data), "path_tf": ep.path_tf,
        "costos": ep.costs.model_dump(), "decide_bars": DECIDES,
        "grid": grid, "por_anio": years, "estable": stable, "veredicto": v, "estres": stress,
        "sombra": {"taker": shadow_arm(market, path, ep, None),
                   "maker": shadow_arm(market, path, ep, DECIDES)},
        "libro_vivo": live_cross(FsPath(a.ledger)) if a.ledger else {},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    out.with_suffix(".md").write_text(rep.render(res), encoding="utf-8")
    rep.write_csv(out.with_suffix(".csv"), res)
    log(t0, f"escrito {out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
