"""Veredicto por estrategia y capital mínimo técnico (T43).

Veredicto (caso base = la cuenta real, VIP 0 verificado):
- No viable: el selector no toma nada o el neto medio por operación es ≤ 0.
- Viable: neto medio > 0 con IC95 % > 0, rentabilidad anual sobre el período Y en los
  últimos 12 meses ≥ umbral de referencia (`hurdle_apr`, supuesto), sin liquidaciones y
  ≥ 10 operaciones.
- Marginal: el resto (positivo pero no significativo, bajo el umbral, o con liquidaciones).
- Triangular: con libros reales manda lo capturado; el ticker es solo una cota superior.
"""

from __future__ import annotations

from eim.arbitrage.params import ArbParams
from eim.arbitrage.sim.frame import ArbHistory
from eim.arbitrage.sim.params import SimParams


def verdicts(res: dict, sp: SimParams) -> dict:
    out = {}
    for s, blk in res["strategies"].items():
        st = blk["stats"]
        if s == "funding_carry":
            best = max(res["carry_horizons"], key=lambda r: r["stats"].get("apr_period") or -1e9,
                       default=None)
            if best is not None:
                st = best["stats"]
        out[s] = verdict(st, sp.hurdle_apr)
    out["triangular"] = _tri_verdict(res["triangular"])
    return out


def _tri_verdict(tri: dict) -> tuple[str, list[str]]:
    """Con libros reales manda lo capturado; el ticker solo es una cota superior."""
    cap = tri.get("captured", {})
    real = cap.get("by_cost", {}).get("VIP 0", {})
    mins = sum(c["by_cost"].get("VIP 0", {}).get("minutes_pos", 0) for c in tri["cycles"])
    why = [f"ticker (optimista, cierres de 1 min no simultáneos): {mins} minutos con neto > 0 "
           "en 30 días con VIP 0, cota superior no ejecutable"]
    if real.get("cycles"):
        why.append(f"libros reales ({cap['captures']} fotografías): {real['positive']} de "
                   f"{real['cycles']} ciclos con neto > 0; mejor {real['best_bps']:+.1f} pb"
                   .replace(".", ","))
        return ("Marginal" if real["positive"] else "No viable"), why
    return ("Marginal" if mins else "No viable"), why + ["sin libros reales capturados"]


def verdict(st: dict, hurdle: float) -> tuple[str, list[str]]:
    if not st.get("n"):
        return "No viable", ["el selector T38 no tomó ninguna operación en todo el período"]
    if (st.get("mean_bps") or 0) <= 0:
        return "No viable", [f"neto medio {st['mean_bps']:+.1f} pb por operación ≤ 0"
                             .replace(".", ",")]
    why = []
    if st["ci95_mean_bps"][0] <= 0:
        why.append("IC95 % de la media incluye 0 (no significativo)")
    if st["apr_period"] < hurdle:
        why.append(f"rentabilidad anual {st['apr_period']:.2%} < umbral de referencia "
                   f"{hurdle:.0%} (supuesto)".replace(".", ","))
    if st.get("last_year_apr", hurdle) < hurdle:
        why.append(f"últimos 12 meses {st['last_year_apr']:.2%} < umbral (régimen actual)"
                   .replace(".", ","))
    if st["liquidations"]:
        why.append(f"{st['liquidations']} liquidaciones")
    if st["n"] < 10:
        why.append(f"solo {st['n']} operaciones")
    return ("Marginal", why) if why else ("Viable", ["neto > 0 significativo y sobre el umbral"])


def capital_min(hist: ArbHistory, p: ArbParams) -> dict:
    """Capital mínimo técnico por estrategia y activo: la mayor orden mínima de sus patas
    (max(nocional mínimo, cantidad mínima × precio, paso × precio) al último precio) más el
    margen de las patas de futuros (× 1/L cada una)."""
    f = hist.filters

    def need(key: str, px: float) -> float | None:
        g = f.get(key)
        if g is None:
            return None
        return max(float(g.get("min_notional") or 0), float(g.get("min_qty") or 0) * px,
                   float(g.get("step") or 0) * px)

    out: dict = {}
    lev = p.perp_leverage
    for a, h in hist.assets.items():
        if h.spot is None or h.perp is None or not len(h.spot):
            continue
        px = float(h.spot.c[-1])
        live = [q.symbol for q in h.quarterlies if q.settle is None]
        legs = {"spot": need(f"spot:{a}USDT", px), "perp": need(f"futures:{a}USDT", px),
                "usdc": need(f"futures:{a}USDC", px),
                "quarterly": need(f"futures:{live[0]}", px) if live else None}
        combos = {"funding_carry": (("spot", "perp"), 1 + 1 / lev),
                  "basis spot/trimestral": (("spot", "quarterly"), 1 + 1 / lev),
                  "basis perpetuo/trimestral": (("perp", "quarterly"), 2 / lev),
                  "related_perps": (("perp", "usdc"), 2 / lev)}
        for name, (ks, mult) in combos.items():
            vals = [legs[k] for k in ks]
            out[f"{name} · {a}"] = (None if any(v is None for v in vals) else
                                    {"min_order_usd": max(vals), "capital_usd": max(vals) * mult,
                                     "legs": dict(zip(ks, vals, strict=True)), "price": px})
    return out
