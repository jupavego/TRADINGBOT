"""Línea de órdenes de la forja (T208).

    python -m eim.forge enumerate                      # la rejilla, sin tocar datos
    python -m eim.forge prereg [--write]               # pre-registro y su huella
    python -m eim.forge build-data --bank <T131> --out <forja>
    python -m eim.forge run --forge-bank <forja> --bank <T131> [--reps 1000]
    python -m eim.forge smoke --forge-bank <forja> [--sessions 40]

`run` es un trabajo pesado: va por la cola (`python -m eim.operation.jobs submit`), nunca directo.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from eim.forge import data, examine, prereg, report, space
from eim.forge.engine import Rules, simulate


def _hold_day(dates: tuple[str, ...], frm: str) -> int:
    for i, d in enumerate(dates):
        if d >= frm:
            return i
    return len(dates)


def cmd_enumerate(a: argparse.Namespace) -> int:
    rec = space.enumerate_recipes()
    fams = {f: sum(1 for t in space.TRIGGERS if t.family == f) for f in space.FAMILIES}
    print(f"disparadores: {len(space.TRIGGERS)} en {len(space.FAMILIES)} familias")
    for k, v in fams.items():
        print(f"  {k:12} {v}")
    print(f"direcciones: {len(space.DIRECTIONS)} · filtros: {len(space.FILTERS)} · "
          f"salidas: {len(space.EXITS)}")
    print(f"m (recetas) = {len(rec)}")
    print(f"huella de la rejilla = {space.grid_fingerprint()}")
    if a.show:
        for r in rec[:a.show]:
            print(f"  {r.id}  {r.fingerprint}")
    return 0


def cmd_prereg(a: argparse.Namespace) -> int:
    decl = prereg.declaration()
    fp = prereg.fingerprint(decl)
    print(f"{prereg.VERSION} · huella {fp} · m = {decl['grid']['m']} · "
          f"rejilla {decl['grid']['fingerprint']}")
    if fp != prereg.FINGERPRINT:
        print(f"AVISO: la huella fijada en prereg.py es {prereg.FINGERPRINT}")
    if a.write:
        print(f"escrito: {prereg.write()}")
    return 0


def cmd_build_data(a: argparse.Namespace) -> int:
    cov = data.build(Path(a.bank), Path(a.out))
    print(json.dumps(cov, indent=1, ensure_ascii=False))
    return 0


def _load(a: argparse.Namespace):
    s = data.load(Path(a.forge_bank), Path(a.bank) if a.bank else None)
    ss, f = examine.build_features(s)
    return s, ss, f


def cmd_smoke(a: argparse.Namespace) -> int:
    """Mide cuánto cuesta una receta en una rodaja corta, para dimensionar la corrida entera."""
    import time

    s, ss, f = _load(a)
    hd = len(ss.dates)
    mk = examine.market(s, ss, f)
    rules = Rules()
    t0 = time.time()
    tot = 0
    for trig in space.TRIGGERS[:a.triggers]:
        sig = space.signal(trig, "ambos", "ninguno", f, ss.can_signal)
        for ex in space.EXITS:
            tr = simulate(mk, sig, ex, rules)
            tot += len(tr)
    dt = time.time() - t0
    n = a.triggers * len(space.EXITS)
    print(f"{len(s)} velas · {len(ss.dates)} sesiones · {hd} dias dentro de muestra")
    print(f"{n} recetas en {dt:.1f} s ({1000 * dt / n:.1f} ms/receta) · {tot} operaciones")
    print(f"estimado para {len(space.enumerate_recipes())} recetas: "
          f"{dt / n * len(space.enumerate_recipes()) / 60:.1f} min")
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    decl = prereg.declaration()
    if prereg.fingerprint(decl) != prereg.FINGERPRINT:
        print("la huella del pre-registro no coincide con la fijada: no se mide nada", flush=True)
        return 2
    decl["fingerprint"] = prereg.FINGERPRINT
    crit = decl["criteria"]
    s, ss, f = _load(a)
    hold_day = _hold_day(ss.dates, prereg.HOLDOUT_FROM)
    print(f"{len(s)} velas de 5 m · {len(ss.dates)} sesiones · dentro de muestra {hold_day} "
          f"(reserva desde {prereg.HOLDOUT_FROM})", flush=True)
    rules = Rules()
    fam = examine.simulate_all(s, ss, f, hold_day, rules)
    print(f"simulado en {fam.seconds:.0f} s · {int(fam.n.sum())} operaciones", flush=True)
    res = examine.screen(fam, decl, a.reps or crit["bootstrap_reps"], crit["seed"])
    n_pos = fam.n[fam.n > 0]
    control = examine.random_control(s, ss, f, rules,
                                     int(np.median(n_pos)) if len(n_pos) else 100)
    # estrés de costos: exacto (se vuelve a simular) solo en las que pueden sobrevivir
    look = list(dict.fromkeys(res["survivors"] + [r["id"] for r in res["rows"][:10]]))
    stress = {i: {"1.0": next(r["mean_r"] for r in res["rows"] if r["id"] == i)} for i in look}
    mk = examine.market(s, ss, f)
    by = {r.id: r for r in fam.recipes}
    exits = {e.id: e for e in space.EXITS}
    trig = {t.id: t for t in space.TRIGGERS}
    for mult in crit["cost_stress"]:
        for i in look:
            r = by[i]
            raw = np.asarray(trig[r.trigger].fn(f), dtype=np.int8)
            sig = space.apply(raw, r.direction, r.filter, f, ss.can_signal)
            tr = simulate(mk, sig, exits[r.exit], rules, cost_mult=mult, flip=raw)
            keep = tr.day < hold_day
            stress[i][str(mult)] = (float(tr.r[keep].mean()) if keep.any() else None)
    hold = examine.holdout(fam, res["survivors"]) if res["survivors"] else None
    cov = json.loads((Path(a.forge_bank) / "cobertura_5m.json").read_text(encoding="utf-8"))
    rep = report.build(res, decl, cov, control, stress, hold)
    j, m = report.write(rep, Path(a.out) if a.out else None)
    print(f"informe: {j} · {m}", flush=True)
    print(f"sobreviven {len(res['survivors'])} de {res['m']}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eim.forge", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("enumerate")
    e.add_argument("--show", type=int, default=0)
    e.set_defaults(fn=cmd_enumerate)
    p = sub.add_parser("prereg")
    p.add_argument("--write", action="store_true")
    p.set_defaults(fn=cmd_prereg)
    b = sub.add_parser("build-data")
    b.add_argument("--bank", required=True)
    b.add_argument("--out", required=True)
    b.set_defaults(fn=cmd_build_data)
    for name, fn in (("run", cmd_run), ("smoke", cmd_smoke)):
        c = sub.add_parser(name)
        c.add_argument("--forge-bank", required=True)
        c.add_argument("--bank", default=None)
        c.add_argument("--out", default=None)
        c.add_argument("--reps", type=int, default=None)
        c.add_argument("--triggers", type=int, default=4)
        c.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    return int(a.fn(a))


if __name__ == "__main__":
    sys.exit(main())
