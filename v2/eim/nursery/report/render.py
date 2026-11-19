"""El informe mensual de la cantera en Markdown (T172). Puro."""

from __future__ import annotations

from datetime import UTC, datetime

STAGE = {"guarderia": "guardería", "cantera": "cantera", "promesa": "promesa",
         "primer_equipo": "primer equipo", "baja": "baja"}


def _t(ms: int | None) -> str:
    if ms is None:
        return "—"
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d %H:%M UTC")


def _n(x, d: int = 3, sign: bool = True) -> str:
    if x is None:
        return "—"
    return (f"{x:+.{d}f}" if sign else f"{x:.{d}f}").replace(".", ",")


def _ci(c: dict) -> str:
    if not c or c.get("mean") is None:
        return "—"
    if c.get("lo") is None:
        return _n(c["mean"])
    return f"{_n(c['mean'])} ({_n(c['lo'])} … {_n(c['hi'])})"


def _head(r: dict) -> list[str]:
    s = r["snapshot"]
    fp = r["false_promises"]
    bh = r.get("buy_hold") or {}
    lines = [f"# Cantera — informe mensual de ojeo y retroalimentación ({r['date']})", "",
             f"**Modo: SIMULADO.** Informa y propone; no cambia pesos ni parámetros por sí solo. "
             f"Generado por `python -m eim.nursery report` (T172) con `{s['prereg']}` "
             f"(huella `{s['sha256'][:12]}…`).", "",
             f"- Libro: `{s['source']}`. Alta {_t(s['alta_ms'])}; lectura hasta "
             f"{_t(s['asof_ms'])} (día {_n(r['elapsed_days'], 1, False)} de "
             f"{r['deadline_days']}).",
             f"- Revisiones hechas: **{r['reviews_done']}** de {len(r['reviews_ms'])}; próxima "
             f"{_t(r['next_review_ms'])}. Solo en ellas cambia una etapa: esta lectura no es una "
             "mirada del método secuencial.",
             f"- Precio declarado de la capa sensible (q = 0,10): bajo la nula global se esperan "
             f"{_n(fp.get('mean'), 4, False)} promesas falsas en la fase "
             f"(P(≥ 1) = {_n(fp.get('p_at_least_one'), 4, False)}).",
             f"- Comprar y mantener desde el alta: {_n(bh.get('return_pct'), 2)} % "
             f"({_n(bh.get('r_long'), 2)} R en largo, {_n(bh.get('r_short'), 2)} R en corto; "
             f"{bh.get('basis', 'sin medir')})."]
    lines += [f"- Aviso: {w}" for w in s["warnings"]]
    return lines + [""]


def _table(r: dict) -> list[str]:
    lines = ["## 1. Rentabilidad neta por prospecto frente al azar y a comprar y mantener", "",
             "d = R de la operación − media de sus 200 gemelos al azar (la vara contra la "
             "suerte). Etapa del escalafón pre-registrado.", "",
             "| Prospecto | Agente | Tema | Marco | Etapa | n | Rent. neta % | vs C&M (pp) | "
             "d vs gemelos (IC 95 %) | DD % / tope | Motivo |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in r["prospects"]:
        motivo = (x.get("exit") or {}).get("motivo", "")
        lines.append(f"| `{x['id']}` | {x['agent']} | {x['theme']} | {x['timeframe']} | "
                     f"{STAGE.get(x['stage'], x['stage'])} | {x['n']} | "
                     f"{_n(x['net_return_pct'], 2)} | {_n(x['vs_buy_hold_pp'], 2)} | "
                     f"{_ci(x['d'])} | {_n(x['max_dd_pct'], 1, False)} / "
                     f"{_n(x['dd_cap_pct'], 1, False)} | {motivo} |")
    moves = r["moves"]
    lines += ["", "### Ascensos y bajas en la última revisión", ""]
    lines += [f"- `{m['id']}` → **{STAGE.get(m['stage'], m['stage'])}**: {m['motivo']}"
              for m in moves] or ["- Ninguno."]
    return lines + [""]


def _theories(r: dict) -> list[str]:
    th = r["theories"]
    lines = ["## 2. Qué teoría se sostuvo", "", "### Por tema (efectos aleatorios, Holm sobre "
             "los temas, α = 0,10)", "", "| Tema | Media d̃ | EE | p | p Holm | ¿Se sostiene? |",
             "|---|---|---|---|---|---|"]
    for k, v in th["by_theme"].items():
        lines.append(f"| {k} | {_n(v['mean'])} | {_n(v['se'], 3, False)} | "
                     f"{_n(v['p'], 4, False)} | {_n(v.get('p_holm'), 4, False)} | "
                     f"{'sí' if v.get('holds') else 'no'} |")
    lines += ["", f"### Por agente (d̃ recortada a ±{th['clip_r']:g} R; media encogida hacia su "
              "tema por prospecto)", "", "| Agente | n | d̃ (IC 95 %) | Prospectos: bruto → "
              "encogido |", "|---|---|---|---|"]
    for a, v in sorted(th["by_agent"].items()):
        ps = "; ".join(f"`{p['id']}` {_n(p.get('raw'))} → {_n(p.get('shrunk'))}"
                       for p in v["prospects"])
        ci = _ci({"mean": v["d_mean"], "lo": v["lo"], "hi": v["hi"]})
        lines.append(f"| {a} | {v['n']} | {ci} | {ps} |")
    nv = r["native_vs_generic"]
    lines += ["", f"### Nativo frente al `agente_{{id}}` genérico (Holm sobre {nv['tests']}, "
              f"α = {_n(nv['alpha'], 2, False)})", "",
              "| Agente | n nativo | n genérico | z | p Holm | ¿Mejor lo nativo? |",
              "|---|---|---|---|---|---|"]
    for a, v in sorted(nv["agents"].items()):
        lines.append(f"| {a} | {v['n_native']} | {v['n_generic']} | {_n(v['z'], 2)} | "
                     f"{_n(v['p_holm'], 4, False)} | {'sí' if v['native_better'] else 'no'} |")
    return lines + [""]


def _shape(r: dict) -> list[str]:
    f = r["family"]
    per, pb = f["persistence"], f["pbo"]
    lines = ["## 3. Forma de la familia (descriptivo)", "",
             f"- N efectivo **{f['n_effective'] or '—'}** (grupos con correlación diaria de d ≥ "
             f"{_n(f['neff_corr'], 1, False)}) frente a {f['with_trades']} con operaciones, "
             f"{f['members']} inscritos y m = {f['m_nominal']} del pre-registro.",
             "- Persistencia del orden (1.ª frente a 2.ª mitad de lo transcurrido): " +
             (f"Spearman {_n(per['spearman'], 2)} (p {_n(per['p'], 3, False)}), mitad alta que "
              f"sigue arriba {per['top_half_kept']}, con {per['prospects']} prospectos."
              if per.get("spearman") is not None else per.get("reason", "—")),
             "- PBO/CSCV: " + (f"{_n(pb['pbo'], 2, False)} (descriptivo; decide la persistencia "
                               "en la mirada final)" if pb.get("pbo") is not None
                               else pb.get("reason", "—")), "",
             "### Señales tempranas (volatilidad y drawdown; se vigilan, no deciden)", ""]
    lines += [f"- `{e['id']}`: {'; '.join(e['why'])}" for e in r["early"]] or ["- Ninguna."]
    return lines + [""]


def _feedback(r: dict) -> list[str]:
    lib, imp = r["library"], r["improvement"]
    lines = ["## 4. Retroalimentación", "", "### A la biblioteca (hechos de aprendizaje)", "",
             f"{lib['facts']} hechos (prospecto × obra) en la revisión {lib['review'] or '—'}: " +
             ", ".join(f"{k} {v}" for k, v in lib["by_verdict"].items()) +
             f". Nuevos en el registro: {lib['added']}. No concluyente es el veredicto por "
             "defecto; los pesos de consenso no cambian solos.", "",
             "### A los agentes y ciclo de mejora (§9.2–9.3)", ""]
    for d in imp["drops"]:
        c = d["chain"]
        lines.append(f"- `{d['id']}` ({(d['exit'] or {}).get('reason')}): causa "
                     f"**{d['cause'] or 'sin causa nombrada'}** — {d['why']}. Cadena: n {c['n']}, "
                     f"R neto {_n(c['r_net'])}, bruto {_n(c['r_gross'])}, costo "
                     f"{_n(c['cost_r'], 3, False)} R, d {_n(c['d'])}.")
    if not imp["drops"]:
        lines.append("- Sin bajas.")
    lines += ["", "**Propuestas de versión nueva (◆, gastan una plaza de reserva de "
              f"{imp['reserve_slots']}):**"]
    lines += [f"- `{p['id']}` ({p['cause']}): MinTRL {_n(p['mintrl_trades'], 0, False)} "
              f"operaciones ≈ {_n(p['mintrl_days'], 1, False) if p['mintrl_days'] else '∞'} días "
              f"de {_n(p['days_left'], 1, False)} que quedan — {p['note']}."
              for p in imp["proposals"]] or ["- Ninguna."]
    lines += ["", "**Variantes de ejecución (mesa aparte, `EIM_PAPER_VARIANTS`, ◆ y para todas "
              "las cuentas a la vez):**"]
    lines += [f"- {v['timeframe']}: {', '.join(v['prospects'])} — {v['how']}."
              for v in imp["variants"]] or ["- Ninguna."]
    lines += ["", "**Para BACKLOG (mejora del agente):**"]
    lines += imp["backlog"] or ["- Nada."]
    lines += ["", "### Eventos de `AUTO_ADAPT` (solo costo y riesgo se adaptan solos)", ""]
    lines += [f"- {_t(int(e.get('t') or 0))} · {e.get('kind')} · {e.get('timeframe', '')}: "
              f"{e.get('before') or 'inicio'} → {e.get('after', '')} (costo "
              f"{_n(e.get('value_r'), 3, False)} R, {e.get('source', '')}; umbral "
              f"{_n(e.get('threshold_r'), 2, False)} R; {len(e.get('accounts') or [])} cuentas)"
              for e in r["events"]] or ["- Ninguno."]
    return lines + [""]


def _synthesis(r: dict) -> list[str]:
    inf = r["informativity"]
    lines = ["## 5. A la síntesis (T150) y a la auditoría (T159)", "",
             "| Agente | Prospecto base | n | d (IC 95 %) | R neto | Lectura |",
             "|---|---|---|---|---|---|"]
    for a, v in sorted(inf["agents"].items()):
        lines.append(f"| {a} | `{v['base']}` | {v['n']} | "
                     f"{_ci({'mean': v['d_mean'], 'lo': v['lo'], 'hi': v['hi']})} | "
                     f"{_n(v['r_net'])} | {v['state']} |")
    lines += ["", inf["rule"], "La auditoría semanal lee `reports/nursery/latest.json`.", ""]
    lines += ["## 6. Graduaciones (◆) y cierre de la fase", ""]
    for g in r["graduations"]:
        h = g["haircut"] or {}
        lines.append(f"- `{g['id']}`: R medio {_n(h.get('mean_r'))} → ventaja en vivo tras el "
                     f"recorte de Harvey-Liu **{_n(h.get('live_edge_r'))} R** (recorte medio "
                     f"{_n(h.get('haircut_mean'), 2, False)}, m = {h.get('tests_m')}). "
                     f"{g['decision']}." + (" Disparador para revisar la decisión D de T145 (◆)."
                                            if g["t145_trigger"] else ""))
    if not r["graduations"]:
        lines.append("- Ningún candidato a primer equipo (solo puede haberlos en la mirada final).")
    c = r.get("closure")
    lines.append("" if c is None else f"\n**Cierre de la fase ({_t(c['deadline_ms'])}): "
                                      f"{c['headline']}.** Veredicto por prospecto en el JSON.")
    if c is None:
        lines.append(f"Cierre de la fase en la fecha límite ({_t(r['reviews_ms'][-1])}), aunque "
                     "sea «ninguno se graduó».")
    return lines + [""]


def markdown(r: dict) -> str:
    out = (_head(r) + _table(r) + _theories(r) + _shape(r) + _feedback(r) + _synthesis(r))
    return "\n".join(out).rstrip() + "\n"
