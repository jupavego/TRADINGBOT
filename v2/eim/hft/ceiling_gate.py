"""Veredicto de la prueba de techo (T80) según el pre-registro. Puro: dicts dentro, dict fuera.

La regla está escrita en `eim/hft/prereg/hft_ceiling_v1.json` y aquí solo se aplica:

- **C1 oportunidad**: con previsión perfecta de la dirección y la reacción medida, ¿qué fracción
  de las ventanas supera el ida y vuelta del estilo? Tiene que llegar al umbral.
- **C2 IC**: ¿hay alguna señal con IC medio por día fuera de muestra > 0, IC 95 % inferior > 0 y
  p de Holm < α sobre los 68 intentos?
- **C3 pb netos**: ¿esa señal (o cualquiera que pase C2) da ≥ +1,0 pb netos por operación con el
  costo de ESE estilo y el IC 95 % inferior > 0?
- **C4 muestra**: días con panel y días de prueba mínimos.

Un horizonte **supera** si C1, C2 y C3 se cumplen con el MISMO estilo de ejecución. Sin C4 no se
publica veredicto: se declara SIN POTENCIA (como T163 y T166).
"""

from __future__ import annotations

SUPERA, NO_SUPERA, SIN_POTENCIA = "SUPERA", "NO SUPERA", "SIN POTENCIA"


def _finite(x) -> bool:
    return x is not None and x == x


def c2_signals(block: dict, alpha: float) -> list[str]:
    """Señales del horizonte con IC fuera de muestra significativo tras Holm."""
    out = []
    for name, s in block.items():
        ic = s.get("ic", {})
        if (_finite(ic.get("mean")) and ic["mean"] > 0 and _finite(ic.get("lo"))
                and ic["lo"] > 0 and s.get("ic_p_holm", 1.0) < alpha):
            out.append(name)
    return sorted(out, key=lambda n: -block[n]["ic"]["mean"])


def c3_pairs(block: dict, signals: list[str], threshold_bps: float) -> list[dict]:
    """(señal, estilo) con pb netos medios ≥ umbral y extremo inferior del IC 95 % > 0."""
    out = []
    for name in signals:
        for style, row in block[name]["net"].items():
            if (_finite(row.get("mean")) and row["mean"] >= threshold_bps
                    and _finite(row.get("lo")) and row["lo"] > 0):
                out.append({"signal": name, "style": style, "net_bps": row["mean"],
                            "lo": row["lo"], "trades": row.get("trades", 0)})
    return sorted(out, key=lambda r: -r["net_bps"])


def c1_styles(ceiling_h: dict, threshold: float) -> list[str]:
    """Estilos cuya fracción de ventanas que pagan llega al umbral (con la reacción medida)."""
    block = ceiling_h.get("with_reaction", {})
    return [name for name, row in block.get("styles", {}).items()
            if row["frac_pays"] >= threshold]


def decide(prereg, ceiling: dict, oos: dict, sample: dict) -> dict:
    """Aplica los criterios del pre-registro y devuelve el veredicto con su detalle."""
    alpha = float(prereg.gate("C2_ic")["alpha"])
    thr_c1 = prereg.threshold("C1_oportunidad")
    thr_c3 = prereg.threshold("C3_net_bps", "threshold_bps")
    min_days = int(prereg.gate("C4_sample")["min_days"])
    min_test = int(prereg.gate("C4_sample")["min_test_days"])
    c4 = {"days": sample["days"], "test_days": sample["test_days"],
          "min_days": min_days, "min_test_days": min_test,
          "pass": sample["days"] >= min_days and sample["test_days"] >= min_test}
    rows = {}
    for h, block in oos["horizons"].items():
        styles = c1_styles(ceiling["horizons"].get(h, {}), thr_c1)
        sigs = c2_signals(block, alpha)
        pairs = [p for p in c3_pairs(block, sigs, thr_c3) if p["style"] in styles]
        rows[h] = {"c1_styles": styles, "c2_signals": sigs, "c3_pairs": pairs,
                   "pass": bool(styles and sigs and pairs)}
    if not c4["pass"]:
        verdict = SIN_POTENCIA
    else:
        verdict = SUPERA if any(r["pass"] for r in rows.values()) else NO_SUPERA
    return {"verdict": verdict, "alpha": alpha, "thresholds":
            {"C1_oportunidad": thr_c1, "C3_net_bps": thr_c3},
            "C4_sample": c4, "by_horizon": rows,
            "passing_horizons": sorted(h for h, r in rows.items() if r["pass"])}
