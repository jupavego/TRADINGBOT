"""Mercado de Hyperliquid para la copia simulada (T42): mínimos (`meta`) y velas de 1 min.

- `exchange_spec`: `szDecimals` por moneda de `meta`, guardado en `<root>/leaders/hl_meta.json`;
  si la red falla se usa la última copia; sin ninguna, la especificación queda vacía y la
  copia rechaza abrir esas monedas con su motivo («sin paso de cantidad»).
- `candles_1m`: velas por moneda en caché `<root>/cache/hl_candles/<moneda>.json`; solo se
  piden los minutos que faltan (≤ 5000 por consulta). El exchange sirve solo las 5000 velas
  más recientes de cada intervalo (≈ 3,5 días de 1 min): lo anterior solo existe en la caché.
  La reproducción las usa para marcas, stops y precio de respaldo sin cotización grabada.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from eim.copytrading.copy_params import ExchangeSpec
from eim.data.providers.binance import ProviderError

Bar = tuple[int, float, float, float, float, float]  # apertura, o, h, l, c, v
MIN_MS = 60_000
CHUNK = 5_000
log = logging.getLogger(__name__)


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def exchange_spec(info, root: str | Path) -> ExchangeSpec:
    path = Path(root) / "leaders" / "hl_meta.json"
    try:
        meta = info.meta()
        _write(path, meta)
        return ExchangeSpec.from_meta(meta)
    except Exception as exc:  # sin red o respuesta rara: la captura no debe caerse por esto
        log.warning("meta de Hyperliquid no disponible (%s): se usa la copia guardada", exc)
    if path.exists():
        return ExchangeSpec.from_meta(json.loads(path.read_text(encoding="utf-8")),
                                      source=f"hyperliquid:info.meta (copia {path.name})")
    return ExchangeSpec(source="sin meta: no se abre ninguna moneda")


def _bar(row: dict) -> Bar:
    return (int(row["t"]), float(row["o"]), float(row["h"]), float(row["l"]), float(row["c"]),
            float(row["v"]))


def candles_1m(info, coin: str, start: int, end: int, cache_dir: str | Path,
               offline: bool = False) -> list[Bar]:
    """Velas de 1 min con apertura en [start, end) (las que existan)."""
    start, end = start - start % MIN_MS, end - end % MIN_MS + MIN_MS
    path = Path(cache_dir) / f"{coin.replace('/', '_')}.json"
    have: dict[int, Bar] = {}
    lo = hi = None
    if path.exists():
        d = json.loads(path.read_text(encoding="utf-8"))
        have = {int(b[0]): tuple(b) for b in d.get("bars", [])}
        lo, hi = d.get("from"), d.get("to")
    missing = []
    if lo is None or hi is None:
        missing.append((start, end))
    else:
        if start < lo:
            missing.append((start, min(lo, end)))
        if end > hi:
            missing.append((max(hi, start), end))
    got = False
    for a, b in ([] if offline else missing):
        t = a
        while t < b:
            u = min(b, t + CHUNK * MIN_MS)
            try:
                rows = info.candles(coin, "1m", t, u - 1)
            except ProviderError as exc:
                log.warning("velas %s no disponibles (%s)", coin, exc)
                break
            for r in rows or []:
                bar = _bar(r)
                have[bar[0]] = bar
            got = True
            t = u
    if got and have:
        # cobertura = velas que hay de verdad (el exchange solo sirve las ~5000 más recientes);
        # el último minuto, quizá aún abierto, se vuelve a pedir la próxima vez
        lo, hi = min(have), max(have)
        _write(path, {"coin": coin, "from": lo, "to": hi,
                      "bars": [list(have[k]) for k in sorted(have)]})
    return [have[k] for k in sorted(have) if start <= k < end]
