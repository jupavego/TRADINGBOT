"""Calidad por dato (T90): cerrado frente a roto, frescura y señales de una serie dañada.

Hasta T89 un hueco era cualquier salto mayor que el marco, porque todo era 24/7: un fin de
semana de acciones o de FX salía como «faltan 48 velas». Aquí el hueco se juzga contra el
calendario del instrumento (`eim/instruments/calendars.py`): si el mercado estaba cerrado no
es un hueco, es un cierre, y se cuenta aparte. En cripto (24/7) no cambia nada.

Funciones **puras** sobre listas y arreglos: el almacén las alimenta desde
`eim/data/quality_io.py`. Un calendario se pasa como función `sesiones(inicio, fin)` para que
las pruebas no dependan de `exchange_calendars`; `calendar_sessions` construye la real.

El informe (`SeriesQuality`) mide continuidad, frescura, duplicados, saltos de precio
anómalos, volumen cero y alineación (una vela fuera de sesión delata una zona horaria mal
puesta), y su resumen viaja en `MarketSnapshot.sources/coverage` (`marks`).
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Callable, Sequence

from eim.core.market import Frozen
from eim.instruments.calendar_specs import Session

SessionsFn = Callable[[int, int], list[Session]]

#: Velas de margen antes de llamar «obsoleta» a una serie, por clase de activo. Cripto deja
#: dos (la vela recién cerrada puede tardar unos segundos en llegar); el resto, una, porque su
#: calendario ya descuenta noches, fines de semana y festivos.
STALE_GRACE_BARS: dict[str, int] = {"crypto": 2}
DEFAULT_GRACE_BARS = 1
JUMP_SIGMAS = 8.0          # salto anómalo: |rendimiento log| > 8 σ robustas…
JUMP_FLOOR = 0.15          # …y además > 15 % (un 1 % en una serie quieta no es un salto)
MAX_LISTED = 5             # cuántos instantes de cada problema se citan en el informe


def calendar_sessions(calendar, *, underlying: bool = False) -> SessionsFn:
    """`sesiones(inicio, fin)` de un calendario (id o instrumento) del registro."""
    from eim.instruments import calendars

    def fn(start: int, end: int) -> list[Session]:
        return calendars.sessions(calendar, start, end, underlying=underlying)
    return fn


def _overlaps(sess: Sequence[Session], opens: Sequence[int], a: int, b: int) -> bool:
    """¿La vela [a, b) toca alguna sesión? (`sess` ordenadas; `opens` sus aperturas)."""
    k = bisect.bisect_left(opens, b)            # sesiones que abren antes de que acabe la vela
    return k > 0 and sess[k - 1].close_t > a


def calendar_gaps(gaps: Sequence[tuple[int, int]], step: int, sessions: SessionsFn
                  ) -> tuple[list[tuple[int, int]], int]:
    """Separa los huecos brutos en (huecos de verdad, nº de huecos que eran cierre).

    Cada hueco bruto `(primera t que falta, última t que falta)` se recorre en la rejilla de la
    propia serie; una casilla falta de verdad solo si su vela toca una sesión. Lo que queda se
    agrupa en tramos contiguos. Un hueco del que no queda nada era un cierre.
    """
    real: list[tuple[int, int]] = []
    closed = 0
    for g0, g1 in gaps:
        if g1 < g0:                  # salto de hora en velas de sesión: no falta ninguna casilla
            continue
        sess = sessions(g0, g1 + step)
        opens = [s.open_t for s in sess]
        run: list[int] = []
        found = False
        for t in range(g0, g1 + 1, step):
            if _overlaps(sess, opens, t, t + step):
                found = True
                if run and t - run[-1] != step:
                    real.append((run[0], run[-1]))
                    run = []
                run.append(t)
        if run:
            real.append((run[0], run[-1]))
        closed += not found
    return real, closed


def expected_slots(first: int, last: int, step: int, sessions: SessionsFn | None) -> int:
    """Casillas de la rejilla de la serie entre `first` y `last` (incluidas) que tocan sesión."""
    if last < first:
        return 0
    if sessions is None:
        return (last - first) // step + 1
    sess = sessions(first, last + step)
    opens = [s.open_t for s in sess]
    return sum(1 for t in range(first, last + 1, step) if _overlaps(sess, opens, t, t + step))


def stale_grace(asset_class: str | None) -> int:
    return STALE_GRACE_BARS.get(str(asset_class or ""), DEFAULT_GRACE_BARS)


class SeriesQuality(Frozen):
    """Informe de calidad de una serie de velas a `asof`."""

    status: str                         # ok · obsoleta · rota · sin_datos · desconocida
    rows: int
    first_t: int | None = None
    last_t: int | None = None
    expected: int | None = None         # casillas que el calendario esperaba con datos
    continuity: float | None = None     # rows / expected, tope 1
    gaps: list[tuple[int, int]] = []    # huecos de verdad (abierto y sin datos)
    missing_bars: int = 0
    closed_gaps: int = 0                # huecos que eran mercado cerrado: no cuentan
    duplicates: int = 0
    jumps: list[int] = []               # aperturas de las velas con salto anómalo (máx. 5)
    n_jumps: int = 0
    zero_volume: int | None = None      # None = el instrumento no declara volumen
    off_session: int = 0                # velas fuera de sesión (¿zona horaria?)
    freshness_ms: int | None = None     # asof − cierre de la última vela
    stale: bool | None = None           # None = sin calendario para juzgarlo
    calendar_id: str = ""
    flags: list[str] = []

    @property
    def broken(self) -> bool:
        return self.status == "rota"


def _jumps(t: Sequence[int], c: Sequence[float]) -> list[int]:
    rets = [math.log(b / a) for a, b in zip(c, c[1:], strict=False) if a > 0 and b > 0]
    if len(rets) < 10:
        return []
    med = sorted(rets)[len(rets) // 2]
    mad = sorted(abs(r - med) for r in rets)[len(rets) // 2]
    thr = max(JUMP_SIGMAS * 1.4826 * mad, JUMP_FLOOR)
    out = []
    for i in range(1, len(c)):
        if c[i - 1] > 0 and c[i] > 0 and abs(math.log(c[i] / c[i - 1]) - med) > thr:
            out.append(int(t[i]))
    return out


def _continuous(t: Sequence[int], step: int, asof: int, raw_gaps, delay_ms: int):
    """24/7: nunca cierra, así que todo hueco es de verdad y la rejilla es la del epoch."""
    first, last = int(t[0]), int(t[-1])
    off = sum(1 for x in t if (int(x) - first) % step)
    due = max(0, (asof - delay_ms - step - (last + step)) // step + 1)
    return list(raw_gaps), 0, (last - first) // step + 1, off, due


def assess(t: Sequence[int], c: Sequence[float], v: Sequence[float] | None, *, step: int,
           asof: int, raw_gaps: Sequence[tuple[int, int]], sessions: SessionsFn | None,
           calendar_id: str = "", duplicates: int = 0, grace_bars: int = DEFAULT_GRACE_BARS,
           delay_ms: int = 0, continuous: bool = False) -> SeriesQuality:
    """Informe de calidad. `continuous=True` = calendario 24/7 (camino rápido, sin sesiones).
    `sessions=None` y no continuo = sin calendario disponible: se informa todo menos lo que
    dependa de él (cerrado/roto y obsoleta quedan sin juzgar, nunca se adivinan)."""
    n = len(t)
    if n == 0:
        return SeriesQuality(status="sin_datos", rows=0, calendar_id=calendar_id,
                             flags=["sin datos"])
    first, last = int(t[0]), int(t[-1])
    flags: list[str] = []
    stale: bool | None
    if continuous:
        gaps, closed, expected, off, due = _continuous(t, step, asof, raw_gaps, delay_ms)
        stale = due >= grace_bars
    elif sessions is not None:
        gaps, closed = calendar_gaps(raw_gaps, step, sessions)
        expected = expected_slots(first, last, step, sessions)
        sess = sessions(first, last + step)
        opens = [s.open_t for s in sess]
        off = sum(1 for x in t if not _overlaps(sess, opens, int(x), int(x) + step))
        due = expected_slots(last + step, asof - delay_ms - step, step, sessions)
        stale = due >= grace_bars
    else:
        gaps, closed, expected, off, stale = list(raw_gaps), 0, None, 0, None
        flags.append("sin calendario: no se distingue cerrado de roto")
    missing = sum((g1 - g0) // step + 1 for g0, g1 in gaps)
    jumps = _jumps(t, c)
    zero = None if v is None else sum(1 for x in v if x == 0)
    judged = continuous or sessions is not None
    if gaps:
        flags.append(f"{len(gaps)} huecos con mercado abierto ({missing} velas)" if judged else
                     f"{len(gaps)} huecos sin juzgar ({missing} velas; ¿cierre o fallo?)")
    if closed:
        flags.append(f"{closed} huecos de mercado cerrado (no cuentan)")
    if duplicates:
        flags.append(f"{duplicates} velas duplicadas entre tramos")
    if jumps:
        flags.append(f"{len(jumps)} saltos de precio anómalos")
    if zero:
        flags.append(f"{zero} velas con volumen cero")
    if off:
        flags.append(f"{off} velas fuera de sesión (¿zona horaria?)")
    if stale:
        flags.append("obsoleta para la cadencia de su clase")
    status = ("desconocida" if not judged else
              "rota" if gaps else "obsoleta" if stale else "ok")
    cont = None if not expected else round(min(1.0, n / expected), 6)
    return SeriesQuality(
        status=status, rows=n, first_t=first, last_t=last, expected=expected, continuity=cont,
        gaps=gaps, missing_bars=missing, closed_gaps=closed, duplicates=duplicates,
        jumps=jumps[:MAX_LISTED], n_jumps=len(jumps), zero_volume=zero, off_session=off,
        freshness_ms=asof - (last + step), stale=stale, calendar_id=calendar_id, flags=flags)


def marks(name: str, q: SeriesQuality) -> tuple[dict[str, str], dict[str, tuple[int, int]]]:
    """Resumen para `MarketSnapshot.sources/coverage` bajo la clave `quality:<name>`."""
    text = q.status if not q.flags else f"{q.status}: " + "; ".join(q.flags)
    cov = {} if q.first_t is None else {f"quality:{name}": (q.first_t, int(q.last_t))}
    return {f"quality:{name}": text}, cov
