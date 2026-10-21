"""Carga de historia de un símbolo nuevo: velas de cada marco + derivados (funding, OI, L/S, base).

Uso (desde `v2/`): `python -m eim.data.backfill --symbols ETHUSDT [--bars 1700] [--data-dir data]`.
Es incremental (`sync_candles`/`sync_derivatives`): repetirlo solo descarga lo que falta. Los
derivados de Binance tienen retención corta (OI y L/S ≈ 30 d): se piden desde el inicio de las
velas del marco, y lo que el proveedor no devuelva queda como cobertura real, no inventada.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from eim.data.providers.base import Provider
from eim.data.store import Store
from eim.data.sync import sync_candles, sync_derivatives
from eim.data.timeframes import TF_MS, tf_ms


def backfill_symbol(store: Store, provider: Provider, symbol: str, bars: int = 1700,
                    now: int | None = None) -> dict[str, dict]:
    """Rellena `bars` velas por marco y los derivados. Devuelve el resumen por marco."""
    now = now if now is not None else int(time.time() * 1000)
    out: dict[str, dict] = {}
    for tf in TF_MS:
        start = now - bars * tf_ms(tf)
        res = {"candles": sync_candles(store, provider, symbol, tf, start, now)}
        try:
            res["derivatives"] = sync_derivatives(store, provider, symbol, tf, start, now)
        except Exception as e:  # noqa: BLE001 - los derivados son opcionales: se informa y se sigue
            res["derivatives"] = {"error": f"{type(e).__name__}: {e}"}
        out[tf] = res
    return out


def main() -> None:
    from eim.data.providers.binance import BinanceFutures

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", required=True)
    ap.add_argument("--bars", type=int, default=1700)
    ap.add_argument("--data-dir", default="data")
    a = ap.parse_args()
    store, prov = Store(Path(a.data_dir)), BinanceFutures()
    for sym in a.symbols:
        for tf, res in backfill_symbol(store, prov, sym, a.bars).items():
            print(f"{sym} {tf}: {res}")


if __name__ == "__main__":
    main()
