"""Snapshot de un instrumento cualquiera (T90): sesión, ajuste, procedencia y calidad.

`build_snapshot` sigue siendo el de BTC/ETH y su salida no cambia. Esta función es la puerta
de las clases nuevas y añade lo que un instrumento con sesión y eventos corporativos
necesita, sin tocar lo que ya existe:

- la vela de sesión se da por cerrada cuando cierra su sesión (`session_bars.closed_before`);
- las velas que reciben los agentes son las **ajustadas** con los eventos conocidos a `asof`
  (la cruda sigue en el almacén y el backtest la pide aparte);
- marcas en `sources`/`coverage`, bajo claves nuevas: `instrument` (id), `provenance:candles`
  (fuente, cobertura 1/2/3, licencia, retraso), `adjustment:candles` y `quality:candles`
  (estado y avisos del informe de `eim/data/quality.py`).

Si el calendario del instrumento no se puede contestar en este equipo, se dice en
`sources["calendar"]` y se usa la regla 24/7 para el corte, que es la conservadora.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from eim.core import MarketSnapshot
from eim.data.adjust import ADJUSTMENT_METHOD, describe
from eim.data.quality import calendar_sessions, marks
from eim.data.quality_io import is_continuous
from eim.data.series import InstrumentData
from eim.data.session_bars import closed_before
from eim.data.snapshot import build_snapshot
from eim.data.store import Store
from eim.instruments.calendar_specs import CalendarUnavailable
from eim.instruments.models import Instrument


def provenance_text(meta) -> str:
    delay = "desconocido" if meta.delay_ms is None else f"{meta.delay_ms} ms"
    return (f"fuente={meta.name}; cobertura={meta.coverage}; licencia={meta.license}; "
            f"retraso={delay}")


def build_instrument_snapshot(
    store: Store, key: str | Instrument, timeframe: str, n: int, asof: int | None = None, *,
    resolver: Callable[[str], Instrument] | None = None,
) -> MarketSnapshot:
    """Últimas `n` velas cerradas (ajustadas) del instrumento a `asof`, con sus marcas."""
    data = InstrumentData(store, resolver)
    inst = data.resolve(key)
    asof = asof if asof is not None else int(time.time() * 1000)
    sessions = None
    cal_note = None
    if not is_continuous(inst):
        try:
            sessions = calendar_sessions(inst)
            sessions(asof - 86_400_000, asof)
        except CalendarUnavailable as exc:
            sessions, cal_note = None, f"no disponible en este equipo: {exc}"
    snap = build_snapshot(store, data.key(inst), timeframe, n, asof,
                          closed_end=closed_before(timeframe, asof, sessions))
    sources, coverage = dict(snap.sources), dict(snap.coverage)
    sources["instrument"] = inst.id
    if cal_note:
        sources["calendar"] = cal_note
    candles, candles_tf = snap.candles, snap.candles_tf
    evs = data.events(inst, asof)
    if candles:
        meta = data.provenance(inst, "candles", timeframe)
        if meta is not None:
            sources["provenance:candles"] = provenance_text(meta)
        if evs:
            candles = data._adjust(inst, timeframe, candles, asof)  # noqa: SLF001
            if candles_tf:
                candles_tf = {tf: data._adjust(inst, tf, cs, asof)  # noqa: SLF001
                              for tf, cs in candles_tf.items()}
            sources["adjustment:candles"] = f"ajustada ({describe(evs)}); {ADJUSTMENT_METHOD}"
        else:
            sources["adjustment:candles"] = "cruda: sin eventos corporativos registrados"
        q = data.quality(inst, timeframe, asof, start=candles[0].t)
        q_src, q_cov = marks("candles", q)
        sources |= q_src
        coverage |= q_cov
    return snap.model_copy(update={"candles": candles, "candles_tf": candles_tf,
                                   "sources": sources, "coverage": coverage})
