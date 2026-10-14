"""Genera UNA VEZ `tests/fixtures/indicators/reference.json` con `_reference.py` (sin red).

Uso (desde v2/): python -m tests.indicators._make_fixtures
Datos: las últimas 400 velas de `tests/fixtures/ethusdt_1h_1000.csv` (OHLCV reales de Binance).
Ese CSV no trae taker_buy_v/trades/índice: para la familia flujo se derivan series sintéticas
deterministas (marcadas `synthetic` en el JSON); solo prueban la aritmética, no el mercado.
"""

from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from pathlib import Path

from tests.indicators import _reference as R

ROOT = Path(__file__).resolve().parents[1] / "fixtures"
OUT = ROOT / "indicators" / "reference.json"
N_BARS = 400


def load() -> dict[str, list]:
    with open(ROOT / "ethusdt_1h_1000.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))[-N_BARS:]
    d = {k: [float(r[k]) for r in rows] for k in ("open", "high", "low", "close", "volume")}
    d["t"] = [int(datetime.fromisoformat(r["timestamp"]).timestamp() * 1000) for r in rows]
    n = len(rows)
    d["taker_buy_v"] = [d["volume"][i] * (0.5 + 0.2 * math.sin(i / 7)) for i in range(n)]
    d["trades"] = [float(1000 + (i * 37) % 500) for i in range(n)]
    d["index"] = [d["close"][i] * (1 - 0.0004 * math.cos(i / 11)) for i in range(n)]
    return d


def build(d: dict[str, list]) -> dict[str, dict[str, list]]:
    h, lo, c, v, t = d["high"], d["low"], d["close"], d["volume"], d["t"]
    tb = d["taker_buy_v"]
    sub = R.r_sma
    mid = sub(c, 20)
    sd = R.r_std(c, 20)
    dif = [a - b for a, b in zip(R.r_ema_first(c, 12), R.r_ema_first(c, 26), strict=True)]
    dea = R.r_ema_first(dif, 9)
    rsi14 = R.r_rsi(c, 14)
    hh, ll = R.r_hhv(rsi14, 14), R.r_llv(rsi14, 14)
    st = [R.NAN if R.isn(a) or a == b else 100 * (x - b) / (a - b)
          for x, a, b in zip(rsi14, hh, ll, strict=True)]
    k_srsi = sub(st, 3)
    hh14, ll14 = R.r_hhv(h, 14), R.r_llv(lo, 14)
    mtm = [R.NAN] * 12 + [c[i] - c[i - 12] for i in range(12, len(c))]
    tr3 = R.r_ema_first(R.r_ema_first(R.r_ema_first(c, 12), 12), 12)
    trix = [R.NAN] + [100 * (tr3[i] - tr3[i - 1]) / tr3[i - 1] for i in range(1, len(c))]
    obv = [v[0]]
    for i in range(1, len(c)):
        obv.append(obv[-1] + (v[i] if c[i] > c[i - 1] else -v[i] if c[i] < c[i - 1] else 0.0))
    tp = [(h[i] + lo[i] + c[i]) / 3 for i in range(len(c))]
    cum_pv = cum_v = 0.0
    avl = []
    for i in range(len(c)):
        cum_pv += tp[i] * v[i]
        cum_v += v[i]
        avl.append(cum_pv / cum_v)
    delta = [2 * tb[i] - v[i] for i in range(len(c))]
    cvd, acc = [], 0.0
    for x in delta:
        acc += x
        cvd.append(acc)
    size = [v[i] / d["trades"][i] for i in range(len(c))]
    return {
        "MA": {f"ma{n}": sub(c, n) for n in (7, 25, 99)},
        "EMA": {f"ema{n}": R.r_ema_first(c, n) for n in (7, 25, 99)},
        "WMA": {f"wma{n}": R.r_wma(c, n) for n in (7, 25, 99)},
        "SAR": {"sar": R.r_sar(h, lo, 0.02, 0.02, 0.2)},
        "SUPER": R.r_supertrend(h, lo, c, 10, 3.0),
        "DMI": R.r_dmi(h, lo, c, 14, 6),
        "MACD": {"dif": dif, "dea": dea, "hist": [a - b for a, b in zip(dif, dea, strict=True)]},
        "RSI": {f"rsi{n}": R.r_rsi(c, n) for n in (6, 12, 24)},
        "KDJ": R.r_kdj(h, lo, c, 9, 3, 3),
        "StochRSI": {"k": k_srsi, "d": sub(k_srsi, 3)},
        "WR": {"wr": [R.NAN if R.isn(a) else -100 * (a - x) / (a - b)
                      for x, a, b in zip(c, hh14, ll14, strict=True)]},
        "CCI": {"cci": R.r_cci(h, lo, c, 14)},
        "MTM": {"mtm": mtm, "mamtm": sub(mtm, 6)},
        "TRIX": {"trix": trix, "matrix": sub(trix, 9)},
        "BOLL": {"up": [m + 2 * s for m, s in zip(mid, sd, strict=True)], "mb": mid,
                 "dn": [m - 2 * s for m, s in zip(mid, sd, strict=True)]},
        "ATR": {"atr": R.r_atr(h, lo, c, 14)},
        "VOL": {"vol": list(v), "ma5": sub(v, 5), "ma10": sub(v, 10)},
        "OBV": {"obv": obv, "maobv": sub(obv, 30)},
        "MFI": {"mfi": R.r_mfi(h, lo, c, v, 14)},
        "EMV": R.r_emv(h, lo, v, 14, 9),
        "VWAP": {"vwap": R.r_vwap(h, lo, c, v, t, 86_400_000)},
        "AVL": {"avl": avl},
        "BS.Vol": {"buy": list(tb), "sell": [v[i] - tb[i] for i in range(len(c))]},
        "TakerRatio": {"takerratio": [tb[i] / (v[i] - tb[i]) for i in range(len(c))]},
        "Delta": {"delta": delta},
        "CVD": {"cvd": cvd},
        "TradeSize": {"size": size, "ma": sub(size, 20)},
        "Basis": {"basis": [100 * (c[i] - d["index"][i]) / d["index"][i]
                            for i in range(len(c))]},
    }


def _clean(x):
    return None if R.isn(x) else x


def main() -> None:
    d = load()
    ref = build(d)
    payload = {
        "generator": "tests/indicators/_reference.py (implementación ingenua independiente)",
        "data": "tests/fixtures/ethusdt_1h_1000.csv, últimas 400 velas",
        "synthetic": ["taker_buy_v", "trades", "index"],
        "inputs": d,
        "expected": {k: {ln: [_clean(x) for x in vals] for ln, vals in lines.items()}
                     for k, lines in ref.items()},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT}: {len(ref)} indicadores")


if __name__ == "__main__":
    main()
