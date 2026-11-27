"""Velas diarias y semanales alineadas a la sesión (T90).

En cripto (24/7) la vela diaria es el día UTC y la semanal la semana que empieza el lunes a
las 00:00 UTC, como las publica Binance. En un instrumento con sesión eso no sirve: la vela
diaria de la NYSE es la sesión de 14:30 a 21:00 UTC (13:30 a 20:00 en verano), y la de un
día UTC mezclaría dos sesiones distintas o ninguna. Aquí la vela es la de la sesión del
calendario del instrumento, y la semana es la de sus sesiones.

También decide cuándo está **cerrada** una vela de sesión a `asof` (`closed_before`): la vela
diaria de una acción cierra con la sesión, no 24 h después de abrir.

Funciones puras: el calendario entra como `sesiones(inicio, fin)` (`quality.SessionsFn`).
"""

from __future__ import annotations

import bisect
import datetime as dt
from collections.abc import Sequence

from eim.core import Candle
from eim.data.quality import SessionsFn
from eim.data.timeframes import DAY_MS, align, tf_ms

WEEK_MS = 7 * DAY_MS
_LOOK_MS = 14 * DAY_MS          # ventana para buscar la sesión vigente alrededor de `asof`


def _day_start(t: int) -> int:
    return t - t % DAY_MS


def _monday(t: int) -> int:
    return align(t, "1w")


def _week_key(t: int) -> tuple[int, int]:
    iso = dt.datetime.fromtimestamp(t / 1000, tz=dt.UTC).isocalendar()
    return iso[0], iso[1]


def _merge(group: Sequence[Candle], t: int) -> Candle:
    tb = [c.taker_buy_v for c in group]
    tr = [c.trades for c in group]
    return Candle(t=t, o=group[0].o, h=max(c.h for c in group), l=min(c.l for c in group),
                  c=group[-1].c, v=sum(c.v for c in group),
                  taker_buy_v=None if None in tb else sum(tb),
                  trades=None if None in tr else sum(tr))


def aggregate(candles: Sequence[Candle], timeframe: str, *, sessions: SessionsFn | None = None,
              asof: int | None = None) -> list[Candle]:
    """Agrega velas intradía a `1d` o `1w`.

    Sin `sessions` (24/7): rejilla UTC (`1w` empieza el lunes). Con `sessions`: una vela por
    sesión (`t` = apertura de la sesión) o por semana de sesiones (`t` = apertura de su primera
    sesión); lo que caiga fuera de sesión no entra. Con `asof`, solo grupos ya cerrados.
    """
    if timeframe not in ("1d", "1w"):
        raise ValueError(f"solo se agrega a 1d o 1w, no a {timeframe!r}")
    cs = sorted(candles, key=lambda c: c.t)
    if not cs:
        return []
    groups: dict[object, list[Candle]] = {}
    starts: dict[object, int] = {}
    ends: dict[object, int] = {}
    if sessions is None:
        step = tf_ms(timeframe)
        for c in cs:
            k = align(c.t, timeframe)
            groups.setdefault(k, []).append(c)
            starts[k], ends[k] = k, k + step
    else:
        sess = sessions(cs[0].t, cs[-1].t + DAY_MS)
        opens = [s.open_t for s in sess]
        for c in cs:
            i = bisect.bisect_right(opens, c.t) - 1
            if i < 0 or c.t >= sess[i].close_t:
                continue                                  # fuera de sesión: no se inventa
            s = sess[i]
            k: object = s.open_t if timeframe == "1d" else _week_key(s.open_t)
            groups.setdefault(k, []).append(c)
            starts.setdefault(k, s.open_t)
            ends[k] = s.close_t if timeframe == "1d" else _monday(s.open_t) + WEEK_MS
    out = []
    for k, g in groups.items():
        if asof is not None and ends[k] > asof:
            continue
        out.append(_merge(g, starts[k]))
    return sorted(out, key=lambda c: c.t)


def closed_before(timeframe: str, asof: int, sessions: SessionsFn | None = None) -> int:
    """Cota EXCLUSIVA de `t` de las velas cerradas a `asof`.

    Sin `sessions` es la regla de siempre (`t + marco <= asof`). Con `sessions` y un marco de
    sesión, la vela del día (o de la semana) está cerrada cuando su sesión (o la última de su
    semana) ha cerrado: se busca la primera sesión aún abierta o futura y se corta en el inicio
    de su día UTC (de su lunes, en `1w`).
    """
    step = tf_ms(timeframe)
    if sessions is None or step < DAY_MS:
        return asof - step + 1
    pending = [s for s in sessions(asof - _LOOK_MS, asof + _LOOK_MS) if s.close_t > asof]
    if not pending:
        return asof + 1
    first = pending[0].open_t
    cut = _day_start(first) if timeframe == "1d" else _monday(first)
    return min(asof + 1, cut)
