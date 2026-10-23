"""Evento normalizado del observatorio (T72) y traza determinista.

Un evento es un HECHO observado en un proceso, con referencias (no copias) a sus entradas y
salidas. Señal, decisión aprobada y orden enviada son tipos distintos y nunca se funden.
Todo tiempo en ms epoch UTC (como el resto del proyecto). Sin I/O: el emisor está en `emit.py`.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from eim.core.market import Frozen
from eim.core.mode import Mode

SCHEMA_VERSION = 1

EventKind = Literal[
    "run_start", "run_end", "data_fetch", "signal", "synthesis", "forecast", "plan",
    "risk_decision", "order_intent", "order_sent", "fill", "alert", "heartbeat",
]
EVENT_KINDS: tuple[str, ...] = EventKind.__args__  # type: ignore[attr-defined]

# `rejected` = veto o rechazo (decisión de riesgo vetada, orden rechazada); no es un fallo.
Status = Literal["ok", "degraded", "no_data", "error", "rejected"]

MAX_DETAIL_KEYS = 16
MAX_STR = 200
MAX_REFS = 16


class Ref(Frozen):
    """Referencia a una entrada o salida: identifica, no contiene (nunca volcados de mercado)."""

    type: str = Field(min_length=1, max_length=40)  # "snapshot", "agent_report", "plan"…
    id: str = Field(min_length=1, max_length=120)
    hash: str | None = Field(default=None, max_length=64)  # huella del contenido (sha256 hex)
    params_version: str | None = Field(default=None, max_length=60)


def _clip_scalar(v: Any) -> Any:
    if v is None or isinstance(v, bool | int):
        return v
    if isinstance(v, float):
        return v if v == v and v not in (float("inf"), float("-inf")) else None
    s = v if isinstance(v, str) else repr(v)
    return s if len(s) <= MAX_STR else s[: MAX_STR - 1] + "…"


def bound_detail(d: Any) -> dict[str, Any]:
    """Acota `detail`: ≤ 16 claves, valores escalares (listas cortas de escalares se unen en
    texto), cadenas ≤ 200 caracteres. Trunca en vez de rechazar (el emisor no puede fallar)."""
    if not isinstance(d, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in list(d.items())[:MAX_DETAIL_KEYS]:
        if isinstance(v, list | tuple):
            v = ",".join(str(_clip_scalar(x)) for x in v[:8])
        out[str(k)[:60]] = _clip_scalar(v)
    return out


class ObsEvent(Frozen):
    schema_version: int = SCHEMA_VERSION
    event_id: str
    ts_utc: int
    process: str = Field(min_length=1, max_length=40)       # "api", "leaders", "collector"…
    component_id: str = Field(min_length=1, max_length=80)  # id del catálogo
    kind: EventKind
    status: Status = "ok"
    run_id: str = Field(min_length=1, max_length=80)        # esta ejecución / tramo
    parent_run_id: str | None = None
    trace_id: str | None = None                             # `trace_for` (misma vela, misma traza)
    duration_ms: float | None = Field(default=None, ge=0)
    inputs: tuple[Ref, ...] = Field(default=(), max_length=MAX_REFS)
    outputs: tuple[Ref, ...] = Field(default=(), max_length=MAX_REFS)
    detail: dict[str, Any] = Field(default_factory=dict)
    mode: Mode = Mode.ANALISIS
    source: str | None = Field(default=None, max_length=120)  # de dónde viene el dato reportado
    coverage: float | None = Field(default=None, ge=0, le=1)  # cobertura real 0..1

    @field_validator("detail", mode="before")
    @classmethod
    def _bound(cls, v: Any) -> dict[str, Any]:
        return bound_detail(v)

    @model_validator(mode="after")
    def _data_needs_source(self) -> ObsEvent:
        # regla del proyecto: ninguna cifra sin `source` (y cobertura cuando hay datos parciales)
        if self.kind == "data_fetch" and self.status in ("ok", "degraded") and not self.source:
            raise ValueError("un data_fetch exitoso debe declarar su `source`")
        return self


def new_event_id(ts_ms: int) -> str:
    """Identificador ordenable por tiempo y sin colisión entre procesos."""
    return f"{ts_ms:012x}-{secrets.token_hex(5)}"


def new_run_id() -> str:
    return secrets.token_hex(6)


def trace_for(symbol: str, tf: str, close_ts: int) -> str:
    """Traza determinista de una vela: dos procesos que trabajan sobre (símbolo, marco, cierre)
    obtienen el mismo `trace_id` sin compartir memoria. `close_ts` = ms epoch UTC del cierre."""
    key = f"{symbol.strip().upper()}|{tf.strip().lower()}|{int(close_ts)}"
    return "tr_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def trace_for_key(*parts: object) -> str:
    """Traza determinista de algo que no es una vela (una propuesta y su perfil, T114). El
    prefijo `K|` impide que coincida con una traza de vela."""
    key = "K|" + "|".join(str(p) for p in parts)
    return "tr_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def event_id_for(ts_ms: int, key: str) -> str:
    """`event_id` determinista (mismo formato que `new_event_id`): reemitir el mismo hecho tras
    un recálculo o un reinicio no lo duplica en la base (el indexador ignora lo ya visto)."""
    return f"{ts_ms:012x}-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:10]}"


def proposal_trace(p: Any, scope: str = "") -> str:
    """Traza de una decisión de la autoridad (T114). El plan de los agentes usa la de su vela
    (misma traza que sus señales, T74); el resto, una por propuesta (y por perfil, `scope`), para
    que T76 cuente cada decisión sin mezclarla con la del plan de esa vela."""
    if p.source == "agents.plan":
        return trace_for(p.symbol, p.timeframe, p.data_asof)
    return trace_for_key("proposal", p.source, p.proposal_id, scope)
