"""Palancas de rentabilidad, disparadores y diferencias entre auditorías (T159). Puro.

Cada oportunidad lleva su **vía**, que es lo que la sesión puede hacer con ella sin reabrir una
decisión del usuario (`PLAN/ESTADO_PROYECTO.md` §4):

- `auto`: ya es una adaptación de `AUTO_ADAPT` (`eim/paper/t143_config.py`); solo se vigila.
- `variante`: se prueba en una corrida aparte (`EIM_PAPER_VARIANTS`), nunca en la oficial de T31.
- `◆`: necesita al usuario (catálogo, perfiles, umbral nuevo de riesgo).
- `cerrada`: una decisión vinculante la cerró (T134 salidas, T137 stop, T139 entradas, T145 D).

El impacto es lo que la palanca habría cambiado **en la muestra observada**, en USDT y en R por
operación. Es una cota, no una promesa: no corrige por selección ni por régimen.
"""

from __future__ import annotations

TF_MAX_COST_R = 0.15        # mismo umbral que `EXEC_T143.tf_max_cost_r`
TAIL_SHARE = 0.40           # las 5 peores pérdidas pesan ≥ 40 % de toda la pérdida
MIN_N = 20
VARIANT_MIN_N = 30
FUNDING_TRIGGER = 0.04      # BACKLOG T145 (3): ≥ 4 % anual en 12 meses móviles → reabrir B
L2_TRIGGER_DAYS = 365       # BACKLOG T145 (4): un año de libro L2 propio → valorar A
HFT_MIN_COMPLETE = 0.99     # T78
CALIB_BIAS = 0.05           # 5 pp entre probabilidad media y frecuencia real de un escenario
NEAR = 0.75                 # un disparador «cerca» al 75 % de su umbral


def _opp(oid, cat, title, evidence, route, ref, usdt=None, r_op=None) -> dict:
    return {"id": oid, "category": cat, "title": title, "evidence": evidence, "route": route,
            "ref": ref, "impact_usdt": usdt, "impact_r_per_op": r_op}


def opportunities(k: dict, variant: dict | None = None,
                  calib: dict | None = None) -> list[dict]:
    """Oportunidades ordenadas por impacto en USDT (las informativas, al final)."""
    out: list[dict] = []
    a = k.get("all", {})
    if not a.get("n"):
        return out
    if a.get("gross_r") is not None and a["gross_r"] <= 0:
        out.append(_opp("sin_bruto", "medición", "Sin ventaja bruta: el costo solo reduce la pérdida",
                        f"bruto {a['gross_r']:+.3f} R/op = neto {a['e_r']:+.3f} + costo "
                        f"{a['cost_r']:.3f} (n={a['n']})", "cerrada", "T139 P1 · T145 D"))
    for tf, s in k.get("by_timeframe", {}).items():
        if s.get("readable") and (s.get("cost_r") or 0) >= TF_MAX_COST_R:
            best = max(k["by_timeframe"].values(), key=lambda x: x.get("e_r", -9))
            warn = " · OJO: es el marco menos malo, retirarlo empeora" if best is s else ""
            out.append(_opp(f"marco_caro_{tf}", "costo", f"Marco {tf} con costo ≥ {TF_MAX_COST_R} R",
                            f"costo {s['cost_r']:.3f} R/op, E[R] {s['e_r']:+.3f}, n={s['n']}, "
                            f"PnL {s['pnl_usdt']:+.1f} USDT{warn}", "auto (tf_max_cost_r)", "T143",
                            -s["pnl_usdt"], -s["e_r"]))
    t = k.get("taker", {})
    if t.get("n_market", 0) >= MIN_N:
        out.append(_opp("maker", "costo", "Entradas a mercado que podrían ir como límite",
                        f"{t['n_market']} de {a['n']} a mercado ({t['share_market']:.0%}); "
                        "solo la diferencia de comisión de entrada", "auto (maker_entry_timeframes)",
                        "T143", t["usdt"], t.get("r_per_op")))
    if a.get("pnl_usdt", 0) < 0 and a.get("cost_usdt", 0) >= -a["pnl_usdt"]:
        out.append(_opp("friccion", "costo", "La fricción supera a la pérdida neta",
                        f"costo {a['cost_usdt']:.1f} USDT frente a PnL {a['pnl_usdt']:+.1f}",
                        "auto · variante", "T143"))
    if a.get("worst5_share", 0) >= TAIL_SHARE:
        lev = k.get("by_leverage", {})
        top = max(lev, key=lambda x: float(x.rstrip("x") or 0)) if lev else None
        s = lev.get(top, {}) if top else {}
        usdt = -0.5 * s["pnl_usdt"] if s.get("pnl_usdt", 0) < 0 else None
        out.append(_opp("cola", "riesgo", "Las 5 peores pérdidas pesan demasiado",
                        f"{a['worst5_share']:.0%} de la pérdida bruta; con {top}: E[R] "
                        f"{s.get('e_r', 0):+.3f}, n={s.get('n', 0)} (impacto = mitad de tamaño)",
                        "variante + umbral nuevo en AUTO_ADAPT (◆)", "T136", usdt))
    if a.get("beyond_sl_n", 0):
        out.append(_opp("mas_alla_sl", "riesgo", "Pérdidas por encima de 1 R",
                        f"{a['beyond_sl_n']} operaciones con bruto < −1,05 R (salto o "
                        "deslizamiento más allá del stop)", "auto (risk_includes_costs)", "T136"))
    for st, s in k.get("by_strategy", {}).items():
        if s.get("readable") and s["e_r_ci"][1] < 0:
            out.append(_opp(f"estrategia_{st}", "catálogo", f"«{st}» pierde con IC 95 % < 0",
                            f"E[R] {s['e_r']:+.3f} [{s['e_r_ci'][0]:+.3f}, {s['e_r_ci'][1]:+.3f}], "
                            f"n={s['n']}, PnL {s['pnl_usdt']:+.1f}", "◆ (catálogo; Holm cuenta)",
                            "T49", -s["pnl_usdt"] if s["pnl_usdt"] < 0 else None, -s["e_r"]))
    be = a.get("breakeven_win_rate")
    if be is not None and a["win_rate"] < be:
        out.append(_opp("equilibrio", "medición", "Acierto por debajo del de equilibrio",
                        f"acierto {a['win_rate']:.1%} frente a equilibrio {be:.1%} (ganadora "
                        f"{a['avg_win_r']:+.3f} R, perdedora {a['avg_loss_r']:+.3f} R)",
                        "cerrada (T134 salidas)", "T134"))
    if variant is not None:
        out.append(variant_vs_official(k, variant))
    out += calibration_opps(calib or {})
    return sorted(out, key=lambda o: -(o["impact_usdt"] or 0))


def calibration_opps(c: dict) -> list[dict]:
    """Calidad del pronóstico (lo que el sistema sigue haciendo con T145 D: analizar bien)."""
    out = []
    if c.get("brier_skill") is not None and c["brier_skill"] <= 0:
        d = (c.get("directional") or {})
        out.append(_opp("calib_sin_skill", "calibración",
                        "Las probabilidades de escenario no superan a la caminata aleatoria",
                        f"Brier skill {c['brier_skill']:+.3f}, acierto direccional "
                        f"{d.get('accuracy', 0):.1%} (n={d.get('n', 0)}, efectiva "
                        f"≈{c.get('n_effective', 0):.0f})",
                        "cerrada (T160: ninguna recalibración pasó)", "T160"))
    mp, rf = c.get("mean_prob") or {}, c.get("realized_freq") or {}
    gaps = {s: mp[s] - rf[s] for s in mp if s in rf}
    if gaps:
        s, g = max(gaps.items(), key=lambda kv: abs(kv[1]))
        if abs(g) >= CALIB_BIAS:
            out.append(_opp(f"calib_sesgo_{s}", "calibración", f"Escenario «{s}» descalibrado",
                            f"probabilidad media {mp[s]:.1%} frente a frecuencia real "
                            f"{rf[s]:.1%} ({g:+.1%})", "cerrada (T160: desvío de régimen, no del modelo)",
                            "T160"))
    return out


def variant_vs_official(k: dict, v: dict) -> dict:
    """La corrida aparte (costo y riesgo adaptados) frente a la oficial, en la misma ventana."""
    vs, os_ = v.get("all", {}), v.get("official_same_window", {})
    n = vs.get("n", 0)
    if n < VARIANT_MIN_N:
        return _opp("variante", "costo", "Corrida aparte T143: aún sin muestra",
                    f"n={n} de {VARIANT_MIN_N} necesarias", "esperar", "T143")
    d_e = vs["e_r"] - os_.get("e_r", 0)
    d_c = (vs.get("cost_r") or 0) - (os_.get("cost_r") or 0)
    return _opp("variante", "costo", "Corrida aparte T143 frente a la oficial",
                f"ΔE[R] {d_e:+.3f} R/op, Δcosto {d_c:+.3f} R/op (n={n} / {os_.get('n', 0)})",
                "◆ adoptar al cerrar T31 (2026-11-27)", "T143 · T31", None, d_e)


def triggers(funding: dict[str, float | None], l2_days: float | None,
             hft_complete: float | None) -> list[dict]:
    """Disparadores de BACKLOG T145 y salud de la única fuente propia (T78)."""
    out = []
    for sym, apr in funding.items():
        out.append({"id": f"funding_{sym}", "fired": apr is not None and apr >= FUNDING_TRIGGER,
                    "near": apr is not None and NEAR * FUNDING_TRIGGER <= apr < FUNDING_TRIGGER,
                    "value": apr, "threshold": FUNDING_TRIGGER,
                    "text": f"Funding medio 12 m de {sym} anualizado"
                            + ("" if apr is not None else " (sin medir)"),
                    "action": "reabrir B (carry) con pre-registro propio · ◆"})
    out.append({"id": "l2_un_ano", "fired": l2_days is not None and l2_days >= L2_TRIGGER_DAYS,
                "near": l2_days is not None and NEAR * L2_TRIGGER_DAYS <= l2_days < L2_TRIGGER_DAYS,
                "value": l2_days, "threshold": L2_TRIGGER_DAYS,
                "text": "Días de libro L2 propio", "action": "valorar A (T80) con pre-registro · ◆"})
    out.append({"id": "hft_calidad", "fired": hft_complete is not None
                and hft_complete < HFT_MIN_COMPLETE, "near": False, "value": hft_complete,
                "threshold": HFT_MIN_COMPLETE, "text": "Horas completas de la captura HFT",
                "action": "diagnosticar cortes (T148 · usage incidents)"})
    return out


DELTA_KEYS = (("all", "n"), ("all", "e_r"), ("all", "win_rate"), ("all", "cost_r"),
              ("all", "gross_r"), ("all", "pnl_usdt"), ("last7", "n"), ("last7", "e_r"),
              ("taker", "share_market"))


def deltas(cur: dict, prev: dict | None) -> dict:
    """Qué cambió desde la auditoría anterior: cifras clave y oportunidades nuevas o resueltas."""
    if not prev:
        return {"previous": None}
    ck, pk = cur["book"], prev.get("book", {})
    metrics = {}
    for sec, key in DELTA_KEYS:
        a, b = ck.get(sec, {}).get(key), pk.get(sec, {}).get(key)
        if isinstance(a, int | float) and isinstance(b, int | float):
            metrics[f"{sec}.{key}"] = {"prev": b, "cur": a, "delta": a - b}
    ids = {o["id"] for o in cur["opportunities"]}
    pids = {o["id"] for o in prev.get("opportunities", [])}
    fired = {t["id"] for t in cur["triggers"] if t["fired"]}
    pfired = {t["id"] for t in prev.get("triggers", []) if t.get("fired")}
    return {"previous": prev.get("generated_at"), "metrics": metrics,
            "new": sorted(ids - pids), "gone": sorted(pids - ids),
            "triggers_new": sorted(fired - pfired)}
