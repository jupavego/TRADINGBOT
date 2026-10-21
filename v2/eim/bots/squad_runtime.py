"""Cableado del escuadrón en el proceso de la API (T60): puntuación + cuarentena → política vigente.

`refresh()` lee la última tabla de T59 y la cuarentena, arma la `SquadPolicy` y la publica con
`set_policy`; se llama al arrancar, tras cada puntuación y cada cambio de cuarentena. Un fallo
nunca tumba el ciclo: se conserva la política anterior y se deja el error a la vista.
"""

from __future__ import annotations

import logging

from eim.bots.quarantine import Quarantine
from eim.bots.scorer import BotScorer
from eim.synthesis.squad import SquadPolicy, current_policy, policy_from_scorecard, set_policy

log = logging.getLogger("eim.bots")


class SquadRuntime:
    def __init__(self, scorer: BotScorer, quarantine: Quarantine | None,
                 symbol: str = "BTCUSDT") -> None:
        self.scorer, self.quarantine, self.symbol = scorer, quarantine, symbol
        self.error = ""
        scorer.on_scored.append(lambda _out: self.refresh())
        if quarantine is not None:
            quarantine.on_change.append(self.refresh)

    def policy(self) -> SquadPolicy | None:
        return current_policy()

    def refresh(self) -> None:
        try:
            sc = self.scorer.scores.latest(self.symbol, self.scorer.crit.version)
            q = self.quarantine.keys() if self.quarantine is not None else ()
            set_policy(policy_from_scorecard(sc, self.scorer.cards, q))
            self.error = ""
        except Exception as exc:  # noqa: BLE001 - conserva la política previa
            self.error = f"{type(exc).__name__}: {exc}"
            log.warning("política del escuadrón: %s", self.error)
