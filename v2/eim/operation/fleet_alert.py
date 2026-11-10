"""Aviso al usuario de que el conjunto se cayó o se levantó solo (T148, entregable 5).

Un apagón no puede enterarse solo el registro. El 2026-11-09 los cinco servicios estuvieron
parados 5 h 26 min y lo que acabó con el apagón fue que una persona mirara; nada le avisó. Así que
el vigilante del conjunto (`fleet_watch.py`) habla por donde ya habla `usage_alert.py`: el registro
de operación (`data/operation/logs/op-*.jsonl`, que el icono de la bandeja lee) y la notificación
de Windows.

Qué se dice y cuándo, que es lo que importa de un aviso:

- **se levantó solo**: cuánto llevaba caído y quién faltaba. Sin esto, un apagón de media hora que
  el vigilante arregla no deja huella que nadie vea, y la cuenta de T78 se encuentra rota sin
  explicación;
- **no arranca** (código de salida distinto de 0): el vigilante seguirá intentándolo, pero con
  espera creciente;
- **sigue caído y hay que mirarlo a mano**: el último intento falló. A partir de aquí el vigilante
  calla durante `GIVE_UP_S` y la persona es el único recurso que queda, así que el aviso es
  crítico.

Los tres llevan la misma clave (`KEY`), de modo que el «resuelta» cierra cualquiera de ellos.
"""

from __future__ import annotations

from collections.abc import Callable

from eim.operation.alerts import CRITICAL, INFO, SERVICE, WARN, Alert

KEY = "conjunto_caido"


def _how_long(down_s: float) -> str:
    return f"{down_s / 3600:.1f} h" if down_s >= 3600 else f"{down_s / 60:.0f} min"


def alert_for(action: str, missing: tuple[str, ...], down_s: float, tries: int, max_tries: int,
              rc: int | None, give_up_s: float, waiting: bool = False) -> Alert | None:
    """El aviso que toca, o None si esta pasada no tiene nada que contar.

    Sin reloj dentro: `fleet_watch` le pone la hora, que es la de la pasada."""
    who = ", ".join(missing) or "ninguno"
    horas = _how_long(down_s)
    rendido = (f"{who} llevan {horas} sin latido y {tries} arranques han fallado; no se reintenta "
               f"hasta {give_up_s / 3600:.0f} h después")
    if action == "recuperado":
        return Alert(0, SERVICE, INFO, "Resuelta: el conjunto del EIM estaba caído",
                     f"levantado tras {horas} sin latido ({who})", KEY, resolved=True)
    if action == "levantar" and rc not in (0, None):
        if tries >= max_tries:          # el último intento: a partir de aquí manda la persona
            return Alert(0, SERVICE, CRITICAL, "El EIM sigue caído y hay que mirarlo a mano",
                         rendido, KEY)
        return Alert(0, SERVICE, CRITICAL, "El conjunto del EIM no arranca",
                     f"{who} llevan {horas} sin latido; el arranque salió con código {rc} "
                     f"(intento {tries} de {max_tries})", KEY)
    if action == "levantar":
        return Alert(0, SERVICE, WARN, "El conjunto del EIM estaba caído",
                     f"{who} llevaban {horas} sin latido; lanzado servicio_continuo.ps1 "
                     f"(intento {tries} de {max_tries})", KEY)
    if action == "rendirse" and not waiting:
        return Alert(0, SERVICE, CRITICAL, "El EIM sigue caído y hay que mirarlo a mano",
                     rendido, KEY)
    return None


def announce(a: Alert, log_sink: Callable[[Alert], None], toast: Callable[[Alert], None] | None,
             on_error: Callable[[str], None]) -> None:
    """Deja el aviso en el registro y, si se puede, en la pantalla.

    Un canal roto no puede dejar el conjunto sin levantar: el registro va primero y el error de la
    notificación se anota, no se lanza."""
    log_sink(a)
    if toast is None:
        return
    try:
        toast(a)
    except Exception as e:  # noqa: BLE001 - el aviso ya quedó en el registro
        on_error(f"{type(e).__name__}: {e}")
