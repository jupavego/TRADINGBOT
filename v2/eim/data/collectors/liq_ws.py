"""Recolector de liquidaciones forzadas EN VIVO (Binance, Bybit, OKX). Proceso separado:

    python -m eim.data.collectors.liq_ws BTCUSDT --root data

Sustituye al dataset histórico de Binance (retirado en oct-2024). Una fila por liquidación en
`root/micro/liqs/` con la bolsa, el lado de la POSICIÓN liquidada (`long_pos`) y el notional USD.
Cada corte de conexión queda como hueco `liq:<bolsa>` (la vela afectada se marca incompleta).
Limitación de Binance: su stream publica solo la última liquidación de cada segundo, por lo que
su notional es una cota inferior (el agente lo trata en relativo y lo declara).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from eim.data.collectors.writer import HourlyWriter
from eim.observability import hooks_service
from eim.observability.emit import configure

WS = {
    "binance": "wss://fstream.binance.com/market/stream?streams={s}@forceOrder",
    "bybit": "wss://stream.bybit.com/v5/public/linear",
    "okx": "wss://ws.okx.com:8443/ws/v5/public",
}
# Valor del contrato OKX en moneda base (documentado por OKX; `okx_ct_val` permite sobrescribirlo).
OKX_CT_VAL = {"BTC": 0.01, "ETH": 0.1}
ALIVE_SECS = 30
OKX_INST = {"BTCUSDT": "BTC-USDT-SWAP", "ETHUSDT": "ETH-USDT-SWAP"}


def parse_binance(msg: dict, symbol: str) -> list[tuple]:
    """`forceOrder`: lado de la ORDEN; SELL liquida una LARGA, BUY una CORTA."""
    d = msg.get("data", msg)
    o = d.get("o") if d.get("e") == "forceOrder" else None
    if not o or o.get("s") != symbol:
        return []
    p = float(o.get("ap") or 0) or float(o["p"])
    q = float(o["z"] if float(o.get("z") or 0) else o["q"])
    return [(int(o.get("T") or d["E"]), "binance", o["S"] == "SELL", p, q, p * q)]


def parse_bybit(msg: dict, symbol: str) -> list[tuple]:
    """`allLiquidation.<s>`: `S`=Buy significa posición LARGA liquidada."""
    if not str(msg.get("topic", "")).startswith("allLiquidation."):
        return []
    return [(int(x["T"]), "bybit", x["S"] == "Buy", float(x["p"]), float(x["v"]),
             float(x["p"]) * float(x["v"]))
            for x in msg.get("data", []) if x.get("s") == symbol]


def parse_okx(msg: dict, symbol: str, ct_val: float | None = None) -> list[tuple]:
    """`liquidation-orders` (SWAP): `sz` en contratos × valor de contrato; posSide=long ⇒ larga."""
    inst = OKX_INST.get(symbol)
    ct = ct_val or OKX_CT_VAL.get(symbol[:-4])
    if msg.get("arg", {}).get("channel") != "liquidation-orders" or not inst or not ct:
        return []
    out = []
    for item in msg.get("data", []):
        if item.get("instId") != inst:
            continue
        for x in item.get("details", []):
            long_pos = (x.get("posSide") == "long") or (
                x.get("posSide") in (None, "", "net") and x.get("side") == "sell")
            p, q = float(x["bkPx"]), float(x["sz"]) * ct
            out.append((int(x["ts"]), "okx", long_pos, p, q, p * q))
    return out


class LiqCollector:
    """Procesa mensajes ya decodificados (testeable sin red)."""

    def __init__(self, root, symbol: str, flush_secs: float = 30.0,
                 okx_ct_val: float | None = None):
        self.symbol, self.okx_ct_val = symbol.upper(), okx_ct_val
        self.liqs = HourlyWriter(root, "liqs", self.symbol, flush_secs=flush_secs)
        self.gaps_w = HourlyWriter(root, "gaps", self.symbol, flush_secs=flush_secs)
        self.n = 0
        self.connected: set[str] = set()

    def alive(self, now: int) -> None:
        """Marca de vida por bolsa conectada: distingue «0 liquidaciones» de «recolector caído»."""
        for v in self.connected:
            self.liqs.add((now, f"alive:{v}", False, 0.0, 0.0, 0.0))

    def on_message(self, venue: str, msg: dict) -> None:
        rows = {"binance": lambda: parse_binance(msg, self.symbol),
                "bybit": lambda: parse_bybit(msg, self.symbol),
                "okx": lambda: parse_okx(msg, self.symbol, self.okx_ct_val)}[venue]()
        for r in rows:
            self.liqs.add(r)
            self.n += 1

    def gap(self, venue: str, detail: str) -> None:
        self.gaps_w.add((int(time.time() * 1000), f"liq:{venue}", detail))

    def flush(self) -> None:
        self.liqs.flush()
        self.gaps_w.flush()


def _subscribe(venue: str, symbol: str) -> dict | None:
    if venue == "bybit":
        return {"op": "subscribe", "args": [f"allLiquidation.{symbol}"]}
    if venue == "okx":
        return {"op": "subscribe", "args": [{"channel": "liquidation-orders", "instType": "SWAP"}]}
    return None


async def _stream(col: LiqCollector, venue: str, stop: asyncio.Event) -> None:
    import websockets

    url = WS[venue].format(s=col.symbol.lower())
    backoff = 1.0
    while not stop.is_set():
        try:
            async with websockets.connect(url, ping_interval=20, open_timeout=15) as ws:
                sub = _subscribe(venue, col.symbol)
                if sub:
                    await ws.send(json.dumps(sub))
                backoff = 1.0
                col.connected.add(venue)
                hooks_service.beat("data.liq_collector", min_interval_s=60,
                                   detail={"venue": venue, "events": col.n})
                async for raw in ws:
                    col.on_message(venue, json.loads(raw))
                    if stop.is_set():
                        break
        except Exception as exc:  # corte de red, 429, etc. → registrar hueco y reintentar
            col.connected.discard(venue)
            col.gap(venue, f"{type(exc).__name__}: {exc}"[:200])
            hooks_service.service_error("data.liq_collector", exc, detail={"venue": venue})
            col.flush()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)


async def run(root, symbol: str, stop: asyncio.Event | None = None) -> None:
    col, stop = LiqCollector(root, symbol), stop or asyncio.Event()

    async def pulse() -> None:
        while not stop.is_set():
            col.alive(int(time.time() * 1000))
            await asyncio.sleep(ALIVE_SECS)

    await asyncio.gather(pulse(), *(_stream(col, v, stop) for v in WS))
    col.flush()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("symbol")
    ap.add_argument("--root", default="data")
    a = ap.parse_args()
    configure(process="liq_collector", spool_dir=Path(a.root) / "obs" / "spool")
    try:
        asyncio.run(run(a.root, a.symbol))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
