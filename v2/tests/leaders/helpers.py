"""Utilidades de tests de líderes (T40): respuestas reales grabadas de Hyperliquid
(`tests/fixtures/leaders/`, 2026-10-15) y constructores de ejecuciones con el mismo formato."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from eim.core.leaders import Leader, leader_id

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "leaders"
ACTIVE = "0xf5d81a135f756ca16544e53c20fc20643ec3ad53"  # paquete «active_*»: 101 ejecuciones
CLOSER = "0x9e1fdc4ed12d7cb16d30542254781eb7d0f3290c"  # paquete «close_*»: cierra su ETH
TEST = "0x" + "ab" * 20  # escenarios sintéticos


def load(name: str):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def leader(addr: str = TEST, status: str = "watch", t: int = 0) -> Leader:
    return Leader(id=leader_id("hyperliquid", addr), venue="hyperliquid", address=addr,
                  origin="manual", status=status, discovered_at=t, source="test")


def fill(coin: str, side: str, sz: str, px: str, start: str, t: int, tid: int, oid: int = 1,
         **extra) -> dict:
    """Ejecución con el formato de `userFills` (cadenas como las del exchange)."""
    return {"coin": coin, "px": px, "sz": sz, "side": side, "time": t, "startPosition": start,
            "dir": "", "closedPnl": "0.0", "hash": "0x0", "oid": oid, "crossed": True,
            "fee": "0.01", "tid": tid, "feeToken": "USDC", "twapId": None} | extra


def state(t: int, *positions: tuple[str, str, str, int, str]) -> dict:
    """`clearinghouseState` mínimo: (moneda, szi, entryPx, apalancamiento, modo)."""
    return {"time": t, "assetPositions": [
        {"type": "oneWay", "position": {
            "coin": c, "szi": szi, "entryPx": px, "leverage": {"type": mode, "value": lev},
            "liquidationPx": None, "unrealizedPnl": "0.0", "marginUsed": "1.0"}}
        for c, szi, px, lev, mode in positions]}


class FakeInfo:
    """`HyperliquidInfo` sin red: estados en secuencia (el último se repite) y ejecuciones
    filtradas por `startTime` como el endpoint real."""

    def __init__(self, states: list[dict], fills: list[dict] | None = None,
                 funding: list[dict] | None = None, offset: int = 0) -> None:
        self.states, self.fills, self.funding_rows = list(states), list(fills or []), funding or []
        self.offset = offset
        self.calls: list[tuple] = []

    def clearinghouse_state(self, user: str) -> dict:
        self.calls.append(("state", user))
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]

    def user_fills_by_time(self, user: str, start: int, end: int | None = None) -> list[dict]:
        self.calls.append(("fills", user, start))
        return [f for f in self.fills if f["time"] >= start]

    def user_funding(self, user: str, start: int, end: int | None = None) -> list[dict]:
        self.calls.append(("funding", user, start))
        return [r for r in self.funding_rows if r["time"] >= start]

    def clock_offset_ms(self) -> int:
        return self.offset


class FakeWS:
    """Conexión WS guionizada: mensajes (dict) o excepciones; luego silencio."""

    def __init__(self, script: list) -> None:
        self.script, self.sent = list(script), []

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def recv(self) -> str:
        if not self.script:
            await asyncio.sleep(3600)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return json.dumps(item)

    async def __aenter__(self) -> FakeWS:
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


def fake_connect(conns: list[FakeWS]):
    it = iter(conns)

    def connect(url: str) -> FakeWS:
        try:
            return next(it)
        except StopIteration:
            raise ConnectionRefusedError("sin más conexiones en el guion") from None

    return connect


async def no_sleep(_s: float) -> None:
    await asyncio.sleep(0)
