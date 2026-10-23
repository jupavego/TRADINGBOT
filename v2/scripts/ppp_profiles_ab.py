"""T111 — A/B de salidas por perfil: reglas actuales (TP/BE+/tiempo) frente a protección progresiva.

    python scripts/ppp_profiles_ab.py --data <carpeta con candles/, funding/ y paper.duckdb>

Reconstruye las ideas y la sombra con el MISMO cálculo que la API (`PaperDesk.view`) sobre una
COPIA del almacén y, por perfil (Conservador, Moderado, Agresivo), corre:
- A: el perfil con `exit_mode="tp"` (TP, BE+ y tiempo, como antes de T109);
- B: el perfil con la escalera de T108/T109 (umbral del encargo) y la sensibilidad 0,5 R y 1 R;
- A/B emparejado: las entradas que A abrió de verdad, con la salida B encima (`ab_pairs`);
- dentro y fuera de muestra por separado, con el capital reiniciado en cada tramo;
- condiciones de mercado por día (`ab_conditions`) y los criterios de T49 (`ab_gate`).
Mismo motor, mismas ideas, mismo camino, mismos costos y la misma semilla de la puerta. NO
modifica nada fuera de la copia. Informe en `reports/ppp_profiles_ab.md` (+ `.json` y `.csv`).
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path as FsPath

from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.validation_store import ValidationStore
from eim.paper.ab_conditions import by_condition, ex_ante, labeler
from eim.paper.ab_gate import gate_trades, gate_verdicts, strict_oos
from eim.paper.ab_pairs import cut_winners, pair_trades, split
from eim.paper.book import run_profile
from eim.paper.desk import MMR, PaperDesk
from eim.paper.engine import Path, _slip
from eim.paper.feedback import Learner
from eim.paper.ladder_book import LadderSim
from eim.paper.ladder_metrics import profile_metrics
from eim.paper.params import PROFILES, ProfileParams
from eim.paper.summary import positions_of
from eim.validation.criteria import load_criteria
from eim.validation.lineage import Window, iso_ms

sys.path.insert(0, str(FsPath(__file__).parent))
from ppp_ab_paths import fine_path, optimistic_fine  # noqa: E402
from ppp_ab_report import render  # noqa: E402

THREE = ("conservador", "moderado", "agresivo")
SENS = (None, 0.5, 1.0)          # None = umbral del encargo (T108); el incremento es la mitad
# Dentro de muestra = lo que se MIRÓ para ajustar alguna de las dos salidas: el BE+ de A se eligió
# con 2026-08-16 → 2026-10-16 (T48b, `val_windows`) y la escalera de B se diseñó y midió con
# 2026-09-10 → hoy (T105–T110). Fuera de muestra = todo lo anterior a 2026-08-16.
IS_FROM = "2026-08-16T00:00:00Z"
EXIT_WINDOW_FROM = "2026-09-10T00:00:00Z"        # T105: primer dato que vio la escalera
REJECT = (("objetivo estimado neto", "viabilidad (usa el objetivo/TP)"),
          ("cupo lleno", "cupo lleno"), ("en observación", "en observación (memoria)"),
          ("estrategia en pausa", "estrategia en pausa (memoria)"),
          ("contexto en pausa", "contexto en pausa (memoria)"),
          ("tope de riesgo", "tope de riesgo por dirección"), ("margen", "margen insuficiente"),
          ("cuenta agotada", "cuenta agotada"), ("capital", "capital insuficiente"),
          ("freno", "freno de entradas"), ("posición duplicada", "posición duplicada"),
          ("lado opuesto", "sin cobertura"), ("costo estimado", "costo > tope"),
          ("cantidad", "cantidad bajo el mínimo"))


def variant(p: ProfileParams, k: float | None) -> ProfileParams:
    if k is None:
        return p
    return p.model_copy(update={"ladder": p.ladder.model_copy(
        update={"first_r": k, "step_r": k / 2})})


def tag(p: ProfileParams, k: float | None) -> str:
    lp = p.ladder
    return f"B {lp.first_r if k is None else k:g} R" + (" (encargo)" if k is None else "")


def book_metrics(st, mmr: float, now: int) -> tuple[dict, list[dict]]:
    pos, _, upnl = positions_of(st, mmr)
    curve = list(st.curve) + ([(now, st.equity + upnl)] if st.curve else [])
    return profile_metrics(st.trades, pos, st.p.initial_equity, curve, st.violations,
                           "equity (curva del libro: cierres y marca final, T107)"), pos


def pair_metrics(pairs, initial: float) -> dict:
    out = {}
    for key, viable in (("comunes", True), ("vetadas_en_b", False)):
        a_cl, a_op, b_cl, b_op = split(pairs, viable)
        base = "R acumulado de las mismas entradas (sin cuenta: tamaños de A)"
        out[key] = {"a": profile_metrics(a_cl, a_op, initial, None, dd_base=base),
                    "b": profile_metrics(b_cl, b_op, initial, None, dd_base=base)}
    out["no_negociables_en_b"] = sum(1 for x in pairs if x.b is None)
    out["mismo_llenado"] = sum(1 for x in pairs if x.same_fill)
    out["negociables"] = sum(1 for x in pairs if x.b is not None)
    out["n"] = len(pairs)
    out["cortes"] = cut_winners(pairs)
    return out


def optimistic(book_a, by_id, pb, opt: dict[int, LadderSim], mmr, initial) -> dict:
    """El emparejado con la cota optimista de B: largos y cortos con su orden favorable."""
    pairs = [x for side in (1, -1) for x in pair_trades(book_a, by_id, pb, opt[side], mmr)
             if (x.a["side"] > 0) == (side > 0)]
    return pair_metrics(pairs, initial)


def entry_diff(book_a, book_b) -> dict:
    ids = [{t["id"] for t in b.trades} | {s for s, x in b.slots.items() if x.filled}
           for b in (book_a, book_b)]
    rej = {e["idea"]: e["text"] for e in book_b.events if e["cat"] == "rechazada"}
    why = Counter(next((lab for k, lab in REJECT if k in rej.get(i, "")),
                       "sin evento" if i not in rej else "otro") for i in ids[0] - ids[1])
    return {"a": len(ids[0]), "b": len(ids[1]), "comunes": len(ids[0] & ids[1]),
            "solo_a": len(ids[0] - ids[1]), "solo_b": len(ids[1] - ids[0]),
            "solo_a_por_motivo": dict(why.most_common()),
            "entradas_minimo_abiertas": {"a": sum(1 for t in book_a.trades if t.get("floor")),
                                         "b": sum(1 for t in book_b.trades if t.get("floor"))}}


def slip_fix(st, path: Path, ep) -> float:
    """≈ USDT de deslizamiento de entrada que el arreglo de BACKLOG T109 (1) deja de cobrar a B."""
    out = 0.0
    for t in st.trades:
        if t["kind"] == "market":
            j = int(path.t.searchsorted(t["fill_t"]))
            out += t["notional"] * (_slip(path, j, ep) - _slip(path, j, ep, entry=True))
    return out


def run_segment(name, outs, by_id, sim, mmr, now, label, rows) -> dict:
    learner = Learner(outs)
    opt = {s: LadderSim(sim.path, sim.ep, optimistic_fine(sim.path, s)) for s in (1, -1)}
    t0 = min(o.idea.t for o in outs)
    res = {"name": name, "ideas": len(outs), "from": t0, "to": max(o.idea.t for o in outs),
           "timeframes": dict(Counter(o.idea.timeframe for o in outs)), "profiles": {}}
    for p in (x for x in PROFILES if x.id in THREE):
        pa = p.model_copy(update={"exit_mode": "tp"})
        book_a = run_profile(pa, outs, learner, mmr, sim)
        ma, _ = book_metrics(book_a, mmr, now)
        r = {"A": {"metrics": ma, "conditions": by_condition(book_a.trades, label)},
             "B": {}, "gate": {"A": (pa, book_a)}}
        for k in SENS:
            pb = variant(p, k)
            book_b = run_profile(pb, outs, learner, mmr, sim)
            mb, _ = book_metrics(book_b, mmr, now)
            pairs = pair_trades(book_a, by_id, pb, sim, mmr)
            common = [x for x in pairs if x.viable_b and x.b is not None
                      and not x.open_a and not x.open_b]
            r["B"][tag(p, k)] = {
                "k": k, "first_r": pb.ladder.first_r, "step_r": pb.ladder.step_r,
                "metrics": mb, "conditions": by_condition(book_b.trades, label),
                "entries": entry_diff(book_a, book_b),
                "pairs": pair_metrics(pairs, p.initial_equity),
                "pairs_optimista": optimistic(book_a, by_id, pb, opt, mmr, p.initial_equity),
                "pair_conditions": {"a": by_condition([x.a for x in common], label),
                                    "b": by_condition([x.b for x in common], label)},
                "pair_regimes": {"a": by_condition([x.a for x in common], label, ex_ante),
                                 "b": by_condition([x.b for x in common], label, ex_ante)},
                "slip_fix_usd": slip_fix(book_b, sim.path, sim.ep)}
            r["gate"][tag(p, k)] = (pb, book_b)
            if k is None:
                rows += [{"tramo": name, "perfil": p.id, "id": t["id"], "t": t["t"],
                          "motivo": t["reason"], "neto": round(t["pnl"], 4),
                          "flotante_max": t["ladder"].get("max_float_usd"),
                          "escalon": t["ladder"]["level"],
                          "protegido": t["ladder"].get("nominal_usd")}
                         for t in book_b.trades if t.get("ladder")]
        res["profiles"][p.id] = r
    return res


def gate_block(segs, by_id, sim, vstore, crit, symbol, asof, prices) -> dict:
    """Informativo (fuera de la ventana de las salidas) y estricto (ventanas registradas)."""
    prior = {f"{s}|{sid}@v{n}": p for (s, sid, n), p in vstore.last_pvalues(crit.version).items()}
    exit_w = (Window(iso_ms(IS_FROM), asof + 1, None, "T111: ajuste del BE+ y de la escalera"),)
    versions = vstore.versions()
    info, strict, excl = [], [], {}
    for pid in THREE:
        for key, (p, book_out) in segs["fuera"]["profiles"][pid]["gate"].items():
            info.append((f"{pid}|{key}", gate_trades(book_out.trades, by_id, sim, p)))
            both = book_out.trades + segs["dentro"]["profiles"][pid]["gate"][key][1].trades
            keep, why = strict_oos(both, by_id, versions, exit_w, symbol)
            excl[f"{pid}|{key}"] = why
            strict.append((f"{pid}|{key}", gate_trades(keep, by_id, sim, p)))
    return {"informativo": gate_verdicts(info, prior, crit, symbol, asof, prices),
            "estricto": gate_verdicts(strict, prior, crit, symbol, asof, prices),
            "excluidas_estricto": excl, "intentos_registrados": len(prior)}


def fine_bias(seg_outs, by_id, path, ep, fine, mmr, fine_from) -> dict:
    """B (umbral del encargo) con y sin velas de 1 min en las mismas entradas (las de A en el
    tramo fuera de muestra, desde donde hay 1 min): mide el sesgo de la regla conservadora."""
    outs = [o for o in seg_outs if o.idea.t >= fine_from]
    if not outs or fine is None:
        return {}
    learner = Learner(outs)
    out = {}
    for p in (x for x in PROFILES if x.id in THREE):
        book_a = run_profile(p.model_copy(update={"exit_mode": "tp"}), outs, learner, mmr)
        nets = []
        for f in (fine, None):
            pr = pair_trades(book_a, by_id, p, LadderSim(path, ep, f), mmr)
            nets.append(sum(x.b["pnl"] for x in pr if x.b is not None and not x.open_b))
        out[p.id] = {"con_1m": nets[0], "sin_1m": nets[1], "n": len(book_a.trades)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--is-from", default=IS_FROM)
    ap.add_argument("--out", default="reports/ppp_profiles_ab")
    ap.add_argument("--no-gate", action="store_true")
    ap.add_argument("--from-json", default="", help="solo vuelve a escribir el informe")
    a = ap.parse_args()
    out = FsPath(a.out)
    if a.from_json:
        res = json.loads(FsPath(a.from_json).read_text(encoding="utf-8"))
        out.with_suffix(".md").write_text(render(res), encoding="utf-8")
        print(f"informe en {out.with_suffix('.md')}")
        return 0
    store, ps = Store(a.data), PaperStore(FsPath(a.data) / "paper.duckdb")
    desk = PaperDesk(store, ps, profiles=())
    v = desk.view(a.symbol)
    if not v.outcomes or v.path is None:
        print("sin contextos guardados en la copia")
        return 1
    path, ep, mmr = v.path, desk.ep, MMR.get(a.symbol, 0.005)
    b1m = store.bounds(a.symbol, "1m")
    fine = fine_path(FsPath(a.data), a.symbol)
    sim = LadderSim(path, ep, fine)
    by_id = {o.idea.id: o for o in v.outcomes}
    cut, label, rows = iso_ms(a.is_from), labeler(path), []
    segs = {}
    for name, outs in (("fuera", [o for o in v.outcomes if o.idea.t < cut]),
                       ("dentro", [o for o in v.outcomes if o.idea.t >= cut])):
        segs[name] = run_segment(name, outs, by_id, sim, mmr, path.end, label, rows)
        print(f"tramo {name}: {len(outs)} ideas", flush=True)
    crit = load_criteria()
    gate = ({} if a.no_gate else gate_block(segs, by_id, sim, ValidationStore(ps), crit,
                                            a.symbol, path.end, (path.t, path.c)))
    bias = fine_bias([o for o in v.outcomes if o.idea.t < cut], by_id, path, ep, fine, mmr,
                     b1m[0] if b1m else 0)
    for s in segs.values():
        for r in s["profiles"].values():
            r.pop("gate")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                          text=True).stdout.strip()
    meta = {"data": a.data, "symbol": a.symbol, "is_from": a.is_from, "exit_window_from":
            EXIT_WINDOW_FROM, "path_end": path.end, "fine_from": b1m[0] if b1m else None,
            "fine_rows": 0 if fine is None else len(fine.t),
            "commit": head, "command": "python scripts/ppp_profiles_ab.py --data <copia> "
            f"--symbol {a.symbol} --is-from {a.is_from}", "ideas": len(v.outcomes),
            "coverage": v.summary.get("coverage"), "ladder": {
                p.id: {"first_r": p.ladder.first_r, "step_r": p.ladder.step_r,
                       "be_with_ladder": p.ladder.be_with_ladder,
                       "max_weight": p.ladder.max_weight} for p in PROFILES if p.id in THREE},
            "exec": ep.model_dump(mode="json"), "criteria": crit.version}
    res = {"meta": meta, "segments": segs, "gate": gate, "fine_bias": bias}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1,
                                                   default=str), encoding="utf-8")
    with out.with_suffix(".csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["tramo"])
        w.writeheader()
        w.writerows(rows)
    out.with_suffix(".md").write_text(render(res), encoding="utf-8")
    print(f"informe en {out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
