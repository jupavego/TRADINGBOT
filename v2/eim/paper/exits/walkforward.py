"""Walk-forward del banco con purga y embargo (T131, E1 de §8 de `PLAN/notas/T129_sl_dinamico.md`).

Tramos de §5.3: 12 meses de ajuste y 3 de prueba, con paso de 3 meses. Los tramos de prueba son
contiguos y cubren todo el periodo; el que se recorta es el de ajuste, que es lo honesto:

- **Purga:** una operación no entra en el ajuste si se CIERRA dentro del tramo de prueba. Una
  posición abierta al final del ajuste conoce precios de la prueba: si se queda, el ajuste ve el
  futuro.
- **Embargo:** además se deja un hueco entre el final del ajuste y el principio de la prueba, de
  al menos la duración **p99** de las operaciones de la política y al menos la ventana más larga de
  sus rasgos (los rasgos de la prueba miran atrás, hasta el ajuste). Todo lo que se cierre dentro
  del hueco también sale del ajuste.

`leaks` es la comprobación que pide la aceptación de T131: con los tramos y las operaciones
elegidas, ninguna operación del ajuste se cierra dentro de su prueba ni de su embargo.

Puro: sin red y sin disco.
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from eim.paper.exits.bench import BenchTrade

FIT_MONTHS, TEST_MONTHS, STEP_MONTHS = 12, 3, 3
P99 = 0.99


def iso(t: int) -> str:
    return datetime.fromtimestamp(t / 1000, UTC).isoformat(timespec="minutes")


def add_months(t: int, n: int) -> int:
    """`t` (ms UTC) más `n` meses naturales, conservando el día (recortado al fin de mes)."""
    d = datetime.fromtimestamp(t / 1000, UTC)
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return int(d.replace(year=y, month=m, day=min(d.day, monthrange(y, m)[1])).timestamp() * 1000)


@dataclass(frozen=True)
class Fold:
    """Un pliegue: ajuste [fit_from, fit_to), embargo y prueba [test_from, test_to)."""

    k: int
    fit_from: int
    fit_to: int
    test_from: int
    test_to: int
    embargo_ms: int

    @property
    def fit_cut(self) -> int:
        """Instante tras el que una operación del ajuste ya no cuenta (purga + embargo)."""
        return self.test_from - self.embargo_ms

    def to_json(self) -> dict:
        return {"k": self.k, "fit": [iso(self.fit_from), iso(self.fit_to)],
                "test": [iso(self.test_from), iso(self.test_to)],
                "embargo_hours": round(self.embargo_ms / 3_600_000, 2),
                "fit_cut": iso(self.fit_cut)}


def folds(start: int, end: int, embargo_ms: int = 0, fit_months: int = FIT_MONTHS,
          test_months: int = TEST_MONTHS, step_months: int = STEP_MONTHS) -> list[Fold]:
    """Pliegues completos dentro de [start, end). Solo entran los que caben enteros."""
    out, k, cursor = [], 0, start
    while True:
        fit_to = add_months(cursor, fit_months)
        test_to = add_months(fit_to, test_months)
        if test_to > end:
            break
        out.append(Fold(k, cursor, fit_to, fit_to, test_to, embargo_ms))
        k += 1
        cursor = add_months(cursor, step_months)
    return out


def embargo_for(trades: Sequence[BenchTrade], feature_ms: int = 0, q: float = P99) -> int:
    """Embargo: el mayor entre la duración p99 de las operaciones y la ventana de los rasgos."""
    if not trades:
        return int(feature_ms)
    d = np.array([t.elapsed_ms for t in trades], dtype=float)
    return int(max(float(np.quantile(d, q)), float(feature_ms)))


def fit_trades(trades: Sequence[BenchTrade], fold: Fold) -> list[BenchTrade]:
    """Operaciones del ajuste: decididas en el tramo y CERRADAS antes del corte (purga+embargo)."""
    return [t for t in trades
            if fold.fit_from <= t.t < fold.fit_to and t.exit_t <= fold.fit_cut]


def test_trades(trades: Sequence[BenchTrade], fold: Fold) -> list[BenchTrade]:
    """Operaciones de la prueba: decididas dentro del tramo de prueba."""
    return [t for t in trades if fold.test_from <= t.t < fold.test_to]


def purged(trades: Sequence[BenchTrade], fold: Fold) -> dict[str, int]:
    """Cuántas operaciones del tramo de ajuste se cayeron, y por qué."""
    inside = [t for t in trades if fold.fit_from <= t.t < fold.fit_to]
    return {"in_window": len(inside), "kept": sum(1 for t in inside if t.exit_t <= fold.fit_cut),
            "purged_into_test": sum(1 for t in inside if t.exit_t >= fold.test_from),
            "embargoed": sum(1 for t in inside
                             if fold.fit_cut < t.exit_t < fold.test_from)}


def leaks(fit: Sequence[BenchTrade], fold: Fold) -> list[str]:
    """Fugas entre tramos: vacío = ninguna operación del ajuste alcanza la prueba ni el embargo."""
    out = []
    for t in fit:
        if t.exit_t >= fold.test_from:
            out.append(f"{t.id}: cierra en {t.exit_t}, dentro de la prueba del pliegue {fold.k}")
        elif t.exit_t > fold.fit_cut:
            out.append(f"{t.id}: cierra en {t.exit_t}, dentro del embargo del pliegue {fold.k}")
        elif not fold.fit_from <= t.t < fold.fit_to:
            out.append(f"{t.id}: decidida en {t.t}, fuera del ajuste del pliegue {fold.k}")
    return out


def slices_by_fold(trades: Sequence[BenchTrade], fs: Sequence[Fold]) -> list[list[BenchTrade]]:
    """Las operaciones de prueba de cada pliegue: los tramos que alimentan el PBO (CSCV)."""
    return [test_trades(trades, f) for f in fs]
