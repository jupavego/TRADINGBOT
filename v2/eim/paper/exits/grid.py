"""La rejilla pre-registrada hecha variantes corribles (T134).

De la rejilla del pre-registro salen **todas** las combinaciones de cada familia implementada, sin
elegir ninguna: elegir es el veredicto de §5.4, no este módulo. Las familias que no están
implementadas o que se descartaron se devuelven aparte, con su motivo, para que el informe las
declare en vez de omitirlas.

El orden de las variantes dentro de cada familia es el de la rejilla, y es el que define los
**vecinos a ±1 paso** de la meseta: con un solo parámetro es inmediato, y con varios se recorre la
rejilla dejando fijos los demás, que es lo que significa «±1 paso» en §5.3.

Puro: sin red y sin disco.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import product

import numpy as np

from eim.paper.exits.candidates import (
    HtfExit,
    InitialStopExit,
    TimeExit,
    TrailExit,
    sigma_floor,
    winners_mae_floor,
)
from eim.paper.exits.features import ExitFeatures
from eim.paper.exits.policy import ExitPolicy, LadderExit, ShadowExit
from eim.paper.exits.prereg import IMPLEMENTED, Prereg
from eim.paper.exits.trail import TrailLimits
from eim.paper.params import LadderParams

FLOOR_N = 2.0           # piso de ruido en σ para las políticas con arrastre (§4.5, n = 2)


@dataclass(frozen=True)
class Variant:
    """Una combinación concreta de la rejilla, ya corrible."""

    id: str
    family: str
    policy: ExitPolicy
    knobs: dict

    @property
    def params(self) -> dict:
        return self.policy.params


def _combos(params: dict[str, Sequence]) -> list[dict]:
    """Todas las combinaciones de la familia, en el orden de la rejilla."""
    keys = list(params)
    return [dict(zip(keys, vals, strict=True)) for vals in product(*(params[k] for k in keys))]


def _tag(prefix: str, knobs: dict) -> str:
    bits = []
    for k, v in knobs.items():
        bits.append(f"{k}={v:g}" if isinstance(v, (int, float)) else f"{k}={v}")
    return f"{prefix} " + " ".join(bits)


def companion_of(pr: Prereg, ladder: LadderParams, vid: str) -> ExitPolicy:
    """La salida que acompaña a S1 y M8, la que declara `initial_stop.companion`.

    Hoy es M0 con sus valores vigentes: así la comparación contra la base M0 aísla exactamente lo
    que esas dos familias cambian —el stop inicial—, con la misma salida a los dos lados.
    """
    name = pr.initial_stop.companion if pr.initial_stop else "M0"
    if name != "M0":
        raise ValueError(f"acompañante no soportado: {name!r} (hoy solo M0)")
    return LadderExit(ladder, id=f"{vid}/M0", label=f"{vid} con M0")


def expand(pr: Prereg, feats: dict[str, ExitFeatures], ladder: LadderParams, path_t: np.ndarray,
           quantile_for: Callable[[float], Callable[[str, int], float | None] | None] | None = None,
           est_cost_frac: float = 0.0) -> tuple[list[Variant], dict[str, str]]:
    """(variantes corribles, familias que no se corren con su motivo).

    `feats` son los rasgos por nombre de estimador σ; cada familia pide el suyo. `quantile_for` es
    una FÁBRICA: recibe el `q` de la variante y devuelve su cuantil del MAE de las ganadoras por
    pliegue (E5). Tiene que ser una fábrica y no una función fija, porque `q` es justo el
    parámetro que M8 varía: con una sola función, sus tres variantes serían la misma política
    contada tres veces, y además entrarían en la corrección por pruebas múltiples como tres copias
    perfectamente correlacionadas. Sin fábrica, M8 no se corre y se declara.
    """
    out: list[Variant] = []
    skipped: dict[str, str] = {}
    lim = TrailLimits(floor_n=FLOOR_N)
    for g in pr.grid:
        if g.status != IMPLEMENTED:
            skipped[g.id] = g.status
            continue
        if g.id == "M8" and quantile_for is None:
            skipped[g.id] = "sin cuantil del MAE (hacen falta los pliegues de la referencia)"
            continue
        for kn in _combos(g.params):
            vid = _tag(g.id, kn)
            qof = quantile_for(float(kn["q"])) if (g.id == "M8" and quantile_for) else None
            if g.id == "M8" and qof is None:
                skipped[vid] = f"sin cuantil del MAE para q={kn['q']}"
                continue
            pol = _policy(g.id, vid, kn, feats, ladder, path_t, qof, lim,
                          est_cost_frac, companion_of(pr, ladder, vid))
            if pol is None:
                skipped[vid] = f"el estimador {kn.get('sigma')!r} no tiene rasgos en esta corrida"
                continue
            out.append(Variant(vid, g.id, pol, kn))
    return out, skipped


def _policy(fam: str, vid: str, kn: dict, feats: dict[str, ExitFeatures], ladder: LadderParams,
            path_t: np.ndarray, quantile_of, lim: TrailLimits, est_cost_frac: float,
            companion: ExitPolicy) -> ExitPolicy | None:
    """La política de una combinación; None si le falta el estimador σ que pide."""
    if fam == "M0":
        v = float(kn["first_r"])
        lp = ladder.model_copy(update={"basis": "r", "first_r": v, "step_r": v / 2})
        return LadderExit(lp, id=vid, label=vid)
    if fam == "M1":
        return ShadowExit(id=vid, label=vid, overrides={
            "be_trigger_r": float(kn["be_trigger_r"]), "be_lock_r": float(kn["be_lock_r"])})
    default = next(iter(feats.values()))
    f = feats.get(str(kn.get("sigma", ""))) or default
    if kn.get("sigma") and kn["sigma"] not in feats:
        return None
    if fam == "M2":
        return TrailExit(vid, vid, f, "M2",
                         {"k": float(kn["k"]), "activate_r": float(kn["activate_r"])}, lim)
    if fam == "M3":
        return TrailExit(vid, vid, f, "M3", {"buffer_sigma": 0.25,
                                             "fractal_bars": int(kn["fractal_bars"]),
                                             "noise_floor_n": float(kn["noise_floor_n"])},
                         TrailLimits(floor_n=float(kn["noise_floor_n"])))
    if fam == "M5":
        return TrailExit(vid, vid, f, "M5",
                         {"k": 3.0, "survival_r": 0.3, "a_r": float(kn["a_r"]),
                          "b_r": float(kn["b_r"]), "trail": str(kn["trail"]),
                          "est_cost_frac": est_cost_frac}, lim)
    if fam == "M6":
        return TimeExit(vid, vid, f, bars=int(kn["bars"]), min_r=float(kn["min_r"]))
    if fam == "M7":
        return HtfExit(vid, vid, f)
    if fam == "M8":
        return InitialStopExit(vid, vid, "M8", f,
                               winners_mae_floor(f, path_t, quantile_of),
                               inner=companion, knobs=dict(kn))
    if fam == "S1":
        return InitialStopExit(vid, vid, "S1", f,
                               sigma_floor(f, path_t, float(kn["d_min_sigma"])),
                               inner=companion, knobs=dict(kn))
    return None


def neighbours(vs: Sequence[Variant]) -> dict[str, list[str]]:
    """Vecinos a ±1 paso DENTRO de la familia: un parámetro NUMÉRICO se mueve y el resto se queda.

    Dos cosas que la meseta de §5.3 no es:
    - No cruza de una familia a otra: M2 con k=4 no es «vecina» de M3 con fractal de 5, son
      mecanismos distintos y no pasos de una rejilla.
    - No se mueve por los parámetros **categóricos** (el estimador σ, o si M5 arrastra con M2 o con
      M3). No hay «un paso» entre Parkinson y Yang–Zhang, así que cambiar de estimador no habla de
      la robustez del parámetro: cada estimador define su propia rejilla y su propia meseta.
    """
    by_fam: dict[str, list[Variant]] = {}
    for v in vs:
        by_fam.setdefault(v.family, []).append(v)
    out: dict[str, list[str]] = {}
    for same in by_fam.values():
        index = {_key(v.knobs): v.id for v in same}
        numeric = [k for k in (same[0].knobs if same else {})
                   if all(isinstance(v.knobs.get(k), (int, float)) for v in same)]
        order = {k: sorted({float(v.knobs[k]) for v in same if k in v.knobs}) for k in numeric}
        for v in same:
            out[v.id] = []
            for k, values in order.items():
                if k not in v.knobs or len(values) < 2:
                    continue
                i = values.index(float(v.knobs[k]))
                for j in (i - 1, i + 1):
                    if not 0 <= j < len(values):
                        continue
                    nb = index.get(_key({**v.knobs, k: values[j]}))
                    if nb and nb != v.id:
                        out[v.id].append(nb)
    return out


def _key(knobs: dict) -> tuple:
    """Clave comparable de una combinación: los números como float, el resto como texto."""
    return tuple(sorted(
        ((k, float(v)) if isinstance(v, (int, float)) else (k, str(v)))
        for k, v in knobs.items()))
