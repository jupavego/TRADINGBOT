"""Kelly fraccionado sobre el **límite inferior** del IC de E[R] (T136 entregable 5, E10 de §8).

Por qué el límite inferior y no la media: con muestras pequeñas la media puede ser positiva por
azar, y Kelly sobre la media manda apostar justo cuando menos se sabe. Tomando el extremo
pesimista del intervalo, el tamaño es 0 mientras no haya **evidencia** de ventaja, no solo una
media favorable. Fuentes: Kelly (1956); MacLean, Thorp y Ziemba (2011), sobre Kelly fraccionado y
el error de estimación.

La fracción: para apuestas pequeñas, maximizar E[log(1 + f·R)] da `f* ≈ E[R] / E[R²]`, con R el
resultado por operación en múltiplos del riesgo. Es una aproximación de segundo orden, exacta en
el límite de `f` pequeño, que es el régimen en el que opera un perfil (0,5–2 % por operación).
Aquí se sustituye `E[R]` por su límite inferior y se multiplica por `frac` (Kelly fraccionado).

**Consecuencia con lo medido hoy:** la escalera tiene E[R] = −0,154 R y las 87 variantes de T134
se rechazaron, así que el límite inferior es negativo con holgura y esta función da **0** para
todos los perfiles. Eso es lo correcto y es justo lo que la fase 22 ha demostrado; por eso el
tamaño por Kelly se entrega **apagado** (`ProfileParams.kelly` a `None`): encenderlo dejaría a los
perfiles sin abrir una sola operación y pararía la corrida de T31 y el A/B de T130. El valor de
tenerlo es que el día que se encienda no haya que decidir nada: sin ventaja demostrada, no hay
tamaño.

Puro: sin red, sin disco y sin estado.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field


class KellyParams(BaseModel):
    """Qué evidencia se exige y cuánto de Kelly se usa."""

    model_config = ConfigDict(frozen=True)

    frac: float = Field(0.25, gt=0.0, le=1.0)   # Kelly fraccionado: 1/4 es lo habitual
    z: float = Field(1.96, ge=0.0)               # 1,96 = límite inferior del IC 95 % a dos colas
    n_min: int = Field(30, ge=1)                 # por debajo de esta muestra no hay tamaño
    max_risk_pct: float | None = None            # tope duro; None = el `risk_pct` del perfil


class Edge(BaseModel):
    """La evidencia sobre una serie de operaciones, en R."""

    model_config = ConfigDict(frozen=True)

    n: int
    mean_r: float
    se_r: float          # error estándar de la media (por bloques de días si las ops se solapan)
    m2_r: float          # segundo momento E[R²] (no la varianza): es el denominador de Kelly

    @classmethod
    def of(cls, rs: Sequence[float], se_r: float | None = None) -> Edge:
        """Evidencia de una muestra de R. `se_r` None = error estándar clásico (ops independientes).

        Con operaciones que se solapan en el tiempo el error clásico se queda corto: hay que pasar
        el de un remuestreo por bloques de días (`exits.stats.cluster_se`), como hace T134.
        """
        n = len(rs)
        if n == 0:
            return cls(n=0, mean_r=0.0, se_r=0.0, m2_r=0.0)
        mean = sum(rs) / n
        m2 = sum(r * r for r in rs) / n
        if se_r is None:
            var = sum((r - mean) ** 2 for r in rs) / (n - 1) if n > 1 else 0.0
            se_r = math.sqrt(var / n) if n > 1 else 0.0
        return cls(n=n, mean_r=mean, se_r=se_r, m2_r=m2)


def lower_bound(e: Edge, z: float) -> float:
    """Límite inferior de E[R] con `z` errores estándar."""
    if e.n <= 0 or not math.isfinite(e.mean_r) or not math.isfinite(e.se_r):
        return 0.0
    return e.mean_r - z * e.se_r


def fraction(e: Edge, k: KellyParams) -> float:
    """Fracción del capital a arriesgar por operación. **0 si no hay ventaja demostrada.**

    Devuelve 0 cuando la muestra no llega a `n_min`, cuando el límite inferior de E[R] es ≤ 0 o
    cuando E[R²] no es positivo. Nunca devuelve un número negativo ni mayor que `frac`.
    """
    if e.n < k.n_min or e.m2_r <= 0 or not math.isfinite(e.m2_r):
        return 0.0
    lo = lower_bound(e, k.z)
    if lo <= 0:
        return 0.0
    return min(k.frac, k.frac * lo / e.m2_r)


def risk_pct(e: Edge, k: KellyParams, profile_risk_pct: float) -> float:
    """Riesgo por operación que el perfil debería usar: Kelly acotado por su propio tope.

    Nunca sube el riesgo del perfil: el tope es `max_risk_pct` si está puesto y, si no, el
    `risk_pct` declarado. Kelly aquí solo puede recortar.
    """
    top = k.max_risk_pct if k.max_risk_pct is not None else profile_risk_pct
    return max(0.0, min(top, fraction(e, k)))
