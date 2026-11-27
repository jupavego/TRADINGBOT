"""La interfaz también se vigila (T206, 2026-11-26).

Cuando T148 montó el vigilante del conjunto, el usuario decidió vigilar **solo los cinco servicios
de datos**, sin `-ConWeb`: son los que pierden información si se paran. La interfaz no pierde nada,
así que se quedó fuera.

Lo que enseñó el 2026-11-25: Vite murió a las 16:27 UTC arrastrado por uno de los cuelgues de la
API y **nadie la levantó en siete horas**. Los cinco servicios estaban vivos, el vigilante decía
«ok» en cada pasada y el icono del escritorio no abría nada. Para quien usa el EIM eso es
exactamente estar caído, y ya había pasado igual el 2026-11-20 (`PLAN/T206.md` §1). No pierde
datos, pero deja al usuario sin forma de verlos, y levantarla cuesta lo mismo que no hacerlo:
`servicio_continuo.ps1 -ConWeb` es idempotente y no toca lo que ya corre.

Va aparte de los cinco a propósito: su propia cuenta, su propia espera creciente y su propio
aviso, para que una interfaz que no arranque no gaste los intentos de la captura ni del bróker.
Se apaga con `EIM_FLEET_WEB=0`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from eim.operation.alerts import CRITICAL, INFO, SERVICE, WARN, Alert
from eim.operation.fleet_state import State

PORT = 5173
DOWN_S = 600.0                            # lo mismo que los cinco: dos pasadas sin escuchar
MAX_TRIES = 4
BACKOFF_S = (0.0, 300.0, 900.0, 3600.0)
GIVE_UP_S = 21_600.0
ENV = "EIM_FLEET_WEB"


def enabled() -> bool:
    return os.environ.get(ENV, "") != "0"


@dataclass(frozen=True)
class WebDecision:
    """Qué hacer con la interfaz en esta pasada."""

    action: str = "ok"        # "ok" | "recuperada" | "levantar" | "esperar" | "rendirse"
    down_s: float = 0.0
    tries: int = 0
    wait_s: float = 0.0

    @property
    def lift(self) -> bool:
        return self.action == "levantar"

    @property
    def holding(self) -> bool:
        return self.action in ("esperar", "rendirse")


def decide(listening: bool | None, st: State, now_ms: int, down_s: float = DOWN_S,
           max_tries: int = MAX_TRIES) -> WebDecision:
    """Regla pura: lo que ve el puerto y lo que pasó antes → qué hacer ahora.

    Una sonda que no puede responder (`None`) no cuenta: no se levanta nada por no saber.
    """
    if listening is None:
        return WebDecision("ok")
    if listening:
        return WebDecision("recuperada", round((now_ms - st.web_down_since_ms) / 1000, 1)
                           ) if st.web_down_since_ms or st.web_tries else WebDecision("ok")
    since = st.web_down_since_ms or now_ms
    elapsed = round((now_ms - since) / 1000, 1)
    if elapsed < down_s:
        return WebDecision("esperar", elapsed, st.web_tries, round(down_s - elapsed, 1))
    tries = st.web_tries
    if st.web_gave_up_ms is not None:
        if now_ms - st.web_gave_up_ms < GIVE_UP_S * 1000:
            return WebDecision("rendirse", elapsed, tries,
                               round(GIVE_UP_S - (now_ms - st.web_gave_up_ms) / 1000, 1))
        tries = 0
    if tries >= max_tries:
        return WebDecision("rendirse", elapsed, tries)
    wait = BACKOFF_S[min(tries, len(BACKOFF_S) - 1)] * 1000
    if tries and st.web_last_try_ms is not None and now_ms - st.web_last_try_ms < wait:
        return WebDecision("esperar", elapsed, tries,
                           round((wait - (now_ms - st.web_last_try_ms)) / 1000, 1))
    return WebDecision("levantar", elapsed, tries + 1)


def remember(st: State, d: WebDecision, now_ms: int, rc: int | None) -> None:
    """Deja en el estado lo que esta pasada tiene que contarle a la siguiente."""
    if d.action == "recuperada":
        st.web_down_since_ms = st.web_last_try_ms = st.web_gave_up_ms = None
        st.web_tries = 0
    elif d.action == "levantar":
        st.web_tries, st.web_last_try_ms = d.tries, now_ms
        st.web_down_since_ms = st.web_down_since_ms or now_ms - int(d.down_s * 1000)
        if d.tries == 1:
            st.web_gave_up_ms = None
        if d.tries >= MAX_TRIES and rc not in (0, None):
            st.web_gave_up_ms = now_ms
    elif d.action == "rendirse" and not d.wait_s:
        st.web_gave_up_ms = now_ms
    elif d.action == "esperar":
        st.web_down_since_ms = st.web_down_since_ms or now_ms - int(d.down_s * 1000)


KEY = "interfaz_caida"


def alert(d: WebDecision, now_ms: int, rc: int | None) -> Alert | None:
    """El aviso de esta pasada, o `None` si no merece ninguno. Misma clave para los tres, así que
    el de vuelta cierra cualquiera de los otros."""
    if d.action == "recuperada":
        return Alert(now_ms, SERVICE, INFO, "Interfaz del EIM, de vuelta",
                     f"Estuvo {d.down_s / 60:.0f} min sin responder.", KEY, True)
    if d.action == "levantar":
        nivel = WARN if rc in (0, None) else CRITICAL
        return Alert(now_ms, SERVICE, nivel,
                     f"Levantando la interfaz del EIM ({d.tries}.º intento)",
                     f"El puerto {PORT} lleva {d.down_s / 60:.0f} min sin escuchar"
                     + ("." if rc in (0, None) else f"; el arranque devolvió {rc}."), KEY)
    if d.action == "rendirse" and not d.wait_s:
        return Alert(now_ms, SERVICE, CRITICAL, "La interfaz del EIM no arranca",
                     f"{MAX_TRIES} intentos sin conseguirlo. Los datos siguen llegando; lo que "
                     f"falta es la pantalla (`servicio_continuo.ps1 -ConWeb`).", KEY)
    return None
