"""Genera `hummingbot_parity.json`: posturas e indicadores del bot NATIVO en las mismas velas (T57).

Ejecuta, por ventana de `max_records` velas, las líneas de `update_processed_data` de
`bollinger_v1.py` y `macd_bb_v1.py` de Hummingbot (Apache-2.0, commit 9af100d6…, ver
`THIRD_PARTY.md`) con `pandas-ta` real, sin el resto del framework. Solo se corre a mano, en un
entorno aparte (Python ≥ 3.12 con `pandas-ta>=0.4.71b0`): `pandas-ta` no es dependencia de EIM.

    python make_hummingbot_parity.py ../ethusdt_1h_1000.csv hummingbot_parity.json
"""

import json
import sys

import pandas as pd
import pandas_ta as ta  # noqa: F401  (registra df.ta)

N_BARS = 1000  # velas del CSV que se guardan en el fixture (todas)
BB = {"bb_length": 100, "bb_std": 2.0, "bb_long_threshold": 0.0, "bb_short_threshold": 1.0}
MACD = {**BB, "macd_fast": 21, "macd_slow": 42, "macd_signal": 9}


def bollinger_v1(df: pd.DataFrame, c: dict) -> tuple[int, dict]:
    # --- líneas de update_processed_data (bollinger_v1.py) ---
    df.ta.bbands(length=c["bb_length"], lower_std=c["bb_std"], upper_std=c["bb_std"], append=True)
    bbp = df[f"BBP_{c['bb_length']}_{c['bb_std']}_{c['bb_std']}"]
    long_condition = bbp < c["bb_long_threshold"]
    short_condition = bbp > c["bb_short_threshold"]
    df["signal"] = 0
    df.loc[long_condition, "signal"] = 1
    df.loc[short_condition, "signal"] = -1
    return int(df["signal"].iloc[-1]), {"bbp": float(bbp.iloc[-1])}


def macd_bb_v1(df: pd.DataFrame, c: dict) -> tuple[int, dict]:
    # --- líneas de update_processed_data (macd_bb_v1.py) ---
    df.ta.bbands(length=c["bb_length"], lower_std=c["bb_std"], upper_std=c["bb_std"], append=True)
    df.ta.macd(fast=c["macd_fast"], slow=c["macd_slow"], signal=c["macd_signal"], append=True)
    bbp = df[f"BBP_{c['bb_length']}_{c['bb_std']}_{c['bb_std']}"]
    macdh = df[f"MACDh_{c['macd_fast']}_{c['macd_slow']}_{c['macd_signal']}"]
    macd = df[f"MACD_{c['macd_fast']}_{c['macd_slow']}_{c['macd_signal']}"]
    long_condition = (bbp < c["bb_long_threshold"]) & (macdh > 0) & (macd < 0)
    short_condition = (bbp > c["bb_short_threshold"]) & (macdh < 0) & (macd > 0)
    df["signal"] = 0
    df.loc[long_condition, "signal"] = 1
    df.loc[short_condition, "signal"] = -1
    return int(df["signal"].iloc[-1]), {"bbp": float(bbp.iloc[-1]), "macd": float(macd.iloc[-1]),
                                        "macdh": float(macdh.iloc[-1])}


def main(src: str, dst: str) -> None:
    raw = pd.read_csv(src).tail(N_BARS)
    stamps = pd.to_datetime(raw["timestamp"], utc=True)
    t = stamps.astype("datetime64[ms, UTC]").astype("int64").tolist()  # ms (pandas 3 usa µs)
    cols = ["open", "high", "low", "close", "volume"]
    candles = [[ti, *map(float, row)] for ti, row in zip(t, raw[cols].to_numpy(), strict=True)]
    out = {"symbol": "ETHUSDT", "timeframe": "1h", "candles": candles,
           "pandas_ta": ta.version, "native": {}}
    for name, fn, cfg, need in (("bollinger_v1", bollinger_v1, BB, BB["bb_length"]),
                                ("macd_bb_v1", macd_bb_v1, MACD,
                                 max(MACD["macd_slow"], MACD["macd_fast"], MACD["macd_signal"],
                                     MACD["bb_length"]) + 20)):
        sigs, feats = {}, {}
        for i in range(need - 1, len(raw)):
            win = raw.iloc[i + 1 - need:i + 1][cols].reset_index(drop=True).copy()
            sigs[str(t[i])], feats[str(t[i])] = fn(win, cfg)
        out["native"][name] = {"params": cfg, "max_records": need, "signals": sigs,
                               "features": feats}
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
