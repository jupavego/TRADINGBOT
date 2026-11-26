"""Oportunidad candidata del escáner global (T94). Modo ANÁLISIS: **nunca es una orden**.

Una oportunidad candidata dice «en este instrumento y este marco, los agentes elegibles apuntan
hacia este lado», con todo lo necesario para seguirla hasta su origen y para que nadie la
confunda con algo validado:

- **Trazabilidad**: `input_hash` resume las velas exactas que vieron los agentes (las mismas que
  se releen con `input_ref`); `agents` lleva id, versión, estado, sesgo y confianza de cada uno;
  `versions` las de la etapa profunda, la síntesis, la proyección y las capacidades (T91). Con
  eso, `opportunity_id` es determinista: los mismos datos y las mismas versiones dan el mismo id
  y las mismas cifras (`eim/scanner/deep.py`, `verify`).
- **Puntuaciones separadas** (todas 0..1, más alto = más favorable), sin mezclarlas en un
  número: calidad de la señal, viabilidad operativa y riesgo/costos. La priorización global
  comparable y el control de multiplicidad son T95: aquí no se ordena el universo.
- **Estado fijo** `candidata_no_validada`: no hay campo de tamaño, de orden ni de cuenta, y no
  hay conversión a `TradeProposal` (lo comprueba `tests/scanner/test_deep.py`). Ningún módulo de
  riesgo, ejecución ni papel la importa.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field

from eim.core.market import Frozen

OPPORTUNITY_VERSION = "1.0.0"
STATUS = "candidata_no_validada"
STATUS_LABEL = "candidata, no validada"

Side = Literal["largo", "corto"]


class AgentVote(Frozen):
    """Lo que dijo un agente elegible sobre el instrumento (lo que sustenta la oportunidad)."""

    agent_id: str
    version: str
    status: Literal["ok", "degraded", "no_data"]
    bias: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)
    votes: bool                         # True si entra en la síntesis (peso > 0 y con datos)
    warnings: list[str] = []
    eligibility: str = "elegible"       # motivo de `eligibility.eligible` (degradado, si aplica)


class Scores(Frozen):
    """Tres puntuaciones separadas con sus componentes a la vista (nada se combina aquí)."""

    signal_quality: float = Field(ge=0, le=1)
    viability: float = Field(ge=0, le=1)
    risk_cost: float = Field(ge=0, le=1)
    components: dict[str, float | None] = {}
    notes: list[str] = []


class InputRef(Frozen):
    """Dónde están los datos que vieron los agentes (para releerlos y comprobar el hash)."""

    store: str = "universe_perps"      # almacén del universo (relativo al directorio de datos)
    symbol: str
    timeframe: str
    n_bars: int
    cut: int                            # velas con t < cut
    first_t: int
    last_t: int


class Opportunity(Frozen):
    opportunity_id: str
    version: str = OPPORTUNITY_VERSION
    status: Literal["candidata_no_validada"] = STATUS
    mode: Literal["ANALISIS"] = "ANALISIS"
    run_id: str                         # barrido del que salió la lista corta
    instrument_id: str
    symbol: str
    asset_class: str
    market: str                         # plaza·mercado (p. ej. `binance·usdm`)
    timeframe: str
    side: Side
    asof: int
    horizon_bars: int = Field(ge=1)
    horizon_ms: int = Field(ge=1)
    valid_until: int                    # vigencia: hasta el cierre de la próxima vela del marco
    input_hash: str
    input_ref: InputRef
    source: str                         # fuente de las velas, como la declara el almacén
    coverage: dict = {}                 # cobertura real (velas, días, volumen, campos)
    agents: list[AgentVote]
    synthesis: dict                     # sesgo, confianza, acuerdo y contribuciones (v1)
    forecast: dict                      # probabilidades y medianas finales de los 3 escenarios
    scores: Scores
    versions: dict[str, str]
    warnings: list[str] = []


def stable_hash(obj: object, size: int = 12) -> str:
    """blake2b de la forma JSON canónica (claves ordenadas, sin espacios)."""
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                     default=str).encode()
    return hashlib.blake2b(raw, digest_size=size).hexdigest()


def opportunity_id(instrument_id: str, timeframe: str, input_hash: str,
                   versions: dict[str, str], agents: list[tuple[str, str]]) -> str:
    """Id determinista: datos + versiones del código y de cada agente que corrió."""
    return "op-" + stable_hash({"i": instrument_id, "tf": timeframe, "h": input_hash,
                                "v": versions, "a": sorted(agents)}, size=10)
