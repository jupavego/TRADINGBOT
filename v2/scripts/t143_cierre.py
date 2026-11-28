"""T143, cierre: la corrida aparte `t143` frente a T31, con la contabilidad oficial de T144.

    python scripts/t143_cierre.py --t31 <ledger.csv> --variant <ledger_t143.csv>
                                  [--out reports/t143_cierre]

Los dos CSV son los libros fijos que exporta la API viva (solo lectura):
`GET /v2/paper/ledger.csv` (mesa principal, T31) y `GET /v2/paper/variant/t143/ledger.csv`.
El libro es de solo adición, así que repetirlo más tarde con la misma ventana da las mismas
cifras (lo comprueban las huellas `counted_digest`). Escribe `.json` y `.md`. Método en
`eim/paper/run_compare.py`.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from eim.paper import run_compare
from eim.paper.t143_config import EXEC_T143

T0 = 1794284220000          # 2026-11-10 04:17 UTC: despliegue de la corrida aparte (PR #243)
T1 = 1795824000000          # 2026-11-28 00:00 UTC: cierre de T31
BENCH_COST_DROP = 0.0432    # `reports/t143_maker.md`: lo que el banco esperaba ahorrar en R
CRITERION = 0.04            # el criterio pre-registrado del entregable 1


def _t(ms: int | None) -> str:
    if ms is None:
        return "—"
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d %H:%M UTC")


def _n(x, fmt: str = "{:+.3f}") -> str:
    return "—" if x is None else fmt.format(x)


def _ci(c) -> str:
    return "—" if not c else f"[{c[0]:+.3f}, {c[1]:+.3f}]"


def _pm(s: dict) -> str:
    return f"{_n(s['mean'])} ± {_n(s['se'], '{:.3f}')}" if s["n"] > 1 else _n(s["mean"])


def _side_rows(res: dict) -> list[str]:
    a, b = res["a"], res["b"]
    oa, ob = a["official"], b["official"]
    def row(lab, x, y, fmt="{:+.3f}"):
        d = None if x is None or y is None else y - x
        return f"| {lab} | {_n(x, fmt)} | {_n(y, fmt)} | {_n(d, fmt)} |"
    dd = lambda o: o["dd"]["usdt"]  # noqa: E731
    return ["| Cifra | T31 (mesa principal) | t143 (corrida aparte) | t143 − T31 |",
            "|---|--:|--:|--:|",
            row("Operaciones que cuentan", oa["n"], ob["n"], "{:d}"),
            row("Acierto", oa["win_rate"], ob["win_rate"], "{:.1%}"),
            row("E[R] neto por operación", oa["mean_r"], ob["mean_r"]),
            f"| IC95 % de E[R] neto | {_ci(oa['ci95'])} | {_ci(ob['ci95'])} | |",
            row("R total", oa["total_r"], ob["total_r"], "{:+.2f}"),
            row("Costo medio en R", a["all"]["cost_r"], b["all"]["cost_r"]),
            row("E[R] bruto (neto + costo)", a["all"]["gross_r"], b["all"]["gross_r"]),
            row("Salidas por SL inicial", a["all"]["sl_rate"], b["all"]["sl_rate"], "{:.1%}"),
            row("PnL (USDT)", oa["pnl_usdt"], ob["pnl_usdt"], "{:+.1f}"),
            row("Comisiones (USDT)", oa["fees"], ob["fees"], "{:.1f}"),
            row("Deslizamiento (USDT)", oa["slip"], ob["slip"], "{:.1f}"),
            row("Funding (USDT)", oa["funding"], ob["funding"], "{:+.1f}"),
            row("Máximo descenso (USDT)", dd(oa), dd(ob), "{:.1f}"),
            f"| Huella de lo contado | `{oa['counted_digest']}` | `{ob['counted_digest']}` | |"]


def _group(res: dict, key: str, title: str) -> list[str]:
    a, b = res["a"][key], res["b"][key]
    out = [f"| {title} | T31 n | T31 neto ± EE | T31 costo | T31 PnL | t143 n | t143 neto ± EE "
           "| t143 costo | t143 PnL |", "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        def cells(z):
            if not z:
                return "0 | — | — | —"
            return (f"{z['n']} | {_n(z['net_r'])} ± {_n(z['net_se'], '{:.3f}')} | "
                    f"{_n(z['cost_r'], '{:.3f}')} | {_n(z['pnl_usdt'], '{:+.1f}')}")
        out.append(f"| {k} | {cells(x)} | {cells(y)} |")
    return out


def _paired_rows(p: dict) -> list[str]:
    out = ["| Marco | Pares | Δ neto ± EE | Δ costo ± EE | Δ bruto ± EE | Mismo motivo de salida "
           "| Tipo de entrada (T31→t143) |", "|---|--:|--:|--:|--:|--:|---|"]
    for k, d in [*p["by_timeframe"].items(), ("todos", p["all"])]:
        if d["n"]:
            kinds = ", ".join(f"{a} {n}" for a, n in d["kinds"].items())
            out.append(f"| {k} | {d['n']} | {_pm(d['d_net_r'])} | {_pm(d['d_cost_r'])} | "
                       f"{_pm(d['d_gross_r'])} | {d['same_reason']} | {kinds} |")
    return out


def _only_rows(p: dict) -> list[str]:
    out = ["| Solo en | Marco | n | E[R] neto ± EE | Salidas por SL | PnL (USDT) |",
           "|---|---|--:|--:|--:|--:|"]
    for lab, key in (("T31", "only_a"), ("t143", "only_b")):
        for tf, z in [*p[f"{key}_by_tf"].items(), ("todos", p[key])]:
            out.append(f"| {lab} | {tf} | {z['n']} | {_n(z['net_r'])} ± "
                       f"{_n(z['net_se'], '{:.3f}')} | {_n(z['sl_rate'], '{:.0%}')} | "
                       f"{_n(z['pnl_usdt'], '{:+.1f}')} |")
    return out


def _conv_rows(c: dict) -> list[str]:
    se = c["same_exit"]
    out = [f"De los pares, **{c['n']} entraron a mercado en T31 y en límite en t143** (la "
           "conversión maker de 1 h y 4 h). Lo que cambió en ellos:", "",
           "| Concepto | T31 | t143 |", "|---|--:|--:|",
           f"| Comisiones (pb del nocional) | {_n(c['fees_bps'][0], '{:.2f}')} | "
           f"{_n(c['fees_bps'][1], '{:.2f}')} |",
           f"| Deslizamiento (pb del nocional) | {_n(c['slip_bps'][0], '{:.2f}')} | "
           f"{_n(c['slip_bps'][1], '{:.2f}')} |",
           f"| Precio de entrada mejor en t143 (pb) | | {_n(c['better_fill_bps'], '{:+.2f}')} |",
           f"| Retraso del llenado en t143 (min) | | {_n(c['fill_delay_min'], '{:+.1f}')} |", "",
           f"- **Misma salida ({se['n']} pares):** Δ neto {_pm(se['d_net_r'])} R por operación.",
           f"- **Otra salida ({len(c['other_exit'])} pares):**"]
    for o in c["other_exit"]:
        out.append(f"  - {o['profile']} {o['timeframe']}: T31 «{o['reason'][0]}» {o['r'][0]:+.2f}"
                   f" R, t143 «{o['reason'][1]}» {o['r'][1]:+.2f} R; cantidad {o['qty'][0]:g} → "
                   f"{o['qty'][1]:g}; cierre {_t(o['exit_t'][0])} → {_t(o['exit_t'][1])}")
    return out


def _reading(res: dict) -> list[str]:
    oa, ob = res["a"]["official"], res["b"]["official"]
    p, g = res["paired"], res["gate"]
    dn, dc = p["all"]["d_net_r"], p["all"]["d_cost_r"]
    zero = dn["ci95"] and dn["ci95"][0] <= 0 <= dn["ci95"][1]
    over = [c for c in g if c["over"]]
    tfc = {tf: p["by_timeframe"][tf]["d_cost_r"]["mean"] for tf in ("1h", "4h")}
    c = p["converted"]
    lost = sum(o["r"][1] - o["r"][0] for o in c["other_exit"])
    return [
        f"- **Cifra oficial: t143 {ob['mean_r']:+.3f} R por operación frente a {oa['mean_r']:+.3f} "
        f"R de T31** ({ob['n']} y {oa['n']} operaciones; PnL {ob['pnl_usdt']:+.1f} frente a "
        f"{oa['pnl_usdt']:+.1f} USDT). La corrida aparte no mejora el resultado oficial.",
        f"- **Sobre las mismas operaciones ({p['all']['n']} pares), el costo baja "
        f"{-dc['mean']:.4f} R** (1 h {_n(tfc['1h'], '{:+.4f}')}, 4 h {_n(tfc['4h'], '{:+.4f}')}), "
        f"lejos de los {BENCH_COST_DROP} R que esperaba el banco y del criterio de {CRITERION} R. "
        f"El neto emparejado cambia {_pm(dn)} R"
        + (" y su IC95 % incluye el 0: en las operaciones comunes la ejecución no se distingue."
           if zero else f" (IC95 % {_ci(dn['ci95'])})."),
        f"- **La entrada maker hace lo que debía, pero ahorra menos de lo previsto.** En las "
        f"{c['n']} convertidas la comisión baja de {_n(c['fees_bps'][0], '{:.1f}')} a "
        f"{_n(c['fees_bps'][1], '{:.1f}')} pb y el deslizamiento casi no cambia "
        f"({_n(c['slip_bps'][0], '{:.1f}')} → {_n(c['slip_bps'][1], '{:.1f}')} pb): casi todo el "
        "deslizamiento es de la salida, no de la entrada. Con la misma salida ganan "
        f"{_pm(c['same_exit']['d_net_r'])} R por operación. **{len(c['other_exit'])} pares "
        f"cambiaron de salida y restan {lost:+.2f} R en total**: entraron al mismo precio y en el "
        "mismo minuto, así que no es la entrada lo que los separa (§5).",
        f"- **La diferencia está en la composición:** t143 tomó {p['only_b']['n']} operaciones "
        f"que T31 no tomó, con {_n(p['only_b']['net_r'])} R de media y "
        f"{_n(p['only_b']['sl_rate'], '{:.0%}')} de salidas por SL, y dejó de tomar "
        f"{p['only_a']['n']} que T31 sí tomó ({_n(p['only_a']['net_r'])} R).",
        f"- **Puerta de marcos (umbral {EXEC_T143.tf_max_cost_r} R):** "
        + (f"{len(over)} {'celda operó' if len(over) == 1 else 'celdas operaron'} con un "
           "costo vivido igual o mayor al umbral: "
           + ", ".join(f"{c['cell']} {c['cost_r']:.3f} R (n = {c['n']})" for c in over)
           + ". La puerta decide con la sombra calibrada, no con lo vivido."
           if over else "ninguna celda operó con un costo vivido por encima del umbral."),
    ]


def render(res: dict) -> str:
    w = res["window"]
    out = ["# T143 — Cierre: la corrida aparte `t143` frente a T31", "",
           f"**Modo: SIMULADO.** Generado {res['generado']} desde los libros fijos que exporta la "
           "API viva (`GET /v2/paper/ledger.csv` y `GET /v2/paper/variant/t143/ledger.csv`, solo "
           f"lectura). Ventana: operaciones abiertas entre {_t(w['t0'])} (despliegue de la "
           f"corrida aparte, PR #243) y {_t(w['t1'])} (cierre de T31), y cerradas antes de esa "
           f"hora. Universo oficial de T144 (`{w['universe']}`): perfiles, vivas, con peso y sin "
           "`retro`. Método en `eim/paper/run_compare.py`.", "",
           "## 1. La cifra oficial", "", *_side_rows(res), "",
           "## 2. Por marco", "", *_group(res, "by_timeframe", "Marco"), "",
           "## 3. Por perfil", "", *_group(res, "by_profile", "Perfil"), "",
           "## 4. Por tipo de entrada", "", *_group(res, "by_kind", "Entrada"), "",
           "## 5. La misma operación en los dos libros", "",
           "Clave: el mismo perfil y la misma idea (`idea_id`). Δ = t143 − T31 por operación.", "",
           *_paired_rows(res["paired"]), "", *_conv_rows(res["paired"]["converted"]), "",
           "## 6. Lo que tomó un libro y el otro no", "", *_only_rows(res["paired"]), "",
           "## 7. Lectura", "", *_reading(res), "",
           "## 8. Lo que esta comparación no cubre", "",
           "- **El R no ve el riesgo con costo de forma directa.** `r` es PnL entre el riesgo de "
           "precio al SL en los dos libros, y `risk_includes_costs` solo reduce la cantidad "
           "(×0,85). Pero la cantidad sí puede cambiar la salida cuando la protección se mide en "
           "USDT (escalones de PPP, BE+ con costo): es uno de los candidatos de los pares que "
           "cambiaron de salida, sin confirmar aquí.",
           "- **Los dos libros divergen por su propia historia**: pesos de realimentación, "
           "posiciones ocupadas y límites sin llenar hacen que cada uno tome operaciones "
           "distintas. Por eso la §5 (lo común) y la §6 (lo distinto) van aparte.",
           "- **La corrida aparte cambió dos veces durante la ventana**: la puerta pasó a medir "
           "solo lo tomable el 2026-11-10 (PR #246) y a decidir por perfil y marco el "
           "2026-11-17 (T179).",
           "- **Muestra corta**: unas tres semanas y unos cientos de operaciones; los EE están "
           "en cada tabla.", ""]
    return "\n".join(out)


def _load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t31", required=True)
    ap.add_argument("--variant", required=True)
    ap.add_argument("--t0", type=int, default=T0)
    ap.add_argument("--t1", type=int, default=T1)
    ap.add_argument("--out", default="reports/t143_cierre")
    a = ap.parse_args()
    t31, var = _load(a.t31), _load(a.variant)
    res = run_compare.compare(t31, var, a.t0, a.t1)
    res["gate"] = run_compare.gate_check(run_compare.in_window(var, a.t0, a.t1),
                                         EXEC_T143.tf_max_cost_r)
    res["generado"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    out.with_suffix(".md").write_text(render(res), encoding="utf-8")
    o = res["b"]["official"]
    print(f"t143: n={o['n']} E[R]={o['mean_r']:+.4f} | T31: n={res['a']['official']['n']} "
          f"E[R]={res['a']['official']['mean_r']:+.4f} -> {out.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
