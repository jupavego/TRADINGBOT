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
    return "\n".join(lines + _distortion_lines(rep.get("distortions") or [])
                     + _hft_lines(rep.get("hft_qc") or {})
                     + _usage_lines(rep.get("usage") or [])) + "\n"


def _distortion_lines(known: list[dict]) -> list[str]:
    if not known:
        return []
    out = ["", "## Distorsiones conocidas de los libros", ""]
    for d in known:
        when = f"desde {_d(d['from'])}" + (f" hasta {_d(d['to'])}" if d["to"] else ", sin resolver")
        out.append(f"- **{d['title']}**, {when}. {d['detail']} Evidencia: `{d['ref']}`.")
    return out


def _hft_lines(hft: dict) -> list[str]:
    """Control de calidad de la captura HFT (T78): solo el resumen, los crudos no viajan."""
    out = ["", "## Captura HFT (calidad de datos)", ""]
    if not hft:
        return out + ["Sin captura HFT en el periodo (`micro_hft/`)."]
    for s, q in hft.items():
        if "error" in q:
            out.append(f"- {s}: resumen de QC ilegible ({q['error']}).")
            continue
        chk = q["checks"]
        out.append(
            f"- {s}: {q['hours_complete']}/{q['hours']} horas completas "
            f"({_f(q['pct_complete'], '{:.1%}')}), racha contigua más larga "
            f"{q['longest_complete_streak_h']} h; verificaciones top-10 con el snapshot REST "
            f"{chk['matched']}/{chk['comparable']} ({_f(chk['match_rate'], '{:.2%}')}); "
            f"huecos encontrados {q['holes_found']}, sin marcar {q['undetected']}; reinicios "
            f"{q['restarts']}; disco {_f(q['mb_per_day'], '{:.0f}')} MB/día "
            f"(30 días ≈ {_f(q['projection_30d_gb'], '{:.1f}')} GB).")
    return out


def _hours(hs: list[str]) -> str:
    return f" ({', '.join(hs)})" if hs else ""


def _usage_lines(days: list[dict]) -> list[str]:
    """Consumo del equipo (T127): ¿coincidieron las horas perdidas de la captura con el equipo
    saturado? Una hora perdida sin saturación ni hueco de registro apunta a otra causa."""
    out = ["", "## Consumo del equipo", ""]
    if not days:
        return out + ["Sin registro de consumo en el periodo (`usage/`)."]
    for d in days:
        if "error" in d:
            out.append(f"- Registro de consumo ilegible ({d['error']}).")
            continue
        h = d["hft"]
        hft = (f"captura HFT: {len(h['incomplete'])} de {h['hours']} horas incompletas"
               f"{_hours(h['incomplete'])}, {len(h['incomplete_saturated'])} con el equipo "
               f"saturado{_hours(h['incomplete_saturated'])} y "
               f"{len(h['incomplete_unlogged'])} sin registro{_hours(h['incomplete_unlogged'])}"
               if h["hours"] else "sin captura HFT")
        if not d["samples"]:
            out.append(f"- {d['day']}: sin registro de consumo; {hft}.")
            continue
        c, p = d["cpu"], d["peak"]
        roles = ", ".join(f"{k} {v:.1f}" for k, v in list(d["roles_cpu_mean"].items())[:4])
        out.append(
            f"- {d['day']}: {d['samples']} muestras ({_f(d['coverage'], '{:.0%}')} del día); CPU "
            f"del equipo media {c['mean']:.0f} % (p95 {c['p95']:.0f} %, máx. {c['max']:.0f} % "
            f"a las {p['ts'][11:16]} UTC, sobre todo {p['top'] or '—'}); RAM libre mín. "
            f"{d['ram_free_min_mb'] / 1024:.1f} GB; EIM {d['eim_cpu_mean']:.1f} % de media "
            f"({roles or '—'}). Horas saturadas: {', '.join(d['saturated_hours']) or 'ninguna'}; "
            f"{hft}.")
    return out


def write(rep: dict, out_dir: Path, name: str | None = None) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = name or f"semana_{rep['period']['label'].split()[0]}"
    j, m = out_dir / f"{stem}.json", out_dir / f"{stem}.md"
    j.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    m.write_text(render_md(rep), encoding="utf-8")
    return j, m
