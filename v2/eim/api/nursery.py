"""`GET /v2/nursery`: lectura del libro de la cantera (T168). Solo lectura, sin POST. SIMULADO.

Por cuenta (prospectos y controles, que no cuentan como prospectos): rentabilidad neta acumulada %,
saldo, curva de capital, drawdown máximo, n, acierto, costo pagado, etapa y R neto con IC frente a
sus gemelos aleatorios. Con la cantera apagada (`EIM_NURSERY=0`, por defecto) lo dice y no inventa
nada.

T171: con el pre-registro, la respuesta trae además `panel` (la panorámica por agente de la pestaña
«Cantera», `eim/nursery/panel.py`) y `GET /v2/nursery/prospect/{id}` da la ficha de un prospecto:
teoría, variables, parámetros citados, obras a favor y en contra, curva y operaciones.

Espejo (2026-11-20, `eim/nursery/mirror.py`): en el equipo que corre la cantera la respuesta lleva
`mirror_publish` (estado de la publicación); en los demás, con la cantera apagada, la respuesta es
la última foto publicada con `mirror` (equipo de origen y hora), o `OFF` mientras no llegue.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from eim.nursery.desk import NurseryDesk
from eim.nursery.mirror import NurseryMirror

# T170 ya la encendió (alta 2026-11-17 03:25:17 UTC), pero solo en el equipo que la corre
# (`juanpablo-cpu`, `PLAN/CONDICIONANTES.md`): en los demás `EIM_NURSERY` sigue en 0 a propósito,
# para que no haya dos canteras con relojes distintos para el mismo pre-registro.
OFF = {"mode": "SIMULADO", "enabled": False, "machine_off": True,
       "reason": "La cantera no corre en este equipo (EIM_NURSERY=0). T170 ya la encendió el "
                 "2026-11-17 en el equipo que la corre (juanpablo-cpu): allí opera sola, en "
                 "vivo, y sus cifras se ven en esta pestaña."}
MIRROR_CARD = ("Aquí se ve el espejo de la cantera: la ficha completa del prospecto (operaciones y "
               "curva) se abre en el equipo que la corre.")


def live_payload(desk: NurseryDesk) -> dict:
    """Lo que devuelve `GET /v2/nursery` con la cantera corriendo en este equipo."""
    s = desk.summary()
    base = {"mode": "SIMULADO", "enabled": True, "variant": desk.name, "label": desk.label,
            "live": desk.live_status()}
    if s is None:
        return {**base, "accounts": [], "reason": "primer cálculo en curso"}
    return {**base, **s}


def mirror_payload(mirror: NurseryMirror | None) -> dict:
    """Con la cantera apagada aquí: la última foto del equipo que la corre, si llegó (espejo)."""
    if mirror is None:
        return dict(OFF)
    if mirror.latest is None:
        why = mirror.error or "esperando la primera foto del equipo que corre la cantera"
        return {**OFF, "mirror": {**mirror.status(), "waiting": True},
                "reason": f"{OFF['reason']} Espejo: {why}."}
    snap = mirror.latest
    return {**snap, "enabled": True,
            "mirror": {**snap.get("mirror", {}), "read_ms": mirror.last_ok_ms,
                       "error": mirror.error}}


def build_nursery_router(desk: NurseryDesk | None,
                         mirror: NurseryMirror | None = None) -> APIRouter:
    router = APIRouter(prefix="/v2/nursery")

    @router.get("")
    def nursery(account: str | None = Query(None, description="una sola cuenta")) -> dict:
        if desk is None:
            return mirror_payload(mirror)
        out = live_payload(desk)
        if account is not None and "accounts" in out:
            out = {**out, "accounts": [a for a in out["accounts"] if a["account"] == account]}
        if mirror is not None:
            out["mirror_publish"] = mirror.status()
        return out

    @router.get("/prospect/{prospect_id}")
    def prospect(prospect_id: str) -> dict:
        if desk is None:
            detail = (MIRROR_CARD if mirror is not None and mirror.latest is not None
                      else OFF["reason"])
            raise HTTPException(404, detail)
        card = desk.card(prospect_id)
        if card is None:
            raise HTTPException(404, f"sin ficha para «{prospect_id}» (no es de la familia o el "
                                     "primer cálculo sigue en curso)")
        return card

    return router
