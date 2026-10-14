"""Render y escritura del informe semanal/final (JSON + Markdown en `reports/operation/`)."""

from __future__ import annotations

import json
import time
from pathlib import Path


def _d(t: int | None) -> str:
    return "—" if t is None else time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(t / 1000))


def _f(x, fmt: str = "{:+.2f}") -> str:
    return "—" if x is None else fmt.format(x)


def render_md(rep: dict) -> str:
    p, eq, acc = rep["period"], rep["equity"], rep["acceptance"]
    lines = [
        f"# Informe de operación — {p['label']}",
        "",
        f"**Modo: {rep['mode']}** (sin dinero real). Periodo {_d(p['from'])} → {_d(p['to'])}; "
        f"semanas operadas {p['weeks_operated']}. Generado {_d(rep['generated_at'])}.",
        "",
        f"> {acc['note']}",
        "",
        "## Resultados",
        "",
        "| Símbolo | Operaciones | Con resultado | R medio neto | IC95 % | Acierto | R total |",
        "|---|---|---|---|---|---|---|",
    ]
    for s, st in {**rep["trades"], "TOTAL": rep["all_trades"]}.items():
        ci = st.get("ci95")
        lines.append(
            f"| {s} | {st['n']} | {st['n_with_result']} | {_f(st.get('mean_r'))} | "
            f"{'—' if not ci else f'{ci[0]:+.2f} … {ci[1]:+.2f}'} | "
            f"{_f(st.get('win_rate'), '{:.0%}')} | {_f(st.get('total_r'))} |")
    lines += ["", f"Capital: {_f(eq.get('start'), '{:,.2f}')} → {_f(eq.get('end'), '{:,.2f}')} "
              f"USDT ({_f(eq.get('return'), '{:+.2%}')}), drawdown máx. "
              f"{_f(eq.get('max_drawdown'), '{:.2%}')}. R neto de comisión estimada, sin funding.",
              "", "## Comparación con el backtest", ""]
    for s, b in rep["backtest"].items():
        lines.append(f"- {s}: backtest {b['n_trades']} operaciones en {b['weeks']:.0f} semanas "
                     f"({_f(b['trades_per_week'], '{:.1f}')}/semana), esperanza "
                     f"{_f(b['expectancy_r'])} R, DD máx. {b['max_drawdown']:.0%}. "
                     f"Fuente: {b['source']}.")
    if not rep["backtest"]:
        lines.append("- Sin resultados de backtest disponibles (falta edge_results.json).")
    lines += ["", "### Desviaciones", ""] + [f"- {x}" for x in rep["deviations"] or ["—"]]
    lines += ["", "## Calibración de escenarios", ""]
    for s, c in rep["calibration"].items():
        cov = c.get("coverage", {})
        lines.append(f"- {s}: {c.get('n_evaluated', 0)} pronósticos evaluados "
                     f"({c.get('n_pending', 0)} pendientes); Brier skill "
                     f"{_f(c.get('brier_skill'), '{:+.1%}')}, cobertura 80 % "
                     f"{_f(cov.get('80', {}).get('terminal'), '{:.0%}')}.")
        lines += [f"  - {v}" for v in c.get("verdict", [])]
    inc, risk = rep["incidents"], rep["risk"]
    lines += ["", "## Incidentes", "",
              f"{inc['n']} alertas: " + (", ".join(f"{k} {v}" for k, v in inc["by_kind"].items())
                                         or "ninguna") + ".",
              f"Reconciliación sin resolver: {', '.join(inc['recon_unresolved']) or 'ninguna'}.",
              ""]
    lines += [f"- {_d(a['t'])} · {a['level']} · {a['title']}: {a['detail']}"
              for a in inc["list"][:30]]
    lines += ["", "## Riesgo", "",
              f"{risk['n_decisions']} decisiones registradas, {risk['n_vetoed']} vetadas. "
              "Motivos más frecuentes: " +
              (", ".join(f"{r} ({n})" for r, n in risk["top_reasons"]) or "—") + "."]
    return "\n".join(lines) + "\n"


def write(rep: dict, out_dir: Path, name: str | None = None) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = name or f"semana_{rep['period']['label'].split()[0]}"
    j, m = out_dir / f"{stem}.json", out_dir / f"{stem}.md"
    j.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    m.write_text(render_md(rep), encoding="utf-8")
    return j, m
