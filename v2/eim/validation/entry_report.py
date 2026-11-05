"""Informe de decisión de T137: filas por versión y markdown. Puro: recibe el resultado calculado.

Se separa del cálculo para poder rehacer el texto sin volver a simular (`--from-json`). Toda cifra
lleva su lectura, porque las tres no significan lo mismo: solo la oficial da veredicto.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from eim.validation.gate import Verdict

MARK = {True: "✓", False: "✗", None: "·"}
TITLE = {"oficial": "Oficial (T49 tal cual, la única que da veredicto)",
         "reserva": "Reserva (datos donde no se eligió nada; descriptiva)",
         "banco": "Banco (donde se eligió la geometría: cota optimista, descriptiva)"}
CSV_FIELDS = ("reading", "id", "variant", "strategy", "timeframe", "verdict", "n", "mean_r",
              "ci_lo", "ci_hi", "p_raw", "p_holm", "max_dd", "windows", "windows_pos", "cost_r",
              "win_rate", "pf", "V1", "V2", "V3", "V4", "V5", "V6", "ideas", "moved", "vetoed",
              "inert", "reason")


def row_of(reading: str, v: Verdict, variant: str, stats: Mapping | None, inert: bool) -> dict:
    """Una fila por versión y lectura, con cada criterio."""
    m, ver = v.measure, v.version
    lo, hi = m.ci
    st = stats or {}
    return {
        "reading": reading, "id": ver.label, "variant": variant, "strategy": ver.strategy,
        "timeframe": ver.timeframe, "verdict": v.verdict, "n": m.n, "mean_r": m.mean_r,
        "ci_lo": lo, "ci_hi": hi, "p_raw": m.p_raw, "p_holm": v.p_holm, "max_dd": m.dd,
        "windows": len(m.windows), "windows_pos": sum(1 for _, _, mu in m.windows if mu > 0),
        "cost_r": m.cost_r, "win_rate": m.extras.get("win_rate"), "pf": m.extras.get("pf"),
        **{c.id: c.ok for c in v.checks}, "ideas": st.get("ideas", 0), "moved": st.get("moved", 0),
        "vetoed": st.get("vetoed", 0), "inert": inert, "reason": v.reason}


def _f(x: float | None, k: int = 3, sign: bool = True) -> str:
    if x is None or x != x:
        return "—"
    return f"{x:+.{k}f}" if sign else f"{x:.{k}f}"


def _pct(x: float | None, k: int = 1) -> str:
    return "—" if x is None or x != x else f"{100 * x:.{k}f} %"


def _head(res: dict) -> list[str]:
    m, o = res["meta"], res["readings"]["oficial"]["summary"]
    counts = o["counts"]
    v = o["validated"]
    verdict = (f"**{len(v)} validada(s):** " + ", ".join(f"`{x}`" for x in v) if v else
               "**Ninguna versión validada.** Es un resultado válido.")
    out = ["# T137 — La entrada: SL inicial más amplio y tope de costo, por la puerta de T49", "",
           f"Modo: **SIMULADO** · {m['symbol']} · datos hasta {m['asof']} · pre-registro "
           f"`{m['prereg']}` (SHA-256 `{m['prereg_sha256'][:16]}…`, commit `{m['prereg_commit']}`, "
           f"anterior a todo cálculo) · criterios `{m['criteria']}` sin cambios · calculado con "
           f"`{m['commit']}` · {m['attempts']} intentos nuevos, familia de Holm de {m['family']}.",
           "", "## 1. Veredicto (lectura oficial)", "", verdict, "",
           "De " + str(sum(counts.values())) + " versiones: " + " · ".join(
               f"{n} {k}" for k, n in sorted(counts.items())) + ".", ""]
    return out + _reasons(res)


def _reasons(res: dict) -> list[str]:
    o = res["readings"]["oficial"]
    out = ["Criterios que más fallan en la lectura oficial:", ""]
    out += [f"- {x['id']} {x['name']}: {x['n']} versiones" for x in o["summary"]["most_failed"]]
    if not o["summary"]["most_failed"]:
        out.append("- ninguno falla: casi todo queda pendiente por falta de muestra.")
    out += ["", f"Llegan al mínimo de V1 (≥ 100 operaciones y ≥ 2 regímenes con ≥ 20): "
            f"**{o['meets_v1']}** de {len(o['rows'])}. Ninguna versión puede salir VALIDADA en "
            "esta corrida: no hay tramo en vivo, así que V5 queda pendiente, y eso se fijó antes "
            "de calcular.", ""]
    return out


def _pooled(res: dict, rid: str) -> list[str]:
    tbl = res["readings"][rid]["pooled"]
    out = ["| Variante | Marco | n | E[R] | Acierto | PF | Costo R | Bruto R |",
           "|---|---|--:|--:|--:|--:|--:|--:|"]
    for vid in ("base", *res["variant_ids"]):
        for tf, x in (tbl.get(vid) or {}).items():
            name = "padre (sin cambios)" if vid == "base" else vid
            out.append(f"| {name} | {tf} | {x['n']} | {_f(x['mean_r'])} | "
                       f"{_pct(x['win_rate'])} | {_f(x['pf'], 3, False)} | "
                       f"{_f(x['cost_r'], 3, False)} | {_f(x['gross_r'])} |")
    return out


def _readings(res: dict) -> list[str]:
    out = ["## 2. Las tres lecturas, agregadas por variante", "",
           "Agregan todas las estrategias: sirven para ver si la geometría cambia algo, no para "
           "validar nada. La versión padre es la vigente, con las mismas ventanas.", ""]
    for rid, title in TITLE.items():
        r = res["readings"][rid]
        s = r["summary"]
        out += [f"### {title}", "", _period(res, rid), "",
                "Veredictos de la puerta: " + (" · ".join(
                    f"{n} {k}" for k, n in sorted(s["counts"].items())) or "ninguno") + ". Falla "
                "más: " + (", ".join(f"{x['id']} ({x['n']})" for x in s["most_failed"][:4])
                           or "nada") + f". Llegan a V1: {r['meets_v1']}.", ""]
        out += [*_pooled(res, rid), ""]
    return out


def _period(res: dict, rid: str) -> str:
    return res["readings"][rid].get("period", "")


def _cap(res: dict) -> list[str]:
    out = ["## 3. Lo que deja fuera el tope de 0,08 R", "",
           "El tope se mide sobre el SL de la versión. «Ideas» son las candidatas desde "
           "2024-01-11; "
           "«operaciones» compara lo que cerró cada versión con su gemela sin tope, en el banco "
           "(1 h y 4 h) y en todo el tramo de 15 m.", "",
           "| Variante | Marco | Ideas | SL movido | Vetadas | Costo ex ante R |",
           "|---|---|--:|--:|--:|--:|"]
    for vid in ("base", *res["variant_ids"]):
        for tf, x in res["variants"][vid]["cost"].items():
            name = "padre" if vid == "base" else vid
            out.append(f"| {name} | {tf} | {x['ideas']} | {_pct(x['moved_frac'])} | "
                       f"{_pct(x['vetoed_frac'])} | {_f(x['cost_ex_ante_r'], 3, False)} |")
    out += ["", "| Con tope | Sin tope | Operaciones con tope | Sin tope | Quedan fuera |",
            "|---|---|--:|--:|--:|"]
    for c in res["cap_left_out"]:
        out.append(f"| {c['with']} | {c['without']} | {c['n_with']} | {c['n_without']} | "
                   f"{_pct(c['left_out'])} |")
    return [*out, ""]


def _control(res: dict) -> list[str]:
    out = ["## 4. Control con entradas al azar", "",
           "Sobre `control_aleatorio@1h`. El cuantil de M8 sale de `consenso_sintesis@1h`, que "
           "tiene sus mismas salidas (`control_aleatorio` no llega a la muestra mínima). Si el "
           "bruto destacara sobre las series sustitutas habría anticipación o un error.", "",
           "| Variante | n real | SL movido (real / sustitutas) | Bruto real | Nulo: media | "
           "p95 | p | ¿La pone a prueba? | ¿Pasa? |",
           "|---|--:|--:|--:|--:|--:|--:|---|---|"]
    for vid, c in res["control"].items():
        name = "padre" if vid == "base" else vid
        out.append(
            f"| {name} | {c['n_real']} | {_pct(c['moved_frac_real'], 0)} / "
            f"{_pct(c['moved_frac_null'], 0)} | {_f(c['observed_gross_r'])} | "
            f"{_f(c['null_mean'])} | {_f(c['null_p95'])} | {_f(c['p_one_sided'], 3, False)} | "
            f"{'sí' if c['tested'] else '**no**'} | {MARK[c['ok']]} |")
    return [*out, ""]


def _tf15(res: dict) -> list[str]:
    t = res["tf15m"]
    out = ["## 5. 15 m", "", t["note"], "",
           "| Variante | Tramo | n | E[R] | Acierto | PF | Costo R | Bruto R |",
           "|---|---|--:|--:|--:|--:|--:|--:|"]
    for vid, spans in t["pooled"].items():
        name = "padre" if vid == "base" else vid
        for span, x in spans.items():
            out.append(f"| {name} | {span} | {x['n']} | {_f(x['mean_r'])} | "
                       f"{_pct(x['win_rate'])} | {_f(x['pf'], 3, False)} | "
                       f"{_f(x['cost_r'], 3, False)} | {_f(x['gross_r'])} |")
    return [*out, ""]


def _regression(res: dict) -> list[str]:
    reg = res.get("regression")
    if not reg:
        return ["## 6. Regresión contra T134 y T136", "", "No se corrió en esta ejecución.", ""]
    out = ["## 6. Regresión contra T134 y T136", "",
           "Con M0 y el mismo código de geometría, sobre los tramos de prueba de T134. Si no "
           "coincidiera, lo medido aquí no sería la geometría que dio la señal.", "",
           "| Caso | n | E[R] | Publicado n | Publicado E[R] | ¿Coincide? |",
           "|---|--:|--:|--:|--:|---|"]
    for k, x in reg.items():
        out.append(f"| `{k}` | {x['n']} | {_f(x['expectancy_r'], 6)} | {x['want_n']} | "
                   f"{_f(x['want_expectancy_r'], 6)} | {MARK[x['ok']]} |")
    return [*out, ""]


def _table(rows: Sequence[dict], limit: int = 40) -> list[str]:
    head = ["| Versión | Variante | Veredicto | n | R medio | IC95 % | p Holm | DD | Costo R | "
            "V1 | V2 | V3 | V4 | V5 | V6 |", "|---|---|---|--:|--:|---|--:|--:|--:|---|---|---|"
            "---|---|---|"]
    shown = sorted(rows, key=lambda x: -(x["mean_r"] if x["mean_r"] is not None else -9e9))[:limit]
    return head + [
        f"| `{x['id']}` | {x['variant']} | {x['verdict']} | {x['n']} | {_f(x['mean_r'])} | "
        f"[{_f(x['ci_lo'], 2)}, {_f(x['ci_hi'], 2)}] | {_f(x['p_holm'], 3, False)} | "
        f"{_pct(x['max_dd'], 0)} | {_f(x['cost_r'], 3, False)} | "
        + " | ".join(MARK[x[k]] for k in ("V1", "V2", "V3", "V4", "V5", "V6")) + " |"
        for x in shown]


def _detail(res: dict) -> list[str]:
    out = ["## 7. Por versión", "",
           f"Cada criterio de las {res['meta']['attempts']} versiones en las tres lecturas está en "
           f"`{res['meta']['csv']}`. Aquí, las de mayor R medio con ≥ 100 operaciones.", ""]
    for rid, title in TITLE.items():
        rows = [x for x in res["readings"][rid]["rows"] if x["n"] >= 100]
        out += [f"### {title}", ""]
        out += [*_table(rows), ""] if rows else ["Ninguna versión llega a 100 operaciones.", ""]
    return out


def render(res: dict) -> str:
    cands = res["candidates"]
    decide = (["## 8. Regla de lectura para la ◆", "", "Ninguna versión cumple la regla fijada en "
               "el pre-registro para proponer seguimiento prospectivo.", ""] if not cands else
              ["## 8. Regla de lectura para la ◆", "", "Cumplen la regla del pre-registro (no "
               "están validadas, solo justificarían un seguimiento prospectivo):", "",
               *[f"- `{c['id']}` ({c['variant']})" for c in cands], ""])
    return "\n".join([*_head(res), *_readings(res), *_cap(res), *_control(res), *_tf15(res),
                      *_regression(res), *_detail(res), *decide])
