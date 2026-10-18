"""Ejecución de arbitraje en la API (T45): estado, ciclo automático y cierres. Modo TESTNET.

Con `EIM_ARB_EXECUTION=testnet` (claves de testnet spot y futuros en el entorno) se crea el
ejecutor y el ciclo corre cada `EIM_ARB_EXEC_S` segundos. Sin eso no hay ejecutor: el estado
dice «apagado» y ningún POST envía órdenes. Todo POST exige la cabecera `X-EIM-Confirm`.
Kill-switch compartido con el carril direccional (T29/T30).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from eim.api.execution import confirm
from eim.data.arb_exec_store import ArbExecStore
from eim.data.arb_store import ArbStore
from eim.execution.arb_book import ACTIVE, position_row
from eim.execution.arb_executor import ArbExecutor
from eim.execution.arb_legs import ExecParams
from eim.execution.arb_recon import ArbReconciler
from eim.execution.arb_runner import ArbAutopilot, decision_row
from eim.execution.binance_spot_testnet import BinanceSpotTestnetBroker
from eim.execution.binance_testnet import BinanceTestnetBroker
from eim.execution.broker import BrokerError
from eim.risk import KillSwitch
from eim.risk.arb_config import ArbRiskConfig, load_arb_config
from eim.risk.arb_engine import ArbRiskEngine

log = logging.getLogger(__name__)
MODE = "TESTNET"


def _now() -> int:
    return int(time.time() * 1000)


@dataclass
class ArbExecRuntime:
    store: ArbExecStore
    kill: KillSwitch
    pilot: ArbAutopilot | None = None
    error: str = ""
    interval_s: float = 60.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def ex(self) -> ArbExecutor | None:
        return self.pilot.ex if self.pilot is not None else None

    def futures_qty(self, symbol: str) -> float:
        """Futuros de arbitrajes activos (del ejecutor o, apagado, del último estado)."""
        ex = self.ex
        return ex.futures_qty(symbol) if ex is not None else self.store.futures_expected(symbol)

    def open_symbols(self) -> tuple[str, ...]:
        ex = self.ex
        if ex is None:                                   # apagado: lo vivo en disco
            return self.store.futures_symbols()
        return tuple(p.fut.symbol for p in ex.active())

    def cycle(self, now: int | None = None) -> dict[str, Any]:
        assert self.pilot is not None
        with self.lock:
            return self.pilot.cycle(now)


def build_arb_runtime(kind: str, kill: KillSwitch, data_dir: Path, scans: ArbStore, *,
                      spot_factory: Callable[[], Any] = BinanceSpotTestnetBroker,
                      fut_factory: Callable[[], Any] = BinanceTestnetBroker,
                      cfg: ArbRiskConfig | None = None, exec_params: ExecParams | None = None,
                      directional_qty: Callable[[str], float] = lambda _s: 0.0,
                      directional_symbols: Callable[[], tuple[str, ...]] = tuple,
                      clock: Callable[[], int] = _now,
                      sleep: Callable[[float], None] = time.sleep,
                      interval_s: float = 60.0) -> ArbExecRuntime:
    """`off` sin ejecutor · `testnet` spot testnet + futuros testnet de Binance."""
    store = ArbExecStore(data_dir)
    if kind in ("", "off"):
        return ArbExecRuntime(store, kill, interval_s=interval_s)
    if kind != "testnet":
        return ArbExecRuntime(store, kill, error=f"EIM_ARB_EXECUTION='{kind}' no soportado "
                              "(solo testnet en T45)", interval_s=interval_s)
    try:
        spot, fut = spot_factory(), fut_factory()
    except BrokerError as e:
        return ArbExecRuntime(store, kill, error=f"testnet no disponible: {e}",
                              interval_s=interval_s)
    cfg = cfg or load_arb_config()

    def journal(k: str, data: dict) -> None:
        store.append(k, clock(), data)

    ex = ArbExecutor(spot, fut, kill, exec_params, sleep, clock, save=store.save_state,
                     journal=journal)
    state = store.load_state()
    if state:
        ex.load(state)
    engine = ArbRiskEngine(cfg, lambda d: journal("riesgo", decision_row(d)), kill)
    recon = ArbReconciler(ex, cfg, directional=directional_qty)
    pilot = ArbAutopilot(ex, recon, engine, scans, journal,
                         directional_symbols=directional_symbols, clock=clock)
    return ArbExecRuntime(store, kill, pilot, interval_s=interval_s)


async def arb_loop(rt: ArbExecRuntime) -> None:
    """Ciclo automático en un hilo (las llamadas al exchange son bloqueantes)."""
    while True:
        try:
            await asyncio.to_thread(rt.cycle)
            rt.error = ""
        except Exception as e:  # noqa: BLE001 - el bucle no muere; el fallo queda en `error`
            log.exception("ciclo de arbitraje fallido")
            rt.error = f"ciclo fallido: {type(e).__name__}: {e}"
        await asyncio.sleep(rt.interval_s)


def build_arb_execution_router(rt: ArbExecRuntime) -> APIRouter:
    router = APIRouter(prefix="/v2/arbitrage/execution", tags=["arbitraje"])

    def _need(value: str | None, expected: str) -> ArbExecutor:
        confirm(value, expected)
        if rt.ex is None:
            raise HTTPException(409, rt.error or "ejecución de arbitraje apagada "
                                "(EIM_ARB_EXECUTION=testnet)")
        return rt.ex

    @router.get("")
    def status(limit: int = Query(80, ge=1, le=300)) -> dict:
        """Modo, posiciones (funding real vs esperado, margen, liquidación), último ciclo,
        reconciliación, kill-switch y bitácora."""
        ex, pilot = rt.ex, rt.pilot
        cfg = pilot.engine.config if pilot else None
        rows = sorted((position_row(p) for p in list(ex.positions.values())) if ex else [],
                      key=lambda r: (r["status"] not in ACTIVE, -(r["created_at"] or 0)))
        return {
            "mode": MODE, "enabled": ex is not None, "error": rt.error,
            "interval_s": rt.interval_s, "kill_switch": rt.kill.state(),
            "positions": rows[:50], "last_cycle": pilot.last if pilot else None,
            "reconciliation": pilot.recon.last.to_json() if pilot and pilot.recon.last else None,
            "config": {"version": cfg.version, "sha256": cfg.sha256,
                       "strategies": list(cfg.strategies),
                       "max_notional_usd": cfg.max_notional_usd,
                       "max_leg_loss_bps": cfg.max_leg_loss_bps,
                       "max_margin_frac": cfg.max_margin_frac,
                       "rebalance_frac": cfg.rebalance_frac} if cfg else None,
            "journal": rt.store.tail(limit),
        }

    @router.post("/cycle")
    def cycle(x_eim_confirm: str | None = Header(None)) -> dict:
        _need(x_eim_confirm, "arb-cycle")
        try:
            return rt.cycle()
        except BrokerError as e:
            raise HTTPException(502, str(e)) from None

    @router.post("/close")
    def close(key: str = Query(..., max_length=80),
              reason: str = Query("manual", max_length=200),
              x_eim_confirm: str | None = Header(None)) -> dict:
        ex = _need(x_eim_confirm, "arb-close")
        pos = ex.positions.get(key)
        if pos is None:
            raise HTTPException(404, f"arbitraje desconocido: {key}")
        with rt.lock:
            flat = ex.close(pos, f"manual: {reason}")
        return {"key": key, "flat": flat, "status": pos.status}

    @router.post("/flatten")
    def flatten(x_eim_confirm: str | None = Header(None)) -> dict:
        ex = _need(x_eim_confirm, "arb-flatten")
        with rt.lock:
            flat = ex.flatten_all("manual: cerrar todo")
        return {"flat": flat}

    return router
