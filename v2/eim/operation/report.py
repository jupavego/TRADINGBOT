"""Render y escritura del informe semanal/final (JSON + Markdown en `reports/operation/`).

Aquí vive también lo que el informe necesita recoger de fuera (la tarifa del simulador y el
resumen de calidad de la captura HFT): es material del informe, no del servicio que lo dispara.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from pathlib import Path

from eim.data.collectors import hft_ops
from eim.execution.sim_broker import SimBroker
from eim.operation.report_costs import cost_lines


def fee_rate(svc) -> float:
    """Tarifa con la que el informe mide el R neto; la del simulador si hay uno."""
    return svc.broker.fee_rate if svc and isinstance(svc.broker, SimBroker) else 0.0005


def hft_qc(data_dir: Path, symbols: Iterable[str], t0: int, t1: int) -> dict[str, dict]:
    """Resumen del control de calidad de la captura HFT (T78) por símbolo, si la hay."""
    out: dict[str, dict] = {}
    for s in symbols:
        try:
            if (q := hft_ops.week_summary(data_dir, s, t0, t1)) is not None:
                out[s] = q
        except Exception as e:  # noqa: BLE001 - un QC ilegible no impide el informe
            out[s] = {"error": f"{type(e).__name__}: {e}"}
    return out


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
    ]
    lines += official_lines(rep)
    lines += [
        "## Vista: corrida de operación (NO es la cifra oficial)",
        "",
        f"{(rep.get('operation_view') or {}).get('label', 'carril de ejecución del servicio')}.",
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
                     + _usage_lines(rep.get("usage") or [])
                     + cost_lines(rep.get("paper_costs") or {})) + "\n"


def official_lines(rep: dict) -> list[str]:
    """Resultados del universo OFICIAL (T144), con el universo y el recuento en la propia tabla.

    Antes el informe decía «4 operaciones» sin decir de dónde salían. Aquí se ve cuántas existen
    en el tramo, cuántas cuentan, por qué quedan fuera las demás y qué `retro` se excluyeron.
    """
    off = rep.get("official")
    dec = (rep.get("universe") or {})
    if not off:
        return ["## Resultados (universo oficial)", "",
                "Informe compuesto sin el libro de perfiles: **sin cifra oficial** (no se "
                "sustituye por la del carril de operación).", ""]
    t = off.get("tally", {})
    out = ["## Resultados (universo oficial)", "",
           f"**Universo:** {dec.get('label', off.get('declaration', {}).get('label', '—'))}. "
           f"{dec.get('decided', '')}", ""]
    if not off.get("available", True):
        return out + [off.get("note", "sin libro disponible"), ""]
    out += ["| Alcance | Operaciones en el tramo | Cuentan | R medio | IC95 % | Acierto "
            "| R total | PnL (USDT) |", "|---|--:|--:|--:|--:|--:|--:|--:|"]
    ci = off.get("ci95")
    out.append(
        f"| **TOTAL (universo oficial)** | {t.get('n_total', 0)} | **{off.get('n', 0)}** | "
        f"{_f(off.get('mean_r'))} | {'—' if not ci else f'{ci[0]:+.2f} … {ci[1]:+.2f}'} | "
        f"{_f(off.get('win_rate'), '{:.0%}')} | {_f(off.get('total_r'))} | "
        f"{_f(off.get('pnl_usdt'), '{:+,.2f}')} |")
    for pid, b in (off.get("by_profile") or {}).items():
        out.append(f"| {pid} | — | {b['n']} | {_f(b.get('mean_r'))} | — | "
                   f"{_f(b.get('win_rate'), '{:.0%}')} | {_f(b.get('total_r'))} | "
                   f"{_f(b.get('pnl_usdt'), '{:+,.2f}')} |")
    why = t.get("excluded_why", {})
    fuera = t.get("n_total", 0) - t.get("n_counted", 0)
    out += ["", f"**Quedan fuera {fuera} de {t.get('n_total', 0)}:** " + (
        "; ".join(f"{k} {n} ({why.get(k, k)})" for k, n in (t.get("excluded") or {}).items())
        or "ninguna") + "."]
    dd = off.get("dd") or {}
    out.append(f"Drawdown {_f(dd.get('usdt'), '{:,.2f}')} USDT "
               f"({_f(dd.get('pct'), '{:.2%}')}); base: {dd.get('base', '—')}.")
    out.append(f"Entradas de suelo incluidas (`floor_trade`): {off.get('floor_trades', 0)} de "
               f"{off.get('n', 0)}; las abrió el mínimo de apertura, no una señal.")
    out.append("Símbolos dentro de la cifra oficial: "
               + (", ".join(off.get("symbols") or []) or "ninguno") + ".")
    out.append(f"Huella de lo contado: `{off.get('counted_digest', '—')}` — identifica exactamente "
               "qué operaciones entraron, para cuadrarlo contra el libro "
               "(`GET /v2/paper/accounting`).")
    r = off.get("retro_excluded") or {}
    out.append(f"**`retro` excluidas: {r.get('n', 0)}** "
               f"(PnL que NO suma: {_f(r.get('pnl_excluded'), '{:+,.2f}')} USDT, "
               f"R {_f(r.get('total_r_excluded'))}): {r.get('why', '')}.")
    return out + [""]


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
        w = q.get("t78_window") or {}
        if w:
            falta = "CUMPLE" if w["passed"] else f"faltan {w['remaining_h']} h"
            att = w["attribution"]
            out.append(
                f"- {s}: **aceptación de T78 (ventana, T147): {w['best']['hours']} h de "
                f"{w['need_h']}** · {falta}; horas perdidas por causa nuestra "
                f"{att.get('nuestra', 0)}, ajena {att.get('ajena', 0)}.")
        out.append(
            f"- {s}: {q['hours_complete']}/{q['hours']} horas completas "
            f"({_f(q['pct_complete'], '{:.1%}')}), racha contigua más larga "
            f"{q['longest_complete_streak_h']} h (T126, informativa); verificaciones top-10 "
            f"con el snapshot REST "
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
        # T148: la cobertura es la medida de verdad, no las muestras contadas; si el registro
        # calló, se dice cuánto y cuándo, para que el día no se lea como si estuviera medido.
        ciego = (f" **sin registro {d['blind_s'] / 3600:.2f} h** ("
                 + ", ".join(f"{g['from'][11:16]}→{g['to'][11:16]} UTC" for g in d["gaps"][:3])
                 + ");") if d.get("gaps") else ""
        out.append(
            f"- {d['day']}: {d['samples']} muestras ({_f(d['coverage'], '{:.0%}')} del día);"
            f"{ciego} CPU "
            f"del equipo media {c['mean']:.0f} % (p95 {c['p95']:.0f} %, máx. {c['max']:.0f} % "
            f"a las {p['ts'][11:16]} UTC, sobre todo {p['top'] or '—'}); RAM libre mín. "
            f"{d['ram_free_min_mb'] / 1024:.1f} GB; EIM {d['eim_cpu_mean']:.1f} % de media"
            f"{_f(d.get('eim_cpu_median'), ', {:.1f} % en reposo')} "
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
