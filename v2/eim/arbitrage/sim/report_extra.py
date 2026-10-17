"""Secciones del informe de arbitraje (T43): triangular, capital mínimo y calibración."""

from __future__ import annotations

from eim.arbitrage.params import ArbParams
from eim.arbitrage.sim.report_fmt import NAMES, bps, day, num, pct, table


def triangular(res: dict) -> list[str]:
    tri = res["triangular"]
    rows = [[c["cycle"], num(c["minutes"]), bps(c["gross_p50_bps"], 2),
             bps(c["gross_p99_bps"], 2), bps(c["gross_max_bps"], 1), bps(c["spread_bps"], 2),
             *[f"{c['by_cost'][k]['minutes_pos']} ({num(c['by_cost'][k]['upper_bound_usd'], 0)}"
               " USD)" for k in c["by_cost"]]] for c in tri["cycles"]]
    keys = list(tri["cycles"][0]["by_cost"]) if tri["cycles"] else []
    return [f"### {NAMES['triangular']} — {tri['label']}", "",
            *table(["Ciclo", "Minutos", "Bruto p50", "Bruto p99", "Bruto máx.",
                    "½ diferencial (perfil)", *[f"Min. neto > 0 · {k}" for k in keys]], rows),
            "", "Pares sin perfil de profundidad (sin medio diferencial: aún más optimista): "
            + (", ".join(tri["no_depth"]) or "ninguno") + ".", "", _captured(tri), ""]


def _captured(tri: dict) -> str:
    cap = tri.get("captured") or {}
    if not cap.get("captures"):
        return "Libros reales capturados: ninguno (no se puede contrastar el ticker)."
    by = {k: v for k, v in cap["by_cost"].items() if v.get("cycles")}
    parts = [f"{k}: {v['positive']} de {v['cycles']} ciclos con neto > 0, mediana "
             f"{bps(v['median_bps'])}, mejor {bps(v['best_bps'])}" for k, v in by.items()]
    vip0 = by.get("VIP 0", {})
    tail = (" Con VIP 0 ningún ciclo real sale positivo: lo que el ticker marca como positivo "
            "son desfases entre cierres de pares poco líquidos, no precios ejecutables a la vez."
            if vip0 and not vip0["positive"] else "")
    return (f"Con libros reales capturados ({cap['captures']} fotografías, {day(cap['from_t'])}"
            f" → {day(cap['to_t'])}; motor T38 `scan_triangular` sin cambios): "
            + "; ".join(parts) + "." + tail)


def capital(res: dict, p: ArbParams) -> list[str]:
    rows = [[k, "sin mínimos (falta `exchangeInfo`)" if v is None else num(v["min_order_usd"], 2),
             "—" if v is None else num(v["capital_usd"], 2)]
            for k, v in sorted(res["capital_min"].items())]
    return ["## Capital mínimo", "",
            "Técnico (mínimos de orden de Binance, `exchangeInfo`, al último precio): la mayor "
            f"orden mínima de las patas más el margen de cada pata de futuros (× 1/"
            f"{p.perp_leverage:g}). Por encima, comisiones y funding son proporcionales al "
            "nocional "
            "(el % neto no mejora con más capital) hasta que el libro se agota: ver «Nocional por "
            "operación (capacidad)».", "",
            *table(["Estrategia · activo", "Orden mínima (USD)", "Capital mínimo (USD)"], rows),
            ""]


def calibration(res: dict) -> list[str]:
    cal = res["calibration"]
    rows = [[r["param"], str(r["before"]), str(r["after"]), r["why"]] for r in res["recommend"]]
    meas = []
    for name, blk, fmt in (
            ("Movimiento \\|rend. 24 h\\|", cal["daily_move"], lambda x: pct(x).lstrip("+")),
            (f"\\|Δ base perp−spot\\| en {cal['carry_h']:g} h", cal["basis_change"],
             lambda x: bps(x).lstrip("+")),
            ("\\|funding realizado (90 liq.) − extrapolado (21)\\| por liquidación",
             cal["funding_shock"], lambda x: pct(x, 4).lstrip("+"))):
        for a, v in blk.items():
            meas.append([name, a, fmt(v["p50"]), fmt(v["p90"]), fmt(v["p99"])])
    return ["## Calibración de riesgos", "", *table(["Medida", "Activo", "p50", "p90", "p99"],
                                                    meas), "",
            "## Parámetros del selector (T38) fijados con esta evidencia", "",
            *table(["Parámetro", "Antes", "Después", "Evidencia"], rows), "",
            "Sin calibrar (sin evidencia suficiente): `risk_aversion`, `risk_weights`, "
            "`max_liquidity_risk` (ver BACKLOG T43).", ""]
