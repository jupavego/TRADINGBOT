"""Ensambla la auditoría a partir de filas ya leídas (T159). Puro: lo usan la consola y las pruebas."""

from __future__ import annotations

from eim.analytics.audit import kpis, levers


def variant_block(official_rows: list[dict], variant_rows: list[dict]) -> dict:
    """La corrida aparte y la oficial recortada a la misma ventana (desde el primer cierre de la
    variante), para que la comparación no mezcle periodos."""
    v_off = kpis.official(variant_rows)
    if not v_off:
        return {"all": {"n": 0}, "official_same_window": {"n": 0}}
    t0 = min(kpis._f(r.get("exit_t")) for r in v_off)
    same = [r for r in kpis.official(official_rows) if kpis._f(r.get("exit_t")) >= t0]
    return {"since_exit_t": int(t0), "all": kpis.stats(v_off),
            "by_timeframe": kpis.by(v_off, lambda r: r.get("timeframe", "")),
            "official_same_window": kpis.stats(same)}


def build(rows: list[dict], now_ms: int, generated_at: str, *,
          variant_rows: dict[str, list[dict]] | None = None,
          funding: dict[str, float | None] | None = None, hft: dict | None = None,
          calibration: dict | None = None, prev: dict | None = None) -> dict:
    book = kpis.book_kpis(rows, now_ms)
    var = {name: variant_block(rows, vr) for name, vr in (variant_rows or {}).items()}
    calibration = {k: v for k, v in (calibration or {}).items() if k != "curve"}
    opps = levers.opportunities(book, var.get("t143"), calibration)
    hft = hft or {}
    trig = levers.triggers(funding or {}, hft.get("l2_days"), hft.get("pct_complete"))
    audit = {"mode": "SIMULADO", "generated_at": generated_at, "now_ms": now_ms, "book": book,
             "variants": var, "hft": hft, "funding_apr": funding or {},
             "calibration": calibration,
             "opportunities": opps, "triggers": trig}
    audit["deltas"] = levers.deltas(audit, prev)
    return audit
