"""Filas sintéticas del libro fijo para las pruebas de T187–T189."""

from __future__ import annotations

from eim.paper.asym import prereg as P

H = 3_600_000


def row(i: int, *, profile: str = "moderado", r: float = 0.1, weight: float = 0.5,
        day: int = 0, hour: int = 1, side: int = 1, sid: str = "agente_ema@15m",
        fill: float = 100.0, sl: float = 99.0, fees: float = 0.5, slip: float = 0.2,
        tf: str = "15m", floor: bool = False, opened: int | None = None,
        exit_after_h: int = 1) -> dict:
    t = opened if opened is not None else P.START_MS + day * P.DAY_MS + hour * H
    risk_usd = 50.0 * weight
    return {"ledger_id": f"L{i}", "scope": "perfil", "profile": profile, "symbol": "BTCUSDT",
            "sid": sid, "strategy": sid.split("@")[0], "timeframe": tf, "side": side,
            "kind": "market", "opened_t": t, "fill_t": t, "exit_t": t + exit_after_h * H,
            "fill": fill, "sl": sl, "r": r, "pnl_usdt": r * risk_usd, "weight": weight,
            "fees": fees, "slip": slip, "funding": 0.0, "floor_trade": floor,
            "origin": "vivo", "retro": False}
