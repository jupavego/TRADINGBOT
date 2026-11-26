"""Los dos ritmos del escáner (T93) y el respeto de sesiones.

- **Rápido** (`fast_pass`, cada `fast_every_s`): no recalcula el universo. Toma lo ya puntuado
  en el último barrido y la cotización de ahora, y avisa de lo que cambió: un precio que se
  movió `alert_sigma` desviaciones desde el cierre puntuado, o un diferencial que se abrió por
  encima del máximo.
- **Profundo** (`deep_jobs`, cada `deep_every_s`, tras un barrido): la lista corta pasa a la cola
  como trabajos de prioridad decreciente con su huella de datos (caché).

**Sesiones.** Ninguno de los dos mira un mercado cerrado ni trata un dato viejo como actual: el
rápido descarta la cotización vieja (`quote_max_age_ms`) y el mercado cerrado según el
calendario del contrato; el barrido ya lo hizo en la etapa 2.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from eim.instruments import calendars
from eim.instruments.calendar_specs import CalendarUnavailable
from eim.instruments.models import Instrument
from eim.scanner.backends import Job, make_job
from eim.scanner.params import ScannerParams

Quote = tuple[float, float, int]          # (bid, ask, t)


def market_state(inst: Instrument, t: int) -> str:
    """`abierto`, `cerrado` o `sin_calendario` (no se adivina un festivo)."""
    try:
        return "abierto" if calendars.is_open(inst, t) else "cerrado"
    except CalendarUnavailable:
        return "sin_calendario"


def spread_bps(q: Quote) -> float | None:
    bid, ask, _ = q
    if not (bid > 0 and ask > 0 and ask >= bid):
        return None
    return (ask - bid) / ((ask + bid) / 2) * 1e4


def spreads_of(quotes: Mapping[str, Quote], insts: Sequence[Instrument], asof: int,
               max_age_ms: int) -> dict[str, float]:
    """{id: diferencial en pb} solo con cotizaciones frescas a `asof` (las viejas no cuentan)."""
    out: dict[str, float] = {}
    for inst in insts:
        q = quotes.get(inst.symbol)
        if q is None or asof - q[2] > max_age_ms:
            continue
        s = spread_bps(q)
        if s is not None:
            out[inst.id] = s
    return out


@dataclass
class FastResult:
    alerts: list[dict] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)
    checked: int = 0


def fast_pass(prev: Sequence[Mapping], quotes: Mapping[str, Quote],
              insts: Mapping[str, Instrument], asof: int, p: ScannerParams) -> FastResult:
    """Alertas sobre lo ya puntuado (`prev` = filas de `scores` del último barrido)."""
    res = FastResult()
    for row in prev:
        inst = insts.get(row["instrument_id"])
        if inst is None:
            res.skipped["fuera_del_catalogo"] += 1
            continue
        state = market_state(inst, asof)
        if state != "abierto":
            res.skipped[f"mercado_{state}"] += 1
            continue
        q = quotes.get(inst.symbol)
        if q is None:
            res.skipped["sin_cotizacion"] += 1
            continue
        if asof - q[2] > p.quote_max_age_ms:
            res.skipped["cotizacion_vieja"] += 1
            continue
        res.checked += 1
        s = spread_bps(q)
        if s is not None and s > p.max_spread_bps:
            res.alerts.append({"t": asof, "instrument_id": inst.id, "kind": "spread",
                               "value": round(s, 3),
                               "detail": f"diferencial {s:.1f} pb > {p.max_spread_bps:g} pb"})
        close = row.get("last_close")
        vol = (row.get("metrics") or {}).get("vol_20")
        if not close or not vol or close <= 0 or vol <= 0:
            continue
        mid = (q[0] + q[1]) / 2
        if mid <= 0:
            continue
        z = math.log(mid / close) / vol
        if abs(z) >= p.alert_sigma:
            res.alerts.append({"t": asof, "instrument_id": inst.id, "kind": "precio",
                               "value": round(z, 3),
                               "detail": f"{z:+.1f} σ desde el cierre puntuado ({close:g} → "
                                         f"{mid:g})"})
    return res


def deep_jobs(run_id: str, shortlist: Sequence[str], insts: Mapping[str, Instrument],
              hashes: Mapping[str, str], *, root: str, timeframe: str, n_bars: int, cut: int,
              asof: int, t: int) -> list[Job]:
    """Trabajos `deep_prep` de la lista corta: el primero de la lista sale antes."""
    out = []
    for k, iid in enumerate(shortlist):
        inst = insts[iid]
        out.append(make_job(
            run_id, "deep_prep", iid, timeframe, "profundo", priority=len(shortlist) - k,
            data_hash=hashes.get(iid, ""), t=t,
            payload={"instrument": inst.model_dump(mode="json"), "root": root,
                     "timeframe": timeframe, "n_bars": n_bars, "cut": cut, "asof": asof}))
    return out


def sync_jobs(run_id: str, insts: Sequence[Instrument], *, root: str, timeframe: str,
              now: int, days: int, limit: int) -> list[Job]:
    """Trabajos `sync_daily` (los primeros `limit`, en el orden recibido: lo más viejo antes)."""
    return [make_job(run_id, "sync_daily", i.id, timeframe, "rapido", t=now, provider="binance",
                     priority=-k, payload={"root": root, "symbol": i.symbol,
                                           "timeframe": timeframe, "now": now, "days": days})
            for k, i in enumerate(insts[:limit])]
