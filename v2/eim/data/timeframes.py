"""Marcos temporales soportados y su duración en ms."""

from __future__ import annotations

from eim.instruments import registry

TF_MS: dict[str, int] = {
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
}

DAY_MS = 86_400_000

# Marcos de sesión (T90, ◆ de T87: `1d` de primera clase). El almacén, `build_snapshot` y la
# sincronización los aceptan, pero la API y la UI NO los exponen: lo que validan los
# endpoints sigue siendo `TF_MS`, que no cambia. En un instrumento con sesión (acciones,
# índices) la vela diaria es la de la sesión y la semanal la de la semana de sesiones
# (`eim/data/session_bars.py`), no la del día o la semana UTC.
SESSION_TF_MS: dict[str, int] = {"1d": DAY_MS, "1w": 7 * DAY_MS}

# Marcos solo de almacén/histórico: no se exponen en la API ni en la UI
# (T43: triangular 1 min; 5m: velas de NFI, agregadas de 1m). `1d` salió de aquí en T90.
STORE_ONLY_TF_MS: dict[str, int] = {"1m": 60_000, "5m": 300_000}

# Desfase de la rejilla respecto del epoch: el epoch cae en jueves y la semana de Binance (y
# la ISO) empieza el lunes a las 00:00 UTC, 4 días después. Los demás marcos, sin desfase.
TF_OFFSET_MS: dict[str, int] = {"1w": 4 * DAY_MS}

# T89: SYMBOLS y FOCUS ya no se escriben aquí, se DERIVAN del registro de instrumentos
# (`eim/instruments/registry.py`), que es donde se da de alta un instrumento desde la fase 17.
# Su valor no cambia: ("BTCUSDT", "ETHUSDT") y ("BTCUSDT",), y `tests/instruments/` lo fija.
# Foco actual: lo que los servicios analizan en vivo y lo que muestra la UI. 2026-10-15: solo
# BTCUSDT; 2026-10-21: volvió ETHUSDT; 2026-10-22 (T122, decisión del usuario): de nuevo solo
# BTCUSDT. ETHUSDT sigue en SYMBOLS (la API y el almacén conservan y sirven su historia), pero
# ningún servicio en vivo lo analiza, simula ni propone, y la UI no lo pide.
SYMBOLS: tuple[str, ...] = registry.store_symbols()
FOCUS: tuple[str, ...] = registry.focus_symbols()


def tf_ms(timeframe: str) -> int:
    """Duración del marco en ms; falla si no está soportado."""
    for table in (TF_MS, SESSION_TF_MS, STORE_ONLY_TF_MS):
        if timeframe in table:
            return table[timeframe]
    raise ValueError(f"marco no soportado: {timeframe!r} (válidos: {list(TF_MS)})")


def tf_offset(timeframe: str) -> int:
    """Desfase de la rejilla del marco respecto del epoch (0 salvo `1w`: lunes)."""
    return TF_OFFSET_MS.get(timeframe, 0)


def align(t: int, timeframe: str) -> int:
    """Inicio de la vela del marco que contiene `t` en la rejilla UTC (lunes para `1w`).

    Es la rejilla de un instrumento 24/7; uno con sesión alinea a su calendario
    (`eim/data/session_bars.py`).
    """
    step, off = tf_ms(timeframe), tf_offset(timeframe)
    return t - (t - off) % step


def analysis_ladder(timeframe: str) -> list[str]:
    """Escalera de marcos vecinos para el snapshot.

    Un marco de `TF_MS` ve solo `TF_MS` —así el 4 h de BTC no gana un vecino diario y su
    snapshot sigue idéntico—; un marco de sesión ve también los intradía (`1d`: 4 h y 1 sem).
    """
    if timeframe in TF_MS:
        return sorted(TF_MS, key=TF_MS.__getitem__)
    both = TF_MS | SESSION_TF_MS
    return sorted(both, key=both.__getitem__)
