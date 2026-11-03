"""Informe de la cota del oráculo de M4 (T133, entregable 0). Puro: del dict al markdown."""

from __future__ import annotations

NA = "—"


def _n(x, k: int = 4) -> str:
    return NA if x is None else (f"{x:+.{k}f}" if isinstance(x, float) else str(x))


def _ok(v) -> str:
    return "sí" if v is True else "**NO**" if v is False else NA


def _metrics_table(mets: dict) -> list[str]:
    out = ["| Serie | n | Acierto | E[R] | Gan. media | Pérd. media | Cociente | PF | DD máx. R | "
           "CVaR 95 % |", "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for k, m in mets.items():
        wr = m.get("win_rate")
        out.append(f"| `{k}` | {m.get('n', 0)} | {NA if wr is None else f'{wr:.1%}'} | "
                   f"{_n(m.get('expectancy_r'))} | {_n(m.get('avg_win_r'), 3)} | "
                   f"{_n(m.get('avg_loss_r'), 3)} | {_n(m.get('win_loss_ratio'), 2)} | "
                   f"{_n(m.get('pf'), 3)} | {_n(m.get('max_dd_r'), 0)} | "
                   f"{_n(m.get('cvar95_r'))} |")
    return out


def _checks_table(name: str, bases: dict) -> list[str]:
    out = [f"### `{name}`", "",
           "| Base | ΔE[R] | IC 95 % | 1 (Δ e IC) | 2 (cociente y PF) | 3 (DD y CVaR) | "
           "¿cumple 1–3? |", "|---|--:|---|---|---|---|---|"]
    for b, c in bases.items():
        ci = c.get("ci") or [None, None]
        ci_s = NA if ci[0] is None or ci[0] != ci[0] else f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"
        out.append(f"| `{b}` | {_n(c.get('delta_expectancy_r'))} | {ci_s} | "
                   f"{_ok(c.get('c1_delta_positivo'))} | {_ok(c.get('c2_cociente_y_pf'))} | "
                   f"{_ok(c.get('c3_dd_y_cvar'))} | {_ok(c.get('cumple_1_a_3'))} |")
    out.append("")
    for b, c in bases.items():
        d = c.get("detalle", {})
        out.append(f"- Frente a `{b}`: cociente {_n(d.get('win_loss_ratio'), 2)} (exige ≥ 0,50) · "
                   f"PF {_n(d.get('pf'), 3)} (exige ≥ {_n(d.get('pf_exigido'), 3)}) · "
                   f"DD {_n(d.get('max_dd_r'), 0)} R (permite ≤ "
                   f"{_n(d.get('max_dd_permitido'), 0)}) · CVaR {_n(d.get('cvar95_r'))} "
                   f"(base {_n(d.get('cvar95_base'))}).")
    return out + [""]


def render(res: dict) -> str:
    m, w = res["meta"], res["window"]
    out = [f"# T133 · entregable 0 — cota del oráculo de M4 ({m['symbol']})", "",
           f"**Modo: SIMULADO.** Pre-registro `{m['prereg']}`, huella "
           f"`{m['prereg_sha256'][:16]}…`. Generado el {m['built']} desde la copia "
           f"`{m['data']}` (commit `{m['commit']}`), {m['fine_bars']} velas de 1 min.", "",
           f"Ventana **{w['from']} → {w['to']}**, {w['folds']} pliegues, embargo "
           f"{w['embargo_hours']:g} h. {res['bench']['ideas']} ideas, "
           f"{res['bench']['paired']} emparejadas; las cifras son de los tramos de **prueba** "
           f"(purga y embargo de T131 incluidos).", "",
           "## Veredicto", "", f"> {res['verdict']}", "",
           "## Qué es cada cota", "",
           "- **`M4_oraculo`** — la cota que pre-registra E6: con la etiqueta **ex post** del día "
           "se toma M0 en los días laterales y M1 en los de tendencia. Es información que no se "
           "conoce al entrar, así que marca el **techo de un selector de régimen perfecto**.",
           "- **`M4_envolvente`** — contexto, no cota: en cada entrada toma la **mejor de las dos "
           "salidas** sabiendo ya cómo acabó. No es un selector de régimen (acierta operación a "
           "operación, no día a día), así que cumplir los criterios con ella **no prueba nada**; "
           "se publica para que se vea cuánta información futura hace falta para que estas "
           "entradas sean rentables.", "",
           f"Reparto de los días: {res['day_counts']}.",
           f"Mapa declarado del oráculo: {res['policy_by_day']}.",
           f"Veces que la envolvente eligió cada salida: {res['envelope_wins']}.", "",
           "## Cifras", ""]
    out += _metrics_table(res["metrics"])
    out += ["", "## Criterios 1–3 de §5.4", ""]
    for name, bases in res["checks"].items():
        out += _checks_table(name, bases)
    out += ["## Lo que esto NO dice", "",
            "- No dice que el régimen sea impredecible: dice que **aunque se predijera perfecto**, "
            "elegir entre M0 y M1 por el régimen del día no alcanza los criterios de adopción.",
            "- No afecta a M2, M3, M5, M8 ni S1: son salidas que cambian la **geometría** del "
            "stop, no un selector entre las dos de hoy. Eso es T132.",
            "- No cambia nada en vivo: la escalera sigue siendo la salida vigente (◆1 de T129).",
            ""]
    return "\n".join(out) + "\n"
