"""Partición por días contiguos con purga y embargo, y walk-forward (T80). Puras.

Reglas (López de Prado, adaptadas al carril HFT):
- la unidad de partición es el **día UTC**, nunca la fila: las variables tienen memoria de
  minutos y partir por filas filtra información de un lado al otro;
- **purga**: ninguna fila de entrenamiento puede tener su etiqueta dentro del tramo de prueba
  (se quitan las últimas `horizon_ms` del entrenamiento);
- **embargo**: además se descartan los `embargo_days` días anteriores al tramo de prueba, que es
  donde vive la autocorrelación lenta (volatilidad, régimen);
- **walk-forward**: se entrena siempre con el pasado y se prueba el día siguiente; ningún
  parámetro se elige con los días de prueba.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DAY_MS = 86_400_000


def day_of(t_ms: np.ndarray) -> np.ndarray:
    """Día UTC absoluto de cada instante (en días desde la época)."""
    return (np.asarray(t_ms, dtype=np.int64) // DAY_MS).astype(np.int64)


def runs_of_days(days) -> list[list[int]]:
    """Tramos de días consecutivos de una lista de días (ordenados y sin repetir)."""
    xs = sorted(set(int(d) for d in days))
    out: list[list[int]] = []
    for d in xs:
        if out and d == out[-1][-1] + 1:
            out[-1].append(d)
        else:
            out.append([d])
    return out


@dataclass(frozen=True)
class Fold:
    """Un pliegue del walk-forward: días de entrenamiento y días de prueba."""

    train: tuple[int, ...]
    test: tuple[int, ...]

    @property
    def label(self) -> str:
        return f"{self.test[0]}..{self.test[-1]}"


def walk_forward(days, train_days: int, test_days: int = 1, embargo_days: int = 1,
                 expanding: bool = False) -> list[Fold]:
    """Pliegues sobre el tramo contiguo más largo: entrenar con el pasado, probar el siguiente.

    `expanding` = usar todo el pasado disponible; si no, una ventana rodante de `train_days`.
    Entre entrenamiento y prueba quedan `embargo_days` días sin usar.
    """
    runs = runs_of_days(days)
    if not runs:
        return []
    span = max(runs, key=len)
    out: list[Fold] = []
    start = train_days + embargo_days
    for i in range(start, len(span), test_days):
        test = span[i:i + test_days]
        if len(test) < test_days:
            break
        lo = 0 if expanding else i - embargo_days - train_days
        train = span[lo:i - embargo_days]
        if train:
            out.append(Fold(tuple(train), tuple(test)))
    return out


def fold_masks(t_ms: np.ndarray, fold: Fold, horizon_ms: int
               ) -> tuple[np.ndarray, np.ndarray]:
    """(máscara de entrenamiento purgada, máscara de prueba) para las filas de `t_ms`."""
    d = day_of(t_ms)
    train = np.isin(d, np.asarray(fold.train, dtype=np.int64))
    test = np.isin(d, np.asarray(fold.test, dtype=np.int64))
    t0 = int(np.asarray(fold.test, dtype=np.int64).min()) * DAY_MS
    train &= np.asarray(t_ms, dtype=np.int64) + horizon_ms < t0       # purga por la etiqueta
    return train, test


def day_table(t_ms: np.ndarray) -> dict[int, int]:
    """Filas por día UTC (para declarar la muestra en el informe)."""
    d, c = np.unique(day_of(t_ms), return_counts=True)
    return {int(k): int(v) for k, v in zip(d.tolist(), c.tolist(), strict=True)}
