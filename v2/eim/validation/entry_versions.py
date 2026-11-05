"""Versiones de entrada de T137: la regla de cada variante y su identidad en el registro. Puro.

Una versión es una estrategia vigente con **otra geometría del SL inicial** (M8 o S1, las de T134)
y/o un **tope de costo en R** (T136) como filtro propio: nada de esto toca los perfiles ni el
catálogo, y estas versiones no generan ideas en vivo.

La geometría no se reescribe: usa `candidates.widen_stop`, `sigma_floor` y `winners_mae_floor`, las
mismas funciones que T134 midió, y el costo en R es `risk_budget.cost_r`, el mismo del veto de los
perfiles. Dos definiciones del mismo número son la forma más fácil de medir otra cosa sin saberlo.

Tres reglas del pre-registro viven aquí porque el resultado depende de ellas:

- **El tope se mide sobre el SL de la versión, ya apartado**: es el stop que esa versión pagaría.
- **`vivo` solo desde el alta**: un contexto en vivo anterior al alta se decidió con otras reglas,
  así que reconstruir la versión sobre él es backtest.
- **El cuantil de M8 se estima sin fuga**: cada instante usa el cuantil del pliegue cuyo tramo de
  prueba lo contiene, y `control_aleatorio`, que no llega a la muestra mínima de ganadoras, toma el
  de la estrategia con sus mismas salidas (BACKLOG T134 (1)).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace

import numpy as np

from eim.paper.exits import walkforward as wf
from eim.paper.exits.bench import BenchTrade
from eim.paper.exits.candidates import sigma_floor, widen_stop, winners_mae_floor
from eim.paper.exits.features import ExitFeatures
from eim.paper.exits.winners_mae import ByFold, WinnersMae, build
from eim.paper.ideas import Idea
from eim.paper.risk_budget import cost_r
from eim.validation.entry_prereg import Prereg, Reading, VariantSpec
from eim.validation.lineage import Version, Window, iso_ms, tuning_windows

HOUR_MS = 3_600_000
FAR_MS = 2**62                       # «sin final»: nunca se alcanza con un instante real
ORIGIN = "T137"
BASE = "base"                        # la versión padre, para comparar; no es un intento nuevo
PARENT_N = 2                         # las 104 vigentes de la copia son v2 (pre-registro)
POOL = "_conjunto"                   # todas las estrategias reales de un marco
CONTROL_TWIN = "consenso_sintesis"   # control_aleatorio declara sus mismas salidas
OUTSIDE = "fuera de la lectura"


def fold_plan(pr: Prereg) -> dict[str, tuple[wf.Fold, ...]]:
    """Los pliegues del cuantil de M8 por marco: los de T134 + el siguiente, y el propio de 15 m."""
    emb = int(pr.m8_folds.embargo_hours * HOUR_MS)
    b = pr.m8_folds.bank
    bank = wf.folds(wf.from_iso(b.from_), wf.from_iso(b.to), emb, b.fit_months, b.test_months,
                    b.step_months)
    plan: dict[str, tuple[wf.Fold, ...]] = {}
    a = pr.m8_folds.after_bank
    after = wf.Fold(len(bank), wf.from_iso(a.fit_from), wf.from_iso(a.fit_to),
                    wf.from_iso(a.test_from), FAR_MS, emb)
    plan.update({tf: (*bank, after) for tf in a.timeframes})
    f = pr.m8_folds.tf15m
    own = wf.Fold(0, wf.from_iso(f.fit_from), wf.from_iso(f.fit_to), wf.from_iso(f.test_from),
                  FAR_MS, emb)
    plan.update({tf: (own,) for tf in f.timeframes})
    return plan


@dataclass(frozen=True)
class QuantileBook:
    """El cuantil del MAE de las ganadoras, en σ, por marco y pliegue, sin fuga."""

    by_tf: dict[str, ByFold]
    control: str

    def _pick(self, w: WinnersMae | None, sid: str) -> float | None:
        if w is None:
            return None
        strategy, tf = sid.split("@")
        if strategy != self.control:
            return w.of(sid)
        twin = w.of(f"{CONTROL_TWIN}@{tf}")
        return twin if twin is not None else w.of(f"{POOL}@{tf}")

    def of(self, sid: str, t: int) -> float | None:
        """Cuantil de esa estrategia@marco en `t`; None sin muestra o si `t` no tiene pliegue."""
        bf = self.by_tf.get(sid.split("@")[1])
        return None if bf is None else self._pick(bf.at(t), sid)

    def table(self, sid: str) -> list[float | None]:
        """Cuantil de cada pliegue: es un parámetro de la versión, así que entra en su huella."""
        bf = self.by_tf.get(sid.split("@")[1])
        return [] if bf is None else [self._pick(w, sid) for w in bf.per_fold]


def quantile_book(reference: Sequence[BenchTrade],
                  ratio_of: Callable[[BenchTrade], float | None],
                  plan: dict[str, tuple[wf.Fold, ...]], pr: Prereg) -> QuantileBook:
    """Cuantiles con las ganadoras de la salida de referencia, sin el control entre ellas."""
    real = [t for t in reference if not t.sid.startswith(f"{pr.strategies.control}@")]
    pooled = [replace(t, sid=f"{POOL}@{t.timeframe}") for t in real]
    m8 = pr.geometry.m8
    out = {}
    for tf, folds in plan.items():
        mine = [t for t in (*real, *pooled) if t.timeframe == tf]
        out[tf] = build(mine, folds, ratio_of, reference=m8.reference, quantile=m8.q,
                        min_trades=m8.min_trades)
    return QuantileBook(out, pr.strategies.control)


def mae_ratio(parkinson: ExitFeatures, path_t: np.ndarray, by_id: dict[str, Idea]
              ) -> Callable[[BenchTrade], float | None]:
    """riesgo en precio / σ de cada operación: pasa el MAE de R a σ, igual que hizo T134."""
    def of(t: BenchTrade) -> float | None:
        i = by_id.get(t.id)
        if i is None or not i.entry:
            return None
        j = int(np.searchsorted(path_t, i.t)) - 1
        if j < 0 or j >= len(parkinson.sigma_abs):
            return None
        s = float(parkinson.sigma_abs[j])
        risk = abs(i.entry - i.sl)
        return None if not np.isfinite(s) or s <= 0 or risk <= 0 else risk / s
    return of


@dataclass(frozen=True)
class Rule:
    """Lo que una variante le hace a una idea, antes de la sombra."""

    vid: str
    min_dist: Callable | None        # (idea, _) → distancia mínima del SL en precio, o None
    max_cost_r: float | None
    est_cost_frac: float
    tick: float
    alta_ms: int

    def apply(self, idea: Idea) -> tuple[Idea | None, bool, float]:
        """(idea de la versión, o None si el tope la veta; si movió el SL; su costo en R)."""
        wide = (idea if self.min_dist is None
                else widen_stop(idea, self.min_dist(idea, None), self.tick))
        cost = cost_r(wide.entry, wide.sl, self.est_cost_frac)
        moved = wide.sl != idea.sl
        if self.max_cost_r is not None and cost > self.max_cost_r:
            return None, moved, cost
        if wide.origin == "vivo" and idea.t < self.alta_ms:
            wide = replace(wide, origin="backtest")
        return wide, moved, cost


def rule_of(v: VariantSpec | None, pr: Prereg, atr: ExitFeatures, path_t: np.ndarray,
            quantile_of: Callable[[str, int], float | None] | None, tick: float) -> Rule:
    """La regla de una variante; con `v=None`, la del padre (sin geometría ni tope)."""
    geo = None if v is None else v.geometry
    if geo == "s1":
        dist = sigma_floor(atr, path_t, pr.geometry.s1.d_min_sigma)
    elif geo == "m8":
        dist = winners_mae_floor(atr, path_t, quantile_of)
    else:
        dist = None
    cap = pr.cost_cap.max_cost_r if v is not None and v.cost_cap else None
    return Rule(BASE if v is None else v.id, dist, cap, pr.cost_cap.est_cost_frac, tick,
                iso_ms(pr.live_rule.alta))


def fingerprint(base_fp: str, v: VariantSpec, pr: Prereg, table: Sequence[float | None]) -> str:
    """Huella de la versión: la del padre + la variante + sus parámetros, cuantiles incluidos.

    Cambia la geometría, el tope o el cuantil y es otra versión. Es estable entre corridas, porque
    el cuantil solo depende de tramos de ajuste que ya no cambian.
    """
    blob = {"base": base_fp, "variant": v.id, "prereg": pr.version, "cap": v.cost_cap and
            pr.cost_cap.max_cost_r, "geometry": v.geometry and getattr(
                pr.geometry, v.geometry).model_dump(exclude={"unit_note", "without_sample"}),
            "q": [None if x is None else round(float(x), 10) for x in table]
            if v.geometry == "m8" else None}
    return hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()[:12]


def own_windows(sid: str, v: VariantSpec, pr: Prereg) -> tuple[Window, ...]:
    """Ventanas de ajuste propias: la de selección de T134/T136 y, en 15 m con M8, su ajuste."""
    w = pr.windows
    out = [Window(iso_ms(w.selection.from_), iso_ms(w.selection.to), None, w.selection.note)]
    if v.geometry == "m8" and sid.split("@")[1] in pr.m8_folds.tf15m.timeframes:
        out.append(Window(iso_ms(w.m8_fit_15m.from_), iso_ms(w.m8_fit_15m.to), None,
                          w.m8_fit_15m.note))
    return tuple(out)


def version_of(sid: str, v: VariantSpec, pr: Prereg, fp: str, parent: int | None = PARENT_N
               ) -> Version:
    """La versión en el registro: **nace retirada**, porque nunca es la vigente de su estrategia.

    Solo existe para contar como intento y para que sus ventanas queden registradas; así dar de
    alta una no retira la versión en vivo, que es lo que haría `ValidationStore.ensure`.
    """
    alta = iso_ms(pr.live_rule.alta)
    strategy, tf = sid.split("@")
    return Version(sid, v.n, fp, strategy, tf, alta, parent, ORIGIN,
                   f"T137 {v.id}: {pr.version}", alta, own_windows(sid, v, pr))


def complement(ranges: Iterable[tuple[str, str | None]]) -> tuple[Window, ...]:
    """Las ventanas que dejan fuera todo lo que no sea `ranges`: así una lectura descriptiva pasa
    por la MISMA `measure` de la puerta, sin una segunda definición de «fuera de muestra»."""
    spans = sorted((iso_ms(a), FAR_MS if b is None else iso_ms(b)) for a, b in ranges)
    out, cur = [], 0
    for a, b in spans:
        if a > cur:
            out.append(Window(cur, a, None, OUTSIDE))
        cur = max(cur, b)
    if cur < FAR_MS:
        out.append(Window(cur, FAR_MS, None, OUTSIDE))
    return tuple(out)


def windows_for(r: Reading, v: Version, family: Iterable[Version]) -> tuple[Window, ...]:
    """Las ventanas que una lectura excluye: las de T49 en la oficial, los rangos en las demás."""
    return tuning_windows(v, family) if r.verdict else complement(r.ranges)


def in_reading(r: Reading, sid: str) -> bool:
    """¿Se mide esta estrategia@marco en esta lectura? El banco no lleva 15 m."""
    return not r.timeframes or sid.split("@")[1] in r.timeframes
