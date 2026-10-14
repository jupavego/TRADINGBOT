"""Ejecución en la API (T30): estado, reconciliación periódica y cierre ordenado.

Con `EIM_EXECUTION=testnet` (y claves de testnet en el entorno) se crea un
`BinanceTestnetBroker`; el modo de toda la API pasa a TESTNET. Sin eso no hay broker: la API
sigue en SIMULADO y ninguna ruta envía órdenes. Las órdenes nuevas solo entran por
`POST /v2/risk/execute` (motor de riesgo → `OrderGateway`).
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import APIRouter, Header, HTTPException, Query

from eim.core import Mode
from eim.data.timeframes import SYMBOLS
from eim.execution.binance_testnet import BinanceTestnetBroker
from eim.execution.broker import Broker, BrokerError
from eim.execution.reconcile import Reconciler
from eim.execution.service import ExecutionService
from eim.risk import AccountState, KillSwitch, RiskConfig

CONFIRM_HEADER = "X-EIM-Confirm"
EQUITY_TTL_S = 5.0


def confirm(value: str | None, expected: str) -> None:
    """Cabecera propia obligatoria: obliga a una petición CORS con verificación previa, así una
    página ajena no puede cambiar el kill-switch ni enviar órdenes con un POST «simple» (CSRF)."""
    if value != expected:
        raise HTTPException(403, f"falta la cabecera {CONFIRM_HEADER}: {expected}")


@dataclass
class ExecutionRuntime:
    svc: ExecutionService | None = None
    recon: Reconciler | None = None
    error: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock)
    _equity: tuple[float, float] | None = None   # (monotónico, capital): caché corta

    @property
    def mode(self) -> Mode:
        return self.svc.mode if self.svc is not None else Mode.SIMULADO

    def account(self) -> AccountState:
        """Cuenta desde el exchange. Sin historial propio aún: inicio de día/semana y pico =
        capital actual (las reglas de pérdida diaria/semanal no ven pérdidas previas; T31)."""
        assert self.svc is not None
        if self._equity is None or time.monotonic() - self._equity[0] > EQUITY_TTL_S:
            self._equity = (time.monotonic(), self.svc.broker.equity())
        eq = self._equity[1]
        return AccountState(
            equity=eq, day_start_equity=eq, week_start_equity=eq, peak_equity=eq,
            open_symbols=tuple(t.symbol for t in self.svc.active()),
            source=f"{self.mode.value}: saldo del exchange (sin historial diario)")

    def reconcile(self, now: int):
        assert self.recon is not None
        with self.lock:
            return self.recon.run(tuple(SYMBOLS), now)


def build_runtime(kind: str, kill: KillSwitch, cfg: RiskConfig,
                  broker_factory: Callable[[], Broker] = BinanceTestnetBroker) -> ExecutionRuntime:
    if kind in ("", "off"):
        return ExecutionRuntime()
    if kind != "testnet":
        return ExecutionRuntime(error=f"EIM_EXECUTION='{kind}' no soportado (solo testnet)")
    try:
        broker = broker_factory()
    except BrokerError as e:
        return ExecutionRuntime(error=f"testnet no disponible: {e}")
    svc = ExecutionService(broker, kill)
    return ExecutionRuntime(svc=svc, recon=Reconciler(svc, cfg))


async def recon_loop(rt: ExecutionRuntime, interval_s: float, clock: Callable[[], int]) -> None:
    """Reconciliación periódica en un hilo (las llamadas al broker son bloqueantes)."""
    while True:
        try:
            await asyncio.to_thread(rt.reconcile, clock())
            rt.error = ""
        except Exception as e:      # el bucle no debe morir; el fallo queda en `error`
            rt.error = f"reconciliación fallida: {type(e).__name__}: {e}"
        await asyncio.sleep(interval_s)


def build_execution_router(rt: ExecutionRuntime, clock: Callable[[], int]) -> APIRouter:
    router = APIRouter(prefix="/v2/execution")

    def _need(value: str | None) -> ExecutionService:
        confirm(value, "execution")
        if rt.svc is None:
            raise HTTPException(409, rt.error or "ejecución desactivada (EIM_EXECUTION)")
        return rt.svc

    @router.get("")
    def status() -> dict:
        svc = rt.svc
        trades = list(svc.trades.values()) if svc else []   # copia: otro hilo puede añadir
        return {
            "mode": rt.mode.value, "enabled": svc is not None, "error": rt.error,
            "trades": [t.to_json() for t in trades],
            "reconciliation": rt.recon.last.to_json() if rt.recon and rt.recon.last else None,
            "kill_switch": svc.kill.state() if svc else None,
        }

    @router.post("/reconcile")
    def reconcile(x_eim_confirm: str | None = Header(None)) -> dict:
        _need(x_eim_confirm)
        try:
            return rt.reconcile(clock()).to_json()
        except BrokerError as e:
            raise HTTPException(502, str(e)) from None

    @router.post("/flatten")
    def flatten(symbol: str = Query(...), reason: str = Query("manual", max_length=200),
                x_eim_confirm: str | None = Header(None)) -> dict:
        svc = _need(x_eim_confirm)
        if symbol not in SYMBOLS:
            raise HTTPException(400, f"símbolo no soportado: {symbol}")
        try:
            with rt.lock:
                flat = svc.flatten(symbol, reason)
        except BrokerError as e:
            raise HTTPException(502, str(e)) from None
        return {"symbol": symbol, "flat": flat}

    return router
