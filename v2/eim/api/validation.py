"""Rutas de la puerta de validación (T49): solo lectura (sin POST). Siempre SIMULADO.

`GET /v2/validation` devuelve los veredictos vigentes por estrategia@marco@versión, los
criterios con su hash, la fecha (`asof`/`computed`) y el registro de intentos. El servicio del
bróker los recalcula al cierre de cada vela de 4 h; si aún no hay ninguno, se calculan una vez.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from eim.data.timeframes import SYMBOLS
from eim.validation.service import Validator


def _check(symbol: str) -> None:
    if symbol not in SYMBOLS:
        raise HTTPException(400, f"símbolo no soportado: {symbol} (válidos: {list(SYMBOLS)})")


def build_validation_router(validator: Validator) -> APIRouter:
    router = APIRouter(prefix="/v2/validation")

    @router.get("")
    def verdicts(symbol: str = "BTCUSDT") -> dict:
        """Veredictos vigentes + criterios + fecha + intentos registrados."""
        _check(symbol)
        return validator.latest(symbol)

    @router.get("/history")
    def history(sid: str, symbol: str = "BTCUSDT",
                limit: int = Query(200, ge=1, le=5000)) -> dict:
        """Historial de veredictos de una estrategia@marco (todas sus versiones)."""
        _check(symbol)
        return {"mode": "SIMULADO", "sid": sid, "criteria": validator.crit.version,
                "history": validator.vstore.history(validator.crit.version, symbol, sid, limit)}

    return router
