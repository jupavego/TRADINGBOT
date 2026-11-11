"""Reglas nativas por agente (T168). Cada módulo `rules/<agente>.py` declara:

- `EXPOSES`: las rutas del reporte de su agente que la cantera sabe leer (las que el agente
  publica de verdad; un prospecto que pida otra falla al cargar);
- `RULES`: `{id del prospecto: función pura (View, parámetros) → Signal}`.
"""

from __future__ import annotations

from types import ModuleType

from eim.nursery.rules import (
    bots,
    derivatives,
    elliott,
    ema,
    levels,
    liquidations,
    literature,
    microstructure,
    price_action,
    regime,
    structure,
    technical,
    vwap,
)

MODULES: dict[str, ModuleType] = {
    "bots": bots, "derivatives": derivatives, "elliott": elliott, "ema": ema, "levels": levels,
    "liquidations": liquidations, "literature": literature, "microstructure": microstructure,
    "price_action": price_action, "regime": regime, "structure": structure,
    "technical": technical, "vwap": vwap,
}
