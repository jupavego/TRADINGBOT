"""Datos sintéticos para la cantera (T168): contextos con variables nativas y un camino de precio.

Valores al azar pero del tipo que publica cada agente (etiquetas, listas paralelas, números),
para ejercitar las 43 reglas sin red ni disco. Semilla fija.
"""

from __future__ import annotations

import numpy as np

from eim.core import Candle
from eim.nursery.native import stored_key
from eim.nursery.prospect import load_prospects, native_paths
from eim.paper.engine import Path

H1, M15 = 3_600_000, 900_000
T0 = 1_767_225_600_000          # 2026-01-01 00:00 UTC

ENUMS = {
    "STACK_ORDER": ["BULL_PERFECT", "BEAR_PERFECT", "NEUTRAL", "BULL_PARTIAL"],
    "SLOPE_DIRECTION": ["UP", "DOWN", "NEUTRAL"],
    "position": ["SOBRE_VWAP", "BAJO_VWAP", "EXTREMO_SOBRE", "EXTREMO_BAJO", "ESTIRADO_SOBRE"],
    "channel.state": ["INSIDE", "INSIDE", "BROKEN_UP", "BROKEN_DOWN"],
    "channel.kind": ["channel", "range"],
    "scenario": ["SC-01_CONTINUATION", "SC-02_BREAKOUT", "SC-03_PULLBACK",
                 "SC-04_STRUCTURAL_CHANGE", "SC-05_CONSOLIDATION"],
    "structural_state": ["E-01_TREND_STRONG", "E-07_DIVERGENT"],
    "last_event": ["BOS_ALCISTA", "BOS_BAJISTA", "CHOCH_ALCISTA", "CHOCH_BAJISTA"],
    "structure_state": ["BULLISH", "BEARISH"],
    "wave_label": ["0", "1", "2", "3", "4", "5", "A", "B", "C"],
    "type": ["H", "L"],
    "regime": ["trend_up", "trend_down", "range", "volatile"],
    "label": ["tendencia", "rango"],
    "state": ["quiet", "active", "exhausted"],
}
INTS = {"PRICE_VS_STACK": 6, "COMPRESSION_DURATION": 9, "BOUNCE_COUNT_21": 4,
        "last_event_age": 3, "bullish_patterns": 3, "bearish_patterns": 3}
BOOLS = {"valid_count", "unstable"}


def _value(path: str, rng: np.random.Generator, close: float, n_list: int):
    leaf = path.split(".")[-1]
    tail2 = ".".join(path.split(".")[-2:])
    if "[]" in path:
        if leaf == "card_id":
            return [str(rng.choice(["nison_hammer", "murphy_rsi", "murphy_weekly_rule",
                                    "nison_engulfing"])) for _ in range(n_list)]
        if leaf in ("direction", "stance"):
            return [int(rng.choice([-1, 0, 1])) for _ in range(n_list)]
        if leaf == "status":
            return [str(rng.choice(["ok", "ok", "stale"])) for _ in range(n_list)]
        if leaf in ("p_low", "p_high"):
            return [round(close * (1 + rng.normal(0, 0.01)), 2) for _ in range(n_list)]
        return [round(abs(float(rng.normal(2, 1))), 3) for _ in range(n_list)]
    for key in (tail2, leaf):
        if key in ENUMS:
            return str(rng.choice(ENUMS[key]))
    if leaf in INTS:
        return int(rng.integers(0, INTS[leaf]))
    if leaf in BOOLS:
        return bool(rng.integers(0, 2))
    if leaf in ("tendencia", "volumen"):
        return {"vote": round(float(rng.normal(0, 0.5)), 3), "weight": 1.0}
    if leaf == "venues":
        return ["binance", "bybit", "okx"][:int(rng.integers(1, 4))]
    if leaf == "sr_zones":
        return [{"price": round(close * (1 + rng.normal(0, 0.004)), 2), "touches": 2}
                for _ in range(3)]
    if leaf in ("EMA_21", "EMA_200", "vwap", "close", "anchored_vwap"):
        return round(close * (1 + rng.normal(0, 0.01)), 2)
    if leaf in ("width_pct", "channel_pos", "incomplete_fraction", "r2"):
        return round(float(rng.uniform(0, 1)), 3)
    return round(float(rng.normal(0, 2)), 4)


def make_path(n: int, step: int = M15, seed: int = 7, start: float = 60_000.0) -> Path:
    rng = np.random.default_rng(seed)
    px = start * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
    cs = []
    for k in range(n):
        o = float(px[k - 1] if k else start)
        c = float(px[k])
        hi = max(o, c) * (1 + abs(rng.normal(0, 0.0015)))
        lo = min(o, c) * (1 - abs(rng.normal(0, 0.0015)))
        cs.append(Candle(t=T0 + k * step, o=o, h=hi, l=lo, c=c, v=1.0))
    funding = [(T0 + j * 8 * H1, 0.0001) for j in range(1, n * step // (8 * H1))]
    return Path(cs, funding, step)


def make_ctxs(path: Path, tf_ms: int, seed: int = 11, n_list: int = 4) -> list[dict]:
    """Un contexto por cierre de vela de `tf_ms` sobre `path`, con `nat` de todos los agentes."""
    rng = np.random.default_rng(seed)
    wanted = native_paths(load_prospects())
    step = int(path.step)
    out = []
    t = int(path.t[0]) + tf_ms
    while t <= int(path.t[-1]):
        j = int(np.searchsorted(path.t, t)) - 1
        close = float(path.c[j])
        nat = {a: {stored_key(p): _value(p, rng, close, n_list) for p in paths} | {"_h": 6}
               for a, paths in wanted.items()}
        agents = {a: [round(float(rng.uniform(-1, 1)), 3), round(float(rng.uniform(0, 1)), 3),
                      "ok"] for a in wanted}
        out.append({"t": t, "close": close, "atr": close * 0.004, "agents": agents, "nat": nat})
        t += tf_ms
    assert step > 0
    return out
