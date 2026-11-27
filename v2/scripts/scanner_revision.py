"""Revisión para decidir T96 (◆ de T95: «acepto y pauso T96»). Desde `v2/`:

    python scripts/scanner_revision.py --summary ../_revision_t96.txt

La lanza sola `scripts/revision_t96.ps1` el 2026-12-29, después de `calibrate` y de repetir el
placebo. Lee el registro de intentos de `data/scanner/scanner.duckdb` y `data/scanner/placebo.json`,
aplica la regla fijada antes en `PLAN/notas/T96_revision.md` y escribe
`reports/revision_t96.{md,json}`. Modo ANÁLISIS: no envía órdenes ni valida nada.
Códigos de salida: 0 hecho (cualquier veredicto); 5 sin registro del escáner.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))

MIN_SYNTH = 200            # resultados maduros de la síntesis para poder juzgar
REPS = 100_000


def _day(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).date().isoformat()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Revisión de T96 (T95)")
    ap.add_argument("--data-dir", default=os.environ.get("EIM_DATA_DIR", "data"))
    ap.add_argument("--out", default="reports/revision_t96.md")
    ap.add_argument("--summary")
    a = ap.parse_args(argv)

    from eim.data.scanner_store import ScannerStore
    from eim.scanner import multiplicity as mu
    from eim.scanner import placebo_eval as pe
    from eim.scanner import rank
    from eim.validation import stats as st
    from eim.validation.criteria import load_criteria

    data = Path(a.data_dir)
    db = data / "scanner" / "scanner.duckdb"
    if not db.exists():
        print(f"sin registro del escáner en {db}", file=sys.stderr)
        return 5
    store = ScannerStore(db)
    try:
        counts = dict(store.attempt_counts())
        days = [r[0] for r in store._q("SELECT DISTINCT cut_ms FROM attempt_obs ORDER BY 1")]
        rows = store._q("SELECT o.cut_ms, o.outcome, o.outcome_flip FROM attempt_obs o JOIN "
                        "attempts a ON a.attempt_key = o.attempt_key WHERE a.agent_id = ? AND "
                        "o.matured = TRUE ORDER BY o.cut_ms", [mu.SYNTHESIS_AGENT])
        fam = store.family()
    finally:
        store.close()
    crit = load_criteria()
    alpha = crit.v3_random.alpha
    adj = mu.adjust(fam)
    holm_pass = sorted(k for k, (ph, _) in adj.items() if ph < alpha)
    # prueba agregada de la síntesis: una media por día de decisión (los instrumentos del mismo
    # día comparten mercado), lado al azar a nivel de día
    by_day: dict[int, list[tuple[float, float]]] = {}
    for t, o, f in rows:
        by_day.setdefault(int(t), []).append((float(o), float(f)))
    d_out = np.array([np.mean([x[0] for x in v]) for v in by_day.values()])
    d_flip = np.array([np.mean([x[1] for x in v]) for v in by_day.values()])
    n_syn = len(rows)
    p_syn = (st.random_side_pvalue(d_out, d_flip, REPS, st.rng_for(crit.seed, "revision_t96"))
             if len(by_day) >= 3 else None)
    mean_syn = float(np.mean([o for _, o, _ in rows])) if rows else None
    w = rank.load_weights(data)
    thr = {}
    try:
        thr = json.loads(pe.threshold_path(data).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    ev = thr.get("evaluation") or {}
    placebo_ok = bool(ev.get("beats_chance"))
    enough = n_syn >= MIN_SYNTH
    syn_ok = enough and p_syn is not None and p_syn < alpha and (mean_syn or 0) > 0
    if not enough:
        verdict = (f"POSPONER: solo {n_syn} resultados maduros de la síntesis (< {MIN_SYNTH}). "
                   "Repetir la revisión en 4 semanas y comprobar que el escáner corrió a diario.")
    elif syn_ok and placebo_ok:
        verdict = ("ARRANCAR T96: la síntesis del escáner gana al lado al azar hacia adelante "
                   f"(p {p_syn:.4f}) y el placebo con los pesos vigentes supera el azar.")
    else:
        verdict = ("NO ARRANCAR T96 todavía: " + "; ".join(x for x in (
            None if syn_ok else f"la síntesis no gana al azar hacia adelante (p "
                                f"{'—' if p_syn is None else f'{p_syn:.4f}'}, media "
                                f"{'—' if mean_syn is None else f'{mean_syn:+.3f}'} σ)",
            None if placebo_ok else "el placebo no supera el azar") if x)
                   + ". Repetir en 4 semanas o replantear la fase 17.")
    rep = {"generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
           "days_with_passes": len(days), "first_day": _day(days[0]) if days else None,
           "last_day": _day(days[-1]) if days else None, "counts": counts,
           "synthesis": {"matured": n_syn, "days": len(by_day), "mean_sigma": mean_syn,
                         "p_day_clustered": p_syn},
           "family": {"total": mu.family_size(len(fam)), "holm_pass": holm_pass},
           "weights": w.as_json(), "placebo": {k: ev.get(k) for k in (
               "threshold", "real_above", "p_global", "beats_chance", "replicas")},
           "placebo_computed_at": thr.get("computed_at"), "verdict": verdict}
    lines = ["# Revisión de T96 (programada por la ◆ de T95)", "",
             f"Generada {rep['generated']}. Regla fijada antes en `PLAN/notas/T96_revision.md`.",
             "", f"**Veredicto: {verdict}**", "",
             f"- Días con pasada de agentes: {len(days)} ({rep['first_day']} → "
             f"{rep['last_day']}).",
             f"- Intentos registrados: {counts.get('attempts')}; observaciones "
             f"{counts.get('observations')}; maduras {counts.get('matured')}.",
             f"- Síntesis: {n_syn} resultados maduros en {len(by_day)} días; media "
             f"{'—' if mean_syn is None else f'{mean_syn:+.3f}'} σ neta de costos; p (lado al "
             f"azar, una media por día) {'—' if p_syn is None else f'{p_syn:.4f}'}.",
             f"- Familia: {rep['family']['total']} hipótesis; superan Holm: {len(holm_pass)}.",
             f"- Pesos del ranking: {'calibrados' if w.calibrated else 'iguales'} "
             f"({w.source}).",
             f"- Placebo ({thr.get('computed_at')}): umbral {ev.get('threshold')}, reales por "
             f"encima {ev.get('real_above')}, p global {ev.get('p_global')} → "
             f"{'supera' if placebo_ok else 'no supera'} el azar.", "",
             "Nada de esto valida una estrategia: la única puerta que valida es la v1 de T49."]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(rep, ensure_ascii=False, indent=1,
                                                   default=str), encoding="utf-8")
    print(verdict)
    if a.summary:
        Path(a.summary).write_text(verdict, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
