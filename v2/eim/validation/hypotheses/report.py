"""Informes de T139 en markdown: cobertura, banco y lectura limpia. Puro.

Toda cifra sale de los datos de la corrida, con su muestra, y el modo se dice arriba. El informe
dice qué condición falla en cada clave: «ninguna validada» es un resultado válido.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import NormalDist

CSV_FIELDS = ("reading", "id", "sid", "verdict", "state", "n", "mean_r", "ci_lo", "ci_hi", "p_raw",
              "p_holm", "max_dd", "windows", "windows_pos", "n_live", "gross", "cost", "n_long",
              "n_short", "gross_long", "gross_short", "balanced", "stressed", "bank_gross",
              "bank_n", "V1", "V2", "V3", "V4", "V5", "V6", "reason")
GATE = ("V1", "V2", "V3", "V4", "V5", "V6")
ALPHA = 0.05
Z_IC = 1.96


def _n(x: float | None, k: int = 3, sign: bool = True) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    return f"{x:+.{k}f}" if sign else f"{x:.{k}f}"


def _ok(x: bool | None) -> str:
    return "·" if x is None else "✓" if x else "✗"


def z_holm(family: int) -> float:
    """El z que Holm exige a la mejor clave de una familia: p < α / familia, una cola."""
    return NormalDist().inv_cdf(1 - ALPHA / family)


def gross_needed(n: int, cost: float | None, family: int, sigma: float = 1.0) -> float | None:
    """El bruto mínimo de la ficha (§4): V3 con Holm y V2 sobre el costo. Solo informa."""
    if n <= 0 or cost is None:
        return None
    se = sigma / math.sqrt(n)
    return max(z_holm(family) * se, cost + Z_IC * se)


def _head(res: dict, title: str) -> list[str]:
    m = res["meta"]
    return [f"# {title}", "",
            f"Modo: **SIMULADO** · {m['symbol']} · datos hasta {m['asof']} · pre-registro "
            f"`{m['prereg']}` (SHA-256 `{m['prereg_sha256'][:16]}…`, commit "
            f"`{m['prereg_commit']}`, anterior a la descarga y a todo cálculo) · criterios "
            f"`{m['criteria']}` sin cambios · "
            f"calculado con `{m['commit']}` · familia de Holm de {m['family']}, "
            f"{m['null_reps']} réplicas.", ""]


def _gate_table(rows: Sequence[dict]) -> list[str]:
    out = ["| Clave | Veredicto | n | R medio | IC95 % | p bruto | p Holm | DD | Ventanas + | "
           "V1 | V2 | V3 | V4 | V5 | V6 |",
           "|---|---|--:|--:|---|--:|--:|--:|--:|---|---|---|---|---|---|"]
    for r in rows:
        ci = f"[{_n(r['ci_lo'], 2)}, {_n(r['ci_hi'], 2)}]"
        dd = "—" if not r["n"] else f"{r['max_dd']:.0%}"
        out.append(f"| `{r['id']}` | {r['verdict']} | {r['n']} | {_n(r['mean_r'])} | {ci} | "
                   f"{_n(r['p_raw'], 4, False)} | {_n(r['p_holm'], 4, False)} | {dd} | "
                   f"{r['windows_pos']}/{r['windows']} | "
                   + " | ".join(_ok(r.get(k)) for k in GATE) + " |")
    return out


def _side_table(rows: Sequence[dict], family: int) -> list[str]:
    out = ["| Clave | n | Bruto | Costo | Mínimo necesario | Largos: n, bruto | Cortos: n, bruto | "
           "Equilibrado | Neto costos × 1,5 |", "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for r in rows:
        out.append(f"| `{r['sid']}` | {r['n']} | {_n(r['gross'])} | {_n(r['cost'], 3, False)} | "
                   f"{_n(gross_needed(r['n'], r['cost'], family), 3, False)} | "
                   f"{r['n_long']}, {_n(r['gross_long'])} | "
                   f"{r['n_short']}, {_n(r['gross_short'])} | "
                   f"{_n(r['balanced'])} | {_n(r['stressed'])} |")
    return out


def _control(control: dict) -> list[str]:
    out = ["| Marco | n | Bruto real | Nulo: media | p95 | p | ¿Pasa? |",
           "|---|--:|--:|--:|--:|--:|---|"]
    for tf, c in control.items():
        out.append(f"| {tf} | {c['n']} | {_n(c.get('gross'))} | "
                   f"{_n(c.get('null_mean'))} | "
                   f"{_n(c.get('null_p95'))} | {_n(c.get('p'), 3, False)} | {_ok(c.get('ok'))} |")
    return out


def render_coverage(res: dict) -> str:
    out = _head(res, "T139 — Cobertura de la historia y muestra, sin ningún R")
    cov = res["coverage"]
    out += ["## 1. Cobertura del tramo limpio", "",
            f"Tramo {cov['from']} → {cov['to']}. Mínimo: {cov['min']:.0%}.", "",
            "| Serie | Filas | Esperadas | Cobertura | ¿Cumple? |", "|---|--:|--:|--:|---|"]
    for name, c in cov["series"].items():
        out.append(f"| {name} | {c['rows']} | {c['expected']} | {c['coverage']:.2%} | "
                   f"{_ok(c['ok'])} |")
    for tf, c in cov["taker"].items():
        out.append(f"| `taker_buy_v` {tf} | {c['with_data']} | {c['rows']} | {c['coverage']:.2%} | "
                   f"{_ok(c['ok'])} |")
    out += ["", f"Primera vela de 1 min: {cov['first_minute']}.", "",
            f"**Veredicto de P0:** {cov['verdict']}", "",
            "## 2. Muestra por clave, sin ningún R", "",
            "| Clave | Ideas | Cerradas antes de 2023 | Largos | Cortos | Banco | En vivo |",
            "|---|--:|--:|--:|--:|--:|--:|"]
    for sid, c in res["sample"].items():
        out.append(f"| `{sid}` | {c['ideas']} | {c.get('antes de 2023', 0)} | "
                   f"{c.get('antes de 2023 largos', 0)} | {c.get('antes de 2023 cortos', 0)} | "
                   f"{c.get('banco', 0)} | {c.get('en vivo', 0)} |")
    return "\n".join(out) + "\n"


def render_bank(res: dict) -> str:
    reg = res["regression"]
    out = _head(res, "T139 — Comprobación del camino: regresión, control y banco")
    out += ["Este tramo ya está contaminado y **no aprueba nada**. Las reglas están congeladas, "
            "así que verlo solo autoriza a corregir defectos, declarándolos.", "",
            "## 1. Regresión contra T137", "",
            f"`control_aleatorio@1h`, publicado: n = {reg['want']['n']}, bruto "
            f"{reg['want']['gross_r']:+.6f}.", "",
            f"- Con los contextos guardados: n = {reg['stored']['n']}, bruto "
            f"{_n(reg['stored']['gross_r'], 6)}. {_ok(reg['stored']['ok'])}",
            f"- Con contextos mínimos: n = {reg['minimal']['n']}, bruto "
            f"{_n(reg['minimal']['gross_r'], 6)}. {_ok(reg['minimal']['ok'])}",
            f"- ATR propio frente al de los {reg['contexts']} contextos: diferencia relativa "
            f"mediana {_n(reg['atr_rel_diff_median'], 7, False)}, máxima "
            f"{_n(reg['atr_rel_diff_max'], 7, False)}; "
            f"{reg['missing_bars']} instantes sin vela.", "",
            "## 2. Control en el banco", "", *_control(res["control"]), "",
            "## 3. Las claves en el banco", "", *_gate_table(res["rows"]), "",
            *_side_table(res["rows"], res["meta"]["family"]), ""]
    return "\n".join(out)


def _conditions(rows: Sequence[dict]) -> list[str]:
    names = ("1_puerta", "2_bruto_equilibrado", "3_costos_x1_5", "4_sustitutas", "5_banco")
    out = ["| Clave | Estado | Puerta | Equilibrado > costo | Costos × 1,5 | Sobre sustitutas | "
           "Banco ≥ 0 | p95 sustitutas | Bruto en el banco |",
           "|---|---|---|---|---|---|---|--:|--:|"]
    for r in rows:
        c = r["conditions"]
        marks = " | ".join(_ok(c[k]) for k in names)
        out.append(f"| `{r['sid']}` | {r['state']} | {marks} | {_n(r['null']['p95'])} | "
                   f"{_n(r['bank_gross'])} ({r['bank_n']}) |")
    return out


def render_clean(res: dict) -> str:
    rec = res["recommendation"]
    out = _head(res, "T139 — Hipótesis de entrada: la lectura limpia")
    if res["meta"].get("repeat_reason"):
        reason = res["meta"]["repeat_reason"]
        out += [f"**Esta lectura se repitió.** Motivo declarado: {reason}", ""]
    out += ["## 1. Recomendación", "", f"**{rec['code']}. {rec['text']}**", ""]
    if rec["follow"]:
        out += ["Siguen: " + ", ".join(f"`{x}`" for x in rec["follow"]) + ".", ""]
    if rec["watch"]:
        out += ["En observación: " + ", ".join(f"`{x}`" for x in rec["watch"]) + ".", ""]
    out += ["Parar no prueba que no exista ventaja: prueba que no la hay por encima de lo "
            "detectable con estos datos. Ninguna clave puede salir VALIDADA aún: V5 exige 20 "
            "operaciones en vivo, y se fijó antes de calcular.", "",
            "## 2. La puerta de T49, tal cual", "",
            "Cuenta lo anterior a 2023 y lo posterior al alta.", "",
            *_gate_table(res["rows"]), "",
            "## 3. El bruto, frente a lo que haría falta", "",
            "«Mínimo necesario» es la cuenta de la ficha con σ = 1 R: `max(z_Holm·σ/√n, costo + "
            "1,96·σ/√n)`. El equilibrado es la media simple de largos y cortos: cancela la deriva.",
            "", *_side_table(res["rows"], res["meta"]["family"]), "",
            "## 4. La regla de lectura, condición a condición", "", *_conditions(res["rows"]), "",
            "## 5. Control con entradas al azar", "",
            "Antes de 2023, frente a sus series sustitutas: no puede destacar.", "",
            *_control(res["control"]), "",
            "## 6. Línea base: ¿era más fácil ese periodo?", "",
            "El catálogo vigente que solo pide velas, antes de 2023. Solo lectura: no escribe en "
            "el registro.", "", "| Familia | Marco | Estrategias | n | Bruto |",
            "|---|---|--:|--:|--:|"]
    for fam, by_tf in res["baseline"].items():
        for tf, b in by_tf.items():
            out.append(f"| {fam} | {tf} | {b['strategies']} | {b['n']} | {_n(b['gross_r'])} |")
    return "\n".join(out) + "\n"
