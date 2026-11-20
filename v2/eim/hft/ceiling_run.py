"""Corrida de la prueba de techo de T80: panel → variables → techo → fuera de muestra → informe.

Una sola corrida, con los criterios ya congelados (`eim/hft/prereg/hft_ceiling_v1.json`):

    python -m eim.hft.ceiling_run --root data --out reports

Lee el panel ya construido (`python -m eim.data.collectors.hft_panel`), no la captura cruda, y
escribe `reports/hft_ceiling.{md,json}` y el registro de intentos `eim/hft/attempts_t80.json`.
El I/O vive aquí y en `hft_panel.py`; todo el cálculo es puro.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from eim.data.collectors.hft_panel import STEP_MS, load_panel, panel_file
from eim.data.collectors.hft_read import parse_hour
from eim.hft import ceiling, ceiling_gate, ceiling_report, edge_oos
from eim.hft.evaluation.attempts import ATTEMPTS_FILE, write_attempts
from eim.hft.evaluation.labels import forward_window_bps
from eim.hft.evaluation.prereg import load_prereg
from eim.hft.evaluation.splits import day_table, walk_forward
from eim.hft.features import FeatureParams, build_matrix, valid_rows
from eim.hft.features.baseline import baseline_v1

BASELINE = "baseline_v1"


def hours_with_panel(root, symbol: str, first: int, last: int, step_ms: int) -> list[int]:
    return [h for h in range(first, last + 1) if panel_file(root, symbol, h, step_ms).exists()]


def signals(panel, params: FeatureParams) -> tuple[tuple[str, ...], np.ndarray]:
    """Matriz de variables + la línea base del agente v1 como una columna más."""
    names, x = build_matrix(panel, params)
    base = baseline_v1(panel)
    return (*names, BASELINE), np.column_stack([x, base])


def labels(t: np.ndarray, mid: np.ndarray, complete: np.ndarray, horizons,
           lag_ms: int) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    """(filas válidas en TODOS los horizontes, Δmid por horizonte) con la reacción aplicada.

    Se exige la misma máscara para todos los horizontes: así las columnas del informe comparan
    horizontes sobre las mismas filas y no sobre muestras distintas.
    """
    ys, ok = {}, np.ones(t.shape[0], bool)
    for h in horizons:
        y, good = forward_window_bps(t, mid, lag_ms, int(h) * 1000, complete)
        ys[int(h)] = y
        ok &= good
    return ok, ys


def run(root: str | Path, out_dir: str | Path, version: str = "hft_ceiling_v1",
        first: str | None = None, last: str | None = None, step_ms: int = STEP_MS,
        say=print) -> dict:
    """Calcula todo y escribe el informe. Devuelve el JSON del informe."""
    t_start = time.time()
    pr = load_prereg(version)
    symbol = pr.data.symbol
    h0 = parse_hour(first or f"{pr.data.from_}")
    h1 = parse_hour(last or f"{pr.data.to}")
    hours = hours_with_panel(root, symbol, h0, h1, step_ms)
    if not hours:
        raise FileNotFoundError("no hay panel construido en la ventana del pre-registro")
    say(f"panel: {len(hours)} horas de {symbol} ({step_ms} ms)")
    panel = load_panel(root, symbol, hours, step_ms, pr.data.levels)
    params = FeatureParams(levels=pr.data.levels)
    names, x = signals(panel, params)
    t, mid, complete = panel.t, panel.mid, panel.complete
    fills = ceiling.fill_table(panel)
    queue = ceiling.queue_summary(panel)
    rows_total = len(panel)
    del panel
    say(f"filas del panel: {rows_total} · variables: {len(names)} · {time.time() - t_start:.0f} s")
    bound = ceiling.bound_table(t, mid, complete, pr.horizons_s, pr.costs_bps,
                                pr.reaction.used_ms)
    say(f"techo con previsión perfecta hecho · {time.time() - t_start:.0f} s")
    ok, ys = labels(t, mid, complete, pr.horizons_s, pr.reaction.used_ms)
    usable = ok & valid_rows(x, complete, t, step_ms, params.history_buckets)
    t_u, x_u = t[usable], x[usable]
    ys_u = {h: y[usable] for h, y in ys.items()}
    days = sorted(day_table(t_u))
    folds = walk_forward(days, pr.split.train_days, pr.split.test_days, pr.split.embargo_days)
    folds_by_h = {h: folds for h in ys_u}
    say(f"filas utilizables: {t_u.size} · días: {len(days)} · pliegues: {len(folds)}")
    oos = edge_oos.evaluate(t_u, x_u, names, ys_u, folds_by_h, pr.costs_bps, pr.metrics.boot_reps,
                            pr.metrics.level, pr.metrics.seed, step_ms)
    say(f"fuera de muestra hecho · {time.time() - t_start:.0f} s")
    test_days = len({d for f in folds for d in f.test})
    sample = {"days": len(days), "test_days": test_days, "rows": int(t_u.size),
              "rows_panel": rows_total, "hours": len(hours),
              "rows_per_day": day_table(t_u),
              "first_day_utc": _iso(days[0]), "last_day_utc": _iso(days[-1])}
    gate = ceiling_gate.decide(pr, bound, oos, sample)
    report = {"task": "T80", "prereg": pr.version, "prereg_sha256": pr.sha256,
              "generated_at": int(time.time() * 1000), "symbol": symbol, "step_ms": step_ms,
              "reaction_ms": pr.reaction.used_ms, "sample": sample, "queue": queue,
              "fills": fills, "ceiling": bound, "oos": oos, "gate": gate,
              "seconds": round(time.time() - t_start, 1)}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "hft_ceiling.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                          encoding="utf-8", newline="\n")
    (out / "hft_ceiling.md").write_text(ceiling_report.render(report, pr), encoding="utf-8",
                                        newline="\n")
    write_attempts(ATTEMPTS_FILE, pr, oos, {"from": sample["first_day_utc"],
                                            "to": sample["last_day_utc"], "symbol": symbol})
    say(f"informe en {out / 'hft_ceiling.md'} · veredicto {gate['verdict']}")
    return report


def _iso(day: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(day * 86400))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="data")
    ap.add_argument("--out", default="reports")
    ap.add_argument("--prereg", default="hft_ceiling_v1")
    ap.add_argument("--from", dest="first", help="hora UTC AAAA-MM-DDTHH (por defecto, la del "
                                                 "pre-registro)")
    ap.add_argument("--to", dest="last")
    ap.add_argument("--step-ms", type=int, default=STEP_MS)
    a = ap.parse_args(argv)
    rep = run(a.root, a.out, a.prereg, a.first, a.last, a.step_ms)
    print(json.dumps({"veredicto": rep["gate"]["verdict"], "dias": rep["sample"]["days"],
                      "dias_prueba": rep["sample"]["test_days"],
                      "segundos": rep["seconds"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":                                   # pragma: no cover
    raise SystemExit(main())
