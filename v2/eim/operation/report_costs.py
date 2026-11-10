"""Sección «Costo medido» del informe semanal (T143, entregable 4).

El costo vivido del libro simulado, por operación y acumulado, con su `source`. Antes había que
sacarlo a mano del `ledger.csv`; el diagnóstico de la fase 24 encontró que era mayor que toda la
pérdida neta, así que el informe lo trae siempre, aunque no haya operaciones.
"""

from __future__ import annotations

import time


def _n(x, fmt: str) -> str:
    return "—" if x is None else fmt.format(x)


def _row(label: str, b: dict) -> str:
    return (f"| {label} | {b['n']} | {_n(b['cost_usdt'], '{:,.2f}')} | "
            f"{_n(b['cost_bps_mean'], '{:.1f}')} | {_n(b['cost_r_mean'], '{:.3f}')} | "
            f"{_n(b['cost_r_median'], '{:.3f}')} | {_n(b['cost_r_sum'], '{:.2f}')} |")


def cost_lines(pc: dict) -> list[str]:
    out = ["", "## Costo medido (libro simulado)", ""]
    if not pc:
        return out + ["Sin datos del libro simulado en este informe."]
    if "error" in pc:
        return out + [f"No se pudo leer: {pc['error']}.", "", f"Fuente: {pc['source']}."]
    a = pc["all"]
    out += [f"Fuente: {pc['source']}.", ""]
    if not a["n"]:
        return out + ["Ninguna operación de perfil cerrada en el periodo."]
    out += ["| | Operaciones | Costo USDT | pb del nocional | R medio | R mediana | R acumulado |",
            "|---|--:|--:|--:|--:|--:|--:|", _row("**Todas**", a)]
    out += [_row(f"marco {k}", b) for k, b in pc["by_timeframe"].items()]
    out += [_row(f"entrada {k}", b) for k, b in pc["by_kind"].items()]
    if a["n_r"] < a["n"]:
        out += ["", f"{a['n'] - a['n_r']} de {a['n']} sin riesgo reconstruible (pnl o r en 0): "
                "cuentan en USDT, no en R."]
    out += ["", "Últimas operaciones:", ""]
    for c in pc["recent"]:
        t = time.strftime("%Y-%m-%d %H:%M", time.gmtime((c["exit_t"] or 0) / 1000))
        out.append(f"- {t} · {c['profile']} · {c['timeframe']} · {c['kind']}: "
                   f"{c['cost_usdt']:.2f} USDT · {_n(c['cost_bps'], '{:.1f}')} pb · "
                   f"{_n(c['cost_r'], '{:.3f}')} R")
    return out
