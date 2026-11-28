"""T222: lo que se publica al lado del veredicto y NO decide (§3.2, §3.3 y §3.8 del pre-registro).

Por perfil, bruto, USDT, `r × peso`, el error típico por bootstrap de días (semilla 222), la
sensibilidad con solo lo vivido en este equipo (T196) y los rechazos por «cupo lleno» de 1 h y 4 h
mientras el perfil tenía abierta una posición de 15 m. Puro: sin red ni disco.
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime

from eim.analytics import tf_retire as tr
from eim.paper.cost_ledger import trade_cost

BOOT_REPS, BOOT_SEED = 10_000, 222
LOCAL = "local"


def _mean(xs: Sequence[float]) -> float | None:
    return statistics.fmean(xs) if xs else None


def _group(rows: Sequence[Mapping]) -> dict:
    r = [tr.r_of(x) for x in rows]
    cost = [c for x in rows if (c := trade_cost(dict(x))["cost_r"]) is not None]
    gross = [tr.r_of(x) + c for x in rows if (c := trade_cost(dict(x))["cost_r"]) is not None]
    w = [tr.r_of(x) * (tr.num(x.get("weight")) or 0.0) for x in rows]
    return {"n": len(rows), "net_r": _mean(r), "cost_r": _mean(cost), "gross_r": _mean(gross),
            "r_x_weight": _mean(w), "pnl_usdt": sum(tr.num(x.get("pnl_usdt")) or 0.0 for x in rows)}


def boot_se(kept: Sequence[Mapping], reps: int = BOOT_REPS, seed: int = BOOT_SEED) -> dict:
    """Error típico de μ̂₁₅ y de Δ̂ remuestreando días enteros de cierre (descriptivo)."""
    by: dict[int, list[float]] = {}
    for r in kept:
        g = by.setdefault(tr.day_of(r), [0.0, 0, 0.0, 0])
        k = 0 if r.get("timeframe") == tr.TF else 2
        g[k] += tr.r_of(r)
        g[k + 1] += 1
    days = list(by.values())
    if len(days) < 2:
        return {"reps": reps, "seed": seed, "se15": None, "se_delta": None}
    rng = random.Random(seed)
    m15, md = [], []
    for _ in range(reps):
        s = [0.0, 0, 0.0, 0]
        for _k in range(len(days)):
            g = days[rng.randrange(len(days))]
            for i in range(4):
                s[i] += g[i]
        if s[1]:
            m15.append(s[0] / s[1])
            if s[3]:
                md.append(s[0] / s[1] - s[2] / s[3])
    return {"reps": reps, "seed": seed,
            "se15": statistics.stdev(m15) if len(m15) > 1 else None,
            "se_delta": statistics.stdev(md) if len(md) > 1 else None}


def cupo_blocked(events: Iterable[Mapping], rows: Iterable[Mapping], look: int) -> dict:
    """Rechazos «cupo» de ideas vivas de 1 h y 4 h con una posición de 15 m abierta en ese perfil.

    `events` son los de la bitácora de cada perfil (`GET /v2/paper/journal`, `cat=rechazada`);
    `rows`, el libro fijo de perfiles (todas sus filas de 15 m, cuenten o no).
    """
    t1 = tr.LOOKS_MS[look]
    spans: dict[str, list[tuple[float, float]]] = {}
    for r in rows:
        if r.get("scope") != "perfil" or r.get("timeframe") != tr.TF:
            continue
        start = tr.num(r.get("fill_t")) or tr.num(r.get("opened_t"))
        if start is None:
            continue
        end = tr.num(r.get("exit_t")) or t1
        spans.setdefault(str(r.get("profile")), []).append((start, end))
    total = hit = 0
    by_profile: dict[str, dict] = {}
    for e in events:
        t = tr.num(e.get("t"))
        if (e.get("cat") != "rechazada" or e.get("code") != "cupo"
                or e.get("timeframe") not in tr.REST or e.get("origin") != "vivo"
                or t is None or not tr.T0_MS <= t < t1):
            continue
        pid = str(e.get("profile"))
        b = by_profile.setdefault(pid, {"cupo_1h4h": 0, "with_15m_open": 0})
        total += 1
        b["cupo_1h4h"] += 1
        if any(a <= t < z for a, z in spans.get(pid, ())):
            hit += 1
            b["with_15m_open"] += 1
    return {"cupo_1h4h": total, "with_15m_open": hit, "by_profile": by_profile}


def describe(rows: Sequence[Mapping], look: int, events: Iterable[Mapping] | None = None,
             machine_known: bool = False) -> dict:
    """Todo lo que acompaña al veredicto. `machine_known`: las filas traen `machine` (T196)."""
    kept = tr.measured(rows, look)
    k15 = [r for r in kept if r.get("timeframe") == tr.TF]
    rest = [r for r in kept if r.get("timeframe") != tr.TF]
    profiles = sorted({str(r.get("profile")) for r in k15})
    local = None
    if machine_known:
        loc = [r for r in kept if r.get("machine", LOCAL) == LOCAL]
        local = tr.estimate(loc).to_json()
    return {"tf15": _group(k15), "rest": _group(rest),
            "by_timeframe": {tf: _group([r for r in kept if r.get("timeframe") == tf])
                             for tf in (tr.TF, *tr.REST)},
            "by_profile_15m": {p: _group([r for r in k15 if str(r.get("profile")) == p])
                               for p in profiles},
            "bootstrap": boot_se(kept), "local_only": local,
            "cupo": cupo_blocked(events, rows, look) if events is not None else None}


def _t(ms: int | None) -> str:
    return "—" if ms is None else datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d %H:%M UTC")


def _x(v: float | None, fmt: str = "{:+.3f}") -> str:
    return "—" if v is None else fmt.format(v)


def render(looks: Mapping[str, Mapping]) -> str:
    """Informe Markdown de las miradas hechas (cada una con `verdict` y `describe`)."""
    out = ["# T222 — ¿Sale 15 m de la mesa principal?", "",
           "**Modo: SIMULADO.** Regla congelada en `PLAN/T222.md` §3 (huella "
           f"`{tr.PREREG_SHA256[:16]}…`). Solo decide el veredicto; lo demás es descriptivo.", ""]
    for key in sorted(looks):
        v, d = looks[key]["verdict"], looks[key]["describe"]
        e = v["estimate"]
        out += [f"## Mirada {v['look']} · {_t(v['look_ms'])}", "",
                f"**Veredicto: {v['status']}** ({v['why']}). Familia de Holm m = {v['family_m']}, "
                f"z_c = {v['z_crit']:.3f}. Cuentan {v['counted']} operaciones "
                f"(huella `{v['counted_digest']}`), abiertas desde {_t(v['t0_ms'])}.", "",
                "| | 15 m | 1 h + 4 h | Δ |", "|---|--:|--:|--:|",
                f"| n | {e['n15']} | {e['n_rest']} | |",
                f"| E[R] neto | {_x(e['mu15'])} | {_x(e['mu_rest'])} | {_x(e['delta'])} |",
                f"| ET por día | {_x(e['se15'], '{:.4f}')} | | {_x(e['se_delta'], '{:.4f}')} |",
                f"| z | {_x(e['z15'], '{:+.2f}')} | | {_x(e['z_delta'], '{:+.2f}')} |", "",
                f"Días con cierres: {e['days']}. Condiciones: " + ", ".join(
                    f"{k} {'sí' if ok else 'no'}" for k, ok in v["checks"].items()) + ".", ""]
        out += ["Descriptivo (no decide):", "",
                "| Grupo | n | neto | costo | bruto | r × peso | PnL (USDT) |",
                "|---|--:|--:|--:|--:|--:|--:|"]
        groups = [(f"marco {k}", g) for k, g in d["by_timeframe"].items()]
        groups += [(f"15 m · {k}", g) for k, g in d["by_profile_15m"].items()]
        for name, g in groups:
            out.append(f"| {name} | {g['n']} | {_x(g['net_r'])} | {_x(g['cost_r'], '{:.3f}')} | "
                       f"{_x(g['gross_r'])} | {_x(g['r_x_weight'])} | {g['pnl_usdt']:+.1f} |")
        b = d["bootstrap"]
        out += ["", f"- Bootstrap de días ({b['reps']} remuestras, semilla {b['seed']}): ET de "
                f"μ̂₁₅ {_x(b['se15'], '{:.4f}')}, de Δ̂ {_x(b['se_delta'], '{:.4f}')}."]
        loc = d["local_only"]
        out.append("- Solo este equipo (T196): " + (
            f"μ̂₁₅ {_x(loc['mu15'])}, Δ̂ {_x(loc['delta'])} (n = {loc['n15']} y {loc['n_rest']})."
            if loc else "no disponible con esta fuente (hace falta `--store` con una copia del libro)."))
        c = d["cupo"]
        out.append("- Rechazos «cupo lleno» de 1 h y 4 h: " + (
            f"{c['cupo_1h4h']}, de ellos {c['with_15m_open']} con una posición de 15 m abierta."
            if c else "no disponible con esta fuente (hace falta `--api`)."))
        reg = v["regime"]
        if reg["last_change_ms"] is not None:
            out.append(f"- Último cambio de régimen: {_t(reg['last_change_ms'])}; "
                       f"tramo vigente {'exigido' if reg['applies'] else 'con menos de 100 de 15 m'}.")
        out.append("")
    return "\n".join(out)
