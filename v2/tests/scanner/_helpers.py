"""Ayudas de las pruebas del escáner (T93): fichas, velas sintéticas y manejadores de prueba.

Los manejadores son funciones de módulo para que viajen a otro proceso (`spawn`).
"""

from __future__ import annotations

import numpy as np

from eim.core import Candle
from eim.instruments.models import (
    AssetClass,
    DataCapability,
    Instrument,
    InstrumentStatus,
    MarketStructure,
    SessionKind,
    TradableLevel,
    make_id,
)

DAY = 86_400_000
T0 = 1_767_225_600_000                      # 2026-01-01 00:00 UTC (jueves)
CAPS = frozenset({DataCapability.CANDLES, DataCapability.REAL_VOLUME, DataCapability.FUNDING})


def perp(symbol: str, *, status: InstrumentStatus = InstrumentStatus.ACTIVE,
         currency: str = "USDT", expiry: int | None = None,
         asset_class: AssetClass = AssetClass.CRYPTO,
         level: TradableLevel = TradableLevel.OPERATIONAL, calendar_id: str = "24/7",
         session: SessionKind = SessionKind.ALWAYS) -> Instrument:
    cls = AssetClass.FUTURE if expiry is not None else asset_class
    return Instrument(
        id=make_id(cls, "binance", symbol, market="usdm"), symbol=symbol, label=symbol,
        asset_class=cls, market_structure=MarketStructure.CONTINUOUS_BOOK, venue="binance",
        status=status, currency=currency, quote_currency=currency, calendar_id=calendar_id,
        session=session, expiry=expiry, tradable_level=level, data_capabilities=CAPS,
        source="prueba")


def candles(n: int, *, seed: int = 0, end_t: int = T0 + 100 * DAY, step: int = DAY,
            price: float = 100.0, volume: float = 1e5, drift: float = 0.0) -> list[Candle]:
    """`n` velas diarias cerradas que terminan en `end_t` (apertura de la última)."""
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, 0.02, n)
    c = price * np.exp(np.cumsum(r))
    o = np.r_[price, c[:-1]]
    out = []
    for k in range(n):
        hi, lo = max(o[k], c[k]) * 1.01, min(o[k], c[k]) * 0.99
        out.append(Candle(t=end_t - (n - 1 - k) * step, o=float(o[k]), h=float(hi), l=float(lo),
                          c=float(c[k]), v=float(volume * (1 + 0.1 * np.sin(k))),
                          taker_buy_v=float(volume / 2)))
    return out


def rows_of(series: dict[str, list[Candle]]):
    """Filas planas ordenadas por (símbolo, t), como las devuelve el cargador del panel."""
    sym, t, o, h, lo, c, v = [], [], [], [], [], [], []
    for s in sorted(series):
        for k in series[s]:
            sym.append(s)
            t.append(k.t)
            o.append(k.o)
            h.append(k.h)
            lo.append(k.l)
            c.append(k.c)
            v.append(k.v)
    f = np.asarray
    return (f(sym, dtype=str), f(t, dtype=np.int64), f(o, float), f(h, float), f(lo, float),
            f(c, float), f(v, float))


# --- manejadores de prueba (nivel de módulo) -------------------------------------------------
def echo(payload: dict) -> dict:
    return {"echo": payload.get("x"), "pid_ok": True}


def boom(payload: dict) -> dict:
    raise RuntimeError(f"falla a propósito ({payload.get('x')})")


def square(payload: dict) -> dict:
    import os
    return {"y": int(payload["x"]) ** 2, "pid": os.getpid()}
