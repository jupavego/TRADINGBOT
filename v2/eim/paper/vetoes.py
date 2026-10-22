"""Motivos por los que un perfil NO toma una idea (función pura sobre su estado).

Devuelve pares (texto, clave del filtro blando o None si es duro) en orden de prioridad: los
blandos pueden saltarse para cumplir el mínimo de operaciones abiertas mientras saltarlos no rinda
con expectativa claramente negativa; los duros, nunca. Nada de esto cierra posiciones: solo frena
entradas nuevas.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from eim.paper.account import exhausted
from eim.paper.feedback import Judgement
from eim.paper.ideas import Idea
from eim.paper.ladder_book import viability

if TYPE_CHECKING:
    from eim.paper.book import ProfileState


def vetoes(st: ProfileState, i: Idea, j: Judgement, jc: Judgement,
           ck: str) -> list[tuple[str, str | None]]:
    p, out = st.p, []
    cost_r = p.est_cost_frac / ((abs(i.entry - i.sl) / i.entry) or 1e-9)
    if st.exhausted_t is not None:    # la cuenta agotada no vuelve: nadie recarga capital
        out.append((exhausted(p, st.equity) or "cuenta agotada: no se abren posiciones nuevas "
                    f"(capital realizado {st.equity:.2f} USDT)", None))
    if j.state == "pausa":
        out.append((f"estrategia en pausa: expectativa {j.m:+.2f} R con {j.n} operaciones", None))
    if jc.state == "pausa":
        reg, lado = ck.split("|")[1:]
        out.append((f"contexto en pausa ({reg}, {lado}): expectativa {jc.m:+.2f} R con {jc.n} "
                    "operaciones en ese contexto", None))
    if j.state == "observacion" and p.feedback.observe_w <= 0:
        out.append((f"en observación: el perfil solo opera lo probado ({j.n}/{p.feedback.n_min}"
                    " ops)", "observacion"))
    if cost_r > p.max_cost_r:
        out.append((f"costo estimado {cost_r:.2f} R > {p.max_cost_r:.2f} R: el SL está "
                    "demasiado cerca para lo que cuesta operar",
                    "costo" if cost_r <= p.floor_max_cost_r else None))
    if p.require_htf and i.htf < 0:
        out.append(("contra la tendencia del marco mayor", None))
    if i.conf < p.min_conf:
        out.append((f"confianza {i.conf:.0%} < {p.min_conf:.0%}", "confianza"))
    if i.rr < p.min_rr:
        out.append((f"R:B {i.rr:.2f} < {p.min_rr:.2f}", "rr" if i.rr >= p.floor_min_rr else None))
    if p.follow_synthesis and (i.syn_bias * i.side <= 0 or abs(i.syn_bias) < p.min_syn_bias):
        out.append((f"va contra la síntesis ({i.syn_bias:+.2f}) o esta es débil", "sintesis"))
    if p.exit_mode == "ladder" and (why := viability(p, i, st.equity) or st.lrisk.veto(i.t)):
        out.append((why, None))
    if p.exit_mode == "ladder" and any(
            x.o.idea.t == i.t and x.side == i.side for x in st.slots.values()):
        out.append(("posición duplicada: ya hay una del mismo lado decidida en esta vela", None))
    if why := st.brake.veto(i.t):
        out.append((why, None))
    if len(st.slots) >= p.max_open:
        out.append((f"cupo lleno ({p.max_open} abiertas)", None))
    if not p.allow_hedge and any(s.side != i.side for s in st.slots.values()):
        out.append(("hay una posición u orden del lado opuesto (sin cobertura)", None))
    return out
