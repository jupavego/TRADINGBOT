"""Concepto de un bot (T59): cuatro dimensiones separadas y un estado, sin nota global.

| Dimensión   | Fuente                                                                    |
| Rendimiento | V2 (expectativa neta), V4 (drawdown) y V6 (costos) de la puerta de T49    |
| Evidencia   | V1 (muestra), V3 (contra el azar, Holm con todos los intentos), V5 (estab.)|
| Seguridad   | ficha de T56: habilitación + aprobación. Sin ella el bot no entra, rinda o no |
| Operativa   | ficha de T56 + datos vivos (`health`: fallos, deriva, rendimiento vivo)   |

Estados: `vota` (seguridad OK y aporte marginal medido > 0, ver `marginal`), `informa` (seguridad OK
sin aporte medido: se ve y, si se midió, modula la confianza; no vota), `rechazado` (la puerta lo
rechaza y no aporta), `deshabilitado_seguridad`. `publicable` (VALIDADA por T49) es una marca
aparte: solo decide si sus operaciones alimentan «Operaciones sugeridas» (T50), no si influye en
la síntesis.
Un bot degradado (`health`) que votaba baja a `informa`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from eim.bots.card import BotCard
from eim.bots.health import Health
from eim.bots.marginal import Marginal
from eim.validation.gate import RECHAZADA, VALIDADA

VOTA, INFORMA, RECHAZADO, DESHABILITADO = "vota", "informa", "rechazado", "deshabilitado_seguridad"
STATES = (VOTA, INFORMA, RECHAZADO, DESHABILITADO)
PERFORMANCE, EVIDENCE = ("V2", "V4", "V6"), ("V1", "V3", "V5")


def _dim(checks: list[dict], ids: tuple[str, ...]) -> dict:
    sel = [c for c in checks if c["id"] in ids]
    oks = [c["ok"] for c in sel]
    state = ("no cumple" if False in oks else "pendiente" if None in oks or not oks
             else "cumple")
    return {"estado": state, "criterios": {c["id"]: {"ok": c["ok"], "detalle": c["reason"]}
                                           for c in sel}}


def security_dim(card: BotCard) -> dict:
    s = card.security
    return {"estado": "cumple" if card.usable else "no cumple", "habilitado": s.enabled,
            "aprobado_por_usuario": card.approval.state == "aprobada", "puntaje": s.total,
            "alertas_rojas": list(s.red_alerts), "fuente": "ficha T56"}


def operative_dim(card: BotCard, health: Health | None) -> dict:
    o = card.operational
    live = None if health is None else health.to_json()
    return {"estado": "degradada" if health is not None and health.degraded else
            ("sin datos vivos" if health is None else "cumple"),
            "puntaje_ficha": o.total, "dias_desde_commit": o.days_since_commit,
            "vivo": live, "fuente": "ficha T56 + señales guardadas"}


@dataclass(frozen=True)
class Concept:
    label: str
    bot_id: str
    strategy: str
    timeframe: str
    version: str
    state: str
    publicable: bool
    weight: float
    dimensions: dict
    reasons: tuple[str, ...] = field(default_factory=tuple)
    marginal: dict | None = None
    modulates: bool = False

    def to_json(self) -> dict:
        return {"id": self.label, "bot": self.bot_id, "strategy": self.strategy,
                "timeframe": self.timeframe, "version": self.version, "state": self.state,
                "publicable": self.publicable, "initial_weight": self.weight,
                "modulates_confidence": self.modulates, "dimensions": self.dimensions,
                "reasons": list(self.reasons), "marginal": self.marginal}


def assign(label: str, ident: tuple[str, str, str, str], card: BotCard, verdict: dict,
           marginal: Marginal | None, health: Health | None) -> Concept:
    """Estado y dimensiones de la versión vigente de un bot."""
    bot_id, strategy, tf, version = ident
    checks = verdict["checks"]
    dims = {"rendimiento": _dim(checks, PERFORMANCE), "evidencia": _dim(checks, EVIDENCE),
            "seguridad": security_dim(card), "operativa": operative_dim(card, health)}
    why = [f"puerta T49: {verdict['verdict']} — {verdict['reason']}"]
    degraded = health is not None and health.degraded
    m = marginal
    if m is None:
        why.append("aporte marginal: sin medir (sin panel de agentes en el periodo)")
    else:
        why.append(f"aporte marginal: {m.reason}")
    if not card.usable:
        state, weight = DESHABILITADO, 0.0
        why.append("seguridad no habilitada o sin aprobación: no entra aunque rinda")
    elif m is not None and m.contributes and not degraded:
        state, weight = VOTA, m.weight
    elif degraded:
        state, weight = INFORMA, 0.0
        why += [f"degradación: {r}" for r in health.reasons]    # type: ignore[union-attr]
    elif verdict["verdict"] == RECHAZADA and not (m is not None and m.modulates):
        state, weight = RECHAZADO, 0.0
    else:
        state, weight = INFORMA, 0.0
    publicable = (state != DESHABILITADO and verdict["verdict"] == VALIDADA and not degraded)
    modulates = bool(m is not None and m.modulates and state in (VOTA, INFORMA))
    return Concept(label, bot_id, strategy, tf, version, state, publicable, weight, dims,
                   tuple(why), None if m is None else m.to_json(), modulates)
