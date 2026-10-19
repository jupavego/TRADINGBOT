"""Genera `passivbot_parity.json`: fills que Passivbot da NATIVAMENTE sobre velas sintéticas fijas.

Se corre a mano en el entorno aparte de Passivbot (Python 3.12 + `passivbot_rust`), llamando
directamente a `backtest.run_backtest` del bot (sin pasar por el adaptador de EIM):

    <python del entorno de Passivbot> tests/fixtures/bots/make_passivbot_parity.py <checkout>

`gen_candles` y `OVERRIDES` los importan también las pruebas (no hace falta el bot para eso).
Las velas son sintéticas (marcha aleatoria con semilla): se comparan motores, no precios.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

START = 1_767_225_600_000   # 2026-01-01T00:00Z
N = 4320                    # 3 días de 1 min
SHA = "772abadc10a5bbf258a84aa8209a9084699fa1bd"
CONFIG = "configs/examples/btc_long.json"
BALANCE, MAKER, TAKER, WARMUP = 10_000.0, 0.0002, 0.0005, 120
MARKET = {"qty_step": 0.001, "price_step": 0.1, "min_qty": 0.001, "min_cost": 100.0}
# EMA cortas para que el bot opere en 3 días de datos (por defecto calienta ~16 días)
OVERRIDES = {"live.max_warmup_minutes": 200, "live.warmup_ratio": 1.0,
             "bot.long.strategy.trailing_martingale.volatility_ema_span_1h": 6,
             "bot.long.strategy.trailing_martingale.volatility_ema_span_1m": 30.0,
             "bot.long.strategy.trailing_martingale.entry.ema_span_0": 60,
             "bot.long.strategy.trailing_martingale.entry.ema_span_1": 30,
             "bot.long.unstuck.ema_span_0": 60.0, "bot.long.unstuck.ema_span_1": 30.0,
             "bot.long.forager.volatility_ema_span_1m": 10,
             "bot.long.forager.volume_ema_span_1m": 60}


def gen_candles(n: int = N, seed: int = 7) -> list[list[float]]:
    """Marcha aleatoria con oscilación lenta: filas [t, o, h, l, c, v] de 1 min consecutivas."""
    rnd, px, rows = random.Random(seed), 70_000.0, []
    for i in range(n):
        o = px
        px = max(1_000.0, px * (1 + rnd.gauss(0, 0.0008) + 0.0006 * ((i // 240) % 2 * 2 - 1)))
        h = max(o, px) * (1 + abs(rnd.gauss(0, 0.0003)))
        lo = min(o, px) * (1 - abs(rnd.gauss(0, 0.0003)))
        rows.append([START + i * 60_000, round(o, 1), round(h, 1), round(lo, 1), round(px, 1),
                     round(rnd.uniform(50, 300), 3)])
    return rows


def main(bot_dir: str) -> None:
    import numpy as np
    sys.path.insert(0, str(Path(bot_dir) / "src"))
    from backtest import run_backtest
    from config_utils import load_config

    rows = gen_candles()
    arr = np.asarray(rows)
    hl = np.empty((len(rows), 1, 4))
    hl[:, 0, 0], hl[:, 0, 1], hl[:, 0, 2], hl[:, 0, 3] = arr[:, 2], arr[:, 3], arr[:, 4], arr[:, 5]
    cfg = load_config(str(Path(bot_dir) / CONFIG), verbose=False)
    cfg["live"].update({"approved_coins": {"long": ["BTC"], "short": []},
                        "ignored_coins": {"long": [], "short": []}, "hedge_mode": False})
    cfg["bot"]["short"]["risk"].update({"n_positions": 0, "total_wallet_exposure_limit": 0})
    cfg["backtest"].update({"exchanges": ["binance"], "coins": {"binance": ["BTC"]},
                            "start_date": "2026-01-01", "end_date": "2026-01-04",
                            "starting_balance": BALANCE, "candle_interval_minutes": 1,
                            "filter_by_min_effective_cost": False, "maker_fee_override": MAKER,
                            "taker_fee_override": TAKER})
    for path, value in OVERRIDES.items():
        node = cfg
        *head, last = path.split(".")
        for k in head:
            node = node[k]
        node[last] = value
    mss = {"BTC": {**MARKET, "c_mult": 1.0, "maker": MAKER, "taker": TAKER, "exchange": "binance",
                   "first_valid_index": 0, "last_valid_index": len(rows) - 1,
                   "warmup_minutes": WARMUP},
           "__meta__": {"requested_start_ts": rows[0][0] + WARMUP * 60_000,
                        "requested_start_date": "2026-01-01", "warmup_minutes_requested": WARMUP}}
    fills, eq, _ = run_backtest(hl, mss, cfg, "binance", arr[:, 4].copy(),
                                arr[:, 0].astype(np.int64))
    keep = [[int(f[1]), str(f[13]), float(f[9]), float(f[10]), float(f[11]), float(f[3]),
             float(f[4])] for f in fills]
    out = {"bot_sha": SHA, "n_candles": len(rows), "seed": 7, "overrides": OVERRIDES,
           "fill_fields": ["t", "type", "qty", "price", "psize", "pnl", "fee_paid"], "fills": keep,
           "equity_points": int(np.asarray(eq).shape[0])}
    Path(__file__).with_name("passivbot_parity.json").write_text(json.dumps(out), encoding="utf-8")
    print(len(keep), "fills nativos")


if __name__ == "__main__":
    main(sys.argv[1])
