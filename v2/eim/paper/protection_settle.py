"""Lo que el diario de la protección aún no puede guardar (T142).

Una vela de 15 m ambigua (puede subir el SL y volver a tocarlo) se resuelve con sus velas de 1 min.
Sin ellas, `ladder.simulate_ladder` aplica la regla conservadora: sube el escalón al cierre de la
vela y da la operación por viva. Eso vale para una vista que se recalcula, pero no para el diario:
lo guardado es un suelo que ya no baja. Si al llegar las velas de 1 min resulta que la operación
cerró dentro de esa vela por debajo del suelo, `protection_sync._never_lower` la retiene y,
retenida, no se cierra sola (decisión de T110). Así quedaron 5 operaciones el 2026-11-04.

El 15 m y el 1 min llegan por caminos distintos: el 1 min solo lo trae el tick del bróker (cada
~62 s), y la pasada usa lo que había cuando empezó a calcular. Por eso el diario espera: de cada
operación guarda el alta y los cambios hasta el primero que dependa de una vela sin sus velas de
1 min completas. El resto, y el cierre, los guarda una pasada posterior, ya con el orden real. La
vista y los libros no cambian: el historial sigue siendo el del recálculo.

La espera no tiene plazo si la cola del 1 min no ha llegado, porque tarde o temprano se sincroniza
(`data.sync.sync_candles`) y mientras tanto no se pierde nada: el recálculo da lo mismo. Un hueco
INTERIOR puede no rellenarse nunca, si Binance no tiene ese minuto: `sync_candles` lo reintenta en
cada ciclo y, cuando la cola lo rebasa en `HOLE_WAIT_MS`, la regla conservadora ya es definitiva.

Puro: sin I/O. Los que esperan salen en `PassResult.waiting` y en la vista (`waiting_fine`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from eim.data.timeframes import tf_ms
from eim.paper.engine import Path
from eim.paper.ladder import _fine_covers
from eim.paper.params import ExecParams
from eim.paper.protection_ops import Cur

HOLE_WAIT_MS = 3_600_000
Ready = Callable[[int], bool]


def gate(fine: Path | None, ep: ExecParams) -> Ready | None:
    """Función «¿lo fijado en el instante `t` ya no puede cambiar?»; None si no hay velas de 1 min
    que esperar (ningún perfil las usa o el almacén no las tiene)."""
    if fine is None or not len(fine.t):
        return None
    step, end = tf_ms(ep.path_tf), fine.end

    def ready(t: int) -> bool:
        close = (t - 1) // step * step + step       # cierre de la vela gruesa que contiene `t`
        if end < close:
            return False
        return end >= close + HOLE_WAIT_MS or _fine_covers(fine, close - step, step)

    return ready


def settled(c: Cur, ready: Ready | None) -> tuple[Cur, bool]:
    """(la operación recortada a lo que ya no puede cambiar, ¿quedó algo a la espera?)."""
    if ready is None:
        return c, False
    hist = c.info["stop_history"]
    n = next((k for k, h in enumerate(hist) if h["source"] != "recuperado" and not ready(h["t"])),
             len(hist))
    if n == len(hist) and (c.close is None or ready(c.close["exit_t"])):
        return c, False
    last = hist[n - 1] if n else None
    return replace(c, close=None, info={
        **c.info, "stop_history": hist[:n], "active": last.get("active", True) if last else False,
        "level": last["level"] if last else 0, "stop": last["stop"] if last else c.initial_sl,
        "max_float_usd": last["max_float"] if last else None,
        "stop_source": last["source"] if last else "inicial"}), True
