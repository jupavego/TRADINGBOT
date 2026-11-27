"""Sonda de T100 sobre datos reales: curva del Tesoro, carry y contraste con el BCE.

Uso (desde `v2/`):  python scripts/fixed_income_probe.py [--summary archivo.txt]

1. Descarga la curva par diaria del Tesoro de EE. UU. del año en curso y del anterior (sin
   clave; fuente aprobada en la ◆ de T88) y corre los dos agentes de prueba
   (`eim/fixed_income/proto.py`): estado de la curva del último día y carry/roll-down a 3 meses
   en los plazos de 2, 5, 10 y 30 años.
2. Contrasta la fórmula de Svensson de `eim/fixed_income/curve.py` con el BCE: descarga los
   parámetros publicados de su curva AAA del euro del último día y los tipos cero que el propio
   BCE publica, y mide la diferencia (es la validación «contra referencia publicada» en vivo).
3. Escribe `reports/fixed_income_probe.{md,json}`. Sin red: lo que falte sale «no disponible»
   (nunca se estima) y el programa termina con código 0; solo un error de programación falla.

Modo ANÁLISIS: no escribe en ningún almacén, no registra agentes y no toca nada vivo.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from eim.data.providers.treasury import TreasuryPar  # noqa: E402
from eim.fixed_income.curve import svensson  # noqa: E402
from eim.fixed_income.proto import carry_state, curve_state  # noqa: E402

ECB_URL = ("https://data-api.ecb.europa.eu/service/data/YC/"
           "B.U2.EUR.4F.G_N_A.SV_C_YM.{keys}")
ECB_PARAMS = ("BETA0", "BETA1", "BETA2", "BETA3", "TAU1", "TAU2")
ECB_SPOTS = {"SR_1Y": 1.0, "SR_2Y": 2.0, "SR_5Y": 5.0, "SR_10Y": 10.0, "SR_30Y": 30.0}
ECB_TOL_BP = 0.5
CARRY_TENORS = (2.0, 5.0, 10.0, 30.0)


def treasury(client: httpx.Client, year: int) -> tuple[list, str | None]:
    curves, errors = [], []
    for y in (year - 1, year):
        try:
            curves += TreasuryPar(client).year(y)
        except (httpx.HTTPError, ValueError) as exc:
            errors.append(f"{y}: {exc}")
    by_day = {c.date: c for c in curves}          # un día no se cuenta dos veces
    return [by_day[d] for d in sorted(by_day)], ("; ".join(errors) or None)


def parse_ecb(text: str) -> dict[str, tuple[str, float]]:
    """{nombre: (fecha, valor)} desde el CSV SDMX del BCE (columnas KEY, TIME_PERIOD, OBS_VALUE)."""
    out: dict[str, tuple[str, float]] = {}
    for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        key = (row.get("KEY") or "").rsplit(".", 1)[-1] or row.get("DATA_TYPE_FM", "")
        try:
            out[key] = (row["TIME_PERIOD"], float(row["OBS_VALUE"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def ecb_check(values: dict[str, tuple[str, float]]) -> dict:
    """Svensson con los parámetros del BCE frente a los tipos cero que publica el BCE."""
    if not all(k in values for k in ECB_PARAMS):
        return {"status": "no disponible", "reason": "faltan parámetros en la respuesta"}
    p = [values[k][1] for k in ECB_PARAMS]
    rows = []
    for name, m in ECB_SPOTS.items():
        if name in values:
            mine = svensson(m, *p)
            rows.append({"plazo": m, "bce_pct": values[name][1], "eim_pct": round(mine, 6),
                         "dif_pb": round((mine - values[name][1]) * 100, 4)})
    if not rows:
        return {"status": "no disponible", "reason": "el BCE no devolvió tipos cero"}
    worst = max(abs(r["dif_pb"]) for r in rows)
    return {"status": "coincide" if worst <= ECB_TOL_BP else "NO coincide",
            "date": values["BETA0"][0], "max_dif_pb": worst, "tol_pb": ECB_TOL_BP,
            "params": dict(zip(ECB_PARAMS, p, strict=True)), "rows": rows}


def ecb(client: httpx.Client) -> dict:
    keys = "+".join((*ECB_PARAMS, *ECB_SPOTS))
    try:
        r = client.get(ECB_URL.format(keys=keys),
                       params={"lastNObservations": "1", "format": "csvdata"})
        r.raise_for_status()
    except httpx.HTTPError as exc:
        return {"status": "no disponible", "reason": f"red: {exc}"}
    return ecb_check(parse_ecb(r.text))


def run(client: httpx.Client, year: int) -> dict:
    curves, err = treasury(client, year)
    out: dict = {"computed_at": datetime.now(UTC).isoformat(timespec="seconds"),
                 "source": "us-treasury", "n_days": len(curves), "treasury_error": err,
                 "attribution_ecb": "Fuente: Banco Central Europeo"}
    if curves:
        last = curves[-1]
        out["curve"] = asdict(curve_state(last.tenors, last.yields_pct, last.date, last.source))
        hist = [(c.date, c.tenors, c.yields_pct) for c in curves]
        out["carry"] = {f"{t:g}a": asdict(carry_state(hist, last.source, maturity=t))
                        for t in CARRY_TENORS}
    out["ecb"] = ecb(client)
    return out


def render(res: dict) -> str:
    ln = ["# T100 · sonda sobre datos reales (renta fija)", "",
          f"Calculado {res['computed_at']} · modo ANÁLISIS · fuente de la curva: Tesoro de "
          "EE. UU. (curva par diaria, reutilización declarada sin restricción).", ""]
    if "curve" not in res:
        ln += [f"**Curva: no disponible** ({res.get('treasury_error') or 'sin datos'}).", ""]
    else:
        c = res["curve"]
        ln += [f"## Curva del {c['as_of']} ({res['n_days']} días descargados)", "",
               *[f"- {e}" for e in c["evidence"]], *[f"- ⚠ {w}" for w in c["warnings"]], "",
               "## Carry + roll-down a 3 meses con la curva quieta", "",
               "| Plazo | Carry | Roll-down | Financiación | Exceso | Vol. rend. | "
               "Exceso/riesgo | Punto muerto |", "|---|---|---|---|---|---|---|---|"]
        for k, r in res["carry"].items():
            m = r["metrics"]
            if r["status"] == "no_data":
                ln.append(f"| {k} | no disponible: {'; '.join(r['warnings'])} ||||||| ")
                continue
            ln.append(f"| {k} | {m['carry_pb']:+.0f} pb | {m['rolldown_pb']:+.0f} pb | "
                      f"{m['financiacion_pb']:.0f} pb | {m['exceso_pb']:+.0f} pb | "
                      f"{m['vol_rend_horizonte_pb']:.0f} pb | {m['sharpe_ex_ante']:+.2f} | "
                      f"{m['punto_muerto_pb']:.0f} pb |")
        ln += ["", "Financiación aproximada por la letra de 3 meses (no repo/SOFR). Prototipo "
               "sin validar: no es una señal ni vota.", ""]
    e = res["ecb"]
    ln += ["## Contraste de la fórmula de Svensson con el BCE", ""]
    if e["status"] == "no disponible":
        ln.append(f"No disponible: {e['reason']}.")
    else:
        ln += [f"**{e['status']}** (día {e['date']}; diferencia máxima {e['max_dif_pb']} pb, "
               f"tolerancia {e['tol_pb']} pb). Fuente: Banco Central Europeo.", "",
               "| Plazo | BCE % | EIM % | Dif. pb |", "|---|---|---|---|",
               *[f"| {r['plazo']:g} | {r['bce_pct']} | {r['eim_pct']} | {r['dif_pb']} |"
                 for r in e["rows"]]]
    return "\n".join(ln) + "\n"


def summary(res: dict) -> str:
    parts = []
    if "curve" in res:
        m = res["curve"]["metrics"]
        parts.append(f"curva del {res['curve']['as_of']}: 10a {m['par_10a_pct']} %, 3m10a "
                     f"{m['pendiente_3m10a_pb']:+.0f} pb, Svensson {m['rmse_svensson_pb']} pb")
        c10 = res["carry"].get("10a", {}).get("metrics", {})
        if c10.get("exceso_pb") is not None:
            parts.append(f"carry+roll 10a a 3 meses {c10['exceso_pb']:+.0f} pb netos "
                         f"(exceso/riesgo {c10['sharpe_ex_ante']:+.2f})")
    else:
        parts.append("curva del Tesoro no disponible")
    e = res["ecb"]
    parts.append(f"BCE: {e['status']}" + (f" ({e['max_dif_pb']} pb)" if "max_dif_pb" in e
                                          else f" ({e.get('reason', '')})"))
    return "sonda T100: " + "; ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--summary", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "reports")
    a = ap.parse_args()
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        res = run(client, datetime.now(UTC).year)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "fixed_income_probe.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (a.out / "fixed_income_probe.md").write_text(render(res), encoding="utf-8")
    line = summary(res)
    print(line)
    if a.summary:
        a.summary.write_text(line + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
