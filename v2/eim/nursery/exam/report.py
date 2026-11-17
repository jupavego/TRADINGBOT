"""Informe del examen físico (T169): JSON + Markdown, **sin ninguna columna de rendimiento**. Puro.

`check_no_performance` recorre todas las claves del JSON y todas las cabeceras de tabla del
Markdown y falla si alguna nombra rendimiento (R neto, acierto, PF, P&L, bruto, gemelos, Sharpe,
saldo…). El informe se comprueba antes de escribirse, y una prueba comprueba que la guarda salta.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

FORBIDDEN = frozenset({
    "net", "neto", "neta", "pnl", "gross", "bruto", "bruta", "acierto", "aciertos", "win", "wins",
    "winrate", "hit", "hits", "pf", "profit", "factor", "beneficio", "ganancia", "ganancias",
    "perdida", "loss", "twin", "twins", "gemelo", "gemelos", "d", "sharpe", "sortino", "equity",
    "balance", "saldo", "drawdown", "rendimiento", "return", "returns", "retorno", "expectancy",
    "esperanza", "payoff", "markout", "tp", "sl",
})
_TOKEN = re.compile(r"[a-záéíóúñ]+|\d+", re.IGNORECASE)


def tokens(name: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(name.replace("_", " "))}


def _keys(obj: object) -> Iterator[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def md_headers(md: str) -> list[str]:
    """Cabeceras de las tablas Markdown (la fila seguida de una línea `|---|`)."""
    lines = md.splitlines()
    out = []
    for a, b in zip(lines, lines[1:], strict=False):
        if a.lstrip().startswith("|") and re.match(r"^\s*\|[\s:|-]+\|\s*$", b):
            out += [c.strip() for c in a.strip().strip("|").split("|")]
    return out


def check_no_performance(data: dict, md: str) -> None:
    """Falla si el informe nombra rendimiento en una clave o en una cabecera de tabla."""
    bad = sorted({k for k in _keys(data) if tokens(k) & FORBIDDEN} |
                 {h for h in md_headers(md) if tokens(h) & FORBIDDEN})
    if bad:
        raise ValueError(f"el informe del examen físico muestra rendimiento: {bad}")


def _f(x: object, nd: int = 2, pct: bool = False) -> str:
    if x is None:
        return "—"
    if isinstance(x, (int, float)):
        return f"{x:.0%}" if pct else f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")
    return str(x)


def _spread(xs: list[float]) -> str:
    if not xs:
        return "—"
    s = sorted(xs)
    return " · ".join(_f(x, 1) for x in (s[0], s[len(s) // 2], s[-1]))


def _band(v: dict) -> str:
    return v["band"] + (f" (declarada {v['declared_band']})" if v["reassigned"] else "")


def _state(v: dict) -> str:
    if v["discarded"]:
        return "**descartado**"
    return "sin opción a primer equipo" if v["no_first_team"] else "sigue"


def _declared(v: dict) -> str:
    kept = v.get("kept_with_declared_band")
    if kept is None:
        return "—"
    return f"seguiría ({v['declared_band']})" if kept else f"también cae ({v['declared_band']})"


def _days(v: dict, key: str) -> str:
    d = (v.get("days_to_verdict") or {}).get(key) or {}
    return _f(d.get("days"), 0)


def to_markdown(data: dict) -> str:
    rows = data["prospects"]
    head = [
        f"# {data.get('task', 'T169')} — Examen físico de los prospectos en la historia", "",
        "**Modo: SIMULADO.** Sin rendimiento: este informe no calcula ni muestra R neto, acierto "
        "ni PF (regla 5 de la nota de T167 §3). La historia no asciende a nadie; solo descarta "
        "por razones mecánicas, con los umbrales fijados en `PLAN/T169.md` antes de correr.", "",
        *data["summary_lines"], "",
        "## Prospectos con historia", "",
        "«Operaciones» son órdenes llenadas (una a la vez); «No llenadas», las límite que "
        "vencieron sin llenarse; «Por bloque», la cadencia mínima · mediana · máxima de los "
        "bloques de 28 días; «En posición», la fracción de días con posición abierta.", "",
        "| Prospecto | Marco | Banda | Ideas | Operaciones | No llenadas | Al mes "
        "| Por bloque | Costo medio (R) | Tenencia mediana (h) | En posición (días) "
        "| Rotación (× capital/mes) | Estado |",
        "|---|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|",
    ]
    for r in rows:
        ph, v = r["physics"], r["verdict"]
        head.append(f"| `{r['id']}` | {r['timeframe']} | {_band(v)} | {ph['ideas']} | "
                    f"{ph['filled']} | {ph['unfilled']} | {_f(ph['ops_month'], 1)} | "
                    f"{_spread(ph['ops_month_by_block'])} | {_f(ph['cost_r_mean'], 3)} | "
                    f"{_f(ph['hold_h_median'], 1)} | {_f(ph['pos_days_frac'], pct=True)} | "
                    f"{_f(ph['turnover_month'], 1)} | {_state(v)} |")
    head += ["", "## Descartes mecánicos", "",
             "Manda la banda medida por la tenencia (`PLAN/T169.md`). «Con la banda declarada» "
             "dice si el prospecto seguiría sin esa reasignación, para que se vea de qué depende "
             "cada descarte.", "",
             "| Prospecto | Motivo | Al borde | Con la banda declarada |", "|---|---|---|---|"]
    for r in rows:
        v = r["verdict"]
        if v["discarded"]:
            head.append(f"| `{r['id']}` | {'; '.join(v['reasons'])} | "
                        f"{', '.join(v['borderline']) or '—'} | {_declared(v)} |")
    head += ["", "## Días hasta el veredicto (supervivientes)", "",
             "σ = 1 R por operación **supuesta**; μ en R por operación; z = 1,645 (α 0,05) y "
             "z ≈ 3,09 (α 0,05/50, la familia). Operaciones necesarias: " +
             "; ".join(f"μ +{_f(m['mu_r'])} R con z {_f(m['z'])} → {m['ops']}"
                       for m in data["mintrl"]) + ".", "",
             "| Prospecto | Banda | Esperadas en 6 meses | +0,10 R | +0,10 R familia | +0,25 R "
             "| +0,25 R familia | Al borde |",
             "|---|---|--:|--:|--:|--:|--:|---|"]
    for r in rows:
        v = r["verdict"]
        if not v["discarded"]:
            head.append(f"| `{r['id']}` | {_band(v)} | {_f(v['expected_in_term'], 0)} | "
                        f"{_days(v, 'mu_0_10_alfa_0_05')} | {_days(v, 'mu_0_10_familia')} | "
                        f"{_days(v, 'mu_0_25_alfa_0_05')} | {_days(v, 'mu_0_25_familia')} | "
                        f"{', '.join(v['borderline']) or '—'} |")
    head += ["", "## Cobertura de las variables declaradas", "",
             "«Agente con datos»: contextos en que el agente no salió `no_data`. «Con valor»: "
             "contextos con la variable presente; en las variables de lista (`[]`), con al menos "
             "un elemento, así que una lista vacía (p. ej., ningún acierto de `literature` en esa "
             "vela) cuenta como sin valor aunque no sea un dato perdido.", "",
             "| Prospecto | Agente con datos | Variable | Con valor |", "|---|--:|---|--:|"]
    for r in rows:
        cov = r["physics"]["coverage"]
        for c in cov["variables"]:
            head.append(f"| `{r['id']}` | {_f(cov['agent_ok'], pct=True)} | `{c['variable']}` | "
                        f"{_f(c['with_value'], pct=True)} |")
    head += ["", *data["checks_lines"], "", "## Sin historia (se examinan hacia adelante)", "",
             "| Prospecto | Por qué |", "|---|---|"]
    head += [f"| `{k}` | {why} |" for k, why in sorted(data["without_history"].items())]
    return "\n".join(head) + "\n"
