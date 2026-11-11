"""T161: potencia a priori y SPA sobre la familia de T139 (sin gastar ninguna lectura).

    python scripts/t161_potencia_spa.py --data backups/t139_banco

Vuelve a simular las operaciones de las 9 claves de T139 con el mismo código y los mismos datos,
**comprueba que salen idénticas a lo publicado** en `reports/t139_entradas.json` (n y media neta
por clave) y solo entonces calcula MinTRL, el SPA de la familia y el MCS. No escribe nada de T139,
no añade intentos a Holm y no cambia ningún veredicto: es otra pregunta sobre los mismos números.

Pesado (velas de 1 min desde 2019): va por la cola, `eim.operation.jobs`, con `--min-ram-mb`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # el `eim` de este checkout

import numpy as np  # noqa: E402
import t139_entradas as t139  # noqa: E402

from eim.data.paper_store import PaperStore  # noqa: E402
from eim.data.store import Store  # noqa: E402
from eim.validation.criteria import load_criteria  # noqa: E402
from eim.validation.hypotheses import pipeline as pp  # noqa: E402
from eim.validation.hypotheses import rules as ru  # noqa: E402
from eim.validation.hypotheses import world as wd  # noqa: E402
from eim.validation.hypotheses.prereg import load_prereg  # noqa: E402
from eim.validation.power import power_row  # noqa: E402
from eim.validation.spa import daily_matrix, mcs, spa_test  # noqa: E402

REPORTS = Path("reports")
TARGET_NET = 0.10        # ventaja neta por operación que se querría poder detectar (R)
REPS = 5000
SEED = 161


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    data = Path(a.data)
    if data.resolve() == Path("data").resolve():
        print("no se corre sobre el almacen vivo")
        return 2
    t0 = time.perf_counter()
    pr, crit = load_prereg(), load_criteria()
    tmp = Path(tempfile.mkdtemp(prefix="t161_"))
    try:
        shutil.copy2(data / "paper.duckdb", tmp / "paper.duckdb")
        ps = PaperStore(tmp / "paper.duckdb")
        try:
            res = run(pr, crit, Store(data), ps, t0)
        finally:
            ps.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if res is None:
        return 1
    res["meta"] = {"data": f"backups/{data.name}", "prereg": pr.version, "reps": REPS,
                   "seed": SEED, "target_net_r": TARGET_NET,
                   "command": f"python scripts/t161_potencia_spa.py --data backups/{data.name}"}
    (REPORTS / "t161_potencia_spa.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    t139.log(t0, "listo: reports/t161_potencia_spa.json")
    return 0


def run(pr, crit, store: Store, ps: PaperStore, t0: float) -> dict | None:
    sym = pr.symbol
    w = t139.load_world(store, sym, t0)
    ep = ru.exec_params(pr)
    cov = wd.coverage_of(pr, w, lambda tf, x, y: len(store.read_arrays(sym, tf, x, y - 1)["t"]))
    dropped = () if cov["flow_ok"] else wd.FLOW
    versions, family = wd.setup(pr, ep, t139.prior_keys(ps, crit, sym), sym)
    ideas = wd.key_ideas(pr, w, ep, dropped)
    trades = wd.key_trades(pr, w, ep, ideas, lambda m: t139.log(t0, m))
    asof = int(w.path.end)
    published = {r["sid"]: r for r in json.loads(
        (REPORTS / "t139_entradas.json").read_text(encoding="utf-8"))["rows"]}
    out: dict = {"family_holm": len(family), "readings": {}}
    for rid in ("oficial", "banco"):
        r = pr.reading(rid)
        sel = {v.sid: pp.selected(r, v, trades.get(v.sid, []), sym, asof) for v in versions}
        if rid == "oficial":
            check = regression(sel, published)
            out["regression"] = check
            if not check["ok"]:
                print(f"la simulacion no reproduce T139: {check}")
                return None
        out["readings"][rid] = reading(sel, w)
        t139.log(t0, f"{rid}: SPA p = {out['readings'][rid]['spa_net']['p_consistent']:.4f}")
    return out


def regression(sel: dict, published: dict) -> dict:
    rows = {}
    for sid, xs in sel.items():
        pub = published.get(sid)
        mean = float(np.mean([x.r for x in xs])) if xs else None
        ok = (pub is not None and pub["n"] == len(xs)
              and (mean is None or abs(mean - pub["mean_r"]) < 1e-9))
        rows[sid] = {"n": len(xs), "n_pub": None if pub is None else pub["n"],
                     "mean": mean, "mean_pub": None if pub is None else pub["mean_r"], "ok": ok}
    return {"ok": all(x["ok"] for x in rows.values()) and len(rows) == len(published),
            "rows": rows}


def reading(sel: dict, w) -> dict:
    power, net, gross = {}, {}, {}
    ts = [x.t for xs in sel.values() for x in xs]
    start, end = min(ts), max(ts) + 1
    days = (end - start) / 86_400_000
    for sid, xs in sel.items():
        r = [x.r for x in xs]
        g = [x.r + x.cost_r for x in xs]
        cost = float(np.mean([x.cost_r for x in xs])) if xs else 0.0
        row_net = power_row(r, 0.0, TARGET_NET)
        row_gross = power_row(g, cost)
        rate = len(xs) / days if days > 0 else 0.0
        power[sid] = {"net": row_net.to_json(), "gross": row_gross.to_json(),
                      "mean_cost": round(cost, 6), "trades_per_day": round(rate, 4),
                      "days_for_target": (round(row_net.n_apriori / rate, 1)
                                          if rate > 0 and row_net.n_apriori < float("inf")
                                          else None)}
        net[sid] = [(x.t, x.r) for x in xs]
        gross[sid] = [(x.t, x.r + x.cost_r) for x in xs]
    names, m_net = daily_matrix(net, start, end)
    _, m_gross = daily_matrix(gross, start, end)
    return {"days": int(m_net.shape[0]), "power": power,
            "spa_net": spa_test(names, m_net, REPS, SEED).to_json(),
            "spa_gross": spa_test(names, m_gross, REPS, SEED).to_json(),
            "mcs_net": {k: round(v, 6) for k, v in mcs(names, m_net, 0.10, REPS, SEED).items()}}


if __name__ == "__main__":
    raise SystemExit(main())
