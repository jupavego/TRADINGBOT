"""Velas de 1 min dentro de la escalera (`ladder.simulate_ladder`): el orden real de los precios.

Dos usos, con la MISMA regla dentro de cada minuto (manda el SL vigente al abrir el minuto; el
avance del minuto sube el SL desde el siguiente):
- Velas de 15 m **ambiguas** (pueden subir el SL y volver a tocarlo, T105): `sub_bars`.
- **Vela del llenado de una entrada límite** (T223): `fill_bar`. El orden dentro del minuto del
  llenado no se conoce, así que en él solo se comprueba el SL vigente (como hacía la vela entera);
  desde el minuto siguiente la posición está viva y el avance cuenta, igual que en una entrada a
  mercado. Antes la escalera no miraba la vela del llenado y una límite llenada a la apertura no
  podía proteger nada en sus primeros 15 min: seis operaciones de 1 h de T143 entraron al mismo
  precio y minuto que en T31 y salieron por el SL inicial en vez de por stop dinámico (−7,2 R).

Sin velas finas completas y válidas para la vela gruesa, cada uso devuelve «no resuelto» y la
escalera se queda con la regla conservadora. `run` es el `_Run` de `ladder.py`. Puro: sin I/O.
"""

from __future__ import annotations

import numpy as np

from eim.paper.engine import Path, _funding
from eim.paper.ideas import Idea
from eim.paper.ladder_floor import adopt
from eim.paper.params import ExecParams

Hit = tuple[str, float, int]          # (motivo, precio de salida, instante de salida)


def fine_covers(fine: Path | None, t0: int, step: int) -> bool:
    """¿Hay velas finas completas y válidas para toda la vela gruesa [t0, t0+step)?"""
    if fine is None or not len(fine.t):
        return False
    a, b = int(np.searchsorted(fine.t, t0)), int(np.searchsorted(fine.t, t0 + step))
    if b - a != step // fine.step:
        return False
    return bool(np.isfinite(fine.o[a:b]).all() and np.isfinite(fine.h[a:b]).all()
                and np.isfinite(fine.l[a:b]).all())


def sub_bars(run, fine: Path, path: Path, ep: ExecParams, fill_t: int, t0: int, step: int,
             cj, reserve: float) -> Hit | None:
    """Recorre las velas finas de [t0, t0+step), en orden real: en cada una manda el SL vigente
    al abrirla y el avance sube el SL desde la siguiente. (motivo, precio, t) si cierra."""
    a, b = int(np.searchsorted(fine.t, t0)), int(np.searchsorted(fine.t, t0 + step))
    s = run.s
    for m in range(a, b):
        o, h, lo = float(fine.o[m]), float(fine.h[m]), float(fine.l[m])
        end = int(fine.t[m]) + fine.step
        adopt(run, int(fine.t[m]))
        if (lo <= run.stop) if s > 0 else (h >= run.stop):
            gap = (o <= run.stop) if s > 0 else (o >= run.stop)
            return ("SLD" if run.protected else "SL"), (o if gap else run.stop), end
        fund = _funding(path, s, fill_t, end, ep)[0] + reserve
        run.ext.see(h if s > 0 else lo, lo if s > 0 else h)
        run.apply(run.peek(h if s > 0 else lo, fund, cj), end, cj)
    return None


def fill_minute(idea: Idea, fine: Path, t0: int, step: int) -> int | None:
    """Índice del primer minuto de [t0, t0+step) que toca el precio límite; None si ninguno
    (las velas finas no cuadran con la gruesa: se queda la regla conservadora)."""
    a, b = int(np.searchsorted(fine.t, t0)), int(np.searchsorted(fine.t, t0 + step))
    touch = (fine.l[a:b] <= idea.entry) if idea.side > 0 else (fine.h[a:b] >= idea.entry)
    idx = np.flatnonzero(touch)
    return a + int(idx[0]) if len(idx) else None


def fill_bar(run, idea: Idea, fine: Path | None, path: Path, ep: ExecParams, k: int, cj,
             reserve: float) -> tuple[bool, Hit | None]:
    """(¿resuelta con 1 min?, cierre si lo hubo) de la vela `k` en la que se llenó una límite.

    En el minuto del llenado solo se comprueba el SL vigente (sin hueco: el llenado fue antes);
    el resto de la vela se recorre con `sub_bars`, desde el minuto siguiente."""
    t0, step = int(path.t[k]), path.step
    m0 = fill_minute(idea, fine, t0, step) if fine_covers(fine, t0, step) else None
    if m0 is None:
        return False, None
    s, end = run.s, int(fine.t[m0]) + fine.step
    adopt(run, int(fine.t[m0]))
    if (float(fine.l[m0]) <= run.stop) if s > 0 else (float(fine.h[m0]) >= run.stop):
        return True, (("SLD" if run.protected else "SL"), run.stop, end)
    return True, sub_bars(run, fine, path, ep, int(path.t[k]), end, t0 + step - end, cj, reserve)
