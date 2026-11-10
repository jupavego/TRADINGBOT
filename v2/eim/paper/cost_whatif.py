"""Antes y después de T143 sobre las mismas operaciones vividas (entregable 5).

Lo vivido con la configuración nueva todavía no existe: no se despliega mientras T31 cuente
semanas. Así que el «después» es un **contrafactual sobre el libro vivido**, con las tres
palancas de T143 aplicadas una a una sobre cada operación real y nada más:

1. **Sin 15 m**: la operación de 15 m no existe (la puerta de `tf_gate`).
2. **Entrada maker en 1 h y 4 h**: la entrada `market` de esos marcos paga la comisión de creador
   en vez de la de tomador. El deslizamiento no se toca (conservador: una límite no desliza al
   entrar). Ni la no ejecución (0,2 % en el banco) ni la selección adversa (−0,001 R de bruto en
   el banco) se pueden reconstruir aquí: las mide `reports/t143_maker.md` y se citan al lado.
3. **Riesgo con costo**: la cantidad se multiplica por `d / (d + c)` para que la pérdida al stop
   sea la declarada, así que todo el resultado en R de esa operación se escala por
   `1 / (1 + costo_R)`, el bruto incluido.

Método del diagnóstico de la fase 24: operaciones de perfil, sin `retro`, riesgo = |pnl| / |r|,
bruto = neto + costo. Puro: recibe filas del `ledger.csv` como diccionarios.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Iterable, Sequence

from eim.paper import universe

STEPS = ("antes", "sin_15m", "sin_15m_maker", "sin_15m_maker_riesgo")
LABELS = {"antes": "Antes (vivido)", "sin_15m": "1 · sin 15 m",
          "sin_15m_maker": "2 · + entrada maker en 1 h y 4 h",
          "sin_15m_maker_riesgo": "3 · + riesgo con costo (T143 completo)"}


def _f(x) -> float:
    return float(x) if x not in (None, "") else 0.0


def base(row: dict) -> dict | None:
    """Neto, costo y bruto en R de una operación vivida; None si su riesgo no se reconstruye."""
    pnl, r = _f(row.get("pnl_usdt")), _f(row.get("r"))
    if not pnl or not r:
        return None
    risk = abs(pnl) / abs(r)
    cost = _f(row.get("fees")) + _f(row.get("slip")) + _f(row.get("funding"))
    fees = json.loads(row["cost_params"]) if row.get("cost_params") else {}
    saving = 0.0
    if row.get("kind") == "market":
        spread = fees.get("taker_fee", 0.0005) - fees.get("maker_fee", 0.0002)
        saving = spread * _f(row["notional"])
    return {"tf": row.get("timeframe"), "net": r, "cost": cost / risk, "saving": saving / risk}


def apply(b: dict, step: str, maker_tfs: Sequence[str] = ("1h", "4h")) -> dict | None:
    """La operación bajo un paso de `STEPS`: None si ese paso la retira."""
    gross = b["net"] + b["cost"]
    if step == "antes":
        return {"net": b["net"], "cost": b["cost"], "gross": gross}
    if b["tf"] == "15m":
        return None
    cost = b["cost"]
    if step in ("sin_15m_maker", "sin_15m_maker_riesgo") and b["tf"] in maker_tfs:
        cost -= b["saving"]
    k = 1 / (1 + cost) if step == "sin_15m_maker_riesgo" else 1.0
    return {"net": (gross - cost) * k, "cost": cost * k, "gross": gross * k}


def _summ(xs: list[dict]) -> dict:
    if not xs:
        return {"n": 0, "cost_r": None, "net_r": None, "gross_r": None, "cost_r_median": None,
                "net_se": None}
    se = statistics.stdev(x["net"] for x in xs) / len(xs) ** 0.5 if len(xs) > 1 else None
    return {"n": len(xs), "net_se": se, "cost_r": statistics.fmean(x["cost"] for x in xs),
            "cost_r_median": statistics.median(x["cost"] for x in xs),
            "net_r": statistics.fmean(x["net"] for x in xs),
            "gross_r": statistics.fmean(x["gross"] for x in xs)}


def compare(rows: Iterable[dict], maker_tfs: Sequence[str] = ("1h", "4h")) -> dict:
    """Resumen por paso y por marco. `excluded` = vividas sin riesgo reconstruible."""
    lived = universe.result_rows(rows)      # la regla única de T144
    bs = [b for b in (base(r) for r in lived) if b is not None]
    out: dict = {"lived": len(lived), "excluded": len(lived) - len(bs), "steps": {}}
    for s in STEPS:
        xs = [y for y in (apply(b, s, maker_tfs) for b in bs) if y is not None]
        by_tf = {}
        for tf in sorted({b["tf"] for b in bs}):
            ys = [y for b in bs if b["tf"] == tf and (y := apply(b, s, maker_tfs)) is not None]
            by_tf[tf] = _summ(ys)
        out["steps"][s] = {**_summ(xs), "by_tf": by_tf}
    return out


def shadow(rows: Iterable[dict]) -> dict[str, dict]:
    """E[R] neto de la sombra por marco (sin `retro`): misma decisión sin peso, muestra mayor.

    La sombra no tiene tamaño, así que su costo en R no se reconstruye: solo su neto.
    """
    out: dict[str, dict] = {}
    sel = [r for r in rows if r.get("scope") == "sombra" and r.get("r") not in (None, "")
           and not universe.is_retro(r)]
    for tf in sorted({r.get("timeframe") for r in sel}):
        xs = [float(r["r"]) for r in sel if r.get("timeframe") == tf]
        se = statistics.stdev(xs) / len(xs) ** 0.5 if len(xs) > 1 else None
        out[tf] = {"n": len(xs), "net_r": statistics.fmean(xs), "net_se": se}
    return out
