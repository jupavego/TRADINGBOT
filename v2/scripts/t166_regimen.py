"""T166: modelo de saltos frente a HMM y BOCPD en el banco de T133, según el pre-registro.

    python scripts/t166_regimen.py --data backups/t131_banco

Familia, tramos, métrica, puerta de potencia y regla de adopción en
`PLAN/notas/T166_preregistro.md` v2, anterior a todo resultado del banco (la v1 es el commit
d5ae85e y su §«Versión 2» dice qué se corrigió y por qué). Escribe
`reports/t166_regimen.json` con las cifras y las secuencias de estados; el informe en Markdown se
redacta a partir de él y el R por estado lo calcula `scripts/t166_r_por_estado.py`.

Va por la cola (`eim.operation.jobs`). No abre red y no toca el almacén vivo.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # el `eim` de este checkout

import duckdb  # noqa: E402
import numpy as np  # noqa: E402

from eim.agents.regime import daily  # noqa: E402
from eim.backtest.edge import holm  # noqa: E402
from eim.data.store import Store  # noqa: E402
from eim.forecast import vol_eval as ve  # noqa: E402
from eim.forecast import vol_models as vm  # noqa: E402
from eim.validation.lineage import iso_ms  # noqa: E402
from eim.validation.power import n_needed  # noqa: E402
from eim.validation.spa import block_length, mcs_with_aliases, mean_diff_test  # noqa: E402

SYMBOL = "BTCUSDT"
FIT_TO = "2023-07-01T00:00:00Z"      # fin del ajuste inicial / inicio del tramo de potencia
EVAL_FROM = "2024-01-01T00:00:00Z"   # el único tramo que decide
REPS = 5000
SEED = 166
K = 2
# Penalización del salto en unidades de los datos (λ = c · distancia cuadrática media con λ = 0):
# «cuántos días de prueba cuesta saltar». Rejilla declarada en el pre-registro v2.
CS = {"J1": 0.5, "J2": 2.0, "J3": 8.0}
NAMES = ("U0", "M0", "J1", "J2", "J3", "H1")
CANDIDATES = ("J1", "J2", "J3", "H1")
MDE_GATE = 0.020                     # puerta de potencia pre-registrada, en unidades de QLIKE
REFIT_EVERY = 20


def log(t0: float, msg: str) -> None:
    print(f"[{time.perf_counter() - t0:7.0f} s] {msg}", flush=True)


def build(data: Path, t0: float) -> dict:
    """Días válidos del banco con sus rasgos estandarizados de forma causal."""
    store = Store(data)
    src = store.sql_source("candles", SYMBOL, "1m", None, None)
    m = duckdb.connect().execute(f"SELECT t, o, h, l, c FROM {src} ORDER BY t").fetchnumpy()
    t = np.asarray(m["t"], np.int64)
    log(t0, f"1 min: {len(t)} velas")
    ds = vm.daily_series(t, np.asarray(m["c"], float))
    ex = daily.day_extras(t, np.asarray(m["o"], float), np.asarray(m["h"], float),
                          np.asarray(m["l"], float), np.asarray(m["c"], float))
    del m
    if not np.array_equal(ds["day"], ex["day"]):
        raise RuntimeError("los días de la RV y de los rasgos no coinciden")
    ok = ds["ok"] & np.isfinite(ds["ret"]) & np.isfinite(ex["er"]) & np.isfinite(ex["rng"])
    days = ds["day"][ok]
    ln_rv = np.log(ds["rv"][ok])
    ret = ds["ret"][ok]
    raw = np.column_stack([ret, ln_rv, ex["er"][ok], ex["rng"][ok]])
    z = daily.expanding_z(raw)
    keep = np.isfinite(z).all(axis=1)
    log(t0, f"días: {int(ok.sum())} válidos de {len(ds['day'])}; {int(keep.sum())} con escala")
    return {"days": days[keep], "ln_rv": ln_rv[keep], "ret": ret[keep], "z": z[keep],
            "excluded_low_cov": int((~ds["ok"]).sum())}


def states_of(b: dict, t0: float) -> dict[str, np.ndarray]:
    """Secuencia de estados causal de cada modelo de la familia."""
    z, n = b["z"], len(b["days"])
    first = int(np.searchsorted(b["days"], iso_ms(FIT_TO) // daily.DAY_MS))
    st: dict[str, np.ndarray] = {"U0": np.zeros(n, dtype=np.int16)}
    st["M0"] = daily.bocpd_states(b["ret"])
    log(t0, f"M0 (BOCPD diario): {int((st['M0'] >= 0).sum())} días con etiqueta")
    for name, c in CS.items():
        st[name] = daily.jump_states(z, first, K, c, REFIT_EVERY)
        log(t0, f"{name} (saltos, c={c:g}) listo")
    st["H1"] = daily.hmm_states(z, first, K, REFIT_EVERY)
    log(t0, "H1 (HMM) listo")
    return st


def masks(b: dict, h: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """(tramo de potencia, tramo de evaluación): días consecutivos con RV y pronósticos válidos."""
    days = b["days"]
    base = np.zeros(len(days), dtype=bool)
    base[1:] = days[1:] == days[:-1] + 1
    base &= np.isfinite(b["ln_rv"])
    for k in NAMES:
        base &= np.isfinite(h[k]) & (h[k] > 0)
    cut = iso_ms(EVAL_FROM) // daily.DAY_MS
    fit_cut = iso_ms(FIT_TO) // daily.DAY_MS
    return base & (days >= fit_cut) & (days < cut), base & (days >= cut)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="reports/t166_regimen.json")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    data = Path(a.data)
    if data.resolve() == Path("data").resolve():
        print("no se corre sobre el almacen vivo")
        return 2
    t0 = time.perf_counter()
    b = build(data, t0)
    st = states_of(b, t0)
    rv = np.exp(b["ln_rv"])
    h = {"U0": daily.forecast_next(st["U0"], b["ln_rv"], 0)}
    for k in NAMES[1:]:
        h[k] = daily.forecast_next(st[k], b["ln_rv"])
    pw, ev = masks(b, h)
    loss = {k: ve.qlike(rv, h[k]) for k in NAMES}

    res = {
        "meta": {"symbol": SYMBOL, "data": f"backups/{data.name}", "reps": REPS, "seed": SEED,
                 "k": K, "jump_c": CS, "refit_every": REFIT_EVERY,
                 "fit_to": FIT_TO, "eval_from": EVAL_FROM,
                 "prereg": "PLAN/notas/T166_preregistro.md v2",
                 "command": f"python scripts/t166_regimen.py --data backups/{data.name}"},
        "days": {"usable": int(len(b["days"])), "power": int(pw.sum()), "eval": int(ev.sum()),
                 "first": int(b["days"][0]), "last": int(b["days"][-1]),
                 "excluded_low_cov": b["excluded_low_cov"]},
    }

    # --- Puerta de potencia: antes de abrir la hipótesis (BACKLOG T161 (3)) ---
    sd = {k: float(np.std(loss[k][pw] - loss["M0"][pw], ddof=1)) for k in CANDIDATES}
    sd_max = max(sd.values())
    n_eval = int(ev.sum())
    mde = float(2.4865 * sd_max / np.sqrt(n_eval)) if n_eval else float("inf")
    res["power"] = {"sd_diff_power_segment": sd, "sd_max": sd_max, "n_eval": n_eval,
                    "mde": mde, "gate": MDE_GATE, "passes": bool(mde <= MDE_GATE),
                    "n_needed_for_gate": n_needed(MDE_GATE, sd_max)}
    log(t0, f"potencia: sd max {sd_max:.4f} en {int(pw.sum())} días -> MDE {mde:.4f} "
            f"(puerta {MDE_GATE})")
    res["persistence"] = {k: daily.persistence(st[k][ev]) for k in NAMES[1:]}
    res["qlike"] = {k: {"eval": float(loss[k][ev].mean()),
                        "power_segment": float(loss[k][pw].mean()),
                        "mean_ratio": float(np.mean(rv[ev] / h[k][ev]))} for k in NAMES}
    # Escala, fuera de la familia y fuera del MCS: el Log-HAR-RV que T162 sí adoptaría.
    har = vm.m1_log_har(np.where(np.isfinite(rv), rv, np.nan))
    hm = ev & np.isfinite(har) & (har > 0)
    res["scale_reference"] = {"name": "Log-HAR-RV (T162 M1)", "in_family": False,
                              "qlike_eval": float(ve.qlike(rv[hm], har[hm]).mean()),
                              "days": int(hm.sum())}

    if not res["power"]["passes"]:
        res["verdict"] = {"decision": "sin potencia", "adopt": None}
        log(t0, "la puerta de potencia NO se pasa: no se calcula el MCS ni ninguna p")
    else:
        losses = np.column_stack([loss[k][ev] for k in NAMES])
        res["block"] = block_length(losses)
        res["mcs"], res["mcs_aliases"] = mcs_with_aliases(list(NAMES), losses, 0.10, REPS, SEED)
        log(t0, f"MCS: {res['mcs']}; alias: {res['mcs_aliases']}")
        praw, vs = {}, {}
        for k in CANDIDATES:
            vs[k] = {}
            for base in ("M0", "U0"):
                d = loss[k][ev] - loss[base][ev]
                lo, hi, p = mean_diff_test(d, REPS, SEED)
                vs[k][base] = {"mean": float(d.mean()), "ci95": [lo, hi], "p_raw": p}
            praw[k] = vs[k]["M0"]["p_raw"]
        for k, p in holm(praw).items():
            vs[k]["M0"]["p_holm"] = p
        res["vs"] = vs
        res["verdict"] = verdict(res)
        log(t0, f"veredicto: {res['verdict']['decision']}")

    res["states"] = {"days": [int(x) for x in b["days"]],
                     "eval_mask": [bool(x) for x in ev],
                     "by_model": {k: [int(x) for x in v] for k, v in st.items()}}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float) + "\n",
                   encoding="utf-8", newline="\n")
    log(t0, f"datos en {out}")
    return 0


def verdict(res: dict) -> dict:
    """Aplica la regla de adopción pre-registrada, sin margen de interpretación."""
    mcs, vs = res["mcs"], res["vs"]
    m0_out = mcs.get("M0", 1.0) < 0.10
    rows = {}
    for k in CANDIDATES:
        c1 = bool(mcs.get(k, 0.0) >= 0.10 and m0_out)
        v0, vu = vs[k]["M0"], vs[k]["U0"]
        c2 = bool(v0["ci95"][1] < 0 and v0.get("p_holm", 1.0) < 0.05)
        c3 = bool(vu["ci95"][1] < 0)
        rows[k] = {"c1_mcs_con_m0_fuera": c1, "c2_mejora_vs_m0": c2, "c3_mejora_vs_u0": c3,
                   "pasa": bool(c1 and c2 and c3)}
    passed = [k for k, v in rows.items() if v["pasa"]]
    best = min(passed, key=lambda k: res["qlike"][k]["eval"]) if passed else None
    if not passed:
        text = ("NINGUNO PASA: ningún etiquetador de régimen condiciona la varianza del día "
                "siguiente mejor que el BOCPD que ya está en producción bajo la regla "
                "pre-registrada. La línea se cierra: `regime` sigue con BOCPD y no se construye "
                "ningún modelo de régimen más.")
    else:
        text = (f"PASA {', '.join(passed)}; se propone {best} por menor QLIKE. **No se adopta "
                "aquí**: la adopción sería otra entrega posterior al cierre de T31 (2026-11-27) "
                "y añadiría el etiquetador como métrica del agente, sin cambiar su voto.")
    return {"decision": "ninguno pasa" if not passed else f"pasa {', '.join(passed)}",
            "m0_out_of_mcs": m0_out, "by_candidate": rows, "proposed": best, "adopt": None,
            "text": text}


if __name__ == "__main__":
    raise SystemExit(main())
