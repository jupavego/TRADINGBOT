"""Caché en disco de los agregados de microestructura de las velas ya cerradas (T206).

Por qué: `/v2/snapshot` de 500 velas de 1 h volvía a leer **toda** la ventana en cada carga del
panel —1,6 millones de fotos del libro a Python y la misma agregación de trades— y eso eran 113 s
medidos el 2026-11-26 (232 s en frío) y unos 2 GB de memoria que la API no devolvía. Una vela
cerrada no vuelve a cambiar: sus agregados se calculan una vez y se guardan aquí.

**Sin cambiar ninguna cifra** (BACKLOG T206 (2), la vía exacta): se guarda lo que `combine`
calcularía para esa vela, en el mismo orden de suma, no una agregación nueva dentro de DuckDB.
Por eso cada entrada lleva dos OFI: el encadenado (su primera foto se empareja con la última de
la vela anterior, que es lo que pasa en mitad de una ventana) y el de la **primera vela con
datos** de la ventana, cuya primera foto no tiene pareja. `eim.data.micro` elige el que toca.

Invalidación: un hueco de la captura puede anotarse tarde, y los huecos cambian tanto `complete`
como el OFI. Cada entrada guarda `gsig`, cuántos tramos de hueco tocaban la vela y la anterior
cuando se calculó; si hoy son otros, la vela se recalcula. La compactación de `hft_ops.maintain`
no cuenta: verifica filas y sumas antes de sustituir, así que los valores son los mismos.

Un fallo al leer o al escribir nunca es un error: la caché es un atajo, no una fuente.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import suppress
from pathlib import Path

DIR = "micro_cache"
VERSION = 1
DAY_MS = 86_400_000
SETTLE_MS = 600_000        # una vela recién cerrada no se guarda: la captura vuelca cada ~30 s
# (buy, sell, trades, ofi encadenado, ofi sin pareja previa, Σ desequilibrio, nº, hubo fotos, gsig)
Entry = tuple[float, float, int, float, float, float, int, bool, int]


def _dir(root: Path, symbol: str, step: int, ignore_liq: bool) -> Path:
    return (Path(root) / DIR / f"symbol={symbol}" / f"step={step}"
            / f"liq={1 if ignore_liq else 0}")


def _day_file(root: Path, symbol: str, step: int, ignore_liq: bool, day_ms: int) -> Path:
    day = time.strftime("%Y-%m-%d", time.gmtime(day_ms / 1000))
    return _dir(root, symbol, step, ignore_liq) / f"date={day}.json"


def _days(t0: int, end: int) -> list[int]:
    first = t0 - t0 % DAY_MS
    return list(range(first, max(end, first + 1), DAY_MS))


def _read_day(path: Path) -> dict[int, Entry]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(d, dict) or d.get("version") != VERSION:
        return {}
    out: dict[int, Entry] = {}
    for k, v in (d.get("bars") or {}).items():
        with suppress(ValueError, TypeError):
            buy, sell, cnt, ofi, ofi0, imb, imb_n, seen, gsig = v
            out[int(k)] = (float(buy), float(sell), int(cnt), float(ofi), float(ofi0),
                           float(imb), int(imb_n), bool(seen), int(gsig))
    return out


def load(root: Path, symbol: str, step: int, ignore_liq: bool,
         t0: int, end: int) -> dict[int, Entry]:
    """Lo guardado para las velas de `[t0, end)`. Vacío si no hay nada o no se puede leer."""
    out: dict[int, Entry] = {}
    for day in _days(t0, end):
        for t, e in _read_day(_day_file(root, symbol, step, ignore_liq, day)).items():
            if t0 <= t < end:
                out[t] = e
    return out


def settled(t_end: int, now_ms: int | None = None) -> bool:
    """¿La vela que acaba en `t_end` lleva cerrada lo bastante como para guardarla?"""
    now = int(time.time() * 1000) if now_ms is None else now_ms
    return t_end + SETTLE_MS <= now


def save(root: Path, symbol: str, step: int, ignore_liq: bool,
         entries: dict[int, Entry], now_ms: int | None = None) -> int:
    """Añade `entries` (solo las velas ya asentadas) a los archivos del día que les toca.

    Devuelve cuántas se guardaron. Escritura atómica (`os.replace`): otro proceso que lea a la
    vez ve el archivo entero, viejo o nuevo, y dos que escriban a la vez guardan lo mismo.
    """
    nuevas = {t: e for t, e in entries.items() if settled(t + step, now_ms)}
    if not nuevas:
        return 0
    guardadas = 0
    for day in sorted({t - t % DAY_MS for t in nuevas}):
        path = _day_file(root, symbol, step, ignore_liq, day)
        del_dia = {t: e for t, e in nuevas.items() if t - t % DAY_MS == day}
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            bars = _read_day(path)
            bars.update(del_dia)
            tmp.write_text(json.dumps({"version": VERSION,
                                       "bars": {str(t): list(e) for t, e in sorted(bars.items())}},
                                      ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
            guardadas += len(del_dia)
        except OSError:
            with suppress(OSError):
                tmp.unlink()
    return guardadas
