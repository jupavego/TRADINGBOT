"""Ensambla la auditoría a partir de filas ya leídas (T159). Puro: lo usan la consola y las pruebas."""

from __future__ import annotations

import math
import statistics

from eim.analytics.audit import kpis, levers


def _key(r: dict) -> tuple[str, str]:
    return str(r.get("profile") or ""), str(r.get("idea_id") or "")


def paired(official_rows: list[dict], variant_rows: list[dict]) -> dict:
    """La variante frente a la oficial en las MISMAS operaciones (perfil + idea), T175.

    Las dos mesas leen los mismos contextos pero no toman las mismas ideas (la variante dimensiona
    con costo y cierra marcos caros), así que comparar sus medias mezcla muestras distintas: el
    2026-11-16 eso daba −0,032 R/op y, emparejado, +0,011. Lo que la variante cambia es la
    ejecución de una idea; eso se mide restando idea a idea."""
    off = {_key(r): r for r in official_rows if _key(r)[1]}
    var = {_key(r): r for r in variant_rows if _key(r)[1]}
    both = sorted(set(off) & set(var))
    out = {"n": len(both), "only_official": len(set(off) - set(var)),
           "only_variant": len(set(var) - set(off))}
    if len(both) < 2:
        return out
    d = [kpis._f(var[k].get("r")) - kpis._f(off[k].get("r")) for k in both]
    dc = [(kpis.trade_cost(var[k])["cost_r"] or 0.0) - (kpis.trade_cost(off[k])["cost_r"] or 0.0)
          for k in both]
    m, half = statistics.fmean(d), 1.96 * statistics.stdev(d) / math.sqrt(len(d))
    return {**out, "d_r": m, "d_r_ci": [m - half, m + half], "d_cost_r": statistics.fmean(dc)}


def variant_block(official_rows: list[dict], variant_rows: list[dict]) -> dict:
    """La corrida aparte y la oficial recortada a la misma ventana (desde el primer cierre de la
    variante), para que la comparación no mezcle periodos; y, sobre todo, emparejadas (T175)."""
    v_off = kpis.official(variant_rows)
    if not v_off:
        return {"all": {"n": 0}, "official_same_window": {"n": 0}, "paired": {"n": 0}}
    t0 = min(kpis._f(r.get("exit_t")) for r in v_off)
    same = [r for r in kpis.official(official_rows) if kpis._f(r.get("exit_t")) >= t0]
    return {"since_exit_t": int(t0), "all": kpis.stats(v_off),
            "by_timeframe": kpis.by(v_off, lambda r: r.get("timeframe", "")),
            "by_profile_tf": kpis.by(v_off, lambda r: f"{r.get('profile', '')}@"
                                                      f"{r.get('timeframe', '')}"),
            "official_same_window": kpis.stats(same), "paired": paired(same, v_off)}


def build(rows: list[dict], now_ms: int, generated_at: str, *,
          variant_rows: dict[str, list[dict]] | None = None,
          funding: dict[str, float | None] | None = None, hft: dict | None = None,
          calibration: dict | None = None, calibration_4h: dict | None = None,
          prev: dict | None = None) -> dict:
    book = kpis.book_kpis(rows, now_ms)
    var = {name: variant_block(rows, vr) for name, vr in (variant_rows or {}).items()}
    calibration = {k: v for k, v in (calibration or {}).items() if k != "curve"}
    cal4 = {k: v for k, v in (calibration_4h or {}).items() if k != "curve"}
    opps = levers.opportunities(book, var.get("t143"), calibration, cal4)
    hft = hft or {}
    trig = levers.triggers(funding or {}, hft.get("l2_days"), hft.get("pct_complete"))
    audit = {"mode": "SIMULADO", "generated_at": generated_at, "now_ms": now_ms, "book": book,
             "variants": var, "hft": hft, "funding_apr": funding or {},
             "calibration": calibration, "calibration_4h": cal4,
             "opportunities": opps, "triggers": trig}
    audit["deltas"] = levers.deltas(audit, prev)
    return audit
