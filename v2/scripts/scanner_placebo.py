"""T95 — control placebo del escáner global. Desde `v2/`:

    python scripts/scanner_placebo.py                          # 30 permutadas + 10 gaussianas
    python scripts/scanner_placebo.py --replicas 3 --gaussian 0   # prueba rápida

Corre el MISMO escáner (etapa 3 → lista corta → agentes elegibles → síntesis → proyección →
ranking) sobre el universo real con la última vela guardada y sobre réplicas sin estructura
temporal (`eim/scanner/placebo.py`). Escribe `reports/scanner_placebo.md` y `.json`, y el umbral
vigente en `<datos>/scanner/placebo.json`, que lee la pasada de agentes. No abre `scanner.duckdb`,
no descarga nada y no envía órdenes. Reglas fijadas antes: `PLAN/notas/T95_preregistro.md`.
Códigos de salida: 0 hecho; 5 sin catálogo o sin velas; 6 error (traza completa en `--log` y en
`reports/scanner_placebo_error.txt`). Si el grupo de procesos se rompe, sigue en un solo proceso.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2))

PREREG = V2.parent / "PLAN" / "notas" / "T95_preregistro.md"


def _f(x, k=3) -> str:
    return "—" if x is None else f"{x:.{k}f}"


def render(rep: dict) -> str:
    ev, g, m = rep["permuted"], rep.get("gaussian"), rep["meta"]
    yes = ev["beats_chance"]
    lines = [
        "# T95 — Control placebo del escáner global", "",
        f"Generado {m['computed_at']} · corte {m['cut_iso']} (última vela guardada) · universo "
        f"de {m['n_universe']} perpetuos que pasan las etapas 1–2 · lista corta "
        f"{m['shortlist_size']} · {m['n_agents']} agentes (huella `{m['agents']}`) · pesos "
        f"`{m['weights']['fingerprint']}` ({m['weights']['source']}) · semilla {m['seed']}.",
        f"Pre-registro `PLAN/notas/T95_preregistro.md` (SHA-256 `{m['prereg_sha256']}`), anterior "
        "a esta corrida. Modo ANÁLISIS: nada de esto es una orden ni una validación.", "",
        "## Respuesta a la ◆", "",
        (f"**Sí, por encima del azar en esta pasada**: {ev['real_above']} candidata(s) superan el "
         f"umbral {_f(ev['threshold'])} y el mejor hallazgo real supera al mejor del azar con p "
         f"global {_f(ev['p_global'], 4)} < α = {ev['alpha']}." if yes else
         f"**No: el escáner no muestra nada que supere el azar** en el universo de Binance. Con "
         f"el umbral {_f(ev['threshold'])}, {ev['real_above']} candidata(s) reales lo superan "
         f"(el azar daría {_f(ev['false_per_pass'], 2)} por pasada) y el p global de «el mejor "
         f"hallazgo real supera al mejor del azar» es {_f(ev['p_global'], 4)} (α = "
         f"{ev['alpha']}). Un «no» es un resultado válido (T95)."),
        "", "Aunque saliera «sí», ninguna candidata queda **validada**: eso solo lo da la puerta "
        "v1 de T49, y el registro de intentos hacia adelante empieza hoy (0 resultados maduros: "
        "p ajustado = 1 para todas hasta que maduren ≥ 10 observaciones por intento).", "",
        "## Real frente a placebo", "",
        "| | Réplicas | Candidatas (media) | Máx. prioridad | Umbral | Reales ≥ umbral | Falsos "
        "por pasada | FDR estimada | p global |", "|---|---|---|---|---|---|---|---|---|",
        f"| Real | — | {ev['real_candidates']} | {_f(ev['real_max'])} | — | — | — | — | — |",
    ]
    for name, e in (("Permutada (vinculante)", ev), ("Gaussiana (sensibilidad)", g)):
        if e:
            nm = [x for x in e["null_max"] if x is not None]
            lines.append(f"| {name} | {e['replicas']} | {_f(e['null_candidates_mean'], 1)} | "
                         f"{_f(float(np.median(nm)) if nm else None)} (mediana) | "
                         f"{_f(e['threshold'])} | {e['real_above']} | "
                         f"{_f(e['false_per_pass'], 2)} | {_f(e['fdr_estimate'], 2)} | "
                         f"{_f(e['p_global'], 4)} |")
    lines += ["", f"Umbral: {ev['threshold_rule']}. Tasa de falsos por candidata con ese umbral: "
              f"{_f(ev['null_rate_per_candidate'], 4)}.", "",
              "## Candidatas reales por prioridad", "",
              "| # | Instrumento | Lado | Prioridad | ≥ umbral | Ventaja neta (σ) | Ventaja (R) | "
              "Incertidumbre (σ) | Señal | Viabilidad | Riesgo/costos |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rep["real_ranked"][:15]:
        n, s = r["normalized"], r["normalized"]["scores"]
        lines.append(f"| {r['position'] or '—'} | {r['symbol']} | {r['side']} | "
                     f"{_f(r['priority'])} | {'sí' if r['priority'] is not None and r['priority'] >= ev['threshold'] else 'no'} | "  # noqa: E501
                     f"{_f(n['edge_sigma'], 2)} | {_f(n['edge_r'], 2)} | "
                     f"{_f(n['uncertainty_sigma'], 2)} | {_f(s['quality'], 2)} | "
                     f"{_f(s['viability'], 2)} | {_f(s['risk'], 2)} |")
    lines += ["", "## Límites (dichos tal cual)", "",
              "- Es **una** pasada real frente a réplicas: dice si la prioridad del escáner "
              "distingue el universo real de uno sin estructura temporal, no si una candidata "
              "paga. Eso lo mide el registro de intentos hacia adelante (Holm/BH sobre la familia "
              "completa) y, al final, la puerta v1 de T49.",
              "- La permutación conserva volatilidad, distribución y correlación contemporánea, y "
              "destruye también la agrupación de la volatilidad; la gaussiana no conserva colas.",
              f"- Con {ev['replicas']} réplicas el p global más pequeño posible es "
              f"{1 / (1 + ev['replicas']):.3f}; el umbral es una estimación con esa resolución.",
              "- Las cifras de prioridad y ventaja salen de la proyección existente (deriva de la "
              "síntesis), no de resultados: son lecturas comparables, no rentabilidades."]
    return "\n".join(lines) + "\n"


class _Tee:
    """Copia lo que se escribe en consola a un archivo (la transcripción de PowerShell no
    recoge la salida de los programas)."""

    def __init__(self, stream, f) -> None:
        self.stream, self.f = stream, f

    def write(self, x: str) -> int:
        self.f.write(x)
        self.f.flush()
        try:
            return self.stream.write(x)
        except (UnicodeEncodeError, ValueError):
            return len(x)

    def flush(self) -> None:
        self.f.flush()
        self.stream.flush()


class _Runner:
    """Analiza las cargas en el grupo de procesos; si se rompe, sigue en este proceso."""

    def __init__(self, pool, analyze) -> None:
        self.pool, self.analyze = pool, analyze

    def __call__(self, payloads: list[dict]) -> list[dict]:
        if self.pool is not None:
            try:
                return list(self.pool.map(self.analyze, payloads))
            except Exception as exc:  # noqa: BLE001 - BrokenProcessPool, pickling, OSError
                print(f"  AVISO: el grupo de procesos falló ({type(exc).__name__}: {exc}); "
                      "sigo en un solo proceso", flush=True)
                self.pool = None
        return [self.analyze(p) for p in payloads]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Control placebo del escáner (T95)")
    ap.add_argument("--data-dir", default=os.environ.get("EIM_DATA_DIR", "data"))
    ap.add_argument("--asof", default="latest")
    ap.add_argument("--replicas", type=int, default=30)
    ap.add_argument("--gaussian", type=int, default=10)
    ap.add_argument("--seed", type=int, default=95)
    ap.add_argument("--alpha", type=float)
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--out", default="reports/scanner_placebo.md")
    ap.add_argument("--summary", help="archivo con una línea de resumen (para el plan)")
    ap.add_argument("--log", help="copia de toda la salida (y de la traza si algo falla)")
    a = ap.parse_args(argv)
    if a.log:
        f = open(a.log, "w", encoding="utf-8")  # noqa: SIM115 - vive lo que dura el proceso
        sys.stdout, sys.stderr = _Tee(sys.stdout, f), _Tee(sys.stderr, f)
    try:
        return _run(a)
    except Exception:  # noqa: BLE001 - se escribe la traza completa y se sale con 6
        tb = traceback.format_exc()
        print(tb, file=sys.stderr, flush=True)
        err = Path(a.out).with_name("scanner_placebo_error.txt")
        err.parent.mkdir(parents=True, exist_ok=True)
        err.write_text(tb, encoding="utf-8")
        return 6


def _run(a) -> int:

    from eim.data import scanner_market as market
    from eim.data.timeframes import tf_ms, tf_offset
    from eim.scanner import deep, placebo, rank, universe
    from eim.scanner import placebo_eval as pe
    from eim.scanner.__main__ import parse_asof
    from eim.scanner.params import DEFAULT_PARAMS as P
    from eim.scanner.service import data_stats
    from eim.validation.criteria import file_hash, load_criteria

    data_dir = Path(a.data_dir)
    root = market.universe_root(data_dir)
    insts, _ = market.read_catalog(data_dir, P.venue)
    if not insts or market.latest_t(root, P.timeframe) is None:
        print("sin catálogo o sin velas del universo: corre `python -m eim.scanner sync "
              "--discover`", file=sys.stderr)
        return 5
    asof = parse_asof(a.asof, root, P.timeframe)
    step, off = tf_ms(P.timeframe), tf_offset(P.timeframe)
    cut = universe.closed_cut(step, asof, off)
    k1, _ = universe.stage1(insts, P, asof)
    panel = market.load_panel(root, {i.symbol: i.id for i in k1}, P.timeframe, P.n_bars, cut)
    k2, _, _ = universe.stage2(k1, data_stats(panel, P), P, step, asof, off)
    print(f"leyendo {len(k2)} series de {P.deep_bars} velas…", flush=True)
    series = {}
    for i in k2:
        cs = market.read_window(root, i.symbol, P.timeframe, P.deep_bars, cut)
        if len(cs) >= P.min_bars:
            series[i.id] = cs
    by_id = {i.id: i for i in k2 if i.id in series}
    s = placebo.stack(series, P.deep_bars)
    print(f"universo: {len(insts)} en el catálogo, {len(k1)} tras la etapa 1, {len(by_id)} con "
          f"velas tras la etapa 2; corte {cut}", flush=True)
    agents = deep.default_agents()
    w = rank.load_weights(data_dir)
    alpha = a.alpha if a.alpha is not None else load_criteria().v3_random.alpha
    t0 = time.perf_counter()
    pool = ProcessPoolExecutor(max_workers=a.procs) if a.procs > 1 else None
    runner = _Runner(pool, placebo.safe_analyze)
    try:
        def one(x, label: str) -> dict:
            t = time.perf_counter()
            r = placebo.scan(x, by_id, n_bars=P.n_bars, shortlist_size=P.shortlist_size,
                             run_many=runner, timeframe=P.timeframe, cut=cut, asof=asof,
                             weights=w, min_score=P.min_score)
            print(f"  {label}: {r['n_candidates']} candidatas, prioridad máx. "
                  f"{_f(r['max'])} ({time.perf_counter() - t:.0f} s)", flush=True)
            return r

        real = one(s, "real")
        nulls = [one(placebo.permuted(s, np.random.default_rng([a.seed, k])),
                     f"permutada {k + 1}/{a.replicas}") for k in range(a.replicas)]
        gauss = [one(placebo.gaussian(s, np.random.default_rng([a.seed, 10_000 + k])),
                     f"gaussiana {k + 1}/{a.gaussian}") for k in range(a.gaussian)]
    finally:
        if pool is not None:
            pool.shutdown(cancel_futures=True)
    ev = pe.evaluate(real, nulls, alpha)
    ev_g = pe.evaluate(real, gauss, alpha) if gauss else None
    fp = pe.fingerprint(w, deep.agents_fingerprint(agents), deep.versions())
    now = dt.datetime.now(dt.UTC)
    meta = {"kind": "permuted", "computed_at": now.isoformat(timespec="seconds"),
            "asof": asof, "cut": cut,
            "cut_iso": dt.datetime.fromtimestamp(cut / 1000, dt.UTC).isoformat(),
            "n_universe": len(by_id), "shortlist_size": P.shortlist_size, "seed": a.seed,
            "n_agents": len(agents), "agents": deep.agents_fingerprint(agents),
            "weights": w.as_json(), "deep_versions": deep.versions(),
            "prereg_sha256": file_hash(PREREG.read_bytes()) if PREREG.exists() else None,
            "elapsed_s": round(time.perf_counter() - t0, 1)}
    pe.write_threshold(data_dir, ev, fp, meta)
    rep = {"meta": meta, "fingerprint": fp, "permuted": ev, "gaussian": ev_g,
           "real_ranked": real["ranked"], "real_shortlist": real["shortlist"],
           "real_reasons": real["reasons"]}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(rep), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(rep, ensure_ascii=False, indent=1,
                                                   default=str), encoding="utf-8")
    line = (f"placebo T95 ({ev['replicas']} permutadas"
            + (f" + {ev_g['replicas']} gaussianas" if ev_g else "")
            + f", universo de {len(by_id)}): umbral {_f(ev['threshold'])}; reales por encima "
            f"{ev['real_above']} de {ev['real_candidates']} (máx. {_f(ev['real_max'])}); falsos "
            f"esperados por pasada {_f(ev['false_per_pass'], 2)}; FDR ≈ "
            f"{_f(ev['fdr_estimate'], 2)}; p global {_f(ev['p_global'], 4)} → "
            + ("SUPERA el azar" if ev["beats_chance"] else "NO supera el azar")
            + (f" (gaussiana: p global {_f(ev_g['p_global'], 4)})" if ev_g else ""))
    print(line)
    print(f"informe: {out} · umbral vigente: {pe.threshold_path(data_dir)}")
    if a.summary:
        Path(a.summary).write_text(line, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
