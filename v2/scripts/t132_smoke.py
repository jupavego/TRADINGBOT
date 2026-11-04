"""T132 — comprobación de que las candidatas corren sobre la copia real y con qué cobertura.

    python scripts/t132_smoke.py --data backups/t131_banco --limit 4000

**No elige ninguna política ni ajusta parámetros**: eso es T134. Lo que hace es lo que las pruebas
sintéticas no pueden: medir la **cobertura real** de los rasgos en 3,5 años de BTC (¿cuántas velas
tienen σ?, ¿cuántas tienen swing confirmado?, ¿cuánto cubre el HAR-RV?) y confirmar que cada
candidata cierra operaciones sin incidencias. Si un rasgo cubre poco, la política que lo use se
queda con su valor base y hay que saberlo ANTES de medir nada.

Escribe `reports/t132_smoke.{json,md}`. No toca nada fuera de la copia y no abre red.
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
from eim.paper.desk import PaperDesk
from eim.paper.engine import Path as PricePath
from eim.paper.exits import bench, features, metrics
from eim.paper.exits.candidates import (
    HtfExit,
    InitialStopExit,
    TimeExit,
    TrailExit,
    sigma_floor,
)
from eim.paper.exits.policy import ExitContext
from eim.paper.exits.prereg import load_prereg
from eim.paper.exits.trail import TrailLimits
from eim.paper.exits.walkforward import iso
from eim.paper.params import spec_for

SIGMAS = ("atr14", "parkinson", "garman_klass", "yang_zhang", "harrv_1m")
# Marco mayor de cada camino, como en `ExecParams.htf`: 1 h para decisiones sobre 15 m.
HTF_OF = {"15m": "1h", "1h": "4h", "4h": "4h"}


def build_policies(f, path_t) -> list:
    """Una variante de cada familia implementada, con parámetros del centro de la rejilla."""
    lim = TrailLimits(floor_n=2.0)
    return [
        TrailExit("M2 k=3", "M2 chandelier k=3", f, "M2", {"k": 3.0, "activate_r": 0.5}, lim),
        TrailExit("M3 f5", "M3 estructura fractal 5", f, "M3", {"buffer_sigma": 0.25}, lim),
        TrailExit("M5", "M5 hibrida", f, "M5",
                  {"k": 3.0, "survival_r": 0.3, "a_r": 1.0, "b_r": 0.1, "trail": "M2"}, lim),
        TimeExit("M6 b16", "M6 barrera de tiempo", f, bars=16, min_r=0.5),
        HtfExit("M7", "M7 reversion del marco mayor", f),
        # S1 cambia la GEOMETRIA del SL inicial, no es una salida por si sola: sin nada que la
        # cierre en positivo solo puede perder (su E[R] condicionado a cerrar es −1 R por
        # construccion). Se mide como T134 la usaria: compuesta con un arrastre.
        InitialStopExit("S1 d2 + M2", "S1 piso de 2 sigma con M2", "S1", f,
                        sigma_floor(f, path_t, 2.0),
                        inner=TrailExit("M2", "M2", f, "M2", {"k": 3.0}, lim)),
        InitialStopExit("S1 d2 sola", "S1 piso de 2 sigma, sin salida", "S1", f,
                        sigma_floor(f, path_t, 2.0)),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="reports/t132_smoke")
    ap.add_argument("--limit", type=int, default=4000)
    ap.add_argument("--sigma", default="parkinson")
    a = ap.parse_args()
    data = Path(a.data)
    if data.resolve() == Path("data").resolve():
        print("no se corre sobre el almacen vivo")
        return 2
    pr = load_prereg()
    sym = pr.symbol
    t0 = time.perf_counter()
    store, ps = Store(data), PaperStore(data / "paper.duckdb")
    desk = PaperDesk(store, ps, profiles=())
    v = desk.view(sym)
    if not v.outcomes or v.path is None:
        print("la copia no tiene contextos guardados")
        return 1
    fine = (PricePath.from_arrays(store.read_arrays(sym, pr.design.fine_timeframe),
                                  tf_ms(pr.design.fine_timeframe))
            if store.bounds(sym, pr.design.fine_timeframe) else None)

    cover = {}
    htf_tf = HTF_OF.get(pr.design.path_timeframe, "1h")
    htf = (PricePath.from_arrays(store.read_arrays(sym, htf_tf), tf_ms(htf_tf))
           if store.bounds(sym, htf_tf) else None)
    for name in SIGMAS:
        cover[name] = features.build(v.path, name, swing_bars=5, fine=fine,
                                     htf=htf).to_json()
    f = features.build(v.path, a.sigma, swing_bars=5, fine=fine, htf=htf)
    print(f"rasgos listos ({time.perf_counter() - t0:.0f} s); cobertura de sigma "
          f"{f.coverage['sigma_abs']:.1%}", flush=True)

    tfs = set(pr.design.decision_timeframes)
    ideas = sorted((o.idea for o in v.outcomes
                    if o.idea.strategy != bench.CONTROL_STRATEGY and o.idea.timeframe in tfs),
                   key=lambda x: (x.t, x.id))[:a.limit]
    pols = build_policies(f, v.path.t)
    ctx = ExitContext(path=v.path, ep=desk.ep, spec=spec_for(sym), fine=fine)
    b = bench.run(ideas, pols, ctx, pr.risk_usd)
    print(f"banco: {len(b.rows)} ideas, {len(b.paired())} emparejadas "
          f"({time.perf_counter() - t0:.0f} s)", flush=True)

    per = {}
    for p in pols:
        ts = b.trades(p.id, paired_only=False)
        m = metrics.summary(ts)
        per[p.id] = {"params": p.params, "n": m.get("n", 0),
                     "expectancy_r": m.get("expectancy_r"), "win_rate": m.get("win_rate"),
                     "pf": m.get("pf"), "cost_r": m.get("cost_r"),
                     "exits": m.get("exits"), "dropped": b.dropped.get(p.id, {})}
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True, check=False).stdout.strip()
    res = {"meta": {"data": str(data), "symbol": sym, "commit": head, "sigma": a.sigma,
                    "htf": htf_tf if htf is not None else "sustituto (sin marco mayor)",
                    "built": iso(int(time.time() * 1000)), "ideas": len(ideas),
                    "paired": len(b.paired()),
                    "fine_bars": 0 if fine is None else len(fine.t),
                    "seconds": round(time.perf_counter() - t0, 1)},
           "feature_coverage": cover, "policies": per}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1,
                                                   default=str), encoding="utf-8")
    out.with_suffix(".md").write_text(render(res), encoding="utf-8")
    print(f"\ninforme en {out.with_suffix('.md')}")
    for pid, x in per.items():
        print(f"  {pid}: n={x['n']} E[R]={x['expectancy_r']} salidas={x['exits']}")
    return 0


def render(res: dict) -> str:
    m = res["meta"]
    out = [f"# T132 — las candidatas sobre la copia real ({m['symbol']})", "",
           f"**Modo: SIMULADO.** Generado el {m['built']} desde `{m['data']}` "
           f"(commit `{m['commit']}`), σ `{m['sigma']}`, marco mayor `{m['htf']}`, "
           f"{m['fine_bars']} velas de 1 min. "
           f"{m['ideas']} ideas, {m['paired']} emparejadas, {m['seconds']:.0f} s.", "",
           "**Esto no elige ninguna política ni ajusta parámetros: eso es T134.** Solo comprueba "
           "que corren sobre datos reales y con qué cobertura de rasgos.", "",
           "## Cobertura de los rasgos", "",
           "| Estimador σ | σ | swing bajo | swing alto | marco mayor | rango |",
           "|---|--:|--:|--:|--:|--:|"]
    for name, c in res["feature_coverage"].items():
        k = c["coverage"]
        out.append(f"| `{name}` | {k['sigma_abs']:.1%} | {k['swing_low']:.1%} | "
                   f"{k['swing_high']:.1%} | {k['htf_dir']:.1%} | {k['bar_range']:.1%} |")
    out += ["", "Un rasgo con poca cobertura no es un error: la política que lo use se queda con "
            "su valor base en esas velas, que es la regla del proyecto (la falta de datos no "
            "aprieta). Pero hay que saberlo antes de medir.", "",
            "## Las candidatas corren", "",
            "| Política | n | Acierto | E[R] | PF | Costo R | Motivos de cierre |",
            "|---|--:|--:|--:|--:|--:|---|"]
    for pid, x in res["policies"].items():
        wr = x.get("win_rate")
        out.append(f"| `{pid}` | {x['n']} | {'—' if wr is None else f'{wr:.1%}'} | "
                   f"{_f(x.get('expectancy_r'))} | {_f(x.get('pf'), 2)} | "
                   f"{_f(x.get('cost_r'))} | {x.get('exits')} |")
    out += ["", "Las cifras son descriptivas y de un tramo recortado: **no** son fuera de muestra "
            "ni pasan por los criterios de §5.4.", ""]
    return "\n".join(out) + "\n"


def _f(x, k: int = 3) -> str:
    return "—" if x is None else f"{x:+.{k}f}"


if __name__ == "__main__":
    raise SystemExit(main())
