"""Política del escuadrón de bots en la síntesis (T60): quién vota, con qué peso y quién informa.

El peso de un bot es el que midió la prueba marginal de T59 (aporte al núcleo, no rentabilidad
propia) con la penalización por correlación como en T44. Vota solo si su estado es `vota`, su
clase es `D` (direccional) y no está en cuarentena; `L` (carril) e `IA` (informa) nunca votan.
Sin política (o con todos en `informa`) la síntesis es idéntica a la de antes de T60.

Funciones puras sobre la tabla de puntuación (`dict` de T59). El proceso de la API guarda la
política vigente con `set_policy` (configuración, no estado de un agente); los tests no la tocan.
"""

from __future__ import annotations

import threading
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from eim.synthesis.params import PEERS, SynthesisParams

VOTA, INFORMA, CUARENTENA = "vota", "informa", "cuarentena"
VOTING_CLASSES = frozenset({"D"})
LANE_CLASSES = frozenset({"L"})


def key_of(bot_id: str, strategy: str) -> str:
    """Misma clave que usa el agente `bots` para cada bot-estrategia."""
    return f"{bot_id}@{strategy}"


@dataclass(frozen=True)
class SquadBot:
    key: str
    bot_id: str
    strategy: str
    bot_class: str
    state: str            # vota | informa | rechazado | deshabilitado_seguridad | cuarentena
    weight: float         # peso medido por T59 (0 si no vota)
    rho: float | None     # |ρ| máx con el núcleo (penalización T44)
    modulates: bool       # T59 midió que su acuerdo con el núcleo predice el acierto del núcleo
    publicable: bool

    @property
    def votes(self) -> bool:
        return (self.state == VOTA and self.bot_class in VOTING_CLASSES and self.weight > 0)

    @property
    def lane(self) -> bool:
        return self.bot_class in LANE_CLASSES


@dataclass(frozen=True)
class SquadPolicy:
    symbol: str
    bots: tuple[SquadBot, ...] = ()

    def get(self, key: str) -> SquadBot | None:
        return next((b for b in self.bots if b.key == key), None)

    @property
    def voters(self) -> tuple[SquadBot, ...]:
        return tuple(b for b in self.bots if b.votes)

    @property
    def modulating(self) -> frozenset[str]:
        """Bots cuyo acuerdo/desacuerdo T59 midió útil (canal de confianza); no votan por ello."""
        return frozenset(b.key for b in self.bots
                         if b.modulates and b.state in (VOTA, INFORMA) and not b.lane)

    @property
    def agent_weight(self) -> float:
        """Peso del agente `bots` en la síntesis: media de los pesos medidos de quien vota."""
        v = self.voters
        return sum(b.weight for b in v) / len(v) if v else 0.0

    @property
    def rho(self) -> float:
        return max((b.rho or 0.0 for b in self.voters), default=0.0)


def policy_from_scorecard(sc: Mapping[str, Any] | None, cards: Mapping[str, Any],
                          quarantined: Collection[str] = ()) -> SquadPolicy:
    """Política desde la tabla de T59; un bot sin ficha o en cuarentena no vota."""
    if not sc or not sc.get("bots"):
        return SquadPolicy(str((sc or {}).get("symbol", "")))
    out: list[SquadBot] = []
    for c in sc["bots"]:
        key = key_of(c["bot"], c["strategy"])
        card = cards.get(c["bot"])
        cls = getattr(card, "bot_class", "INFRA")
        m = c.get("marginal") or {}
        state = CUARENTENA if key in quarantined else c["state"]
        out.append(SquadBot(
            key, c["bot"], c["strategy"], cls, state,
            float(c.get("initial_weight") or 0.0), m.get("rho_max"),
            bool(c.get("modulates_confidence")), bool(c.get("publicable"))))
    return SquadPolicy(str(sc.get("symbol", "")), tuple(out))


def apply(base: SynthesisParams, policy: SquadPolicy | None) -> SynthesisParams:
    """Parámetros de síntesis con el escuadrón integrado.

    Sin votantes ni canal de confianza activo devuelve `base` tal cual (sesgo idéntico al previo).
    """
    if policy is None:
        return base
    upd: dict[str, Any] = {}
    if policy.voters:
        upd["weights"] = {**base.weights, "bots": policy.agent_weight}
        upd["excluded"] = base.excluded - {"bots"}
        upd["correlation"] = {**base.correlation,
                              "bots": {p: policy.rho for p in PEERS if policy.rho > 0}}
    if policy.modulating:
        upd["squad_confidence"] = True
    return base.model_copy(update=upd) if upd else base


def support(rows: list[dict]) -> dict[str, int]:
    """Segunda opinión (canal b): cuántos bots con señal válida apoyan cada dirección.

    `rows`: filas del agente `bots` (`stance`, `status`). No altera probabilidades calibradas."""
    ok = [r for r in rows if r.get("status") == "ok"]
    return {"up": sum(1 for r in ok if r["stance"] > 0),
            "down": sum(1 for r in ok if r["stance"] < 0),
            "flat": sum(1 for r in ok if r["stance"] == 0), "total": len(ok)}


_lock = threading.Lock()
_current: SquadPolicy | None = None


def set_policy(policy: SquadPolicy | None) -> None:
    global _current
    with _lock:
        _current = policy


def current_policy() -> SquadPolicy | None:
    with _lock:
        return _current


def default_params() -> SynthesisParams:
    """Parámetros vigentes: los base + el escuadrón según la última puntuación (si la hay)."""
    return apply(SynthesisParams(), current_policy())
