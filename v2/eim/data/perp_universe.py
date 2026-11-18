"""Historia del universo de perpetuos USDT de Binance para T164 (T181). Solo análisis, sin claves.

T164 (carry y momentum transversales) solo necesita, de cada perpetuo, su **funding** y sus
**velas diarias**; no el escáner en vivo de T93. Esto lo reúne en un almacén aparte
(`data/universe_perps/`, mismo formato que `Store`), sin tocar el de BTC ni el flujo vivo.

**Despacio, a propósito.** `/fapi/v1/fundingRate` comparte con el bróker simulado un límite de
500 llamadas cada 5 min por IP; un exceso devuelve 429/418 y dejaría sin datos a la corrida de
T31 y a la captura. Con `min_interval` = 3 s son 100 cada 5 min, una quinta parte del límite.
`BinanceFutures` ya reintenta y respeta `Retry-After`.

**Reanudable.** Cada símbolo sigue desde su último dato guardado; un símbolo que falla se anota y
no detiene a los demás.

**Sesgo de supervivencia, declarado.** `exchangeInfo` lista los perpetuos vigentes y algunos en
liquidación o cerrados (`status` ≠ TRADING), no todos los que existieron. `universe.json` guarda
cuántos hay de cada estado; T164 tiene que leerlo antes de calcular nada.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

from eim.data.providers.binance import BinanceFutures
from eim.data.store import Store

DAY_MS = 86_400_000
START_MS = 1_567_296_000_000          # 2019-09-01 UTC: primer perpetuo USDT de Binance
SOURCE = "binance-futures (universo de perpetuos, T181)"
MIN_INTERVAL_S = 3.0


def universe(futures: BinanceFutures) -> list[dict]:
    """Todos los perpetuos con margen y cotización USDT que lista `exchangeInfo`, en cualquier
    estado (vigentes y los que aún aparecen en liquidación o cerrados)."""
    out = []
    for s in futures.request("/fapi/v1/exchangeInfo").get("symbols", []):
        if s.get("contractType") != "PERPETUAL" or s.get("quoteAsset") != "USDT" \
                or s.get("marginAsset") != "USDT":
            continue
        out.append({"symbol": s["symbol"], "base": s.get("baseAsset"), "status": s.get("status"),
                    "onboard_t": int(s.get("onboardDate") or 0)})
    return sorted(out, key=lambda x: x["symbol"])


def _start_funding(store: Store, sym: str, onboard: int) -> int:
    last = store.read_series("funding", sym, last=1)
    return last[-1][0] + 1 if last else max(START_MS, onboard)


def _start_candles(store: Store, sym: str, onboard: int) -> int:
    b = store.bounds(sym, "1d")
    return b[1] + DAY_MS if b else max(START_MS, onboard - onboard % DAY_MS)


def sync_symbol(store: Store, futures: BinanceFutures, info: dict, now: int) -> dict:
    """Pone al día el funding y las velas diarias de un perpetuo. Devuelve lo descargado."""
    sym, onboard = info["symbol"], info.get("onboard_t") or 0
    got = {"symbol": sym, "funding": 0, "candles": 0}
    a = _start_funding(store, sym, onboard)
    if a < now:
        rows = futures.funding_rates(sym, a, now)
        if rows:
            store.upsert_series("funding", sym, "-", rows, SOURCE)
            got["funding"] = len(rows)
    a = _start_candles(store, sym, onboard)
    if a < now - DAY_MS:
        cs = futures.klines(sym, "1d", a, now)
        if cs:
            store.upsert_candles(sym, "1d", cs, SOURCE)
            got["candles"] = len(cs)
    return got


def sync(root: Path, futures: BinanceFutures, now: int | None = None,
         symbols: list[str] | None = None, say: Callable[[str], None] = print) -> dict:
    """Universo + historia de cada símbolo; guarda `universe.json` y `sync.json` en `root`."""
    now = int(time.time() * 1000) if now is None else now
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    uni = universe(futures)
    by_status: dict[str, int] = {}
    for u in uni:
        by_status[u["status"]] = by_status.get(u["status"], 0) + 1
    (root / "universe.json").write_text(json.dumps(
        {"t": now, "n": len(uni), "by_status": by_status, "symbols": uni,
         "note": "exchangeInfo no lista todos los perpetuos retirados: sesgo de supervivencia"},
        ensure_ascii=False, indent=1), encoding="utf-8")
    store = Store(root)
    done, errors = [], {}
    todo = [u for u in uni if symbols is None or u["symbol"] in symbols]
    for i, u in enumerate(todo, 1):
        try:
            done.append(sync_symbol(store, futures, u, now))
        except Exception as exc:  # noqa: BLE001 - un símbolo no detiene a los demás
            errors[u["symbol"]] = f"{type(exc).__name__}: {exc}"[:200]
        if i % 25 == 0 or i == len(todo):
            say(f"{i}/{len(todo)} símbolos · {len(errors)} con error")
    out = {"t": now, "symbols": len(todo), "errors": errors,
           "funding_rows": sum(d["funding"] for d in done),
           "candle_rows": sum(d["candles"] for d in done), "by_status": by_status}
    (root / "sync.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eim.data.perp_universe", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("sync", "status"))
    ap.add_argument("--root", default="data/universe_perps")
    ap.add_argument("--min-interval", type=float, default=MIN_INTERVAL_S,
                    help="segundos mínimos entre llamadas (no bajar de 3: límite compartido)")
    ap.add_argument("--symbols", nargs="*", help="solo estos símbolos (por defecto, todos)")
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.cmd == "status":
        p = root / "sync.json"
        print(p.read_text(encoding="utf-8") if p.exists() else "sin sincronizar")
        return 0
    if a.min_interval < MIN_INTERVAL_S:
        print(f"--min-interval por debajo de {MIN_INTERVAL_S} s pondría en riesgo el límite "
              "compartido con el bróker simulado", file=sys.stderr)
        return 2
    out = sync(root, BinanceFutures(min_interval=a.min_interval), symbols=a.symbols)
    print(json.dumps({k: v for k, v in out.items() if k != "errors"} | {
        "errors": len(out["errors"])}, ensure_ascii=False))
    return 0 if not out["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
