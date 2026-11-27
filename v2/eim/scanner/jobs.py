"""Manejadores de los trabajos de la cola (T93). Funciones de nivel de módulo: viajan a otro
proceso por nombre (Windows arranca los procesos con `spawn`).

- `deep_prep` (ritmo profundo, CPU, cacheable): prepara un instrumento de la lista corta para
  los agentes profundos **sin correrlos** (eso es T94): lee sus velas, mide la cobertura real
  (`eligibility.coverage_of`) y decide con las capacidades declaradas (T91) qué agentes podrían
  correr y por qué no los demás. Su versión incluye la huella de `CAPABILITIES`: si cambia una
  ficha de agente, la caché se invalida sola.
- `deep_run` (T94, ritmo profundo, CPU, cacheable): corre los agentes **elegibles** del
  instrumento, la síntesis y la proyección existentes, y arma la oportunidad candidata
  (`eim/scanner/deep.py`). Su versión incluye la de la etapa, la de la oportunidad, la de las
  puntuaciones y la huella de capacidades; la de cada agente va en la huella de datos del trabajo.
- `sync_daily` (red, en línea, con límite de tasa): pone al día las velas de un perpetuo en el
  almacén del universo. Nunca se cachea.

Ninguno envía órdenes ni toca el flujo de operación.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Handler:
    name: str
    fn: Callable[[dict], dict]
    version: str
    inline: bool = False         # True = en el proceso principal (red); False = puede ir a otro
    cacheable: bool = True
    provider: str | None = None  # límite de tasa que consume


#: Agentes del registro que el escáner no considera (T214). `vol_surface` lee la cadena de
#: opciones de Deribit de BTC, que ningún perpetuo del universo tiene: no podría correr nunca y,
#: si contara, cambiaría las huellas de capacidades y de agentes, dejaría «desactualizado» el
#: umbral del placebo de T95 y abriría intentos nuevos de la síntesis sin ninguna razón.
OUT_OF_SCANNER: frozenset[str] = frozenset({"vol_surface"})


def capabilities_fingerprint() -> str:
    """Huella de las fichas de capacidades de los agentes (T91), sin los de `OUT_OF_SCANNER`."""
    from eim.agents.capabilities import CAPABILITIES

    d = hashlib.blake2b(digest_size=6)
    for aid in sorted(set(CAPABILITIES) - OUT_OF_SCANNER):
        caps = CAPABILITIES[aid]
        for f in fields(caps):
            v = getattr(caps, f.name)
            d.update(f"{f.name}={sorted(map(str, v)) if isinstance(v, frozenset) else v};"
                     .encode())
    return d.hexdigest()


DEEP_PREP_VERSION = "1"
#: Versión de la etapa profunda de T94 (`eim/scanner/deep.py` la usa como `DEEP_VERSION`).
DEEP_RUN_VERSION = "1"


def deep_prep(payload: dict) -> dict:
    """Cobertura y agentes elegibles de un instrumento de la lista corta (sin correr agentes)."""
    from eim.agents.capabilities import CAPABILITIES, CostClass
    from eim.agents.eligibility import check, coverage_of
    from eim.core import MarketSnapshot
    from eim.data.scanner_market import read_window
    from eim.instruments.models import Instrument

    inst = Instrument.model_validate(payload["instrument"])
    candles = read_window(payload["root"], inst.symbol, payload["timeframe"],
                          int(payload["n_bars"]), int(payload["cut"]))
    snap = MarketSnapshot(symbol=inst.symbol, timeframe=payload["timeframe"], candles=candles,
                          asof=int(payload["asof"]))
    cov = coverage_of(snap, inst)
    eligible, degraded, ineligible, cheap = [], {}, {}, []
    for aid in sorted(set(CAPABILITIES) - OUT_OF_SCANNER):
        ok, why = check(CAPABILITIES[aid], inst, cov)
        if not ok:
            ineligible[aid] = why
            continue
        eligible.append(aid)
        if why != "elegible":
            degraded[aid] = why
        if CAPABILITIES[aid].cost_class is CostClass.CHEAP:
            cheap.append(aid)
    return {"instrument_id": inst.id, "n_bars": cov.n_bars, "span_days": round(cov.span_days, 2),
            "volume": cov.volume, "taker_flow": cov.taker_flow, "fields": sorted(cov.fields),
            "eligible": eligible, "cheap_eligible": cheap, "degraded": degraded,
            "ineligible": ineligible, "note": "preparado para T94: aquí no corre ningún agente"}


def deep_run(payload: dict) -> dict:
    """Agentes elegibles → síntesis → proyección → oportunidad candidata (T94)."""
    from eim.scanner.deep import run_payload

    return run_payload(payload)


def _deep_run_version() -> str:
    from eim.core.opportunity import OPPORTUNITY_VERSION
    from eim.scanner.candidates import SCORING_VERSION

    return (f"deep_run:{DEEP_RUN_VERSION}+opp:{OPPORTUNITY_VERSION}+score:{SCORING_VERSION}"
            f"+caps:{capabilities_fingerprint()}")


def sync_daily(payload: dict) -> dict:
    """Velas que faltan de un perpetuo (como mucho `days` días atrás) en el almacén del universo."""
    from eim.data.scanner_market import sync_symbol

    return sync_symbol(payload["root"], payload["symbol"], payload["timeframe"],
                       int(payload["now"]), int(payload["days"]))


def _handlers() -> dict[str, Handler]:
    return {
        "deep_prep": Handler("deep_prep", deep_prep,
                             f"deep_prep:{DEEP_PREP_VERSION}+caps:{capabilities_fingerprint()}"),
        "deep_run": Handler("deep_run", deep_run, _deep_run_version()),
        "sync_daily": Handler("sync_daily", sync_daily, "sync_daily:1", inline=True,
                              cacheable=False, provider="binance"),
    }


HANDLERS: dict[str, Handler] = _handlers()
