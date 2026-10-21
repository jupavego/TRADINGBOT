"""Genera `trendrider_parity.json`: banderas y posturas del bot NATIVO `TrendRiderStrategy`.

Corre la estrategia real (MIT, SHA 621b0c86…, ver `THIRD_PARTY.md`) con Freqtrade y TA-Lib sobre
ventanas de 5400 velas de 1 h, con un `DataProvider` de mentira que entrega los marcos 4 h y 1 d
agregados de esas mismas velas (solo barras completas) y las de BTC (= las propias). Después aplica
el filtro de confianza de `confirm_trade_entry` (llamando a sus `_calc_confidence` y
`_get_market_regime` reales) y la regla de posición de Freqtrade. Solo se corre a mano, en el
entorno aparte de Python 3.12 (D:/eim-bots/ft-env):

    python make_trendrider_parity.py candles.json <checkout trendrider> trendrider_parity.json
"""

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
from freqtrade.enums import RunMode

WINDOW, STEP, STARTUP = 5400, 37, 210
BTC = "BTC/USDT:USDT"


class Dp:
    def __init__(self, df1h):
        self.df1h = df1h

    def current_whitelist(self):
        return [BTC]

    def get_pair_dataframe(self, pair, timeframe=None, candle_type=""):
        if timeframe == "1h":
            return self.df1h.copy()
        rule = {"4h": "4h", "1d": "1D"}[timeframe]
        need = {"4h": 4, "1d": 24}[timeframe]
        g = self.df1h.set_index("date").resample(rule, label="left", closed="left")
        out = g.agg({"open": "first", "high": "max", "low": "min", "close": "last",
                     "volume": "sum"})
        out["n"] = g["close"].count()
        return out[out["n"] == need].drop(columns="n").reset_index()

    def send_msg(self, *a, **k):
        pass


def load(checkout):
    path = Path(checkout) / "TrendRiderStrategy.py"
    spec = importlib.util.spec_from_file_location("TrendRiderStrategy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    config = {"stake_currency": "USDT", "dry_run": True, "runmode": RunMode.BACKTEST,
              "trading_mode": "futures", "margin_mode": "isolated", "timeframe": "1h"}
    strat = mod.TrendRiderStrategy(config)
    strat.ft_load_hyper_params()   # lo que hace el resolvedor: aplica buy_params/sell_params
    return strat


def positions(enter, exit_):
    state, out = 0, []
    for i in range(len(enter)):
        if i < STARTUP:
            state = 0
        elif enter[i] and not exit_[i]:
            state = 1
        elif state > 0 and exit_[i]:
            state = 0
        out.append(state)
    return out


def main(src, checkout, dst):
    rows = json.load(open(src))
    strat = load(checkout)
    out = {"window": WINDOW, "candles": rows, "native": {}}
    for i in range(WINDOW - 1, len(rows), STEP):
        win = rows[i + 1 - WINDOW:i + 1]
        df = pd.DataFrame(win, columns=["t", "open", "high", "low", "close", "volume"])
        df.insert(0, "date", pd.to_datetime(df.pop("t"), unit="ms", utc=True))
        strat.dp = Dp(df[["date", "open", "high", "low", "close", "volume"]])
        d = strat.populate_indicators(df.copy(), {"pair": BTC})
        d = strat.populate_entry_trend(d, {"pair": BTC})
        d = strat.populate_exit_trend(d, {"pair": BTC})
        enter = d.get("enter_long", pd.Series(0, index=d.index)).fillna(0).astype(int).tolist()
        exit_ = d.get("exit_long", pd.Series(0, index=d.index)).fillna(0).astype(int).tolist()
        conf = []
        for k in range(len(d)):
            if enter[k]:
                last = d.iloc[k]
                num = strat._calc_confidence(last)[3]
                bear = "Bear" in strat._get_market_regime(last)
                if num < (6 if bear else 5):
                    enter[k] = 0
                conf.append((k, num))
        pos = positions(enter, exit_)
        out["native"][str(rows[i][0])] = {
            "stance": pos[-1], "enter_last": enter[-1], "exit_last": exit_[-1],
            "n_enter": int(sum(enter[STARTUP:])), "n_exit": int(sum(exit_[STARTUP:])),
            "conf_last": next((c for k, c in conf if k == len(d) - 1), None)}
    json.dump(out, open(dst, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main(*sys.argv[1:4])
