"""Motivos por los que un perfil NO toma una idea (función pura sobre su estado).

Devuelve vetos (texto, clave del filtro blando o None si es duro, código) en orden de prioridad:
los blandos pueden saltarse para cumplir el mínimo de operaciones abiertas mientras saltarlos no
rinda con expectativa claramente negativa; los duros, nunca. Nada de esto cierra posiciones: solo
frena entradas nuevas.

El código (T118) es la identidad estable del motivo: el texto es para personas y el código separa,
sin leer el texto, la cuenta agotada o sin capital del tope de riesgo por dirección y del freno por
drawdown. Viaja en el evento `rechazada` y se cuenta por perfil (`rejections` del resumen).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from eim.paper.account import Capital, capital, exhausted
from eim.paper.feedback import Judgement
from eim.paper.ideas import Idea
from eim.paper.ladder_book import viability

if TYPE_CHECKING:
    from eim.paper.book import ProfileState

# motivos que dependen del capital de la cuenta (nunca se etiquetan como tope ni como freno)
CAPITAL_CODES = frozenset({"cuenta_agotada", "capital_insuficiente"})


class Veto(NamedTuple):
    text: str
    soft: str | None          # clave del filtro blando (se puede saltar por el mínimo) o None
    code: str


def vetoes(st: ProfileState, i: Idea, j: Judgement, jc: Judgement, ck: str,
           cap: Capital | None = None) -> list[Veto]:
    p, out = st.p, []
    eq = (cap or capital(st)).balance      # la misma lectura con la que la política dimensiona
    cost_r = p.est_cost_frac / ((abs(i.entry - i.sl) / i.entry) or 1e-9)
    if st.exhausted_t is not None or exhausted(p, eq):   # nadie recarga: la cuenta no vuelve
        out.append(Veto(exhausted(p, eq) or "cuenta agotada: no se abren posiciones nuevas "
                        f"(capital realizado {eq:.2f} USDT)", None, "cuenta_agotada"))
    if j.state == "pausa":
        out.append(Veto(f"estrategia en pausa: expectativa {j.m:+.2f} R con {j.n} operaciones",
                        None, "pausa_estrategia"))
    if jc.state == "pausa":
        reg, lado = ck.split("|")[1:]
        out.append(Veto(f"contexto en pausa ({reg}, {lado}): expectativa {jc.m:+.2f} R con "
                        f"{jc.n} operaciones en ese contexto", None, "pausa_contexto"))
    if j.state == "observacion" and p.feedback.observe_w <= 0:
        out.append(Veto(f"en observación: el perfil solo opera lo probado ({j.n}/"
                        f"{p.feedback.n_min} ops)", "observacion", "observacion"))
    if cost_r > p.max_cost_r:
        out.append(Veto(f"costo estimado {cost_r:.2f} R > {p.max_cost_r:.2f} R: el SL está "
                        "demasiado cerca para lo que cuesta operar",
                        "costo" if cost_r <= p.floor_max_cost_r else None, "costo"))
    if p.require_htf and i.htf < 0:
        out.append(Veto("contra la tendencia del marco mayor", None, "contra_tendencia"))
    if i.conf < p.min_conf:
        out.append(Veto(f"confianza {i.conf:.0%} < {p.min_conf:.0%}", "confianza", "confianza"))
    if i.rr < p.min_rr:
        out.append(Veto(f"R:B {i.rr:.2f} < {p.min_rr:.2f}", "rr" if i.rr >= p.floor_min_rr
                        else None, "rr"))
    if p.follow_synthesis and (i.syn_bias * i.side <= 0 or abs(i.syn_bias) < p.min_syn_bias):
        out.append(Veto(f"va contra la síntesis ({i.syn_bias:+.2f}) o esta es débil", "sintesis",
                        "sintesis"))
    if p.exit_mode == "ladder" and (why := viability(p, i, eq)):
        out.append(Veto(why, None, "viabilidad"))
    elif p.exit_mode == "ladder" and (why := st.lrisk.veto(i.t)):     # un solo veto, como antes
        out.append(Veto(why, None, "freno_escalera"))
    if p.exit_mode == "ladder" and p.ladder.one_per_bar and any(
            x.o.idea.t == i.t and x.side == i.side for x in st.slots.values()):
        out.append(Veto("posición duplicada: ya hay una del mismo lado decidida en esta vela",
                        None, "duplicada"))
    if why := st.brake.veto(i.t):
        out.append(Veto(why, None, "freno_drawdown"))
    if len(st.slots) >= p.max_open:
        out.append(Veto(f"cupo lleno ({p.max_open} abiertas)", None, "cupo"))
    if not p.allow_hedge and any(s.side != i.side for s in st.slots.values()):
        out.append(Veto("hay una posición u orden del lado opuesto (sin cobertura)", None,
                        "cobertura"))
    return out
