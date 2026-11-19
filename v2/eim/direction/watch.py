"""Vigía de dirección (T191): control automático del acierto de la entrada. Juicio puro.

`assess` aplica las reglas pre-registradas a la boleta de un marco; `streak` cuenta revisiones
seguidas en que una sombra pasa su puerta. El servicio que corre cada 6 h vive en
`eim/api/direction_watch.py`.
"""

from __future__ import annotations

from collections.abc import Sequence

from eim.direction.params import SYNTH_ID, DirectionParams
from eim.direction.score import EDGE

OK, WATCH, ALERT, SUSTAINED, NO_VERDICT = ("ok", "vigilar", "alerta", "alerta_sostenida",
                                           "sin_veredicto")


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:.1%}"


def assess(board: dict[int, dict[str, dict]], p: DirectionParams, prev: str | None) -> dict:
    """Estado del marco: la síntesis peor que una moneda con certeza = alerta (dos seguidas =
    sostenida, ámbar en el mapa); ningún informante con ventaja = vigilar; si no, ok."""
    prim = board.get(p.primary, {})
    syn = prim.get(SYNTH_ID)
    edge = sorted(a for a, st in prim.items() if st.get("verdict") == EDGE and a != SYNTH_ID)
    judged = [a for a, st in prim.items() if st["n_eff"] >= p.min_eff_verdict and a != SYNTH_ID]
    reasons: list[str] = []
    level = 0
    if syn and syn["n_eff"] >= p.min_eff_verdict and syn["ci95"] and syn["ci95"][1] < 0.5:
        level = 2
        reasons.append(f"la síntesis v1 acierta {_pct(syn['acc_eff'])} de la dirección a "
                       f"{p.primary} velas (IC 95 % {_pct(syn['ci95'][0])}–{_pct(syn['ci95'][1])},"
                       f" n = {syn['n_eff']} sin solape): peor que una moneda")
    if not judged and not (syn and syn["n_eff"] >= p.min_eff_verdict):
        return {"state": NO_VERDICT, "level": 0, "edge": [],
                "reasons": [f"muestra insuficiente: ningún informante con {p.min_eff_verdict} "
                            "votos sin solape todavía"]}
    if edge:
        reasons.append("con ventaja medida (Holm): " + ", ".join(edge))
    else:
        level = max(level, 1)
        reasons.append(f"ningún informante tiene ventaja medida ({len(judged)} con veredicto)")
    state = (OK, WATCH, ALERT)[level]
    if level == 2 and prev in (ALERT, SUSTAINED):
        state = SUSTAINED
    return {"state": state, "level": level, "edge": edge, "reasons": reasons}


def streak(history: Sequence[dict], symbol: str, tf: str, name: str, passes: bool) -> int:
    """Revisiones seguidas (con la actual) en que la sombra `name` pasa su puerta."""
    if not passes:
        return 0
    k = 1
    for h in reversed([x for x in history if x.get("symbol") == symbol
                       and x.get("timeframe") == tf]):
        if not ((h.get("shadows") or {}).get(name) or {}).get("passes"):
            break
        k += 1
    return k


def compact(board: dict[int, dict[str, dict]], p: DirectionParams) -> dict:
    """La boleta para el historial: cifras redondeadas; el régimen solo al horizonte principal."""
    def r(x):
        return round(x, 4) if isinstance(x, float) else x
    out: dict[str, dict] = {}
    for h, agents in board.items():
        out[str(h)] = {}
        for a, st in agents.items():
            row = {k: r(st.get(k)) for k in ("n", "acc", "n_eff", "acc_eff", "p_gt", "pending",
                                             "long_share")}
            row["ci95"] = [r(x) for x in st["ci95"]] if st.get("ci95") else None
            if h == p.primary:
                row.update(verdict=st.get("verdict"), p_holm=r(st.get("p_holm")),
                           by_regime={g: {k: r(v) for k, v in d.items()}
                                      for g, d in st["by_regime"].items()})
            out[str(h)][a] = row
    return out
