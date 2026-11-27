"""Sincronización incremental genérica por instrumento (T90).

`sync_candles` (`eim/data/sync.py`) sigue siendo el camino de BTC/ETH y no cambia. Esto es
lo que necesita un universo de cientos de instrumentos de clases distintas:

- **calendario**: solo se piden los huecos con mercado abierto; un fin de semana de acciones
  no se vuelve a pedir en cada pasada (el proveedor no tiene nada que dar);
- **límite de tasa por proveedor**, compartido en el proceso y sacado de su ficha
  (`SourceMeta.rate_limit_per_min`), además del que el propio proveedor ya aplique;
- **reintentos** con espera creciente, y si se agotan la pasada termina con el error escrito,
  sin tumbar a quien la lanzó;
- **reanudación**: cada tramo se escribe en cuanto llega, así que la siguiente pasada empieza
  donde quedó; los tramos que la fuente devolvió vacíos se anotan en `_sync/` para no
  pedirlos otra vez (un instrumento listado ayer no tiene velas de hace un año);
- **presupuesto**: peticiones y segundos por pasada acotados para el equipo de referencia
  (4 núcleos y 16 GB con la captura 24/7 y el bróker simulado en marcha, ◆ T88 §3). Lo que no
  quepa queda para la pasada siguiente (`complete: False`).
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from collections.abc import Callable

from eim.core.market import Frozen
from eim.data.providers.base import CandleProvider
from eim.data.providers.meta import meta_of
from eim.data.quality_io import raw_gaps
from eim.data.series import InstrumentData
from eim.data.store import Store
from eim.data.timeframes import align, tf_ms
from eim.instruments.calendar_specs import CalendarUnavailable
from eim.instruments.models import Instrument

SYNC_DIR = "_sync"
DEFAULT_PER_MIN = 60        # proveedor sin cifra publicada: prudente, una por segundo


class SyncBudget(Frozen):
    """Lo que una pasada puede gastar (pensado para el equipo de referencia)."""

    max_requests: int = 200
    max_seconds: float = 120.0
    chunk_bars: int = 1000
    retries: int = 3
    backoff_s: float = 1.0


class RateLimiter:
    """Como mucho `per_min` peticiones en cualquier ventana de 60 s (ventana deslizante)."""

    def __init__(self, per_min: int, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if per_min <= 0:
            raise ValueError("per_min debe ser > 0")
        self.per_min, self._clock, self._sleep = per_min, clock, sleep
        self._calls: deque[float] = deque(maxlen=per_min)   # nunca guarda más de un minuto
        self._lock = threading.Lock()

    def wait(self) -> float:
        """Espera lo justo para no pasarse; devuelve los segundos esperados."""
        with self._lock:
            now = self._clock()
            while self._calls and now - self._calls[0] >= 60.0:
                self._calls.popleft()
            waited = 0.0
            if len(self._calls) >= self.per_min:
                waited = 60.0 - (now - self._calls[0])
                self._sleep(waited)
                now = self._clock()
                self._calls.popleft()
            self._calls.append(now)
            return waited


_LIMITERS: dict[str, RateLimiter] = {}
_LIMITERS_LOCK = threading.Lock()


def limiter_for(provider: object, **kw) -> RateLimiter:
    """Limitador compartido por nombre de proveedor en este proceso."""
    meta = meta_of(provider)
    with _LIMITERS_LOCK:
        if meta.name not in _LIMITERS:
            _LIMITERS[meta.name] = RateLimiter(meta.rate_limit_per_min or DEFAULT_PER_MIN, **kw)
        return _LIMITERS[meta.name]


def _state_file(store: Store, sk: str, timeframe: str):
    return store.root / SYNC_DIR / "candles" / sk / f"{timeframe}.json"


def _load_state(store: Store, sk: str, timeframe: str) -> dict:
    f = _state_file(store, sk, timeframe)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"empty": []}


def _save_state(store: Store, sk: str, timeframe: str, state: dict) -> None:
    f = _state_file(store, sk, timeframe)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(f)


def _minus(ranges: list[tuple[int, int]], holes: list[list[int]]) -> list[tuple[int, int]]:
    """`ranges` sin lo que ya se sabe vacío en la fuente."""
    out = []
    for a, b in ranges:
        segs = [(a, b)]
        for h0, h1 in holes:
            nxt = []
            for s0, s1 in segs:
                if h1 <= s0 or h0 >= s1:
                    nxt.append((s0, s1))
                    continue
                if s0 < h0:
                    nxt.append((s0, h0))
                if h1 < s1:
                    nxt.append((h1, s1))
            segs = nxt
        out += segs
    return [(a, b) for a, b in out if a < b]


def plan(data: InstrumentData, inst: Instrument, timeframe: str, start: int, end: int
         ) -> tuple[list[tuple[int, int]], int, bool]:
    """(tramos que pedir, huecos que eran cierre y no se piden, ¿se juzgó con calendario?)."""
    step, sk = tf_ms(timeframe), data.key(inst)
    start = align(start, timeframe)
    bounds = data.store.bounds(sk, timeframe)
    if bounds is None:
        return [(start, end)], 0, True
    ranges = [(start, bounds[0])] if bounds[0] > start else []
    raw = raw_gaps(data.store, sk, timeframe)
    judged = True
    try:
        real = data.find_gaps(inst, timeframe)
    except CalendarUnavailable:
        real, judged = raw, False
    ranges += [(g0, g1 + step) for g0, g1 in real]
    ranges.append((bounds[1] + step, end))
    closed = sum(1 for g in raw if not any(g[0] <= r[0] <= g[1] for r in real))
    return [(a, b) for a, b in ranges if a < b], closed, judged


def sync_instrument_candles(
    store: Store, provider: CandleProvider, key: str | Instrument, timeframe: str, start: int,
    end: int | None = None, *, resolver: Callable[[str], Instrument] | None = None,
    budget: SyncBudget | None = None, limiter: RateLimiter | None = None,
    sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
    now_ms: Callable[[], int] = lambda: int(time.time() * 1000),
) -> dict:
    """Trae lo que falta de un instrumento en [start, end) dentro del presupuesto.

    Devuelve {fetched, requests, complete, remaining, closed_skipped, calendar, gaps, error,
    source}. `gaps` = huecos con mercado abierto que siguen sin datos tras la pasada.
    """
    budget = budget or SyncBudget()
    data = InstrumentData(store, resolver)
    inst = data.resolve(key)
    sk, step, meta = data.key(inst), tf_ms(timeframe), meta_of(provider)
    end = end if end is not None else now_ms()
    limiter = limiter or limiter_for(provider)
    state = _load_state(store, sk, timeframe)
    ranges, closed, judged = plan(data, inst, timeframe, start, end)
    ranges = _minus(ranges, state["empty"])
    width = budget.chunk_bars * step
    chunks = [(x, min(x + width, b)) for a, b in ranges for x in range(a, b, width)]
    fetched = requests = done = 0
    error: str | None = None
    t0 = clock()
    for a, b in chunks:
        if requests >= budget.max_requests or clock() - t0 >= budget.max_seconds:
            break
        got = None
        for k in range(budget.retries + 1):
            limiter.wait()
            requests += 1
            try:
                got = provider.klines(inst.symbol, timeframe, a, b)
                break
            except Exception as exc:  # noqa: BLE001 — se reintenta y se informa, no se tumba
                error = f"{type(exc).__name__}: {exc}"
                if k < budget.retries:
                    sleep(budget.backoff_s * 2 ** k)
        if got is None:
            break
        error = None
        if got:
            fetched += len(got)
            data.upsert_candles(inst, timeframe, got, meta)
        elif b <= now_ms() - step:            # vacío y ya cerrado: no se vuelve a pedir
            state["empty"].append([a, b])
        done += 1
        _save_state(store, sk, timeframe, state)
    left = len(chunks) - done
    try:
        gaps = len(data.find_gaps(inst, timeframe))
    except CalendarUnavailable:
        gaps = len(raw_gaps(store, sk, timeframe))
    return {"fetched": fetched, "requests": requests, "complete": left == 0 and error is None,
            "remaining": left, "closed_skipped": closed, "calendar": judged, "gaps": gaps,
            "error": error, "source": meta.name}
