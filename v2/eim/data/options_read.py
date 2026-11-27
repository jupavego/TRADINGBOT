"""Lectura de la última toma de opciones para el snapshot (T214). Solo lee; nunca descarga.

Las tomas las escribe el colector de T213 (`eim/data/options_chain.py`) en
`data/options/<MONEDA>/<AAAA-MM-DD>/<HH>.jsonl.gz` con su `<HH>.quality.json` al lado. Aquí se
busca la **más reciente con `taken_ms <= asof`** (nunca una posterior: sin mirar el futuro) y no
más vieja que `MAX_AGE_MS`; si no la hay, `None` y el agente lo dice. No se rellena nada: una
hora sin toma es una hora sin toma.

Las tomas solo existen en el equipo donde corre el colector (la portátil, ◆ de T213): en otro
equipo el snapshot sale sin cadena y el agente `vol_surface` responde «sin datos» con el motivo.
"""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from eim.core.options import OptionChain, OptionRow

DIR = "options"
MAX_AGE_MS = 26 * 3_600_000          # más vieja que esto no entra (el agente avisa desde 2 h)
#: Moneda base de las cadenas por símbolo del proyecto (T213 solo recoge BTC; ETH si cabe).
OPTION_BASE = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}
SOURCE = "deribit-options (API pública, nivel 1, solo uso personal)"


def option_currency(symbol: str) -> str | None:
    return OPTION_BASE.get(symbol.upper())


def _candidates(root: Path, currency: str, asof: int) -> list[Path]:
    """Tomas del día de `asof` y del anterior, de la más reciente a la más vieja."""
    base = Path(root) / DIR / currency
    d = datetime.fromtimestamp(asof / 1000, UTC).date()
    out: list[Path] = []
    for day in (d, d - timedelta(days=1)):
        folder = base / day.isoformat()
        if folder.is_dir():
            out += sorted(folder.glob("*.jsonl.gz"), reverse=True)
    return out


def _taken_ms(data_path: Path) -> int | None:
    q = data_path.with_name(data_path.name.replace(".jsonl.gz", ".quality.json"))
    try:
        return int(json.loads(q.read_text(encoding="utf-8"))["taken_ms"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


@lru_cache(maxsize=8)
def _load(path: str, mtime_ns: int, currency: str, taken_ms: int) -> OptionChain:
    """Filas de una toma (caché por ruta y fecha de modificación: el ciclo la relee cada minuto)."""
    del mtime_ns                                   # solo forma parte de la clave de la caché
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        raw = [json.loads(line) for line in fh if line.strip()]
    rows = [OptionRow(instrument=r["instrument"], expiry=int(r["expiry"]),
                      strike=float(r["strike"]), kind=r["kind"], bid=r.get("bid"),
                      ask=r.get("ask"), mark=float(r["mark"]), mark_iv=float(r["mark_iv"]),
                      underlying=float(r["underlying"]), rate=float(r.get("rate") or 0.0),
                      oi=r.get("oi")) for r in raw]
    return OptionChain(source=f"{SOURCE} {currency}", currency=currency, taken_ms=taken_ms,
                       rows=rows)


def read_option_chain(root: Path, symbol: str, asof: int,
                      max_age_ms: int = MAX_AGE_MS) -> OptionChain | None:
    """Última toma de la moneda base de `symbol` conocida a `asof`; `None` si no hay."""
    cur = option_currency(symbol)
    if cur is None or not (Path(root) / DIR / cur).is_dir():
        return None
    for path in _candidates(Path(root), cur, asof):
        taken = _taken_ms(path)
        if taken is None or taken > asof:
            continue
        if asof - taken > max_age_ms:
            return None
        try:
            return _load(str(path), path.stat().st_mtime_ns, cur, taken)
        except (OSError, ValueError, KeyError, TypeError):
            continue                               # toma ilegible: se prueba la anterior
    return None
