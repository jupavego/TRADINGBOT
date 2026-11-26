"""Etapas 1 y 2 del embudo (T93): qué instrumentos entran y por qué sale cada uno.

Funciones **puras** sobre fichas del registro (T89) y estadísticas de datos ya calculadas: la
lectura del catálogo y del almacén vive en `eim/data/scanner_market.py`.

- **Etapa 1 — descubrimiento.** Del catálogo: estado en la plaza, vencimiento, que sea
  perpetuo, moneda, nivel de permiso y la lista escrita de pre-OPV (T88). Además cuenta las
  altas, bajas y vencimientos recientes para el informe de la corrida.
- **Etapa 2 — datos.** Velas suficientes y frescas (frescura juzgada contra el calendario del
  instrumento: un fin de semana de bolsa no es un dato viejo), mercado abierto según su
  calendario, precio válido, liquidez mínima y diferencial máximo si hay cotización.

Cada exclusión lleva su motivo (código estable) y un detalle legible, y se cuenta: nada sale
del embudo sin decir por qué.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from eim.core.market import Frozen
from eim.instruments import calendars
from eim.instruments.calendar_specs import CalendarUnavailable
from eim.instruments.models import EventKind, Instrument, InstrumentEvent, InstrumentStatus
from eim.scanner.params import DAY_MS, PRE_IPO, ScannerParams

#: Motivos de exclusión (código → explicación). Los códigos son estables: el informe y la base
#: los cuentan por código.
REASONS: dict[str, str] = {
    "estado": "no está en negociación en la plaza",
    "vencido": "contrato vencido",
    "no_perpetuo": "no es un perpetuo (fuera del primer universo)",
    "moneda": "moneda de liquidación fuera del universo",
    "nivel": "nivel de permiso por debajo del mínimo",
    "pre_opv": "pre-OPV sin mercado subyacente (T88)",
    "sin_datos": "sin velas en el almacén",
    "pocas_velas": "velas insuficientes para la etapa 3",
    "dato_viejo": "la última vela es vieja para su calendario",
    "calendario": "calendario no disponible en este equipo",
    "mercado_cerrado": "mercado cerrado según su calendario",
    "precio_invalido": "precio no positivo o no finito",
    "liquidez": "liquidez por debajo del mínimo",
    "spread": "diferencial por encima del máximo",
    "spread_sin_medir": "sin cotización para medir el diferencial",
}


class Exclusion(Frozen):
    instrument_id: str
    stage: int
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class DataStats:
    """Lo que el almacén tiene de un instrumento a `asof` (velas cerradas)."""

    n_bars: int
    last_t: int | None = None              # apertura de la última vela cerrada
    last_close: float | None = None
    median_quote_volume: float | None = None   # mediana de v · c por vela
    spread_bps: float | None = None


@dataclass
class UniverseResult:
    included: list[Instrument]
    exclusions: list[Exclusion]
    lifecycle: dict[str, list[str]] = field(default_factory=dict)
    notes: Counter = field(default_factory=Counter)

    @property
    def counts(self) -> dict[str, int]:
        return dict(sorted(Counter(e.reason for e in self.exclusions).items()))

    def stage_counts(self) -> dict[int, int]:
        return dict(sorted(Counter(e.stage for e in self.exclusions).items()))


def _x(inst: Instrument, stage: int, reason: str, detail: str = "") -> Exclusion:
    return Exclusion(instrument_id=inst.id, stage=stage, reason=reason,
                     detail=detail or REASONS[reason])


def stage1_reason(inst: Instrument, p: ScannerParams, asof: int) -> Exclusion | None:
    """Motivo de exclusión de la etapa 1, o None si pasa."""
    if inst.status is not InstrumentStatus.ACTIVE:
        return _x(inst, 1, "estado", f"estado {inst.status.value}")
    if inst.expiry is not None and inst.expiry <= asof:
        return _x(inst, 1, "vencido", f"venció en {inst.expiry}")
    if p.perpetual_only and inst.expiry is not None:
        return _x(inst, 1, "no_perpetuo", f"vence en {inst.expiry}")
    if p.quote_currencies and inst.currency not in p.quote_currencies:
        return _x(inst, 1, "moneda", f"liquida en {inst.currency}")
    if int(inst.tradable_level) < p.min_level:
        return _x(inst, 1, "nivel", f"nivel {int(inst.tradable_level)} < {p.min_level}")
    if inst.symbol in PRE_IPO:
        return _x(inst, 1, "pre_opv")
    return None


def lifecycle(events: Iterable[InstrumentEvent], asof: int, days: int) -> dict[str, list[str]]:
    """Altas, bajas, vencimientos y suspensiones fechados en los últimos `days` días."""
    lo = asof - days * DAY_MS
    out: dict[str, list[str]] = {}
    for e in events:
        if lo <= e.t <= asof and e.kind in (EventKind.LISTED, EventKind.DELISTED,
                                            EventKind.EXPIRED, EventKind.SUSPENDED,
                                            EventKind.RESUMED):
            out.setdefault(e.kind.value, []).append(e.instrument_id)
    return {k: sorted(set(v)) for k, v in sorted(out.items())}


def stage1(instruments: Iterable[Instrument], p: ScannerParams, asof: int
           ) -> tuple[list[Instrument], list[Exclusion]]:
    """(los que pasan, ordenados por id; las exclusiones)."""
    kept, out = [], []
    for inst in sorted(instruments, key=lambda i: i.id):
        if p.venue and inst.venue != p.venue:
            continue                       # otra plaza: no es parte de este universo
        why = stage1_reason(inst, p, asof)
        (out if why else kept).append(why or inst)
    return kept, out


def closed_cut(step_ms: int, asof: int, offset_ms: int = 0) -> int:
    """Cota exclusiva de `t` de las velas cerradas a `asof` (regla nominal `t + marco ≤ asof`).

    `offset_ms` es el desfase de la rejilla (la semana empieza el lunes: `TF_OFFSET_MS`)."""
    return ((asof - offset_ms) // step_ms) * step_ms + offset_ms


def missing_bars(inst: Instrument, step_ms: int, last_t: int, asof: int,
                 offset_ms: int = 0) -> int:
    """Velas que el calendario esperaba después de `last_t` y antes de `asof` (cerradas)."""
    start = last_t + step_ms
    end = closed_cut(step_ms, asof, offset_ms)     # la vela que abre aquí aún no ha cerrado
    if end <= start:
        return 0
    return calendars.expected_bars(inst, step_ms, start, end)


def stage2_reason(inst: Instrument, st: DataStats | None, p: ScannerParams, step_ms: int,
                  asof: int, offset_ms: int = 0) -> tuple[Exclusion | None, str | None]:
    """(exclusión o None, nota o None). La nota cuenta lo que no excluye pero se declara."""
    if st is None or st.n_bars == 0 or st.last_t is None:
        return _x(inst, 2, "sin_datos"), None
    if st.n_bars < p.min_bars:
        return _x(inst, 2, "pocas_velas", f"{st.n_bars} < {p.min_bars} velas"), None
    try:
        if not calendars.is_open(inst, asof):
            return _x(inst, 2, "mercado_cerrado"), None
        gap = missing_bars(inst, step_ms, st.last_t, asof, offset_ms)
    except CalendarUnavailable as exc:
        return _x(inst, 2, "calendario", f"{exc}"[:200]), None
    grace = p.grace(inst.asset_class.value)
    if gap > grace:
        return _x(inst, 2, "dato_viejo", f"faltan {gap} velas desde {st.last_t} "
                  f"(margen {grace})"), None
    if st.last_close is None or not (math.isfinite(st.last_close) and st.last_close > 0):
        return _x(inst, 2, "precio_invalido"), None
    floor = p.min_quote_volume_per_day * step_ms / DAY_MS
    if st.median_quote_volume is None or not st.median_quote_volume >= floor:
        got = "sin volumen" if st.median_quote_volume is None else f"{st.median_quote_volume:,.0f}"
        return _x(inst, 2, "liquidez", f"mediana {got} < {floor:,.0f} por vela"), None
    if st.spread_bps is None:
        if p.require_spread:
            return _x(inst, 2, "spread_sin_medir"), None
        return None, "spread_sin_medir"
    if st.spread_bps > p.max_spread_bps:
        return _x(inst, 2, "spread", f"{st.spread_bps:.1f} pb > {p.max_spread_bps:g} pb"), None
    return None, None


def stage2(instruments: Iterable[Instrument], stats: Mapping[str, DataStats], p: ScannerParams,
           step_ms: int, asof: int, offset_ms: int = 0
           ) -> tuple[list[Instrument], list[Exclusion], Counter]:
    kept, out, notes = [], [], Counter()
    for inst in instruments:
        why, note = stage2_reason(inst, stats.get(inst.id), p, step_ms, asof, offset_ms)
        if note:
            notes[note] += 1
        (out if why else kept).append(why or inst)
    return kept, out, notes


def filter_universe(instruments: Iterable[Instrument], stats: Mapping[str, DataStats],
                    p: ScannerParams, step_ms: int, asof: int,
                    events: Iterable[InstrumentEvent] = (), offset_ms: int = 0) -> UniverseResult:
    """Etapas 1 y 2 de una vez (para pruebas y para quien ya tiene las estadísticas)."""
    k1, x1 = stage1(instruments, p, asof)
    k2, x2, notes = stage2(k1, stats, p, step_ms, asof, offset_ms)
    return UniverseResult(included=k2, exclusions=x1 + x2,
                          lifecycle=lifecycle(events, asof, p.lifecycle_days), notes=notes)
