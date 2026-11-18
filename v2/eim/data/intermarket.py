"""Intermercado en el almacén (T183): velas diarias de oro, S&P 500, Nasdaq y de la cripto.

`read_intermarket` solo lee disco (lo usa `build_snapshot`); `sync_intermarket` es la única con
red y la llama el ciclo de operación con su propio ritmo (cada `INTERVAL_MS`, por activo).
Point-in-time: a `asof` solo se ve una vela diaria ya CERRADA (`t + 1 día ≤ asof`), porque su
cierre es público desde entonces; en los índices de Yahoo `t` es la medianoche de Nueva York,
después del cierre de la sesión. `seen_at` queda en cada fila para auditar cuándo se descargó.
Un activo que falla o no está no se rellena: el agente dice `no_data` con el motivo.

Archivos: `root/intermarket/<ACTIVO>.jsonl` (solo añadir; una fila por vela nueva con `seen_at`)
y `root/intermarket/_sync.json` (último intento por activo, para no pedir a Yahoo cada 10 min).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path

from eim.core import Candle
from eim.data.providers.binance import BinanceFutures
from eim.data.providers.multi_asset import fetch_ohlcv

DAY_MS = 86_400_000
INTERVAL_MS = 6 * 3_600_000      # intento por activo como mucho cada 6 h (velas diarias)
RETRY_MS = 30 * 60_000           # tras un fallo se reintenta a los 30 min, no a las 6 h
ENV = "EIM_INTERMARKET"          # «0» lo apaga (la suite de pruebas, o quien no lo quiera)
BARS = 400                       # ~1,5 años de sesiones: correlación de 60 d y tendencia de 50 d
KEEP_BARS = 400                  # lo que entra al snapshot por activo
# Activos de contexto (fuentes reales de `multi_asset`): oro como refugio, índices de EE. UU. como
# apetito por riesgo, y las dos criptos en diario para medir la correlación con los índices.
ASSETS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "XAUUSDT", "SP500", "NASDAQ")
SOURCES: dict[str, str] = {"BTCUSDT": "binance futures 1d", "ETHUSDT": "binance futures 1d",
                           "XAUUSDT": "binance futures 1d (XAUUSDT)",
                           "SP500": "yahoo finance 1d (^GSPC)",
                           "NASDAQ": "yahoo finance 1d (^IXIC)"}

Fetcher = Callable[[str, str, int], tuple[list[Candle], str]]


def enabled(env: Mapping[str, str] | None = None) -> bool:
    """Encendido salvo `EIM_INTERMARKET=0` (el mapa lo pinta «pausado» con el motivo)."""
    return (os.environ if env is None else env).get(ENV, "1") != "0"


def fetch_fast(key: str, tf: str, n: int) -> tuple[list[Candle], str]:
    """`fetch_ohlcv` sin reintentos con espera: una vela diaria puede esperar a la próxima
    pasada (`RETRY_MS`); el ciclo de operación no se queda dormido por una red caída."""
    return fetch_ohlcv(key, tf, n, client=BinanceFutures(max_retries=0))


def _dir(root: Path) -> Path:
    return root / "intermarket"


_CACHE: dict[Path, tuple[tuple[int, int], list[dict]]] = {}


def _rows(f: Path) -> list[dict]:
    """Filas del archivo; se relee solo si cambió (cada snapshot lo consulta)."""
    try:
        st = f.stat()
    except OSError:
        return []
    key = (st.st_mtime_ns, st.st_size)
    hit = _CACHE.get(f)
    if hit is not None and hit[0] == key:
        return hit[1]
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    _CACHE[f] = (key, out)
    return out


def read_intermarket(root: Path, asof: int, keep: int = KEEP_BARS
                     ) -> tuple[dict[str, list[Candle]], dict[str, str],
                                dict[str, tuple[int, int]]] | None:
    """(velas por activo, fuentes, coberturas) cerradas a `asof`; None si no hay nada."""
    d = _dir(root)
    if not d.is_dir():
        return None
    bars: dict[str, list[Candle]] = {}
    sources: dict[str, str] = {}
    coverage: dict[str, tuple[int, int]] = {}
    for key in ASSETS:
        seen: dict[int, Candle] = {}
        for r in _rows(d / f"{key}.jsonl"):
            try:
                if r["t"] + DAY_MS <= asof and r["t"] not in seen:
                    seen[r["t"]] = Candle(t=r["t"], o=r["o"], h=r["h"], l=r["l"], c=r["c"],
                                          v=r.get("v", 0.0))
            except (KeyError, TypeError, ValueError):
                continue
        cs = [seen[t] for t in sorted(seen)][-keep:]
        if cs:
            bars[key] = cs
            sources[f"intermarket:{key}"] = SOURCES.get(key, "desconocida")
            coverage[f"intermarket:{key}"] = (cs[0].t, cs[-1].t)
    return (bars, sources, coverage) if bars else None


def _state(root: Path) -> dict[str, int]:
    f = _dir(root) / "_sync.json"
    try:
        return {k: int(v) for k, v in json.loads(f.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError, AttributeError):
        return {}


def sync_intermarket(root: Path, now: int, *, fetcher: Fetcher = fetch_fast,
                     interval_ms: int = INTERVAL_MS) -> dict[str, int | str]:
    """Añade las velas diarias nuevas de cada activo; devuelve {activo: nuevas | «error: …»}.

    Cada activo tiene su propio ritmo y su propio fallo: Yahoo caído no frena al oro. Nunca borra
    lo ya guardado; una vela ya conocida no se reescribe (la primera vista manda)."""
    d = _dir(root)
    d.mkdir(parents=True, exist_ok=True)
    state = _state(root)
    out: dict[str, int | str] = {}
    for key in ASSETS:
        if now - state.get(key, 0) < interval_ms:
            continue
        state[key] = now
        try:
            candles, _src = fetcher(key, "1d", BARS)
        except Exception as e:  # noqa: BLE001 - red, límite de tasa o símbolo: se dice y se sigue
            out[key] = f"error: {type(e).__name__}: {e}"[:200]
            state[key] = now - interval_ms + RETRY_MS
            continue
        f = d / f"{key}.jsonl"
        known = {r.get("t") for r in _rows(f)}
        new = [c for c in candles if c.t not in known and c.t + DAY_MS <= now]
        if new:
            with f.open("a", encoding="utf-8") as fh:
                for c in new:
                    fh.write(json.dumps({"t": c.t, "o": c.o, "h": c.h, "l": c.l, "c": c.c,
                                         "v": c.v, "seen_at": now}) + "\n")
        out[key] = len(new)
    (d / "_sync.json").write_text(json.dumps(state), encoding="utf-8")
    return out
