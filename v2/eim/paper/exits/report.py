"""Informe del banco de salidas (T131) en markdown. Puro: del dict de `run.analyse` al texto.

Reglas del proyecto que el informe respeta: toda cifra dice de dónde sale y cuál es su cobertura
real, lo que no se pudo medir se dice, y lo que falta por implementar aparece con su tarea. No hay
ninguna conclusión de adopción: eso es T134.
"""

from __future__ import annotations

NA = "—"


def _n(x, k: int = 3, pct: bool = False) -> str:
    if x is None:
        return NA
    if pct:
        return f"{x:.1%}"
    return f"{x:+.{k}f}" if isinstance(x, float) else str(x)


def _row(vid: str, m: dict) -> str:
    return (f"| `{vid}` | {m.get('n', 0)} | {_n(m.get('win_rate'), pct=True)} | "
            f"{_n(m.get('expectancy_r'))} | {_n(m.get('avg_win_r'))} | "
            f"{_n(m.get('avg_loss_r'))} | {_n(m.get('win_loss_ratio'), 2)} | "
            f"{_n(m.get('pf'), 2)} | {_n(m.get('cost_r'))} | {_n(m.get('max_dd_r'), 2)} | "
            f"{_n(m.get('cvar95_r'))} | {_n(m.get('giveback_r'))} | "
            f"{_n(m.get('mfe1r_to_loss'), pct=True)} |")


def _variants(res: dict) -> list[str]:
    head = ("| Variante | n | Acierto | E[R] | Gan. media | Pérd. media | Cociente | PF | "
            "Costo R | DD máx. R | CVaR 95 % | Devolución | MFE≥1R → pérdida |")
    sep = "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|"
    out = ["### Fuera de muestra (solo los tramos de prueba de los pliegues)", "", head, sep]
    for vid, v in res["variants"].items():
        out.append(_row(vid, v["test"]))
    out += ["", "### Todo el periodo (descriptivo: incluye los tramos de ajuste)", "", head, sep]
    for vid, v in res["variants"].items():
        out.append(_row(vid, v["all"]))
    return out


def _multiplicity(res: dict) -> list[str]:
    out = []
    for base, blk in res["multiplicity"].items():
        out += [f"### ΔE[R] emparejado frente a `{base}`", "",
                f"{blk.get('n_paired_in_test', 0)} operaciones emparejadas en los tramos de "
                f"prueba, {blk.get('days', NA)} días de remuestreo, "
                f"{blk.get('reps', 0)} réplicas.", "",
                "| Variante | ΔE[R] (t) | IC 95 % | p bruto | p Romano-Wolf | p Holm |",
                "|---|--:|---|--:|--:|--:|"]
        for vid in sorted(blk.get("p_raw", {}), key=lambda k: -blk["t"].get(k, 0)):
            ci = blk.get("ci", {}).get(vid)
            ci_s = NA if not ci else f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"
            out.append(f"| `{vid}` | {_n(blk['t'].get(vid), 2)} | {ci_s} | "
                       f"{blk['p_raw'][vid]:.4f} | {blk['p_rw'][vid]:.4f} | "
                       f"{blk['p_holm'][vid]:.4f} |")
        if blk.get("skipped"):
            out.append("")
            out.append(f"Sin estadístico (muestra o varianza insuficientes): "
                       f"{', '.join('`' + x + '`' for x in blk['skipped'])}.")
        disagree = [k for k in blk.get("p_rw", {})
                    if (blk["p_rw"][k] < 0.05) != (blk["p_holm"][k] < 0.05)]
        out += ["", "Romano-Wolf y Holm "
                + ("coinciden en todas las variantes." if not disagree else
                   "**discrepan** en " + ", ".join(f"`{k}`" for k in disagree)
                   + " (E3: se informa)."), ""]
    return out


def _folds(res: dict) -> list[str]:
    w = res["walkforward"]
    out = ["| Pliegue | Ajuste | Prueba | Embargo (h) | Elegida en el ajuste | Motivo |",
           "|--:|---|---|--:|---|---|"]
    for f in w["folds"]:
        d, s = f["fold"], f["selection"]
        out.append(f"| {d['k']} | {d['fit'][0]} → {d['fit'][1]} | {d['test'][0]} → "
                   f"{d['test'][1]} | {d['embargo_hours']:g} | "
                   f"`{s.get('winner') or NA}` | {s.get('reason', '')} |")
    out += ["", f"**Fugas entre tramos: {w['leaks_total']}.** "
            + ("Ninguna operación de un tramo de ajuste se cierra dentro de su tramo de prueba "
               "ni de su embargo (purga y embargo de E1)."
               if w["leaks_total"] == 0 else
               "**Hay fugas: el resultado no es válido hasta resolverlas.**"), ""]
    first = w["folds"][0] if w["folds"] else None
    if first:
        p = first["fit"][next(iter(first["fit"]))]["purga"]
        out += [f"Purga del primer pliegue (ejemplo): {p['in_window']} operaciones decididas en "
                f"el ajuste, {p['kept']} se conservan, {p['purged_into_test']} se cierran dentro "
                f"de la prueba y {p['embargoed']} dentro del embargo.", ""]
    return out


def _control(ctrl: dict) -> list[str]:
    if not ctrl.get("n_ideas"):
        return ["No hay entradas de `control_aleatorio` en la copia: "
                f"{ctrl.get('note', 'control no evaluado')}.", ""]
    out = [f"{ctrl['n_ideas']} ideas de `control_aleatorio`. Lo que tiene que pasar es que el R "
           "**bruto** (neto + costo) sea compatible con 0: la salida no puede volver rentables "
           "unas entradas al azar. Si el 0 no está en el IC, hay un error o anticipación.", "",
           "| Variante | n | E[R] neto | Costo R | IC 95 % del bruto | ¿contiene el 0? |",
           "|---|--:|--:|--:|---|---|"]
    for vid, v in ctrl["variants"].items():
        ci = v.get("gross_ci") or []
        ci_s = NA if len(ci) != 2 or ci[0] != ci[0] else f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"
        ok = v.get("zero_in_gross_ci")
        out.append(f"| `{vid}` | {v['n']} | {_n(v.get('expectancy_r'))} | "
                   f"{_n(v.get('cost_r'))} | {ci_s} | "
                   f"{'sí' if ok else 'NO' if ok is False else NA} |")
    return out + [""]


def render(meta: dict, res: dict, ctrl: dict, stress: dict | None = None) -> str:
    """Informe completo. `stress` = {factor: res} del estrés de costos (E4a)."""
    pr, w = meta["prereg"], res["window"]
    out = [f"# T131 — banco de salidas emparejado ({meta['symbol']})", "",
           f"**Modo: SIMULADO.** Pre-registro `{pr['version']}`, huella "
           f"`{pr['sha256'][:16]}…`, {res['attempts']} intentos pre-registrados. "
           f"Generado el {meta['built']} desde la copia `{meta['data']}` "
           f"(commit `{meta['commit']}`).", "",
           f"Ventana medida: **{w['from']} → {w['to']}**, embargo "
           f"{w['embargo_hours']:g} h. Ideas simuladas: {res['bench']['ideas']}, de las que "
           f"{res['bench']['paired']} están emparejadas (todas las variantes las cerraron); "
           f"{res['bench']['skipped_qty']} se descartaron por no llegar a la cantidad mínima con "
           f"el riesgo fijo de {pr['risk_usd']:g} USDT.", "",
           "Lo que **no** se mide aquí, con su tarea: "
           + ", ".join(f"`{k}` ({v})" for k, v in res["pending_variants"].items())
           + ". Cuentan como intentos aunque no se corran (E12).", "",
           "## 1. Variantes", ""]
    ident = res.get("engine_identity")
    if ident:
        out += [(f"**Regresión con T111:** M0 y M1 devuelven exactamente lo que "
                 f"`simulate_ladder` y `engine.simulate` —las dos funciones que llamó T111— en "
                 f"las {ident['checked']} ideas reales comprobadas, campo a campo. Cualquier "
                 f"cifra de T111 sale igual del banco por construcción."
                 if ident.get("identical") else
                 f"**ATENCIÓN: los adaptadores NO reproducen el motor** en "
                 f"{len(ident['mismatches'])} de {ident['checked']} ideas: "
                 f"{ident['mismatches'][:3]}. El resto del informe no es comparable con T111."),
                ""]
    out += _variants(res)
    out += ["", "## 2. Pliegues, purga y embargo", ""] + _folds(res)
    out += ["## 3. Pruebas múltiples (E3)", ""] + _multiplicity(res)
    pb = res["pbo"]
    out += ["## 4. Probabilidad de sobreajuste (PBO, CSCV)", "",
            (f"PBO = **{pb['pbo']:.2f}** con {pb['splits']} tramos, {pb['combinations']} "
             f"combinaciones y {pb['variants']} variantes (logit mediano "
             f"{pb['logit_median']:+.2f}; degradación media {pb['degradation_mean']:+.4f}). "
             f"El pre-registro pide < {pr['pbo']['max_pbo']}."
             if pb.get("pbo") is not None else
             f"No se pudo calcular: {pb.get('reason', 'sin datos')}."), ""]
    out += ["## 5. Control aleatorio", ""] + _control(ctrl)
    if stress:
        out += ["## 6. Estrés de costos (E4a)", "",
                "| Factor | Variante | E[R] fuera de muestra | Costo R |", "|--:|---|--:|--:|"]
        for f, r in sorted(stress.items()):
            for vid, v in r["variants"].items():
                out.append(f"| ×{float(f):g} | `{vid}` | {_n(v['test'].get('expectancy_r'))} | "
                           f"{_n(v['test'].get('cost_r'))} |")
        out.append("")
    out += ["## Sharpe deflactado", "",
            f"Con {res['attempts']} intentos pre-registrados:", "",
            "| Variante | DSR |", "|---|--:|"]
    out += [f"| `{vid}` | {_n(v.get('dsr'), 3)} |" for vid, v in res["variants"].items()]
    out += ["", "El DSR usa TODOS los intentos de la rejilla, no solo los corridos: es lo honesto "
            "cuando la rejilla ya está pre-registrada.", "",
            "## Lo que este informe NO dice", "",
            "- No decide qué salida se adopta: eso es T134, con los criterios de §5.4.",
            "- Las variantes de M2 a M8 y S1 a S3 no están implementadas (T132, T133 y T136).",
            "- El tramo posterior a la ventana queda de reserva; la prueba definitiva es la "
            "prospectiva en papel (T135).", ""]
    return "\n".join(out) + "\n"
