"""Descarga 1m de BTCUSDT (futuros Binance) a un parquet aparte, sin tocar el almacen vivo.

Uso (desde la raiz del repo): `python v2/scripts/descargar_1m_btc.py <salida>.parquet 2024-01-01`.
Investigacion: el parquet que escribe NO es el almacen de `data/candles/` y nada lo lee en vivo.
Licencia de los datos: ver `v2/docs/SEGURIDAD.md` y la linea de T88 en `PLAN/BACKLOG.md`.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from eim.data.providers.binance import BinanceFutures  # noqa: E402

OUT = Path(sys.argv[1])
START = int(pd.Timestamp(sys.argv[2], tz="UTC").timestamp() * 1000)
END = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
MIN = 60_000

prov = BinanceFutures()
rows: list[tuple] = []
cur = START
last_report = time.time()
while cur < END:
    stop = min(cur + 1500 * MIN, END)
    try:
        cs = prov.klines("BTCUSDT", "1m", cur, stop)
    except Exception as e:  # noqa: BLE001
        print(f"reintento tras {type(e).__name__}: {e}", flush=True)
        time.sleep(3)
        continue
    if not cs:
        cur = stop
        continue
    rows.extend((c.t, c.o, c.h, c.l, c.c, c.v) for c in cs)
    cur = cs[-1].t + MIN
    if time.time() - last_report > 20:
        print(f"{len(rows)} velas, en {pd.Timestamp(cur, unit='ms', tz='UTC')}", flush=True)
        last_report = time.time()
    time.sleep(0.12)

df = pd.DataFrame(rows, columns=["t", "o", "h", "l", "c", "v"])
df = df.drop_duplicates("t").sort_values("t")
df.to_parquet(OUT, index=False)
print(f"LISTO {len(df)} velas -> {OUT}")
bordes = df["t"].agg(["min", "max"])
print({k: str(pd.Timestamp(v, unit="ms", tz="UTC")) for k, v in bordes.items()})
