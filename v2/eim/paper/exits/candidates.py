"""Las salidas candidatas de T132 como `ExitPolicy`: M2, M3, M5, M6, M7, S1 y M8.

Cada una es un adaptador fino sobre `trail.simulate_trail` y una regla de `rules.py`. No se
conectan a los perfiles ni tocan el libro: solo existen en el banco, que es lo que T132 pide.

Dos de ellas cambian el **SL inicial**, no el arrastre, y por eso llevan aparte la geometría:

- **S1** (§3): el SL inicial se aparta a `d_min·σ` como mínimo, con el **tamaño constante en
  riesgo**. Al alejar el stop, la misma pérdida en R cuesta menos en costos (el costo por R baja
  casi a la mitad al doblar la distancia), que es el argumento de Lo y Remorov.
- **M8** (§7): el SL inicial es el cuantil `q` del MAE de las **ganadoras** de esa
  estrategia@marco, en unidades de σ, calculado sin fuga ni circularidad (E5, `winners_mae.py`).

Las dos respetan la regla del proyecto: si falta el dato (σ o muestra), **no aprietan**; se quedan
con el SL de la idea. Y las dos recolocan el SL **solo hacia fuera**: nunca lo acercan al precio,
porque eso sería empeorar el riesgo de la idea sin pedirlo.

Puro: sin red, sin disco y sin estado global.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

from eim.paper.engine import Outcome
from eim.paper.exits.features import ExitFeatures
from eim.paper.exits.policy import ExitContext
from eim.paper.exits.rules import Chandelier, FixedStop, Hybrid, Structure
from eim.paper.exits.trail import NO_LIMITS, TrailLimits, round_against, simulate_trail
from eim.paper.ideas import Idea


def _sigma_at(feats: ExitFeatures, path_t: np.ndarray, t: int) -> float | None:
    """σ en precio de la vela de decisión (la última que cerró en `t`), o None si no hay."""
    j = int(np.searchsorted(path_t, t)) - 1
    if j < 0 or j >= len(feats.sigma_abs):
        return None
    v = float(feats.sigma_abs[j])
    return v if math.isfinite(v) and v > 0 else None


def widen_stop(idea: Idea, min_dist: float | None, tick: float) -> Idea:
    """La idea con el SL apartado a `min_dist` como mínimo. Solo hacia fuera, nunca hacia dentro."""
    if min_dist is None or not math.isfinite(min_dist) or min_dist <= 0:
        return idea
    ref = idea.entry if idea.entry else 0.0
    if ref <= 0:
        return idea
    now = abs(ref - idea.sl)
    if now >= min_dist - 1e-12:
        return idea
    wanted = ref - idea.side * min_dist
    return replace(idea, sl=round_against(wanted, -idea.side, tick))


@dataclass(frozen=True)
class TrailExit:
    """M2, M3 y M5: arrastre sobre el SL inicial de la idea."""

    id: str
    label: str
    feats: ExitFeatures
    kind: str                          # "M2" | "M3" | "M5"
    knobs: dict = field(default_factory=dict)
    limits: TrailLimits = NO_LIMITS

    @property
    def params(self) -> dict:
        return {"policy": self.kind, "sigma": self.feats.sigma_name,
                "features": self.feats.version, **self.knobs,
                "floor_n": self.limits.floor_n}

    def _rule(self):
        f, k = self.feats, self.knobs
        if self.kind == "M2":
            return Chandelier(k["k"], f.sigma_abs, k.get("activate_r", 0.0), id=self.id)
        if self.kind == "M3":
            return Structure(f.swing_low, f.swing_high, f.sigma_abs,
                             k.get("buffer_sigma", 0.25), id=self.id)
        inner = (Chandelier(k["k"], f.sigma_abs, 0.0, id=self.id) if k.get("trail", "M2") == "M2"
                 else Structure(f.swing_low, f.swing_high, f.sigma_abs,
                                k.get("buffer_sigma", 0.25), id=self.id))
        return Hybrid(inner, k["survival_r"], k["a_r"], k["b_r"], k.get("est_cost_frac", 0.0),
                      id=self.id)

    def simulate(self, idea: Idea, ctx: ExitContext, qty: float) -> Outcome:
        return simulate_trail(idea, ctx.path, ctx.ep, self._rule(), qty, spec=ctx.spec,
                              sigma_abs=self.feats.sigma_abs, limits=self.limits,
                              fine=ctx.fine, htf_dir=self.feats.htf_dir, guard=ctx.guard)


@dataclass(frozen=True)
class TimeExit:
    """M6 — barrera vertical: cierra a la apertura de la vela `bars` si no llegó a `min_r`."""

    id: str
    label: str
    feats: ExitFeatures
    bars: int
    min_r: float = 0.0

    @property
    def params(self) -> dict:
        return {"policy": "M6", "bars": self.bars, "min_r": self.min_r,
                "features": self.feats.version}

    def simulate(self, idea: Idea, ctx: ExitContext, qty: float) -> Outcome:
        limits = TrailLimits(time_bars=self.bars, time_min_r=self.min_r)
        return simulate_trail(idea, ctx.path, ctx.ep, FixedStop(id=self.id), qty, spec=ctx.spec,
                              sigma_abs=self.feats.sigma_abs, limits=limits, fine=ctx.fine,
                              htf_dir=self.feats.htf_dir, guard=ctx.guard)


@dataclass(frozen=True)
class HtfExit:
    """M7 — cierra cuando la tendencia del marco mayor cambia de signo respecto a la entrada."""

    id: str
    label: str
    feats: ExitFeatures

    @property
    def params(self) -> dict:
        return {"policy": "M7", "features": self.feats.version,
                "htf_coverage": round(self.feats.coverage.get("htf_dir", 0.0), 6)}

    def simulate(self, idea: Idea, ctx: ExitContext, qty: float) -> Outcome:
        return simulate_trail(idea, ctx.path, ctx.ep, FixedStop(id=self.id), qty, spec=ctx.spec,
                              sigma_abs=self.feats.sigma_abs,
                              limits=TrailLimits(htf_flip=True), fine=ctx.fine,
                              htf_dir=self.feats.htf_dir, guard=ctx.guard)


@dataclass(frozen=True)
class InitialStopExit:
    """S1 y M8 — cambian el SL inicial y delegan el resto en otra política.

    `min_dist_of` recibe la idea y el contexto y devuelve la distancia mínima del SL en precio, o
    None si no hay dato. `inner` es la salida que se aplica después (por defecto, ninguna: el SL
    inicial manda hasta el final).
    """

    id: str
    label: str
    kind: str                          # "S1" | "M8"
    feats: ExitFeatures
    min_dist_of: object                # Callable[[Idea, ExitContext], float | None]
    inner: object | None = None        # ExitPolicy a la que se delega tras recolocar el SL
    knobs: dict = field(default_factory=dict)

    @property
    def params(self) -> dict:
        inner = getattr(self.inner, "params", None)
        return {"policy": self.kind, "sigma": self.feats.sigma_name,
                "features": self.feats.version, **self.knobs,
                "inner": inner() if callable(inner) else inner}

    def simulate(self, idea: Idea, ctx: ExitContext, qty: float) -> Outcome:
        wide = widen_stop(idea, self.min_dist_of(idea, ctx), ctx.spec.tick)
        if self.inner is not None:
            return self.inner.simulate(wide, ctx, qty)
        return simulate_trail(wide, ctx.path, ctx.ep, FixedStop(id=self.id), qty, spec=ctx.spec,
                              sigma_abs=self.feats.sigma_abs, fine=ctx.fine,
                              htf_dir=self.feats.htf_dir)


def sigma_floor(feats: ExitFeatures, path_t: np.ndarray, d_min: float):
    """Distancia mínima de S1: `d_min·σ` de la vela de decisión (None sin σ)."""
    def of(idea: Idea, ctx: ExitContext) -> float | None:
        s = _sigma_at(feats, path_t, idea.t)
        return None if s is None else d_min * s
    return of


def winners_mae_floor(feats: ExitFeatures, path_t: np.ndarray, quantile_of):
    """Distancia mínima de M8: cuantil del MAE de las ganadoras (en σ) × σ de la decisión.

    `quantile_of(sid, t)` devuelve el cuantil en unidades de σ para esa estrategia@marco en ese
    instante, o None si no hay muestra suficiente: entonces M8 no toca el SL de la idea.
    """
    def of(idea: Idea, ctx: ExitContext) -> float | None:
        q = quantile_of(idea.sid, idea.t)
        if q is None:
            return None
        s = _sigma_at(feats, path_t, idea.t)
        return None if s is None else q * s
    return of
