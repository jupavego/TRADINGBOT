"""Punto de entrada que corre DENTRO del entorno aparte de Passivbot (modo B, simulación).

No importa nada de `eim`. Lee `request.json` y `candles.json` (velas de 1 min locales) del
directorio
de trabajo, ejecuta el backtester de Passivbot con esas velas (sin descargar nada, sin claves, sin
exchange) y escribe `out.json` con los fills y la curva de capital que el bot simuló. Los costos del
bot se reportan tal cual: el modelo de costos de EIM (T25) los recalcula aparte (T59).
"""

from __future__ import annotations

import copy
import json
import logging
import sys
from pathlib import Path

import numpy as np

REQ = json.loads(Path("request.json").read_text(encoding="utf-8"))
BOT = Path(REQ["bot_dir"])
sys.path.insert(0, str(BOT / "src"))
logging.disable(logging.CRITICAL)

import passivbot_rust as pbr  # noqa: E402
from backtest import run_backtest  # noqa: E402
from config_utils import load_config  # noqa: E402

FILL_COLS = ["index", "timestamp", "coin", "pnl", "fee_paid", "usd_total_balance",
             "btc_cash_wallet", "usd_cash_wallet", "btc_price", "qty", "price", "psize", "pprice",
             "type", "liquidity", "wallet_exposure", "twe_long", "twe_short", "twe_net"]
MINUTE = 60_000


def build_config() -> dict:
    cfg = load_config(str(BOT / REQ["config"]), verbose=False)
    coin = REQ["coin"]
    cfg["live"].update({"approved_coins": {"long": [coin], "short": []},
                        "ignored_coins": {"long": [], "short": []}, "hedge_mode": False})
    cfg["bot"]["short"]["risk"].update({"n_positions": 0, "total_wallet_exposure_limit": 0})
    bt = cfg["backtest"]
    bt.update({"exchanges": ["binance"], "coins": {"binance": [coin]},
               "start_date": REQ["start_date"], "end_date": REQ["end_date"],
               "starting_balance": float(REQ["starting_balance"]), "candle_interval_minutes": 1,
               "filter_by_min_effective_cost": False,
               "maker_fee_override": REQ["maker_fee"], "taker_fee_override": REQ["taker_fee"]})
    for path, value in REQ.get("overrides", {}).items():   # «bot.long.risk.n_positions»: valor
        node = cfg
        *head, last = path.split(".")
        for key in head:
            node = node[key]
        node[last] = value
    return copy.deepcopy(cfg)


def main() -> None:
    rows = json.loads(Path("candles.json").read_text(encoding="utf-8"))
    arr = np.asarray(rows, dtype=np.float64)           # t, o, h, l, c, v
    ts = arr[:, 0].astype(np.int64)
    if len(ts) < 2 or not np.all(np.diff(ts) == MINUTE):
        raise ValueError("las velas deben ser de 1 min consecutivas (sin huecos)")
    n = len(ts)
    hlcvs = np.empty((n, 1, 4), dtype=np.float64)       # el motor usa alto, bajo, cierre, volumen
    hlcvs[:, 0, 0], hlcvs[:, 0, 1], hlcvs[:, 0, 2], hlcvs[:, 0, 3] = (
        arr[:, 2], arr[:, 3], arr[:, 4], arr[:, 5])
    coin, warm = REQ["coin"], int(REQ["warmup_minutes"])
    mss = {coin: {"qty_step": REQ["qty_step"], "price_step": REQ["price_step"],
                  "min_qty": REQ["min_qty"], "min_cost": REQ["min_cost"], "c_mult": 1.0,
                  "maker": REQ["maker_fee"], "taker": REQ["taker_fee"], "exchange": "binance",
                  "first_valid_index": 0, "last_valid_index": n - 1, "warmup_minutes": warm},
           "__meta__": {"requested_start_ts": int(ts[0]) + warm * MINUTE,
                        "requested_start_date": REQ["start_date"],
                        "warmup_minutes_requested": warm}}
    cfg = build_config()
    fills, equities, analysis = run_backtest(hlcvs, mss, cfg, "binance", arr[:, 4].copy(), ts)
    eq = np.asarray(equities)
    step = max(1, int(REQ.get("equity_every_min", 60)))
    out = {"engine": getattr(pbr, "__version__", "0.1.0"), "bot_version": REQ["bot_sha"],
           "fill_columns": FILL_COLS, "fills": [list(map(_plain, f)) for f in fills],
           "equity_shape": list(eq.shape), "equity": [list(map(_plain, r)) for r in eq[::step]],
           "n_candles": n, "analysis": {k: _plain(v) for k, v in dict(analysis).items()
                                  if isinstance(v, (int, float, bool, np.generic))}}
    Path("out.json").write_text(json.dumps(out), encoding="utf-8")


def _plain(x):
    return x.item() if hasattr(x, "item") else x


main()
