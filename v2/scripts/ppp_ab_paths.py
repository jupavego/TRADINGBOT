"""Caminos de precios para el A/B de T111: velas de 1 min leídas como arreglos y la cota
optimista sintética del orden dentro de la vela."""

from __future__ import annotations

from pathlib import Path as FsPath

import numpy as np

from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.paper.engine import Path


def fine_path(root: FsPath, symbol: str) -> Path | None:
    """Velas de 1 min como arreglos (millones de filas: sin un objeto por vela), de los dos
    tramos del almacén. None si el almacén no las tiene."""
    st = Store(root)
    if st.bounds(symbol, "1m") is None:
        return None
    return Path.from_arrays(st.read_arrays(symbol, "1m"), tf_ms("1m"))


def optimistic_fine(path: Path, side: int) -> Path:
    """Velas «finas» sintéticas (4 por vela de 15 m) con el orden de precios MÁS favorable a la
    escalera de ese lado: primero el extremo a favor (sube el stop) y luego el contrario. Da una
    COTA SUPERIOR de B donde no hay velas de 1 min; no es un dato real."""
    sub = path.step // 4
    a, b = (path.h, path.l) if side > 0 else (path.l, path.h)
    so = np.stack([path.o, a, b, path.c], 1).ravel()
    sc = np.stack([a, b, path.c, path.c], 1).ravel()
    f = Path([], (), sub)
    f.t = (np.repeat(path.t, 4) + np.tile(np.arange(4) * sub, len(path.t))).astype(np.int64)
    f.o, f.c, f.h, f.l = so, sc, np.maximum(so, sc), np.minimum(so, sc)
    return f
