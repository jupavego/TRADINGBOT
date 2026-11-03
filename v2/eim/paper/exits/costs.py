"""Estrés de costos del banco (E4a de §8 de `PLAN/notas/T129_sl_dinamico.md`).

Las salidas ajustadas son las más sensibles a los costos: una que solo gana con el costo base no
se aprueba (criterio 8 de §5.4). Todo el banco se repite con el deslizamiento **de los stops**
multiplicado por ×1,5 y ×2.

Qué se multiplica y qué no:
- Sí: `slip_base_bps`, `slip_vol_k` y `slip_cap_bps`, que son los que paga una salida a mercado
  (SL, SLD, BE y tiempo; `engine._slip`).
- No: el deslizamiento de ENTRADA (`slip_entry_*`), que está calibrado aparte con el libro real
  (≈ 0,01 pb) y es el mismo para todas las salidas, ni las comisiones, que son tarifa y no
  deslizamiento.
Así el estrés toca exactamente el costo que distingue a una salida de otra, y no mete ruido en la
comparación por el lado de la entrada.

Puro: devuelve `ExecParams` nuevos (son inmutables), no muta nada.
"""

from __future__ import annotations

from eim.paper.params import ExecParams

BASE = 1.0


def stressed(ep: ExecParams, factor: float) -> ExecParams:
    """`ExecParams` con el deslizamiento de las salidas a mercado multiplicado por `factor`."""
    if factor < 1:
        raise ValueError(f"el estrés de costos nunca abarata: factor {factor} < 1")
    if factor == BASE:
        return ep
    c = ep.costs
    return ep.model_copy(update={"costs": c.model_copy(update={
        "slip_base_bps": c.slip_base_bps * factor,
        "slip_vol_k": c.slip_vol_k * factor,
        "slip_cap_bps": c.slip_cap_bps * factor})})


def label(factor: float) -> str:
    return "costo base" if factor == BASE else f"deslizamiento de stops ×{factor:g}"
