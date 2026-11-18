"""Libros de los perfiles con «lo vivo manda» (T182).

Sin `ExecParams.live_first` cada perfil corre su libro sobre todas las ideas que puede tomar, como
hasta ahora (configuración de T31). Encendido:
- El libro que se muestra y se mide (capital, balance, Historial, libro fijo, diario de la
  protección) solo toma ideas decididas en tiempo real (`origin = vivo`).
- Lo reconstruido corre en un libro previo del mismo perfil, que no se muestra ni se registra: sus
  cierres (en R, con las reglas del perfil) son la opinión inicial de la memoria propia del libro
  vivo, acotada a `prior_cap` operaciones y diluida con cada cierre vivo (`eim/paper/prior.py`).
  Los perfiles que aprenden de la sombra reciben ese prior por el `Learner` (`LiveFirstLearner`).
"""

from __future__ import annotations

from eim.paper.book import ProfileState, run_profile
from eim.paper.engine import Outcome
from eim.paper.feedback import Learner
from eim.paper.ladder_book import LadderSim
from eim.paper.params import ExecParams, ProfileParams
from eim.paper.prior import Prior, is_live


def profile_books(profiles: tuple[ProfileParams, ...], by_p: dict[str, list[Outcome]],
                  learner: Learner, mmr: float, sim: LadderSim | None,
                  ep: ExecParams) -> dict[str, ProfileState]:
    if not ep.live_first:
        return {p.id: run_profile(p, by_p[p.id], learner, mmr, sim) for p in profiles}
    books = {}
    for p in profiles:
        outs = by_p[p.id]
        past = [o for o in outs if not is_live(o)]
        prior = (Prior(run_profile(p, past, learner, mmr, sim).lrisk.log)
                 if p.stop_driven and past else None)
        books[p.id] = run_profile(p, [o for o in outs if is_live(o)], learner, mmr, sim,
                                  prior=prior, prior_cap=ep.prior_cap)
    return books
