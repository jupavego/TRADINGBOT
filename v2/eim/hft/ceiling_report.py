"""Informe de la prueba de techo (T80) en Markdown: criterios antes, resultados después.

Puro: recibe el JSON que calcula `ceiling_run` y devuelve texto. El mismo orden que
`reports/edge_gate.md` (T27), porque el informe tiene que poder leerse como una decisión y no
como una tabla de números.
"""

from __future__ import annotations

STYLES = ("taker", "mixto", "maker")
MARK = {"SUPERA": "SUPERA", "NO SUPERA": "NO SUPERA", "SIN POTENCIA": "SIN POTENCIA"}


def n(x, nd: int = 2, pct: bool = False) -> str:
    """Número en castellano (coma decimal); «—» si no hay dato."""
    if x is None or x != x:
        return "—"
    v = float(x) * (100 if pct else 1)
    s = f"{v:,.{nd}f}".replace(",", " ").replace(".", ",")
    return s + (" %" if pct else "")


def _ci(row: dict, nd: int = 3) -> str:
    return f"{n(row.get('lo'), nd)} … {n(row.get('hi'), nd)}"


def head(rep: dict, pr) -> list[str]:
    s = rep["sample"]
    return [
        "# T80 — Prueba de techo del carril HFT (informe de decisión)",
        "",
        f"Modo: **ANÁLISIS** (no se opera nada aquí). Símbolo **{rep['symbol']}**, "
        f"cubos de {rep['step_ms']} ms, reacción aplicada {rep['reaction_ms']} ms.",
        f"Ventana: **{s['first_day_utc']} → {s['last_day_utc']}** "
        f"({s['days']} días UTC, {s['hours']} horas completas de la captura de T78, "
        f"{s['rows']} cubos utilizables de {s['rows_panel']}).",
        f"Pre-registro `{rep['prereg']}` · SHA-256 `{rep['prereg_sha256'][:16]}…` · "
        f"calculado en {n(rep['seconds'], 0)} s.",
        "",
    ]


def criteria(pr) -> list[str]:
    g = pr.gates
    out = [
        "## 1. Criterios (congelados ANTES de calcular cualquier resultado)",
        "",
        f"Archivo `eim/hft/prereg/{pr.version}.json`, con su SHA-256 fijado en el código: "
        "cambiar un umbral es una versión nueva, no una edición. Ni uno de estos números se "
        "tocó después de ver los resultados.",
        "",
        "| # | Criterio | Umbral |",
        "|---|---|---|",
        "| C1 | Oportunidad: fracción de ventanas en las que |Δmid| supera el ida y vuelta "
        "(previsión perfecta de la dirección, reacción medida) | ≥ "
        + n(g["C1_oportunidad"]["threshold"], 2, True) + " |",
        f"| C2 | IC fuera de muestra de alguna señal (Spearman por día) | media > 0, IC 95 % "
        f"inferior > 0 y **p de Holm < {n(g['C2_ic']['alpha'], 2)}** sobre "
        f"{pr.attempts.family} intentos |",
        f"| C3 | pb netos por operación fuera de muestra, con el costo de ese estilo | "
        f"media ≥ **+{n(g['C3_net_bps']['threshold_bps'], 1)} pb** e IC 95 % inferior > 0 |",
        f"| C4 | Muestra | ≥ {g['C4_sample']['min_days']} días con panel y "
        f"≥ {g['C4_sample']['min_test_days']} días de prueba |",
        "",
        "Horizontes: " + ", ".join(f"{h} s" for h in pr.horizons_s)
        + " (T77 fijó 30 s como tenencia mínima viable y taker desde 60 s; 1 s y 5 s se miden "
          "como variables, no como tenencia).",
        "Costos de ida y vuelta (`CostParams`, VIP 0): "
        + " · ".join(f"{k} {n(v, 1)} pb" for k, v in pr.costs_bps.items()) + ".",
        f"Partición: walk-forward por días UTC contiguos, {pr.split.train_days} de "
        f"entrenamiento, {pr.split.test_days} de prueba, embargo de {pr.split.embargo_days} día "
        "y purga por la etiqueta (ninguna fila de entrenamiento tiene su etiqueta dentro del "
        "día de prueba).",
        "",
        "Regla de veredicto, fijada de antemano:",
        "",
    ]
    out += [f"- **{k}**: {v}" for k, v in pr.verdict_rule.items()]
    return [*out, ""]


def how(rep: dict, pr) -> list[str]:
    q = rep["queue"]
    return [
        "## 2. Cómo se obtuvo la evidencia",
        "",
        "```",
        "python -m eim.data.collectors.hft_panel --from "
        f"{pr.data.from_} --to {pr.data.to}     # panel: reproduce el libro de T78",
        "python -m eim.hft.ceiling_run --root data --out reports      # esta corrida",
        "```",
        "",
        "El panel tiene una fila por segundo con el libro top-5 al CIERRE del cubo, el OFI "
        "multinivel acumulado dentro del cubo y el flujo agresor del cubo; se muestrea por hora "
        "de RECEPCIÓN, que es lo que se pudo saber en el momento. Solo entran horas que el "
        "control de calidad de T78 da por completas y sin huecos sin detectar, y dentro de "
        "ellas solo los cubos completos.",
        "",
        f"Contexto del libro: cola visible al frente {n(q['front_qty_p50'], 3)} BTC (mediana), "
        f"spread {n(q['spread_bps_p50'], 2)} pb (p50) y {n(q['spread_bps_p95'], 2)} pb (p95), "
        f"volumen negociado {n(q['volume_per_s_mean'], 3)} BTC/s de media.",
        "",
        "Avisos que hay que leer con los números:",
        "",
        "- Las ventanas se solapan (una por cubo): las medias por día y sus IC por bloques de "
        "día valen; el número de operaciones **no es realizable** (el equivalente sin solape es "
        "filas ÷ horizonte en segundos).",
        "- La reacción se aplica retrasando la entrada un cubo entero (1 000 ms) cuando lo "
        f"medido en T77 es {pr.reaction.p50_ms}/{pr.reaction.p99_ms} ms (p50/p99): el resultado "
        "es **más pesimista** que la latencia real.",
        "- El camino del mid se mira al cierre de cada cubo: un toque y vuelta dentro del mismo "
        "segundo no se ve.",
        "",
    ]


def ceiling_section(rep: dict) -> list[str]:
    out = ["## 3. (a) Techo con previsión perfecta de la dirección", "",
           "Se conoce el signo del Δmid y se entra siempre del lado bueno, sin selección "
           "adversa, sin cola y sin impacto: **nadie puede superar esto**. «paga» = las ventanas "
           "en las que |Δmid| supera el ida y vuelta; «techo» = E[máx(|Δmid| − costo, 0)] por "
           "ventana (pb).", ""]
    for key, title in (("no_reaction", "Sin reacción (cota de arriba absoluta)"),
                       ("with_reaction", "Con la reacción medida (entrada un cubo después)")):
        out += [f"### {title}", "",
                "| h | n | |Δmid| medio | p90 | p99 | " + " | ".join(
                    f"paga {s} / techo" for s in STYLES) + " |",
                "|---|---|---|---|---|" + "---|" * len(STYLES)]
        for h, block in sorted(rep["ceiling"]["horizons"].items(), key=lambda kv: int(kv[0])):
            b = block.get(key, {})
            if not b.get("n"):
                out.append(f"| {h} s | 0 | — | — | — |" + " — |" * len(STYLES))
                continue
            cells = []
            for s in STYLES:
                row = b["styles"][s]
                cells.append(f"{n(row['frac_pays'], 2, True)} / "
                             f"{n(row['ceiling_bps_per_window'], 3)}")
            out.append(f"| {h} s | {b['n']} | {n(b['mean_abs_bps'], 3)} | "
                       f"{n(b['p90_abs_bps'], 3)} | {n(b['p99_abs_bps'], 3)} | "
                       + " | ".join(cells) + " |")
        out.append("")
    return out


def ic_section(rep: dict) -> list[str]:
    oos = rep["oos"]
    hs = sorted(oos["horizons"], key=int)
    out = ["## 4. (b) IC fuera de muestra de cada variable y de la ridge conjunta", "",
           f"IC de Spearman medio por día de prueba. **=** marca p de Holm < 0,05 sobre los "
           f"{oos['attempts']} intentos de la familia (todos los de esta tabla).", "",
           "| señal | " + " | ".join(f"IC {h} s" for h in hs) + " |",
           "|---|" + "---|" * len(hs)]
    names = sorted(oos["horizons"][hs[0]])
    for name in names:
        cells = []
        for h in hs:
            s = oos["horizons"][h][name]
            star = " =" if s["ic_p_holm"] < 0.05 else ""
            cells.append(f"{n(s['ic']['mean'], 4)}{star}")
        out.append(f"| `{name}` | " + " | ".join(cells) + " |")
    out += ["", "Detalle de la mejor señal de cada horizonte (IC 95 % por bloques de día):", "",
            "| h | señal | IC medio | IC 95 % | días + | p | p Holm |",
            "|---|---|---|---|---|---|---|"]
    for h in hs:
        block = oos["horizons"][h]
        best = max(block, key=lambda k: (block[k]["ic"]["mean"] is not None,
                                         block[k]["ic"]["mean"] or -9))
        s = block[best]
        out.append(f"| {h} s | `{best}` | {n(s['ic']['mean'], 4)} | {_ci(s['ic'], 4)} | "
                   f"{n(s['ic'].get('positive_days'), 0, True)} | {n(s['ic_p'], 3)} | "
                   f"{n(s['ic_p_holm'], 3)} |")
    return [*out, ""]


def gross_section(rep: dict) -> list[str]:
    """pb BRUTOS por operación (sin costo): lo que hay antes de pagar nada."""
    oos = rep["oos"]
    out = ["## 5. (c) pb brutos por operación, antes de pagar el costo", "",
           "Media de signo(predicción) × Δmid por día de prueba, con la reacción aplicada y SIN "
           "restar costo: es el edge bruto que existe. «decil» = solo el 10 % de filas con la "
           "predicción más fuerte. Al lado, el costo más bajo que habría que pagar "
           f"({n(min(rep['ceiling']['costs_bps'].values()), 1)} pb, maker-maker).", "",
           "| h | señal | bruto todas (pb) | IC 95 % | bruto decil (pb) | IC 95 % |",
           "|---|---|---|---|---|---|"]
    for h in sorted(oos["horizons"], key=int):
        block = oos["horizons"][h]
        cand = [(k, v) for k, v in block.items() if v.get("gross", {}).get("mean") is not None]
        if not cand:
            out.append(f"| {h} s | — | — | — | — | — |")
            continue
        name, s = max(cand, key=lambda kv: kv[1]["gross_top"]["mean"] or -9)
        out.append(f"| {h} s | `{name}` | {n(s['gross']['mean'], 4)} | {_ci(s['gross'], 4)} | "
                   f"{n(s['gross_top']['mean'], 4)} | {_ci(s['gross_top'], 4)} |")
    return [*out, ""]


def net_section(rep: dict) -> list[str]:
    oos = rep["oos"]
    out = ["### pb netos por operación, con el costo de cada estilo", "",
           "De cada horizonte, la señal con los mejores pb netos de cada estilo: se opera solo "
           "cuando la predicción (ajustada con el entrenamiento) supera el costo. «—» significa "
           "que la predicción nunca llegó a ese costo: no hay operación que hacer.", "",
           "| h | estilo | señal | pb netos | IC 95 % | operaciones | % de filas | sin solape |",
           "|---|---|---|---|---|---|---|---|"]
    for h in sorted(oos["horizons"], key=int):
        block = oos["horizons"][h]
        for style in STYLES:
            cand = [(k, v["net"][style]) for k, v in block.items()
                    if v["net"][style].get("mean") is not None]
            if not cand:
                out.append(f"| {h} s | {style} | — | — | — | — | — | — |")
                continue
            name, row = max(cand, key=lambda kv: kv[1]["mean"])
            overlap = block[name].get("overlap", 1)
            out.append(f"| {h} s | {style} | `{name}` | {n(row['mean'], 3)} | {_ci(row, 3)} | "
                       f"{row['trades']} | {n(row['share_of_rows'], 2, True)} | "
                       f"{int(row['trades'] / max(overlap, 1))} |")
    return [*out, ""]


def cost_section(rep: dict) -> list[str]:
    out = ["## 6. (d) Qué parte del movimiento se come el costo", "",
           "Con la reacción medida, sobre las ventanas que pagan: «bruto» es |Δmid| medio ahí y "
           "«costo/bruto» la parte que se lleva la comisión más el spread.", "",
           "| h | estilo | bruto (pb) | neto (pb) | costo/bruto | costo/|Δmid| medio |",
           "|---|---|---|---|---|---|"]
    for h, block in sorted(rep["ceiling"]["horizons"].items(), key=lambda kv: int(kv[0])):
        b = block.get("with_reaction", {})
        if not b.get("n"):
            continue
        for s in STYLES:
            row = b["styles"][s]
            out.append(f"| {h} s | {s} | {n(row['gross_bps_when_pays'], 3)} | "
                       f"{n(row['net_bps_when_pays'], 3)} | "
                       f"{n(row['cost_share_when_pays'], 2, True)} | "
                       f"{n(row['cost_share_of_mean_move'], 2)}× |")
    out += ["", "### Llenado de la cola: ¿existe la entrada pasiva?", "",
            "Cola pesimista (al final de la cola visible al llegar, sin avanzar por "
            "cancelaciones): fracción de cubos en los que una orden al mejor precio se habría "
            "llenado dentro de la espera.", "",
            "| espera | compra | venta | media |", "|---|---|---|---|"]
    for w, row in sorted(rep["fills"].items(), key=lambda kv: int(kv[0])):
        out.append(f"| {w} s | {n(row['buy'], 2, True)} | {n(row['sell'], 2, True)} | "
                   f"{n(row['both'], 2, True)} |")
    return [*out, ""]


def verdict_section(rep: dict, pr) -> list[str]:
    g = rep["gate"]
    c4 = g["C4_sample"]
    out = ["## 7. Veredicto", "", f"### {MARK.get(g['verdict'], g['verdict'])}", "",
           f"- **C4 muestra**: {c4['days']} días (mínimo {c4['min_days']}) y "
           f"{c4['test_days']} días de prueba (mínimo {c4['min_test_days']}) → "
           f"{'cumple' if c4['pass'] else 'NO cumple'}.", ""]
    out += ["| h | C1 estilos que pagan | C2 señales con IC (Holm) | C3 (señal, estilo) | "
            "¿supera? |", "|---|---|---|---|---|"]
    for h, row in sorted(g["by_horizon"].items(), key=lambda kv: int(kv[0])):
        sigs = ", ".join(f"`{s}`" for s in row["c2_signals"][:4]) or "—"
        pairs = ", ".join(f"`{p['signal']}`/{p['style']} ({n(p['net_bps'], 2)} pb)"
                          for p in row["c3_pairs"][:3]) or "—"
        out.append(f"| {h} s | {', '.join(row['c1_styles']) or '—'} | {sigs} | {pairs} | "
                   f"{'sí' if row['pass'] else 'no'} |")
    out += ["", "Lo que decide el usuario (◆, §Aceptación de T80):", "",
            "- si el techo o el IC no superan los costos con margen en ningún horizonte → se "
            "archiva con el resultado honesto (como T28) o se redirige: otro horizonte, otro "
            "símbolo, comisión VIP/rebate;",
            "- si lo superan → siguen T81–T85 con este marco y estas variables.", "",
            f"Registro de intentos: `eim/hft/attempts_t80.json` "
            f"({rep['oos']['attempts']} intentos; cuentan en la familia de Holm de T84 aunque "
            "se descarten).", ""]
    return out


def render(rep: dict, pr) -> str:
    """Informe completo en Markdown."""
    parts = [*head(rep, pr), *criteria(pr), *how(rep, pr), *ceiling_section(rep),
             *ic_section(rep), *gross_section(rep), *net_section(rep), *cost_section(rep),
             *verdict_section(rep, pr)]
    return "\n".join(parts).rstrip() + "\n"
