"""Piezas comunes de las reglas nativas (T168, entregable 2). Puro: sin red, disco ni estado.

Una regla recibe una `View` y los parámetros canónicos del prospecto y devuelve una `Signal`:

- `enter`: lado a abrir en el cierre de esta vela (+1, −1; 0 = nada);
- `hold`: lado que la regla sostiene ahora (None = no opina); la plantilla `rule_flip` sale cuando
  opina y no coincide con el de la posición (0 = ya no sostiene ninguno);
- `target`: precio objetivo (plantilla `mean_target`: la media de referencia).

La `View` solo deja leer las variables que el prospecto declaró (otra lectura lanza
`UndeclaredVariable`, que no se silencia) y solo contextos con `t ≤` la vela actual: la vela
siguiente no existe para la regla.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from eim.nursery.native import HORIZON_KEY, stored_key


class UndeclaredVariable(Exception):
    """La regla leyó una variable que su prospecto no declaró (error de programación)."""


@dataclass(frozen=True)
class Signal:
    enter: int = 0
    hold: int | None = None
    target: float | None = None


NONE = Signal()


@dataclass(frozen=True)
class View:
    """Variables declaradas de un agente en la vela actual y en las anteriores (más reciente al
    final). `close` y `atr` son los del contexto de esa vela."""

    agent: str
    declared: frozenset[str]
    rows: tuple[Mapping[str, Any] | None, ...]     # ≤ vela actual; la última es la actual
    close: float | None = None
    atr: float | None = None

    def _row(self, back: int) -> Mapping[str, Any] | None:
        return self.rows[-1 - back] if back < len(self.rows) else None

    def get(self, name: str, back: int = 0) -> Any:
        """Valor de la variable `name` hace `back` velas (0 = ahora); None si falta."""
        if name not in self.declared:
            raise UndeclaredVariable(f"{self.agent}: {name} no está declarada")
        row = self._row(back)
        return None if row is None else row.get(stored_key(name))

    def has(self, back: int = 0) -> bool:
        """¿Hubo reporte del agente hace `back` velas?"""
        return self._row(back) is not None

    @property
    def horizon(self) -> int | None:
        row = self._row(0)
        h = row.get(HORIZON_KEY) if row is not None else None
        return int(h) if isinstance(h, (int, float)) and h > 0 else None


def sign(x: float | None) -> int:
    return 0 if x is None else 1 if x > 0 else -1 if x < 0 else 0


def num(x: Any) -> float | None:
    """Número o None (cadenas, listas y booleanos no son números)."""
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def nums(xs: Any) -> list[float]:
    return [v for v in (num(x) for x in (xs or [])) if v is not None] if isinstance(
        xs, (list, tuple)) else []


def steady(side: int) -> Signal:
    """Condición de estado (no de transición): entra y sostiene el mismo lado."""
    return Signal(enter=side, hold=side)


def first_of(rows: Sequence[Any]) -> Any:
    return rows[0] if rows else None
