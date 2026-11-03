"""T131 — corre el banco de salidas sobre una COPIA del almacén y escribe su informe.

    python scripts/t131_bench.py --data backups/t131_banco

Reconstruye las ideas con el MISMO cálculo que la API (`PaperDesk.view`, como T111), corre las
variantes implementadas de la rejilla **pre-registrada** (M0 y M1; las demás llegan con T132, T133
y T136) sobre las mismas entradas con tamaño fijo, y escribe `reports/t131_banco.{json,md}`.

No toca nada fuera de la copia y no abre red. La copia la prepara `scripts/t131_history.py`.
Con `--stress` repite el banco con el deslizamiento de los stops ×1,5 y ×2 (E4a); con `--to`
se recorta el camino, que es lo que permite reproducir una corrida anterior (T111) con su mismo
final de camino.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.paper.desk import MMR, PaperDesk
from eim.paper.engine import Path as PricePath
from eim.paper.exits import run
from eim.paper.exits.costs import stressed
from eim.paper.exits.policy import ExitContext
from eim.paper.exits.prereg import load_prereg
from eim.paper.exits.report import render
from eim.paper.exits.walkforward import from_iso, iso
from eim.paper.params import LADDER_BY_PROFILE, spec_for


def fine_path(store: Store, symbol: str, tf: str) -> PricePath | None:
    """Velas finas de la copia como camino (sin un objeto por vela: pueden ser millones)."""
    if store.bounds(symbol, tf) is None:
        return None
    return PricePath.from_arrays(store.read_arrays(symbol, tf), tf_ms(tf))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True, help="copia del almacén (nunca data/)")
    ap.add_argument("--out", default="reports/t131_banco")
    ap.add_argument("--prereg", default="")
    ap.add_argument("--to", default="", help="recorta el camino en este instante ISO")
    ap.add_argument("--limit", type=int, default=0, help="solo las N primeras ideas (pruebas)")
    ap.add_argument("--stress", action="store_true", help="repite con los costos de E4a")
    ap.add_argument("--no-fine", action="store_true", help="sin velas de 1 min (más rápido)")
    ap.add_argument("--identity", type=int, default=500,
                    help="ideas reales con las que comprobar la identidad con el motor de T111")
    a = ap.parse_args()
    data = Path(a.data)
    if data.resolve() == Path("data").resolve():
        print("el banco no corre sobre el almacén vivo")
        return 2
    pr = load_prereg(**({"path": a.prereg} if a.prereg else {}))
    symbol = pr.symbol

    t0 = time.perf_counter()
    store, ps = Store(data), PaperStore(data / "paper.duckdb")
    desk = PaperDesk(store, ps, profiles=())
    v = desk.view(symbol)
    if not v.outcomes or v.path is None:
        print("la copia no tiene contextos guardados: nada que medir")
        return 1
    ideas = [o.idea for o in v.outcomes]
    if a.to:
        cut = from_iso(a.to)
        ideas = [i for i in ideas if i.t < cut]
    if a.limit:
        ideas = sorted(ideas, key=lambda x: (x.t, x.id))[:a.limit]
    fine = None if a.no_fine else fine_path(store, symbol, pr.design.fine_timeframe)
    print(f"ideas {len(ideas)} - camino {len(v.path.t)} velas - finas "
          f"{0 if fine is None else len(fine.t)} - {time.perf_counter() - t0:.0f} s", flush=True)
    ladder = LADDER_BY_PROFILE["moderado"]
    base_ctx = ExitContext(path=v.path, ep=desk.ep, spec=spec_for(symbol), fine=fine)
    ident = run.engine_identity(ideas, base_ctx, ladder, pr.risk_usd, a.identity)
    print(f"identidad con el motor de T111: {ident['checked']} ideas, "
          f"{len(ident['mismatches'])} diferencias ({time.perf_counter() - t0:.0f} s)", flush=True)
    res = run.analyse(ideas, base_ctx, pr, ladder)
    res["engine_identity"] = ident
    print(f"banco base: {time.perf_counter() - t0:.0f} s", flush=True)
    ctrl = run.control_report(ideas, base_ctx, pr, ladder)
    stress = {}
    if a.stress:
        for f in pr.cost_stress.stop_slip_multipliers:
            if f == 1.0:
                continue
            ctx = ExitContext(path=v.path, ep=stressed(desk.ep, f), spec=base_ctx.spec, fine=fine)
            stress[f] = run.analyse(ideas, ctx, pr, ladder, cost_factor=f)
            print(f"estrés ×{f:g}: {time.perf_counter() - t0:.0f} s", flush=True)

    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True, check=False).stdout.strip()
    meta = {"data": str(data), "symbol": symbol, "commit": head,
            "built": iso(int(time.time() * 1000)), "prereg": pr.to_json(),
            "path": {"bars": len(v.path.t), "from": iso(int(v.path.t[0])),
                     "to": iso(int(v.path.t[-1]))},
            "fine_bars": 0 if fine is None else len(fine.t),
            "coverage": v.summary.get("coverage"), "mmr": MMR.get(symbol, 0.005),
            "exec": desk.ep.model_dump(mode="json"), "ladder": ladder.model_dump(mode="json"),
            "seconds": round(time.perf_counter() - t0, 1)}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(
        {"meta": meta, "result": res, "control": ctrl,
         "stress": {str(k): x for k, x in stress.items()}},
        ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    out.with_suffix(".md").write_text(render(meta, res, ctrl, stress or None), encoding="utf-8")
    print(f"informe en {out.with_suffix('.md')} ({meta['seconds']:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
