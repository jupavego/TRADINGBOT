"""Rastro de la tarea del bucle de operación dentro de la API.

`asyncio.create_task(Supervisor(op).run())` no avisaba si la tarea moría: la API seguía
respondiendo HTTP sin ciclos y solo el vigilante lo notaba, con el latido parado 15 min (así pasó
el 2026-10-24). Ahora, si la tarea termina sin que la cancelen (el apagado normal de la API sí
la cancela), deja rastro: línea `bucle_detenido` en el registro de operación, alerta crítica
«servicio», error en el observatorio, la traza en el stderr del proceso (el vigilante guarda su
cola al reiniciar) y el estado `caido` en `/v2/operation`. No relanza nada: eso es del vigilante.
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from eim.observability import hooks_service
from eim.operation.alerts import CRITICAL, SERVICE, Alert
from eim.operation.supervisor import Operation

STOPPED = "bucle_detenido"


def watch_supervisor(task: asyncio.Task, op: Operation) -> asyncio.Task:
    """Engancha a `task` (el `Supervisor.run` de `op`) el aviso de muerte; devuelve la tarea."""
    task.add_done_callback(lambda t: on_done(t, op))
    return task


def on_done(task: asyncio.Task, op: Operation) -> None:
    if task.cancelled():
        return                                      # apagado normal de la API
    exc = task.exception()
    why = f"{type(exc).__name__}: {exc}" if exc is not None else "terminó sin error"
    if exc is not None:
        traceback.print_exception(exc, file=sys.stderr)
    st = op.status
    st["state"], st["last_error"] = "caido", why[:500]
    hooks_service.service_error("operation.supervisor", exc or why, mode=op.desk.mode)
    try:
        op.log.write(STOPPED, "error", error=why, cycles=st["cycles"])
        op.alerts.emit(Alert(op.clock(), SERVICE, CRITICAL, "El bucle de operación se detuvo",
                             f"{why}. La API responde pero sin ciclos; el vigilante la relanzará "
                             "cuando note el latido parado.", SERVICE))
    except Exception as e:  # noqa: BLE001 - el aviso nunca falla en silencio
        print(f"{STOPPED}: {why}; aviso fallido: {type(e).__name__}: {e}", file=sys.stderr,
              flush=True)
