"""T139 — una ronda de hipótesis de entrada, por la puerta de T49. Tres etapas, en este orden:

    python scripts/t139_entradas.py --data backups/t139_banco --stage cobertura   # ningún R
    python scripts/t139_entradas.py --data backups/t139_banco --stage banco       # contaminado
    python scripts/t139_entradas.py --data backups/t139_banco --stage limpia      # una vez

Aplica `prereg_t139_v1` tal cual y escribe `reports/t139_*`. Abre una COPIA temporal del
`paper.duckdb` de la copia: no toca el almacén vivo, no abre red y no habilita dinero real.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import duckdb
import numpy as np

from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.data.validation_store import ValidationStore
from eim.paper.exits import walkforward as wf
from eim.validation.attempts import ATTEMPTS_DIR, load_attempts, write_attempts
from eim.validation.criteria import load_criteria
from eim.validation.hypotheses import report as rp
from eim.validation.hypotheses import rules as ru
from eim.validation.hypotheses import world as wd
from eim.validation.hypotheses.prereg import Prereg, load_prereg
from eim.validation.lineage import iso_ms

PREREG_COMMIT = "3d396f7"
T137_FILE = ATTEMPTS_DIR / "attempts_t137.json"
THIS_FILE = ATTEMPTS_DIR / "attempts_t139.json"
REPORTS = Path("reports")


def log(t0: float, msg: str) -> None:
    print(f"[{time.perf_counter() - t0:7.0f} s] {msg}", flush=True)


def load_minutes(store: Store, sym: str) -> ru.Minutes:
    """Velas de 1 min con su volumen, que `read_arrays` no trae, y solo aquí hace falta."""
    src = store.sql_source("candles", sym, "1m", None, None)
    a = duckdb.connect().execute(f"SELECT t, o, h, l, c, v FROM {src} ORDER BY t").fetchnumpy()
    t = np.asarray(a["t"], dtype=np.int64)
    return ru.Minutes(t, *(np.asarray(a[k], dtype=float) for k in "ohlcv"))


def load_world(store: Store, sym: str, t0: float) -> wd.World:
    candles = {tf: store.read_candles(sym, tf) for tf in ("1h", "4h", "15m")}
    log(t0, f"velas: { {k: len(v) for k, v in candles.items()} }")
    w = wd.world_of(sym, candles, store.read_series("funding", sym), load_minutes(store, sym))
    log(t0, f"1 min: {len(w.minutes.t)}; funding: {len(w.funding)}; 1 d: {len(w.series['1d'].t)}")
    return w


def measure_coverage(store: Store, w: wd.World, pr: Prereg) -> dict:
    """Cobertura real del tramo limpio. Nada se da por cubierto."""
    cov = pr.coverage
    a, b = iso_ms(cov.from_), iso_ms(cov.to)
    series = {}
    for name in cov.series:
        if name == "funding":
            rows = sum(1 for t, _ in w.funding if a <= t < b)
            expected = (b - a) // (8 * 3_600_000)
        else:
            ts = store.read_arrays(pr.symbol, name, a, b - 1)["t"]
            rows, expected = len(ts), (b - a) // tf_ms(name)
        series[name] = {"rows": int(rows), "expected": int(expected),
                        "coverage": rows / expected if expected else 0.0,
                        "ok": bool(expected and rows / expected >= cov.min)}
    taker = {}
    for tf in cov.taker_timeframes:
        s = w.series[tf]
        keep = (s.t >= a) & (s.t < b)
        with_data = int(np.isfinite(s.taker[keep]).sum())
        rows = int(keep.sum())
        taker[tf] = {"rows": rows, "with_data": with_data,
                     "coverage": with_data / rows if rows else 0.0,
                     "ok": bool(rows and with_data / rows >= cov.min)}
    ok, flow = all(x["ok"] for x in series.values()), all(x["ok"] for x in taker.values())
    verdict = ("cumple." if ok and flow else
               "H2 y H3 caen por falta de `taker_buy_v`; siguen contando en Holm." if ok else
               "NO cumple: se para (P0).")
    return {"from": cov.from_, "to": cov.to, "min": cov.min, "series": series, "taker": taker,
            "first_minute": wf.iso(int(w.minutes.t[0])) if len(w.minutes.t) else None,
            "ok": ok, "flow_ok": flow, "verdict": verdict}


def prior_keys(ps: PaperStore, crit, sym: str) -> dict:
    """La familia ya gastada: el registro de la copia + los intentos de T137, que no están en él."""
    vstore = ValidationStore(ps)
    prior = {f"{s}|{sid}@v{n}": p for (s, sid, n), p in vstore.last_pvalues(crit.version).items()}
    for v in vstore.versions():
        prior.setdefault(f"{sym}|{v.label}", None)
    for v in load_attempts(T137_FILE):
        prior.setdefault(f"{sym}|{v.label}", None)
    return prior


def meta(a, pr: Prereg, crit, w: wd.World, family: int, t0: float) -> dict:
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                          check=False).stdout.strip()
    return {"data": a.data, "symbol": pr.symbol, "stage": a.stage, "commit": head,
            "prereg": pr.version, "prereg_sha256": pr.sha256, "prereg_commit": PREREG_COMMIT,
            "criteria": crit.version, "criteria_sha256": crit.sha256,
            "asof": wf.iso(int(w.path.end)),
            "family": family, "null_reps": crit.null_reps(family),
            "code": ru.code_hash(), "seconds": round(time.perf_counter() - t0, 1),
            "command": f"python scripts/t139_entradas.py --data {a.data} --stage {a.stage}",
            "repeat_reason": a.repeat_reason or None}


def dump(path: Path, res: dict) -> None:
    keep = {k: v for k, v in res.items() if k not in ("versions", "trades")}
    path.write_text(json.dumps(keep, ensure_ascii=False, indent=0, default=_num) + "\n",
                    encoding="utf-8", newline="\n")


def _num(x):
    return x.item() if isinstance(x, np.generic) else str(x)


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=rp.CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--stage", required=True, choices=("cobertura", "banco", "limpia"))
    ap.add_argument("--repeat-reason", default="", help="solo un defecto del código, y se declara")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    data = Path(a.data)
    if data.resolve() == Path("data").resolve():
        print("no se corre sobre el almacen vivo")
        return 2
    clean_json = REPORTS / "t139_entradas.json"
    if a.stage == "limpia" and clean_json.exists() and not a.repeat_reason:
        print("la lectura limpia ya se gasto: repetirla exige --repeat-reason, y queda declarado")
        return 2
    t0 = time.perf_counter()
    pr, crit = load_prereg(), load_criteria()
    tmp = Path(tempfile.mkdtemp(prefix="t139_"))
    try:
        shutil.copy2(data / "paper.duckdb", tmp / "paper.duckdb")
        ps = PaperStore(tmp / "paper.duckdb")
        try:
            return run_stage(a, pr, crit, Store(data), ps, t0)
        finally:
            ps.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_stage(a, pr: Prereg, crit, store: Store, ps: PaperStore, t0: float) -> int:
    sym = pr.symbol
    w = load_world(store, sym, t0)
    ep = ru.exec_params(pr)
    cov = measure_coverage(store, w, pr)
    log(t0, f"cobertura: {cov['verdict']}")
    dropped = () if cov["flow_ok"] else wd.FLOW
    prior = prior_keys(ps, crit, sym)
    log(t0, f"claves previas: {len(prior)}")
    REPORTS.mkdir(exist_ok=True)

    if a.stage == "cobertura":
        ideas = wd.key_ideas(pr, w, ep, dropped)
        res = {"coverage": cov, "sample": wd.sample_counts(pr, w, ep, ideas)}
        res["meta"] = meta(a, pr, crit, w, len(prior) + pr.attempts.new, t0)
        dump(REPORTS / "t139_cobertura.json", res)
        (REPORTS / "t139_cobertura.md").write_text(rp.render_coverage(res), encoding="utf-8",
                                                   newline="\n")
        log(t0, f"muestra: {json.dumps(res['sample'], ensure_ascii=False)}")
        return 0 if cov["ok"] else 1

    if not cov["ok"]:
        print("P0: el tramo limpio no tiene cobertura; no se corre nada mas")
        return 1
    if a.stage == "banco":
        stored = [c for c in ps.load(sym, "1h")]
        res = wd.bank_stage(pr, crit, w, ep, prior, stored, lambda m: log(t0, m), dropped)
        res["meta"] = meta(a, pr, crit, w, res["family"], t0)
        dump(REPORTS / "t139_banco.json", res)
        (REPORTS / "t139_banco.md").write_text(rp.render_bank(res), encoding="utf-8", newline="\n")
        variant = {v.label: v.sid.split("@")[0] for v in res["versions"]}
        write_attempts(THIS_FILE, pr.version, pr.sha256, res["versions"], variant, task="T139")
        log(t0, f"informe en {REPORTS / 't139_banco.md'}; intentos en {THIS_FILE.name}")
        return 0

    reg_ok = _bank_regression_ok()
    if not reg_ok:
        print("sin regresion en verde en reports/t139_banco.json: primero la etapa banco")
        return 2
    res = wd.clean_stage(pr, crit, w, ep, prior, cov["ok"], lambda m: log(t0, m), dropped)
    res["meta"] = meta(a, pr, crit, w, res["family"], t0)
    res["coverage"] = cov
    dump(REPORTS / "t139_entradas.json", res)
    write_csv(REPORTS / "t139_entradas.csv", res["rows"])
    (REPORTS / "t139_entradas.md").write_text(rp.render_clean(res), encoding="utf-8", newline="\n")
    log(t0, f"recomendación: {res['recommendation']['code']}")
    return 0


def _bank_regression_ok() -> bool:
    p = REPORTS / "t139_banco.json"
    if not p.exists():
        return False
    reg = json.loads(p.read_text(encoding="utf-8")).get("regression") or {}
    return (reg.get("stored") or {}).get("ok") is True


if __name__ == "__main__":
    raise SystemExit(main())
