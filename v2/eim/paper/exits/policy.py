"""Interfaz pura de una política de salida (T131) y los adaptadores M0 y M1.

Una política es una **función pura** que, dada una idea, el camino de precios y la cantidad,
devuelve el `Outcome` de esa operación. Nada más: sin red, sin disco y sin estado global (las
reglas de `CLAUDE.md`). Así el banco (`bench.py`) mide cualquier salida sobre LAS MISMAS entradas
con los mismos costos, y T132 añade políticas nuevas sin tocar el banco ni el motor.

Los dos adaptadores de esta tarea no reimplementan nada: delegan en el motor que ya validó T111,
así que reproducen sus cifras por construcción (`tests/paper/exits/test_m0_m1_regression.py` lo
comprueba campo a campo).

- **M0** (referencia provisional, ◆1 de T129): escalera de protección progresiva, `simulate_ladder`.
- **M1** (salida A de T111): TP, BE+ y cierre por tiempo de la sombra, `engine.simulate`.

`ExitContext` reúne lo que no depende de la política (camino, costos, velas finas, ficha del
instrumento y el suelo guardado del diario T110) para que la firma de `simulate` no crezca con cada
política nueva.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from eim.paper.engine import Outcome, Path, simulate
from eim.paper.ideas import Idea
from eim.paper.ladder import simulate_ladder
from eim.paper.ladder_floor import Guard
from eim.paper.params import ExecParams, LadderParams, SymbolSpec


@dataclass(frozen=True)
class ExitContext:
    """Todo lo común a las políticas de una corrida del banco.

    `fine` son las velas de 1 min que resuelven el orden real dentro de una vela ambigua de 15 m;
    sin ellas cada política se queda con su regla conservadora. `guard` es lo que el diario de
    protección (T110) guardó de la operación, y solo aplica al medir operaciones reales.
    """

    path: Path
    ep: ExecParams
    spec: SymbolSpec
    fine: Path | None = None
    guard: Guard | None = None


@runtime_checkable
class ExitPolicy(Protocol):
    """Contrato de una salida. `id` es el identificador pre-registrado (M0, M1, M2…)."""

    id: str
    label: str

    @property
    def params(self) -> dict:
        """Parámetros que la definen: entran TAL CUAL en la huella del pre-registro."""
        ...

    def simulate(self, idea: Idea, ctx: ExitContext, qty: float) -> Outcome:
        """`Outcome` de esta idea con esta salida. Pura y determinista."""
        ...


@dataclass(frozen=True)
class LadderExit:
    """M0 — escalera de protección progresiva (T108/T109), la salida vigente en los perfiles."""

    lp: LadderParams
    id: str = "M0"
    label: str = "M0 escalera (protección progresiva)"

    @property
    def params(self) -> dict:
        return {"policy": "ladder", **self.lp.model_dump(mode="json")}

    def simulate(self, idea: Idea, ctx: ExitContext, qty: float) -> Outcome:
        return simulate_ladder(idea, ctx.path, ctx.ep, self.lp, qty, ctx.fine, spec=ctx.spec,
                               guard=ctx.guard)


@dataclass(frozen=True)
class ShadowExit:
    """M1 — TP, BE+ y cierre por tiempo: la salida A de T111 (`engine.simulate`).

    El resultado de la sombra está en fracciones del nocional, así que no depende de `qty`: el
    banco lo escala al tamaño fijo igual que hacía el emparejado de T111 (`ab_pairs._b_trade`).
    """

    id: str = "M1"
    label: str = "M1 TP/BE+/tiempo (sombra)"
    overrides: dict = field(default_factory=dict)

    @property
    def params(self) -> dict:
        return {"policy": "shadow_tp_be_time", **self.overrides}

    def _ep(self, ep: ExecParams) -> ExecParams:
        return ep.model_copy(update=self.overrides) if self.overrides else ep

    def simulate(self, idea: Idea, ctx: ExitContext, qty: float) -> Outcome:
        del qty                       # la sombra no depende del tamaño (resultado en fracciones)
        return simulate(idea, ctx.path, self._ep(ctx.ep))


def policy_fingerprint(policies: list[ExitPolicy]) -> list[dict]:
    """Identidad de las políticas de una corrida, para la huella del pre-registro y del informe."""
    return [{"id": p.id, "label": p.label, "params": p.params} for p in policies]
