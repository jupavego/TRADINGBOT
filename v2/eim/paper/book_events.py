"""Bitácora del libro y aprendizaje de los filtros blandos saltados por el mínimo de abiertas."""

from __future__ import annotations

from eim.paper.engine import Outcome
from eim.paper.feedback import judge

FLOOR_LABEL = {"observacion": "solo lo probado", "costo": "costo", "confianza": "confianza",
               "rr": "R:B", "sintesis": "síntesis"}


def ev(st, t: int, cat: str, o: Outcome, text: str, **kw) -> None:
    i = o.idea
    st.events.append({"t": t, "cat": cat, "profile": st.p.id, "strategy": i.strategy,
                      "sid": i.sid, "timeframe": i.timeframe,
                      "family": i.family, "idea": i.id, "side": i.side, "kind": i.kind,
                      "text": text, "origin": i.origin, **kw})


def learned_bad(st, keys: tuple[str | None, ...], t: int, o: Outcome) -> bool:
    """True si algún filtro blando a saltar ya demostró (con lo cerrado hasta ahora) que saltarlo
    rinde con expectativa claramente negativa en este perfil. Registra el cambio en la bitácora."""
    bad = False
    for k in keys:
        jk = judge(st.floor_r.get(k, []), st.p.feedback)
        if st.floor_states.get(k, "observacion") != jk.state and (
                jk.state == "pausa" or st.floor_states.get(k) == "pausa"):
            ev(st, t, "aprendizaje", o, f"saltar «{FLOOR_LABEL[k]}» para el mínimo de abiertas: "
               f"{'bloqueado' if jk.state == 'pausa' else 'reactivado'} "
               f"(expectativa {jk.m:+.2f} R con {jk.n} operaciones)", m=jk.m, n=jk.n)
        st.floor_states[k] = jk.state
        bad = bad or jk.state == "pausa"
    return bad
