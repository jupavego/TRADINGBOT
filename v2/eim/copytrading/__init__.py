"""Copy trading (T41): evaluación de líderes, puro (sin red ni disco). I/O en `eim/data/`.

`trades` (viajes de plano a plano) → `metrics` (muestra) + `portfolio` (cartera larga) +
`copyability` (lo que obtiene un seguidor) → `scorecard` (reglas y veredicto) → `board`.
"""

from eim.copytrading.board import LABEL, Board, build_board
from eim.copytrading.params import ScoreParams
from eim.copytrading.scorecard import LeaderData, Reason, Scorecard, score

__all__ = ["LABEL", "Board", "LeaderData", "Reason", "ScoreParams", "Scorecard", "build_board",
           "score"]
