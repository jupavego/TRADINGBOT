"""Informe de la auditoría (T159): Markdown completo y un resumen corto para la consola. Puro."""

from __future__ import annotations


def _r(x, d=3) -> str:
    return "—" if x is None else f"{x:+.{d}f}"


def _p(x) -> str:
    return "—" if x is None else f"{x:.1%}"


def _row(name: str, s: dict) -> str:
    if not s.get("n"):
        return f"| {name} | 0 | — | — | — | — | — | — |"
    mark = "" if s.get("readable") else " ·"
    return (f"| {name}{mark} | {s['n']} | {_p(s['win_rate'])} | {_p(s.get('breakeven_win_rate'))} "
            f"| {_r(s['e_r'])} | {_r(s.get('cost_r'))} | {_r(s.get('gross_r'))} "
            f"| {s['pnl_usdt']:+.1f} |")


HEAD = ("| Grupo | n | Acierto | Equilibrio | E[R] neto | Costo R | Bruto R | PnL USDT |\n"
        "|---|---|---|---|---|---|---|---|")


def _impact(o: dict) -> str:
    u = "" if o["impact_usdt"] is None else f"{o['impact_usdt']:.0f} USDT"
    r = "" if o["impact_r_per_op"] is None else f"{o['impact_r_per_op']:+.3f} R/op"
    return " · ".join(x for x in (u, r) if x) or "—"


def markdown(a: dict) -> str:
    b = a["book"]
    s = b["all"]
    lines = [f"# Auditoría periódica EIM — {a['generated_at'][:10]}", "",
             f"**Modo: SIMULADO.** Generado {a['generated_at']} por `python -m eim.analytics.audit` "
             f"(T159). Universo: {b['universe']}; {b['rows_official']} de {b['rows_total']} filas "
             f"cuentan (excluidas: {b['excluded']}).", "",
             "## 1. Resultado", ""]
    if s.get("n"):
        lines += [f"- E[R] neto **{_r(s['e_r'])} R/op** (IC 95 % {_r(s['e_r_ci'][0])} … "
                  f"{_r(s['e_r_ci'][1])}), bruto **{_r(s.get('gross_r'))}**, costo "
                  f"{_r(s.get('cost_r'))} R ({s.get('cost_bps_median') or 0:.1f} pb mediana).",
                  f"- Acierto {_p(s['win_rate'])} frente a equilibrio "
                  f"{_p(s.get('breakeven_win_rate'))}; ganadora {_r(s['avg_win_r'])} R, perdedora "
                  f"{_r(s['avg_loss_r'])} R. PnL {s['pnl_usdt']:+.1f} USDT, fricción "
                  f"{s['cost_usdt']:.1f} USDT.", ""]
    lines += [HEAD, _row("todo", s), _row("últimos 28 d", b["last28"]),
              _row("últimos 7 d", b["last7"]), ""]
    for title, key in (("Perfil", "by_profile"), ("Marco", "by_timeframe"),
                       ("Tipo de entrada", "by_kind"), ("Salida", "by_reason"),
                       ("Apalancamiento", "by_leverage"), ("Estrategia", "by_strategy")):
        lines += [f"### {title}", "", HEAD] + [_row(k, v) for k, v in b[key].items()] + [""]
    lines += ["`·` = menos de 20 operaciones: se lista, no se lee como resultado.", "",
              "## 2. Oportunidades (impacto sobre la muestra observada; cota, no promesa)", "",
              "| # | Categoría | Oportunidad | Evidencia | Impacto | Vía | Ref. |",
              "|---|---|---|---|---|---|---|"]
    for i, o in enumerate(a["opportunities"], 1):
        lines.append(f"| {i} | {o['category']} | {o['title']} | {o['evidence']} | {_impact(o)} "
                     f"| {o['route']} | {o['ref']} |")
    lines += ["", "## 3. Disparadores (BACKLOG T145) y salud de datos", "",
              "| Disparador | Valor | Umbral | ¿Saltó? | Acción |", "|---|---|---|---|---|"]
    for t in a["triggers"]:
        v = "sin medir" if t["value"] is None else f"{t['value']:.4g}"
        state = "**SÍ**" if t["fired"] else ("cerca" if t.get("near") else "no")
        lines.append(f"| {t['text']} | {v} | {t['threshold']} | {state} | {t['action']} |")
    c = a.get("calibration") or {}
    if c.get("n_evaluated"):
        d = c.get("directional") or {}
        lines += ["", f"**Calibración BTCUSDT {c.get('tf', '1h')}** (`/v2/calibration`): "
                  f"{c['n_evaluated']} pronósticos (efectiva ≈{c.get('n_effective', 0):.0f}), "
                  f"Brier skill {c.get('brier_skill', 0):+.3f}, acierto direccional "
                  f"{d.get('accuracy', 0):.1%}, ECE {c.get('ece', 0):.3f}."]
    lines += ["", "## 4. Cambios desde la auditoría anterior", ""]
    d = a["deltas"]
    if not d.get("previous"):
        lines.append("Primera auditoría: es la línea base.")
    else:
        lines.append(f"Anterior: {d['previous']}.")
        lines += [f"- `{k}`: {m['prev']:.4g} → {m['cur']:.4g} ({m['delta']:+.4g})"
                  for k, m in d["metrics"].items()]
        lines += [f"- Oportunidades nuevas: {', '.join(d['new']) or 'ninguna'}; resueltas: "
                  f"{', '.join(d['gone']) or 'ninguna'}; disparadores nuevos: "
                  f"{', '.join(d['triggers_new']) or 'ninguno'}."]
    return "\n".join(lines) + "\n"


def console(a: dict) -> str:
    """Lo mínimo que la skill necesita leer (≈ 25 líneas)."""
    s = a["book"]["all"]
    out = [f"AUDITORÍA {a['generated_at']} · SIMULADO · n={s.get('n', 0)}"]
    if s.get("n"):
        out.append(f"E[R] {_r(s['e_r'])} [{_r(s['e_r_ci'][0])},{_r(s['e_r_ci'][1])}] · bruto "
                   f"{_r(s.get('gross_r'))} · costo {_r(s.get('cost_r'))} · acierto "
                   f"{_p(s['win_rate'])}/eq {_p(s.get('breakeven_win_rate'))} · PnL "
                   f"{s['pnl_usdt']:+.0f}")
    l7 = a["book"]["last7"]
    if l7.get("n"):
        out.append(f"7 d: n={l7['n']} E[R] {_r(l7['e_r'])} costo {_r(l7.get('cost_r'))}")
    out.append("OPORTUNIDADES:")
    out += [f" {i}. [{o['category']}] {o['title']} — {_impact(o)} — vía: {o['route']} ({o['ref']})"
            for i, o in enumerate(a["opportunities"], 1)]
    fired = [t for t in a["triggers"] if t["fired"]]
    near = [t for t in a["triggers"] if t.get("near")]
    out.append("DISPARADORES: " + (", ".join(f"{t['id']}={t['value']:.4g}" for t in fired)
                                   if fired else "ninguno")
               + (" · cerca: " + ", ".join(f"{t['id']}={t['value']:.4g}/{t['threshold']}"
                                          for t in near) if near else ""))
    d = a["deltas"]
    if d.get("previous"):
        ch = [f"{k} {m['delta']:+.3g}" for k, m in d["metrics"].items() if m["delta"]]
        out.append(f"DESDE {d['previous'][:10]}: " + ("; ".join(ch) or "sin cambios"))
        out.append(f" nuevas: {d['new'] or '—'} · resueltas: {d['gone'] or '—'}")
    else:
        out.append("PRIMERA AUDITORÍA (línea base)")
    out.append(f"INFORME: {a['paths']['md']}")
    return "\n".join(out)
