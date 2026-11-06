"""¿Sigue escuchando el servicio en su puerto? (T140)

El latido lo escribe una tarea del mismo bucle que atiende el puerto, así que no dice si el puerto
sigue abierto. El 2026-11-06 `asyncio` cerró el socket de escucha tras un `WinError 64` y la API
pasó casi 12 h sin puerto, con el proceso vivo y el latido al día, sin que nadie lo notara
(`PLAN/notas/T140_api_sin_puerto.md`).

Se mira la tabla de puertos del sistema en vez de conectarse. Con el bucle bloqueado el socket sigue
en escucha, de modo que un bloqueo no se confunde con un socket perdido. Y ninguna sonda puede
provocar el fallo con una conexión que se corta antes de aceptarse.
"""

from __future__ import annotations

import socket
import time
from collections.abc import Callable

from eim.operation import usage_win

Probe = Callable[[], bool | None]

GRACE_S = 1200.0        # arranque: mayor que los 900 s del latido, que ya cubren uno colgado
LOST_S = 120.0          # sostenido: tiempo sin escuchar para reiniciar, una vez visto abierto
CONNECT_TIMEOUT_S = 5.0  # en Windows, una conexión rechazada en loopback tarda unos 2 s


def _in_table(port: int) -> bool:
    if not usage_win.supported():
        return False
    try:
        return port in usage_win.listeners({port})
    except OSError:
        return False


def listening(port: int, host: str = "127.0.0.1",
              timeout_s: float = CONNECT_TIMEOUT_S) -> bool | None:
    """True si alguien escucha en `port`, False si nadie, None si no se pudo saber.

    Que no figure en la tabla no basta para decir que no: la consulta puede fallar sin avisar. Solo
    entonces se intenta conectar, y como nadie figura en escucha no hay socket al que dañar.
    """
    if _in_table(port):
        return True
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except ConnectionRefusedError:
        return False
    except OSError:
        return None


class PortWatch:
    """Decide cuándo un puerto que no escucha justifica reiniciar. Uno por cada lanzamiento.

    Hasta verlo abierto por primera vez manda `grace_s`, porque un arranque con el equipo cargado
    tardó 7 min. Una vez visto, basta con `lost_s` seguidos sin escuchar. Una sonda que no puede
    responder (None) o que falla no cuenta ni a favor ni en contra.
    """

    def __init__(self, probe: Probe, grace_s: float = GRACE_S, lost_s: float = LOST_S,
                 clock: Callable[[], float] = time.time) -> None:
        self.probe, self.grace_s, self.lost_s, self.clock = probe, grace_s, lost_s, clock
        self.started = clock()
        self.seen = False
        self.down_since: float | None = None

    def check(self) -> str | None:
        """El motivo para reiniciar, o None si todavía no lo hay."""
        try:
            state = self.probe()
        except Exception:  # noqa: BLE001 - una sonda rota nunca tumba al vigilante
            return None
        if state is None:
            return None
        if state:
            self.seen, self.down_since = True, None
            return None
        now = self.clock()
        if self.down_since is None:
            self.down_since = now
        if self.seen:
            down = now - self.down_since
            return f"puerto sin escuchar {down:.0f} s" if down >= self.lost_s else None
        waited = now - self.started
        if waited < self.grace_s:
            return None
        return f"puerto sin escuchar {waited:.0f} s: no llegó a abrirse"
