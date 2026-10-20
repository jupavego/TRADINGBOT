"""Genera `jesse_parity.json`: posturas de las reglas de `jesse-example-strategies` calculadas como
las calcula Jesse (vela a vela, indicadores de TA-Lib sobre `candles[:i+1]`) en velas reales de 1 h.

No ejecuta el framework de Jesse (necesita base de datos, Redis y su propio motor de indicadores en
Rust); replica a mano las condiciones de cada `should_long/should_short/update_position` con
TA-Lib, que es la biblioteca que usaban estas estrategias (SHA 7c91e0a3, 2024-03-21). Se corre a
mano en el entorno aparte de Python 3.12 (D:/eim-bots/ft-env, trae TA-Lib):

    python make_jesse_parity.py candles.json jesse_parity.json

`candles.json` = [[t, o, h, l, c, v], …] (≥ 1000 + 200 velas). Ventana por estrategia: 1000 velas,
como el adaptador. Se guardan las posturas tras la última vela de cada ventana, cada STEP velas.
"""

import json
import sys

import numpy as np
import talib

WINDOW, STEP, WARMUP = 1000, 7, 210   # WARMUP: igual que el adaptador


def crossed(s, level, above):
    a, b = s[-1], s[-2]
    return (a > level and b <= level) if above else (a < level and b >= level)


def rules(name, o, h, l, c):
    """(largo, corto, salir_de_largo, salir_de_corto) con los datos hasta la vela actual."""
    f = False
    if len(c) < WARMUP:
        return f, f, f, f
    if name == "Donchian":
        up, lo = np.max(h[-21:-1]), np.min(l[-21:-1])        # donchian(candles[:-1], 20)
        return (c[-1] > up and c[-1] > talib.SMA(c, 200)[-1]), f, c[-1] < lo, f
    if name == "RSI2":
        slow, fast, r = talib.SMA(c, 200)[-1], talib.SMA(c, 5)[-1], talib.RSI(c, 2)[-1]
        return (c[-1] > slow and r <= 10), (c[-1] < slow and r >= 90), c[-1] > fast, c[-1] < fast
    if name == "SMACrossover":
        fa, sl = talib.SMA(c, 50)[-1], talib.SMA(c, 200)[-1]
        return fa > sl, fa < sl, fa < sl, fa > sl
    if name == "MACD_EMA":
        m, s, _ = talib.MACD(c, 12, 26, 9)
        e = talib.EMA(c, 100)[-1]
        return (c[-1] > e and m[-1] > s[-1]), f, (m[-1] < s[-1] and c[-1] < e), f
    if name == "TradingView_RSI":
        r = talib.RSI(c, 5)
        return crossed(r, 35, True), f, (crossed(r, 75, False) or crossed(r, 10, False)), f
    if name == "TurtleRules":
        ue, le = np.max(h[-20:]), np.min(l[-20:])
        ux, lx = np.max(h[-10:]), np.min(l[-10:])
        entry = "L" if h[-1] >= ue else ("S" if l[-1] <= le else None)
        exit_ = "xS" if h[-1] >= ux else ("xL" if l[-1] <= lx else None)
        return entry == "L", entry == "S", (entry == "S" or exit_ == "xL"), (entry == "L" or exit_ == "xS")
    raise KeyError(name)


def stance(name, win):
    o, h, l, c = (np.array([r[k] for r in win], float) for k in (1, 2, 3, 4))
    state = 0
    for j in range(len(win)):
        el, es, xl, xs = rules(name, o[:j + 1], h[:j + 1], l[:j + 1], c[:j + 1])
        if state == 0:
            state = 1 if el else (-1 if es else 0)
        elif (state > 0 and xl) or (state < 0 and xs):
            state = 0
    return state


def main(src, dst):
    rows = json.load(open(src))
    names = ["Donchian", "RSI2", "SMACrossover", "MACD_EMA", "TradingView_RSI", "TurtleRules"]
    out = {"candles": rows, "window": WINDOW, "native": {n: {} for n in names}}
    for i in range(WINDOW - 1, len(rows), STEP):
        for n in names:
            out["native"][n][str(rows[i][0])] = stance(n, rows[i + 1 - WINDOW:i + 1])
    json.dump(out, open(dst, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main(*sys.argv[1:3])
