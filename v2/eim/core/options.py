"""Cadena de opciones en el snapshot (T214): la última toma de Deribit conocida a `asof`.

Las filas son las que guarda T213 (`eim/data/options_parse.normalize`), sin tocar: precios en la
**moneda base** (las opciones de Deribit son inversas), `mark_iv` en %, interés abierto con 8 h
de retraso, `expiry` a las 08:00 UTC. La lectura del disco vive en `eim/data/options_read.py`.
Fuente de nivel 1 y **solo uso personal** (◆ de T213): nada de esto se publica ni se reenvía.
"""

from __future__ import annotations

from typing import Literal

from eim.core.market import Frozen


class OptionRow(Frozen):
    """Una opción viva en la toma."""

    instrument: str
    expiry: int                       # ms UTC (08:00 del día del nombre)
    strike: float
    kind: Literal["call", "put"]
    bid: float | None = None          # cara vacía del libro = None (es un dato, no un hueco)
    ask: float | None = None
    mark: float
    mark_iv: float                    # %
    underlying: float                 # futuro o índice que Deribit usa para la IV del vencimiento
    rate: float = 0.0
    oi: float | None = None


class OptionChain(Frozen):
    """Toma completa de una moneda (todas las opciones vivas en una sola llamada)."""

    source: str                       # «deribit-options …»: la ficha `DERIBIT` de nivel 1
    currency: str
    taken_ms: int
    rows: list[OptionRow]
    n_dropped: int = 0                # filas incompletas que T213 descartó (contadas)
