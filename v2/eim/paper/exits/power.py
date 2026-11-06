"""Potencia de la prueba en papel (T135, E9 de §8 de `T129_sl_dinamico.md`).

Antes de la primera operación de un A/B hay que saber dos cosas: cuántas operaciones emparejadas
hacen falta para ver el efecto que T134 estimó, y qué efecto se puede ver con las que dé el libro en
vivo. Sin eso, «el mismo signo» lo cumple por azar una salida sin efecto la mitad de las veces.

Prueba a una cola sobre la media de las diferencias emparejadas por operación:

    n = ((z₁₋α + z₁₋β) · σ / δ)²        δ_min = (z₁₋α + z₁₋β) · σ / √n

El plan queda en un archivo con su huella, **confirmado antes de empezar**: `write_plan` se niega a
reescribir un plan con otro contenido, porque cambiar la potencia después de ver datos es otra forma
de ajustar el resultado. Puro salvo `write_plan`, que solo escribe el archivo que se le pide.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist

ALPHA = 0.05
POWER = 0.80
MIN_WEEKS = 4                # criterio 7 de §5.4: ≥ 4 semanas aunque las operaciones lleguen antes


def _z_sum(alpha: float, power: float) -> float:
    if not (0 < alpha < 1 and 0 < power < 1):
        raise ValueError("`alpha` y `power` tienen que estar entre 0 y 1")
    nd = NormalDist()
    return nd.inv_cdf(1 - alpha) + nd.inv_cdf(power)


def required_n(sd: float, effect: float, alpha: float = ALPHA, power: float = POWER) -> int:
    """Operaciones emparejadas para detectar `effect` (en R) con esa σ de las diferencias."""
    if sd <= 0 or effect <= 0:
        raise ValueError("`sd` y `effect` tienen que ser positivos: sin efecto no hay potencia")
    return math.ceil((_z_sum(alpha, power) * sd / effect) ** 2)


def min_detectable(sd: float, n: int, alpha: float = ALPHA, power: float = POWER) -> float:
    """Efecto mínimo detectable, en R, con `n` operaciones emparejadas."""
    if sd <= 0 or n <= 0:
        raise ValueError("`sd` y `n` tienen que ser positivos")
    return _z_sum(alpha, power) * sd / math.sqrt(n)


def power_plan(candidate: str, base: str, sd: float, effect: float, trades_per_week: float,
               source: str, *, alpha: float = ALPHA, power: float = POWER) -> dict:
    """El plan del A/B: operaciones, semanas y efecto detectable con el ritmo del libro en vivo.

    `trades_per_week` tiene que ser el ritmo **del libro en vivo**: el del banco corre con tamaño
    fijo y sin cupos, y no sirve para estimar cuánto tarda el papel.
    """
    if trades_per_week <= 0:
        raise ValueError("`trades_per_week` tiene que ser positivo: sin operaciones no hay A/B")
    n = required_n(sd, effect, alpha, power)
    weeks = max(MIN_WEEKS, math.ceil(n / trades_per_week))
    plan = {"candidate": candidate, "base": base, "alpha": alpha, "power": power,
            "one_sided": True, "sd_paired_r": sd, "effect_r": effect,
            "trades_per_week": trades_per_week, "source": source, "required_n": n,
            "weeks": weeks, "min_weeks": MIN_WEEKS,
            "min_detectable_r_at_required_n": min_detectable(sd, n, alpha, power),
            "min_detectable_r_at_min_weeks": min_detectable(
                sd, max(1, math.floor(trades_per_week * MIN_WEEKS)), alpha, power)}
    return {**plan, "fingerprint": fingerprint(plan)}


def fingerprint(plan: dict) -> str:
    """Huella del plan, sin contar la propia huella."""
    body = {k: v for k, v in plan.items() if k != "fingerprint"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()


def inputs_from_report(report: dict, candidate: str, base: str) -> float:
    """σ de las diferencias emparejadas `candidato − base`, del informe de T134 (`power_inputs`)."""
    got = (report.get("power_inputs") or {}).get(candidate)
    if got is None:
        raise LookupError(f"el informe no tiene insumos de potencia para «{candidate}»")
    sd = (got.get("sd_paired") or {}).get(base)
    if sd is None:
        raise LookupError(f"el informe no tiene la varianza de «{candidate}» frente a «{base}»")
    return float(sd)


def write_plan(plan: dict, path: str | Path) -> Path:
    """Guarda el plan. Si ya existe otro distinto, se niega: se confirma una sola vez."""
    p = Path(path)
    if p.exists():
        old = json.loads(p.read_text(encoding="utf-8"))
        if old.get("fingerprint") != plan.get("fingerprint"):
            raise FileExistsError(f"{p} ya guarda otro plan ({str(old.get('fingerprint'))[:12]}): "
                                  "un cambio es una versión nueva con su propio archivo")
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                 encoding="utf-8")
    return p
