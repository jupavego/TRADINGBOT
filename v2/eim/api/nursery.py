"""`GET /v2/nursery`: lectura del libro de la cantera (T168). Solo lectura, sin POST. SIMULADO.

Por cuenta (prospectos y controles, que no cuentan como prospectos): rentabilidad neta acumulada %,
saldo, curva de capital, drawdown máximo, n, acierto, costo pagado, etapa y R neto con IC frente a
sus gemelos aleatorios. Con la cantera apagada (`EIM_NURSERY=0`, por defecto) lo dice y no inventa
nada.

T171: con el pre-registro, la respuesta trae además `panel` (la panorámica por agente de la pestaña
«Cantera», `eim/nursery/panel.py`) y `GET /v2/nursery/prospect/{id}` da la ficha de un prospecto:
teoría, variables, parámetros citados, obras a favor y en contra, curva y operaciones.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from eim.nursery.desk import NurseryDesk

OFF = {"mode": "SIMULADO", "enabled": False,
       "reason": "cantera apagada (EIM_NURSERY=0); se enciende en T170"}


def build_nursery_router(desk: NurseryDesk | None) -> APIRouter:
    router = APIRouter(prefix="/v2/nursery")

    @router.get("")
    def nursery(account: str | None = Query(None, description="una sola cuenta")) -> dict:
        if desk is None:
            return dict(OFF)
        s = desk.summary()
        base = {"mode": "SIMULADO", "enabled": True, "variant": desk.name, "label": desk.label,
                "live": desk.live_status()}
        if s is None:
            return {**base, "accounts": [], "reason": "primer cálculo en curso"}
        if account is not None:
            s = {**s, "accounts": [a for a in s["accounts"] if a["account"] == account]}
        return {**base, **s}

    @router.get("/prospect/{prospect_id}")
    def prospect(prospect_id: str) -> dict:
        if desk is None:
            raise HTTPException(404, OFF["reason"])
        card = desk.card(prospect_id)
        if card is None:
            raise HTTPException(404, f"sin ficha para «{prospect_id}» (no es de la familia o el "
                                     "primer cálculo sigue en curso)")
        return card

    return router
