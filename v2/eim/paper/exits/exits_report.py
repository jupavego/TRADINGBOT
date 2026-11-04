"""Informe del experimento de T134 (`reports/exits_ab.md`). Puro: del dict al texto.

Reglas que el informe cumple, porque son el punto de la tarea: ninguna política se presenta como
mejor sin cumplir §5.4; lo que no se pudo medir se dice; lo que no se corrió aparece con su motivo;
y nada de aquí habilita dinero real.
"""

from __future__ import annotations

from collections import Counter

NA = "—"
TOP = 12            # variantes que se listan en las tablas largas


def _n(x, k: int = 4) -> str:
    return NA if x is None or x != x else f"{x:+.{k}f}"


def _pct(x) -> str:
    return NA if x is None else f"{x:.1%}"


def _head(res: dict) -> list[str]:
    m, w = res["meta"], res["window"]
    return [f"# T134 — experimento pre-registrado de salidas ({m['symbol']})", "",
            "**Modo: SIMULADO. Nada de este informe habilita dinero real.**", "",
            f"Pre-registro `{m['prereg']}`, huella `{m['prereg_sha256'][:16]}…`, semilla "
            f"{m['seed']}, **{m['attempts']} intentos** pre-registrados. Generado el "
            f"{m['built']} desde `{m['data']}` (commit `{m['commit']}`) con "
            f"`{m['command']}`, en {m['seconds']:.0f} s.", "",
            f"Ventana **{w['from']} → {w['to']}**, {w['folds']} pliegues, embargo "
            f"{w['embargo_hours']:g} h. {m['ideas']} ideas, {m['fine_bars']} velas de 1 min, "
            f"{m['htf_bars']} del marco mayor. Bases: "
            + ", ".join(f"`{b}`" for b in res["bases"]) + ".", "",
            f"**{res['variants_run']} variantes corridas** de la rejilla. Fuera: "
            + ("; ".join(f"`{k}` ({v})" for k, v in res["grid_skipped"].items()) or "ninguna")
            + ". Cuentan como intentos igualmente (E12).", ""]


def _verdicts(res: dict) -> list[str]:
    vs = res["verdicts"]
    tally = Counter(x["status"] for x in vs)
    out = ["## 1. Veredicto", "",
           "Recuento: " + (", ".join(f"**{v} {k}**" for k, v in tally.most_common()) or "ninguno")
           + f", de {len(vs)} variantes juzgadas.", ""]
    live = [x for x in vs if x["status"] != "RECHAZADA"]
    if not live:
        out += ["**Ninguna variante pasa los criterios de §5.4.** No hay nada que llevar a la "
                "prueba en papel de T135.", ""]
    else:
        out += ["| Variante | Estado | Motivo |", "|---|---|---|"]
        out += [f"| `{x['variant']}` | {x['status']} | {x['reason']} |" for x in live]
        out.append("")
    out += ["### Por qué falla cada familia", "",
            "| Familia | n | Criterio que falla primero |", "|---|--:|---|"]
    by_fam: dict[str, list[dict]] = {}
    for x in vs:
        by_fam.setdefault(x["family"], []).append(x)
    for fam, xs in sorted(by_fam.items()):
        first = Counter()
        for x in xs:
            bad = [c["n"] for c in x["checks"] if c["ok"] is False]
            first[bad[0] if bad else 0] += 1
        bits = ", ".join(f"{'ninguno' if k == 0 else f'criterio {k}'}: {v}"
                         for k, v in sorted(first.items()))
        out.append(f"| `{fam}` | {len(xs)} | {bits} |")
    return out + [""]


def _table(res: dict, key: str, title: str) -> list[str]:
    rows = sorted(res["metrics"].items(),
                  key=lambda kv: -(kv[1][key].get("expectancy_r") or -9e9))[:TOP]
    out = [f"### {title}", "",
           "| Variante | n | Acierto | E[R] | Cociente | PF | Costo R | DD R | CVaR | "
           "Devolución |", "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for k, x in rows:
        m = x[key]
        out.append(f"| `{k}` | {m.get('n', 0)} | {_pct(m.get('win_rate'))} | "
                   f"{_n(m.get('expectancy_r'))} | {_n(m.get('win_loss_ratio'), 2)} | "
                   f"{_n(m.get('pf'), 3)} | {_n(m.get('cost_r'))} | "
                   f"{_n(m.get('max_dd_r'), 0)} | {_n(m.get('cvar95_r'))} | "
                   f"{_n(m.get('giveback_r'))} |")
    return out + ["", f"Solo las {TOP} mejores por E[R]; el resto, en el `.json` y el `.csv`.", ""]


def _multiplicity(res: dict) -> list[str]:
    out = ["## 3. Pruebas múltiples (E3)", ""]
    for base, blk in res["multiplicity"].items():
        raw = blk.get("p_raw", {})
        if not raw:
            out += [f"### Frente a `{base}`", "", "Sin comparaciones con muestra suficiente.", ""]
            continue
        order = sorted(raw, key=lambda k: -(blk.get("t", {}).get(k, -9e9)))[:TOP]
        out += [f"### Frente a `{base}`", "",
                f"{blk.get('days', NA)} días de remuestreo, {blk.get('reps', 0)} réplicas.", "",
                "| Variante | t | IC 95 % | p bruto | p Romano-Wolf | p Holm |",
                "|---|--:|---|--:|--:|--:|"]
        for k in order:
            ci = blk.get("ci", {}).get(k)
            ci_s = NA if not ci or ci[0] != ci[0] else f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"
            out.append(f"| `{k}` | {_n(blk.get('t', {}).get(k), 2)} | {ci_s} | "
                       f"{raw[k]:.4f} | {blk['p_rw'][k]:.4f} | {blk['p_holm'][k]:.4f} |")
        disagree = [k for k in blk.get("p_rw", {})
                    if (blk["p_rw"][k] < 0.05) != (blk["p_holm"][k] < 0.05)]
        out += ["", "Romano-Wolf y Holm "
                + ("coinciden en todas las variantes."
                   if not disagree else "**discrepan** en "
                   + ", ".join(f"`{k}`" for k in disagree[:8]) + " (E3: se informa)."), ""]
    return out


def _control(res: dict) -> list[str]:
    c = res.get("control") or {}
    out = ["## 5. Control aleatorio (criterio 6, nulo por series sustitutas)", ""]
    if not c:
        out += ["No se midió: solo se mide en las variantes que pasan el criterio 1, y ninguna "
                "llegó. El nulo está implementado y probado (`exits/surrogate.py`).", ""]
        return out
    out += ["El nulo conserva la distribución de retornos y destruye la dependencia serial: se "
            "barajan los log-retornos reales de 1 min y se rehace el camino. Se **rechaza** la "
            "variante si su R bruto destaca sobre ese nulo.", "",
            "| Variante | Bruto | Nulo (media) | Nulo p95 | p | ¿Pasa? |",
            "|---|--:|--:|--:|--:|---|"]
    for k, x in c.items():
        out.append(f"| `{k}` | {_n(x.get('observed_gross_r'))} | {_n(x.get('null_mean'))} | "
                   f"{_n(x.get('null_p95'))} | {_n(x.get('p_one_sided'), 3)} | "
                   f"{'sí' if x.get('ok') else 'NO' if x.get('ok') is False else NA} |")
    return out + [""]


def _power(res: dict) -> list[str]:
    p = res.get("power_inputs") or {}
    out = ["## 6. Insumos de potencia para T135 (E9)", "",
           p.get("_nota", ""), "",
           "| Variante | n cerradas | n en prueba | Op./semana | σ de las diferencias |",
           "|---|--:|--:|--:|---|"]
    for k, x in list(p.items())[:TOP + 2]:
        if k.startswith("_"):
            continue
        sd = x.get("sd_paired") or {}
        out.append(f"| `{k}` | {x.get('n_closed', 0)} | {x.get('n_tested', 0)} | "
                   f"{_n(x.get('trades_per_week'), 1)} | "
                   + ", ".join(f"{b}: {_n(v, 3)}" for b, v in sd.items()) + " |")
    return out + [""]


def render(res: dict) -> str:
    out = _head(res)
    out += _verdicts(res)
    out += ["## 2. Cifras", ""]
    out += _table(res, "test", "Fuera de muestra (tramos de prueba de los pliegues)")
    out += _table(res, "all", "Todo el periodo (descriptivo)")
    out += _multiplicity(res)
    pb = res.get("pbo") or {}
    out += ["## 4. Probabilidad de sobreajuste (PBO, CSCV)", "",
            (f"PBO = **{pb['pbo']:.2f}** con {pb.get('splits')} tramos, "
             f"{pb.get('combinations')} combinaciones y {pb.get('variants')} variantes "
             f"(logit mediano {_n(pb.get('logit_median'), 2)}). El pre-registro pide < 0,2."
             if pb.get("pbo") is not None else
             f"No se pudo calcular: {pb.get('reason', 'sin datos')}."), ""]
    out += _control(res)
    out += _power(res)
    st = res.get("stress") or {}
    out += ["## 7. Estrés de costos (E4a)", "",
            (f"Medido en {len(st)} variantes (las que pasan el criterio 1 con el costo base; "
             "una que no lo pasa tampoco lo pasaría con costos mayores, así que ningún veredicto "
             "cambia)." if st else
             "No se midió: ninguna variante pasó el criterio 1 con el costo base, así que su "
             "criterio 8 queda **pendiente**, no cumplido."), ""]
    cov = res.get("feature_coverage") or {}
    if cov:
        out += ["## 8. Cobertura de los rasgos", "",
                "| Estimador σ | σ | swing bajo | marco mayor |", "|---|--:|--:|--:|"]
        for name, x in cov.items():
            k = x["coverage"]
            out.append(f"| `{name}` | {k['sigma_abs']:.1%} | {k['swing_low']:.1%} | "
                       f"{k['htf_dir']:.1%} |")
        out.append("")
    out += ["## Lo que este informe NO dice", "",
            "- **No adopta nada.** La decisión es del usuario (◆ de T134) y ninguna variante "
            "puede estar aprobada aquí: el criterio 7 de §5.4 es prospectivo y su dato nace en "
            "T135.",
            f"- **Libro completo:** {res.get('libro_completo', '')}.",
            "- **S2** (cierres parciales) y **S3** (riesgo de cartera) no se corrieron: la "
            "primera necesita permiso del usuario y código; la segunda es de T136. Cuentan como "
            "intentos.",
            "- **M4** quedó descartada en T133 por su cota del oráculo, no por este experimento.",
            "- Nada de aquí habilita dinero real: sigue hecho falta la puerta de edge (T27) y las "
            "semanas de papel (T31).", ""]
    return "\n".join(out) + "\n"
