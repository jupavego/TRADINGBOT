"""Almacén por instrumento (T90): el almacén habla de `Instrument.id`, no de símbolos de Binance.

`InstrumentData` envuelve al `Store` de siempre. Un instrumento se pide por su id, su símbolo
nativo o su alias legado (`crypto.binance.usdm.BTCUSDT`, `BTCUSDT`, `SP500`), y sus series se
guardan bajo una **clave de almacén** estable:

- los de la semilla del registro conservan su carpeta de siempre (`symbol=BTCUSDT`,
  `symbol=SP500`): nada de lo ya guardado se mueve ni cambia de nombre;
- todos los demás se guardan por su id (`symbol=equity.binance.usdm.AAPLUSDT`).

Series nuevas, además de velas, funding e interés abierto:

- `corporate_actions` (fecha ex, split, dividendo, empalme) y `adj_factor` (factores
  acumulados que se derivan de ellas);
- `quotes` (mejor compra y venta), `fundamentals` (un campo por serie, point-in-time) y
  `curve` (un plazo por serie). En estas dos la ranura del marco lleva el campo o el plazo.

**Crudo y ajustado nunca se mezclan**: en `candles` solo hay velas crudas; la ajustada se
calcula al leer (`read_candles(..., adjusted=True)`, lo que reciben los agentes) y el backtest
puede pedir las dos (`read_both`). El ajuste es point-in-time: a `asof` solo cuentan los
eventos con fecha ex ≤ `asof`.

Cada escritura deja `provenance.json` junto a la serie con la ficha de su fuente (cobertura,
licencia, retraso, atribución); las series anteriores a T90 la sacan del catálogo por nombre.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence

from eim.core import Candle
from eim.data.adjust import Factor, PriceEvent, adjust_candles, factors
from eim.data.providers.meta import SourceMeta, lookup
from eim.data.quality import SeriesQuality
from eim.data.quality_io import series_quality
from eim.data.store import Store
from eim.data.timeframes import tf_ms
from eim.instruments import registry
from eim.instruments.models import Instrument

ACTIONS_SCHEMA = "t BIGINT, split DOUBLE, dividend DOUBLE, roll DOUBLE"
ADJ_SCHEMA = "t BIGINT, price DOUBLE, volume DOUBLE"
QUOTES_SCHEMA = "t BIGINT, bid DOUBLE, ask DOUBLE, bid_size DOUBLE, ask_size DOUBLE"
VALUE_SCHEMA = "t BIGINT, x DOUBLE"
SERIES_KINDS = ("candles", "corporate_actions", "adj_factor", "quotes", "fundamentals", "curve")
PROVENANCE = "provenance.json"
_SLOT = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")    # campo o plazo en la ranura del marco
_SEED_KEYS = {i.id: (i.aliases[0] if i.aliases else i.symbol) for i in registry.SEED}


def storage_key(inst: Instrument) -> str:
    """Carpeta del instrumento en el almacén: la de siempre en la semilla, el id en el resto."""
    return _SEED_KEYS.get(inst.id, inst.id)


def _slot(name: str) -> str:
    if not _SLOT.match(name):
        raise ValueError(f"campo o plazo inválido para el almacén: {name!r}")
    return name


class InstrumentData:
    """Series de un almacén por instrumento. `resolver` traduce una clave a su instrumento
    (por defecto, la semilla del registro; con el catálogo: `InstrumentsStore.resolve`)."""

    def __init__(self, store: Store, resolver: Callable[[str], Instrument] | None = None):
        self.store = store
        self._resolver = resolver or registry.resolve

    def resolve(self, key: str | Instrument) -> Instrument:
        return key if isinstance(key, Instrument) else self._resolver(key)

    def key(self, key: str | Instrument) -> str:
        return storage_key(self.resolve(key))

    # --- procedencia ----------------------------------------------------------
    def _write_provenance(self, kind: str, sk: str, slot: str, meta: SourceMeta) -> None:
        d = self.store._dir(kind, sk, slot)  # noqa: SLF001 — misma capa de datos
        d.mkdir(parents=True, exist_ok=True)
        (d / PROVENANCE).write_text(json.dumps(meta.as_dict(), ensure_ascii=False),
                                    encoding="utf-8")

    def provenance(self, key: str | Instrument, kind: str = "candles", slot: str = "-"
                   ) -> SourceMeta | None:
        """Ficha de la fuente de una serie: la que se escribió con ella o, si es anterior a
        T90, la del catálogo según el nombre guardado. None si la serie no existe."""
        sk = key if kind == "curve" else self.key(key)
        d = self.store._dir(kind, sk, slot)  # noqa: SLF001
        f = d / PROVENANCE
        if f.exists():
            return SourceMeta(**json.loads(f.read_text(encoding="utf-8")))
        src = self.store.source(kind, sk, slot)
        return None if src is None else lookup(src)

    # --- velas crudas y ajustadas -------------------------------------------------
    def upsert_candles(self, key: str | Instrument, timeframe: str, candles: list[Candle],
                       meta: SourceMeta) -> int:
        """Velas CRUDAS, tal como las publica la fuente. Nunca se escribe aquí una ajustada."""
        sk = self.key(key)
        n = self.store.upsert_candles(sk, timeframe, candles, meta.name)
        self._write_provenance("candles", sk, timeframe, meta)
        return n

    def read_raw(self, key: str | Instrument, timeframe: str, start: int | None = None,
                 end: int | None = None, last: int | None = None) -> list[Candle]:
        return self.store.read_candles(self.key(key), timeframe, start, end, last)

    def read_candles(self, key: str | Instrument, timeframe: str, start: int | None = None,
                     end: int | None = None, last: int | None = None, *,
                     adjusted: bool = True, asof: int | None = None) -> list[Candle]:
        """Velas ajustadas (por defecto) con los eventos conocidos a `asof` (o a `end`)."""
        raw = self.read_raw(key, timeframe, start, end, last)
        if not adjusted or not raw:
            return raw
        return self._adjust(key, timeframe, raw, asof if asof is not None else end)

    def read_both(self, key: str | Instrument, timeframe: str, start: int | None = None,
                  end: int | None = None, *, asof: int | None = None
                  ) -> tuple[list[Candle], list[Candle]]:
        """(crudas, ajustadas) de la misma ventana: lo que necesita el backtest."""
        raw = self.read_raw(key, timeframe, start, end)
        return raw, (self._adjust(key, timeframe, raw, asof if asof is not None else end)
                     if raw else [])

    def events(self, key: str | Instrument, asof: int | None = None) -> list[PriceEvent]:
        """Eventos con fecha ex ≤ `asof` (todos si `asof` es None)."""
        return [e for e in self.read_actions(key) if asof is None or e.t <= asof]

    def _context(self, key: str | Instrument, timeframe: str, raw: Sequence[Candle],
                 evs: Sequence[PriceEvent]) -> list[Candle]:
        """La ventana más la vela previa a cada dividendo posterior a ella: su cierre crudo
        hace falta para el factor y no está en la ventana (con `end` en el pasado y `asof` hoy).
        Un dividendo dentro de la ventana ya tiene su vela previa; uno anterior no la afecta."""
        last = raw[-1].t
        extra = []
        for e in evs:
            if e.dividend and e.t > last:
                extra += self.read_raw(key, timeframe, end=e.t, last=1)
        merged = {c.t: c for c in [*extra, *raw]}
        return [merged[t] for t in sorted(merged)]

    def _adjust(self, key, timeframe: str, raw: list[Candle], asof: int | None) -> list[Candle]:
        evs = self.events(key, asof)
        if not evs:
            return raw
        ctx = self._context(key, timeframe, raw, evs)
        keep = {c.t for c in raw}
        return [c for c in adjust_candles(ctx, evs) if c.t in keep]

    # --- eventos corporativos y factores --------------------------------------------
    def upsert_actions(self, key: str | Instrument, events: Sequence[PriceEvent],
                       meta: SourceMeta) -> int:
        sk = self.key(key)
        rows = [(e.t, e.split, e.dividend, e.roll) for e in events]
        n = self.store._upsert("corporate_actions", sk, "-", rows,  # noqa: SLF001
                               ACTIONS_SCHEMA, meta.name)
        self._write_provenance("corporate_actions", sk, "-", meta)
        return n

    def read_actions(self, key: str | Instrument) -> list[PriceEvent]:
        sk = self.key(key)
        rows = self.store._read("corporate_actions", sk, "-",  # noqa: SLF001
                                "t, split, dividend, roll", None, None, None)
        src = self.store.source("corporate_actions", sk) or ""
        return [PriceEvent(t=int(t), split=s, dividend=d, roll=r, source=src)
                for t, s, d, r in rows]

    def write_adj_factor(self, key: str | Instrument, timeframe: str) -> list[Factor]:
        """Guarda en `adj_factor` los factores que se derivan de las velas y los eventos
        (para auditarlos o servirlos sin recalcular). Devuelve los factores."""
        sk = self.key(key)
        evs = self.read_actions(key)
        raw = self.read_raw(key, timeframe)
        fs = factors(raw, evs) if raw and evs else []
        if fs:
            src = self.store.source("corporate_actions", sk) or "derivado"
            self.store._upsert("adj_factor", sk, timeframe,  # noqa: SLF001
                               [(f.until, f.price, f.volume) for f in fs], ADJ_SCHEMA,
                               f"derivado de {src}")
        return fs

    def read_adj_factor(self, key: str | Instrument, timeframe: str) -> list[Factor]:
        rows = self.store._read("adj_factor", self.key(key), timeframe,  # noqa: SLF001
                                "t, price, volume", None, None, None)
        return [Factor(until=int(t), price=p, volume=v) for t, p, v in rows]

    # --- cotizaciones, fundamentales y curvas -------------------------------------
    def upsert_quotes(self, key: str | Instrument, rows: Sequence[tuple],
                      meta: SourceMeta) -> int:
        """(t, bid, ask, bid_size, ask_size); los tamaños pueden ser None."""
        sk = self.key(key)
        n = self.store._upsert("quotes", sk, "-", [tuple(r) for r in rows],  # noqa: SLF001
                               QUOTES_SCHEMA, meta.name)
        self._write_provenance("quotes", sk, "-", meta)
        return n

    def read_quotes(self, key: str | Instrument, start: int | None = None,
                    end: int | None = None, last: int | None = None) -> list[tuple]:
        return self.store._read("quotes", self.key(key), "-",  # noqa: SLF001
                                "t, bid, ask, bid_size, ask_size", start, end, last)

    def upsert_fundamentals(self, key: str | Instrument, field: str,
                            rows: Sequence[tuple[int, float]], meta: SourceMeta) -> int:
        """Un campo por serie; `t` = cuándo se publicó (point-in-time), no el periodo."""
        sk, slot = self.key(key), _slot(field)
        n = self.store.upsert_series("fundamentals", sk, slot, list(rows), meta.name)
        self._write_provenance("fundamentals", sk, slot, meta)
        return n

    def read_fundamentals(self, key: str | Instrument, field: str, start: int | None = None,
                          end: int | None = None) -> list[tuple[int, float]]:
        return self.store.read_series("fundamentals", self.key(key), _slot(field), start, end)

    def upsert_curve(self, curve_id: str, tenor: str, rows: Sequence[tuple[int, float]],
                     meta: SourceMeta) -> int:
        """Un plazo por serie (`10Y`, `3M`…) de una curva que no es un instrumento."""
        cid, slot = _slot(curve_id), _slot(tenor)
        n = self.store.upsert_series("curve", cid, slot, list(rows), meta.name)
        self._write_provenance("curve", cid, slot, meta)
        return n

    def read_curve(self, curve_id: str, tenor: str, start: int | None = None,
                   end: int | None = None) -> list[tuple[int, float]]:
        return self.store.read_series("curve", _slot(curve_id), _slot(tenor), start, end)

    # --- calidad --------------------------------------------------------------------
    def find_gaps(self, key: str | Instrument, timeframe: str, start: int | None = None,
                  end: int | None = None) -> list[tuple[int, int]]:
        """Huecos con mercado abierto según el calendario del instrumento (no los cierres)."""
        inst = self.resolve(key)
        return self.store.find_gaps(storage_key(inst), timeframe, start, end, calendar=inst)

    def quality(self, key: str | Instrument, timeframe: str, asof: int,
                start: int | None = None) -> SeriesQuality:
        """Informe de calidad a `asof` (desde `start`, o toda la serie), con el calendario y
        el retraso declarado de la fuente."""
        inst = self.resolve(key)
        meta = self.provenance(inst, "candles", timeframe)
        delay = (meta.delay_ms or 0) if meta is not None else 0
        tf_ms(timeframe)
        return series_quality(self.store, storage_key(inst), timeframe, asof=asof,
                              instrument=inst, delay_ms=delay, start=start)
