"""Informe de decisión de la puerta de validación (T49): payload de `/v2/validation` → Markdown.

Mismo espíritu que `reports/edge_gate.md`: criterios fijados antes, resultados contra cada uno,
veredicto por estrategia@marco@versión y, si ninguna pasa, qué criterio falla más a menudo.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from eim.validation.gate import OBSERVACION, RECHAZADA, VALIDADA

ORDER = {VALIDADA: 0, OBSERVACION: 1, RECHAZADA: 2}


def _d(t: int | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return "—" if not t else datetime.fromtimestamp(t / 1000, UTC).strftime(fmt)


def _f(x: float | None, fmt: str = "+.3f") -> str:
    return "—" if x is None else format(x, fmt)


def _ok(c: dict) -> str:
    return {True: "✔", False: "✘", None: "…"}[c["ok"]]


def _criteria(c: dict) -> list[str]:
    v1, v2, v3 = c["v1_data"], c["v2_expectancy"], c["v3_random"]
    v4, v5, v6, ng = c["v4_drawdown"], c["v5_stability"], c["v6_costs"], c["clear_negative"]
    rows = [
        ("V1", "Suficiencia de datos", f"≥ {v1['min_trades']} operaciones cerradas fuera de "
         f"muestra y ≥ {v1['min_regimes']} regímenes con ≥ {v1['min_per_regime']} cada uno"),
        ("V2", "Expectativa neta", f"R medio neto > 0 con IC{v2['level']:.0%} bootstrap por "
         f"bloques de día ({v2['boot_reps']} remuestreos) que excluye 0"),
        ("V3", "Contra el azar", f"Réplica con lado aleatorio (≥ {v3['min_reps']} réplicas, "
         f"{v3['reps_per_attempt']} × intentos): p unilateral < {v3['alpha']} tras Holm sobre "
         "todos los intentos registrados (también retirados)"),
        ("V4", "Drawdown", f"DD máximo ≤ {v4['max_dd']:.0%} con riesgo fijo de "
         f"{v4['risk_per_trade']:.0%} por operación"),
        ("V5", "Estabilidad", f"R medio > 0 en ≥ {v5['min_positive_frac']:.0%} de ventanas "
         f"disjuntas de {v5['window_days']} días (≥ {v5['min_windows']} ventanas con ≥ "
         f"{v5['window_min_trades']} op.) y tramo en vivo con ≥ {v5['live_min_trades']} op. y "
         "R medio > 0"),
        ("V6", "Costos", f"Costo medio (comisiones + deslizamiento + funding) ≤ "
         f"{v6['max_cost_r']} R por operación"),
    ]
    out = ["| ID | Criterio | Umbral |", "|---|---|---|"]
    out += [f"| {a} | {b} | {u} |" for a, b, u in rows]
    out += ["", f"Claramente negativa (en cualquier momento, con ≥ {ng['min_trades']} op.): "
            f"R medio + {ng['z']:g}·EE < 0 → RECHAZADA.", ""]
    out += [f"- {n}" for n in c.get("notes", [])]
    return out


def _windows(p: dict) -> list[str]:
    by: dict[str, set] = defaultdict(set)
    nver: dict[str, int] = defaultdict(int)
    for v in p["versions"]:
        nver[v["origin"]] += 1
        for w in v["windows"]:
            by[v["origin"]].add((w["from"], w["to"], w["symbol"] or "todos", w["note"]))
    out = ["| Origen | Versiones | Ventana de ajuste (UTC) | Símbolos | Nota |",
           "|---|---|---|---|---|"]
    for o in sorted(nver):
        for a, b, s, n in sorted(by[o]) or [(None, None, "—", "")]:
            out.append(f"| {o} | {nver[o]} | {_d(a)} → {_d(b)} | {s} | {n} |")
    return out


def _coverage(p: dict) -> list[str]:
    cov = p.get("coverage") or {}
    out = ["| Marco | Contextos | Desde | Hasta | Orígenes |", "|---|---|---|---|---|"]
    for tf, x in (cov.get("timeframes") or {}).items():
        org = ", ".join(f"{k} {n}" for k, n in sorted(x.get("origins", {}).items()))
        out.append(f"| {tf} | {x['contexts']} | {_d(x['from'])} | {_d(x['to'])} | {org} |")
    return out


def _oos_by_tf(vs: list[dict]) -> list[str]:
    g: dict[str, list[dict]] = defaultdict(list)
    for v in vs:
        g[v["timeframe"]].append(v)
    out = ["| Marco | Versiones | Op. fuera de muestra | Excluidas por ajuste | Con ≥ 100 | "
           "Primera decisión FdM | Último cierre FdM |", "|---|---|---|---|---|---|---|"]
    for tf, xs in sorted(g.items()):
        fr = [x["oos"]["from"] for x in xs if x["oos"]["from"]]
        to = [x["oos"]["to"] for x in xs if x["oos"]["to"]]
        out.append(f"| {tf} | {len(xs)} | {sum(x['n_oos'] for x in xs)} | "
                   f"{sum(x['oos']['excluded_in_windows'] for x in xs)} | "
                   f"{sum(x['n_oos'] >= 100 for x in xs)} | {_d(min(fr) if fr else None)} | "
                   f"{_d(max(to) if to else None)} |")
    return out


def _row(v: dict) -> str:
    ck = {c["id"]: c for c in v["checks"]}
    ci = ck["V2"]["value"]["ci"]
    v3, v5 = ck["V3"]["value"], ck["V5"]["value"]
    return (f"| `{v['id']}` | **{v['verdict']}** | {v['n_oos']} | {v['n_live']} | "
            f"{_f(v['mean_r'])} [{_f(ci[0])}, {_f(ci[1])}] | {_f(v3['p'], '.4f')} → "
            f"{_f(v3['p_holm'], '.4f')} | {_f(ck['V4']['value']['max_dd'], '.1%')} | "
            f"{v5['positive']}/{v5['windows']} | {_f(ck['V6']['value']['cost_r'], '.3f')} | "
            + " ".join(f"{c['id']}{_ok(c)}" for c in v["checks"]) + f" | {v['reason']} |")


def _extras(vs: list[dict]) -> list[str]:
    out = ["| Versión | Acierto | PF | MFE / MAE (R) | DSR (intentos) | Retorno al 1 % | "
           "Comprar y mantener (mismo tramo) |", "|---|---|---|---|---|---|---|"]
    for v in vs:
        e = v["extras"]
        if not v["n_oos"]:
            continue
        out.append(f"| `{v['id']}` | {_f(e['win_rate'], '.1%')} | {_f(e['pf'], '.2f')} | "
                   f"{_f(e['mfe_r'], '.2f')} / {_f(e['mae_r'], '.2f')} | {_f(e['dsr'], '.3f')} "
                   f"| {_f(e['ret_1pct'], '+.1%')} | {_f(e['buy_hold'], '+.1%')} |")
    return out


def render(p: dict, notes: list[str] | None = None, commit: str = "") -> str:
    crit, vs = p["criteria"], p["verdicts"]
    vs = sorted(vs, key=lambda v: (ORDER[v["verdict"]], -(v["mean_r"] or -9), v["id"]))
    s = p["summary"]
    cnt = s["counts"]
    head = [f"# T49 — Puerta de validación por estrategia (`{crit['version']}`)", "",
            f"Modo: **SIMULADO** · símbolo {p['symbol']} · datos hasta {_d(p['asof'])} UTC · "
            f"calculado {_d(p['computed'])} UTC · intentos registrados: {p['attempts']}.",
            f"Criterios `{crit['version']}` (SHA-256 `{crit['sha256'][:16]}…`)"
            + (f", fijados en el commit `{commit}` antes del primer cálculo con datos reales."
               if commit else "."), "", "## 1. Veredicto", ""]
    if s["validated"]:
        head.append(f"**{len(s['validated'])} validada(s):** "
                    + ", ".join(f"`{x}`" for x in s["validated"]) + ".")
    else:
        head.append("**Ninguna estrategia validada.** Es un resultado válido: ninguna "
                    "`estrategia@marco@versión` tiene hoy evidencia fuera de muestra suficiente.")
    head += ["", f"De {len(vs)} versiones vigentes: {cnt.get(VALIDADA, 0)} VALIDADA · "
             f"{cnt.get(OBSERVACION, 0)} EN OBSERVACIÓN · {cnt.get(RECHAZADA, 0)} RECHAZADA.", ""]
    if s["most_failed"]:
        head += ["Criterios que más fallan (insumo del ciclo de mejora):", ""]
        head += [f"- {m['id']} {m['name']}: {m['n']} versiones" for m in s["most_failed"]]
        head.append("")
    body = ["## 2. Criterios (fijados antes de calcular)", "", *_criteria(crit), "",
            "## 3. Datos y muestra fuera de muestra", "", "Contextos del bróker simulado:", "",
            *_coverage(p), "", "Ventanas de ajuste registradas (se excluyen de la evidencia de "
            "la versión y de sus descendientes):", "", *_windows(p), "",
            "Historial fuera de muestra disponible por marco:", "", *_oos_by_tf(vs), "",
            "## 4. Resultados por estrategia@marco@versión", "",
            "| Versión | Veredicto | FdM | Vivo | R medio [IC95 %] | p → Holm | DD | Ventanas + "
            "| Costo R | V1–V6 | Motivo |", "|---|---|---|---|---|---|---|---|---|---|---|",
            *[_row(v) for v in vs], "", "✔ cumple · ✘ falla · … pendiente (sin datos para "
            "juzgarlo).", "", "## 5. Informativo (no son criterios)", "", *_extras(vs), ""]
    if notes:
        body += ["## 6. Notas y riesgos conocidos", "", *[f"- {n}" for n in notes], ""]
    return "\n".join(head + body)


def write(p: dict, out_dir: Path, notes: list[str] | None = None, commit: str = ""
          ) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{p['criteria']['version']}_{_d(p['asof'], '%Y-%m-%d')}"
    md, js = out_dir / f"{stem}.md", out_dir / f"{stem}.json"
    md.write_text(render(p, notes, commit), encoding="utf-8")
    js.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    return md, js
