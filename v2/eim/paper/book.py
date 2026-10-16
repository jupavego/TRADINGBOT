"""Libro de un perfil: toma (o rechaza) las ideas sombra, dimensiona en USDT y lleva la cuenta.

Orden de eventos por tiempo: cierres → cancelaciones → llenados → señales. El tamaño usa el
capital REALIZADO en el instante de la señal y el peso de la retroalimentación con lo cerrado
hasta entonces (por estrategia@marco y, desde T48, por contexto: un contexto que pierde de forma
consistente se pausa). Margen aislado; apalancamiento entero tal que la liquidación quede a ≥
`liq_buffer` veces la distancia del SL. Siempre SIMULADO.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from eim.paper.engine import Outcome
from eim.paper.feedback import Learner, context_key
from eim.paper.params import ProfileParams

PRIO = {"close": 0, "cancel": 1, "fill": 2, "signal": 3}
EXIT_CAT = {"TP": "tp", "SL": "sl", "BE": "be", "TIEMPO": "tiempo"}


@dataclass
class Slot:
    """Orden pendiente o posición abierta del perfil."""

    o: Outcome
    qty: float
    leverage: int
    margin: float
    weight: float
    risk_usd: float
    filled: bool = False

    @property
    def side(self) -> int:
        return self.o.idea.side


@dataclass
class ProfileState:
    p: ProfileParams
    equity: float
    used: float = 0.0
    slots: dict[str, Slot] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    curve: list[tuple[int, float]] = field(default_factory=list)
    states: dict[str, str] = field(default_factory=dict)
    ctx_states: dict[str, str] = field(default_factory=dict)


def _ev(st: ProfileState, t: int, cat: str, o: Outcome, text: str, **kw) -> None:
    i = o.idea
    st.events.append({"t": t, "cat": cat, "profile": st.p.id, "strategy": i.strategy,
                      "sid": i.sid, "timeframe": i.timeframe,
                      "family": i.family, "idea": i.id, "side": i.side, "kind": i.kind,
                      "text": text, "origin": i.origin, **kw})


def leverage_for(p: ProfileParams, entry: float, sl: float, mmr: float) -> int:
    dist = abs(entry - sl) / entry
    return max(1, min(p.max_leverage, math.floor(1 / (p.liq_buffer * dist + mmr))))


def liq_price(side: int, entry: float, lev: int, mmr: float) -> float:
    return entry * (1 - side * (1 / lev - mmr))


def _signal(st: ProfileState, o: Outcome, learner: Learner, mmr: float, q: list,
            seq: list[int]) -> None:
    i, p = o.idea, st.p
    if o.status == "RECHAZADA" or i.family not in p.families:
        return
    j = learner.at(i.sid, i.t, p.feedback)
    if st.states.get(i.sid, "observacion") != j.state:
        _ev(st, i.t, "aprendizaje", o, f"{st.states.get(i.sid, 'observacion')} → {j.state}",
            weight=j.weight, m=j.m, n=j.n)
        st.states[i.sid] = j.state
    jc = learner.context_at(i, i.t, p.feedback)
    ck = context_key(i)
    if (st.ctx_states.get(ck) == "pausa") != (jc.state == "pausa"):
        _ev(st, i.t, "aprendizaje", o, "contexto en pausa" if jc.state == "pausa"
            else "contexto reactivado", weight=jc.weight, m=jc.m, n=jc.n,
            context=ck.split("|", 1)[1])
    st.ctx_states[ck] = jc.state
    why = ""
    if j.state == "pausa":
        why = f"estrategia en pausa: expectativa {j.m:+.2f} R con {j.n} operaciones"
    elif jc.state == "pausa":
        reg, lado = ck.split("|")[1:]
        why = (f"contexto en pausa ({reg}, {lado}): expectativa {jc.m:+.2f} R con {jc.n} "
               "operaciones en ese contexto")
    elif j.state == "observacion" and p.feedback.observe_w <= 0:
        why = f"en observación: el perfil solo opera lo probado ({j.n}/{p.feedback.n_min} ops)"
    elif p.est_cost_frac / (abs(i.entry - i.sl) / i.entry) > p.max_cost_r:
        why = (f"costo estimado {p.est_cost_frac / (abs(i.entry - i.sl) / i.entry):.2f} R > "
               f"{p.max_cost_r:.2f} R: el SL está demasiado cerca para lo que cuesta operar")
    elif p.require_htf and i.htf < 0:
        why = "contra la tendencia del marco mayor"
    elif i.conf < p.min_conf:
        why = f"confianza {i.conf:.0%} < {p.min_conf:.0%}"
    elif i.rr < p.min_rr:
        why = f"R:B {i.rr:.2f} < {p.min_rr:.2f}"
    elif p.follow_synthesis and (i.syn_bias * i.side <= 0 or abs(i.syn_bias) < p.min_syn_bias):
        why = f"va contra la síntesis ({i.syn_bias:+.2f}) o esta es débil"
    elif len(st.slots) >= p.max_open:
        why = f"cupo lleno ({p.max_open} abiertas)"
    elif not p.allow_hedge and any(s.side != i.side for s in st.slots.values()):
        why = "hay una posición u orden del lado opuesto (sin cobertura)"
    if why:
        _ev(st, i.t, "rechazada", o, why)
        return
    entry = o.fill if i.kind == "market" and o.fill else i.entry
    risk_usd = st.equity * p.risk_pct * j.weight
    qty = risk_usd / abs(entry - i.sl)
    lev = leverage_for(p, entry, i.sl, mmr)
    margin = qty * entry / lev
    free = st.equity - st.used
    if margin > free:
        scale = max(0.0, free * 0.98 / margin)
        if scale < p.min_risk_fill:
            _ev(st, i.t, "rechazada", o, f"margen insuficiente (libre {free:.2f} USDT)")
            return
        qty, margin, risk_usd = qty * scale, margin * scale, risk_usd * scale
    st.slots[i.id] = Slot(o, qty, lev, margin, j.weight, risk_usd)
    st.used += margin
    _ev(st, i.t, "orden", o, "límite" if i.kind == "limit" else "a mercado", price=entry,
        qty=qty, leverage=lev, margin=margin, sl=i.sl, tp=i.tp, weight=j.weight,
        risk_usd=risk_usd, why=list(i.why))
    if o.fill_t is not None:
        heapq.heappush(q, (o.fill_t, PRIO["fill"], _next(seq), "fill", o))
    elif o.status == "CANCELADA":
        heapq.heappush(q, (o.exit_t, PRIO["cancel"], _next(seq), "cancel", o))


def _next(seq: list[int]) -> int:
    seq[0] += 1
    return seq[0]


def _fill(st: ProfileState, o: Outcome, mmr: float, q: list, seq: list[int]) -> None:
    s = st.slots[o.idea.id]
    s.filled = True
    _ev(st, o.fill_t, "llenada", o, "posición abierta", price=o.fill, qty=s.qty,
        leverage=s.leverage, liq=liq_price(o.idea.side, o.fill, s.leverage, mmr))
    if o.status == "CERRADA":
        heapq.heappush(q, (o.exit_t, PRIO["close"], _next(seq), "close", o))


def _close(st: ProfileState, o: Outcome) -> None:
    s = st.slots.pop(o.idea.id)
    st.used -= s.margin
    notional = s.qty * o.fill
    pnl = float(notional * o.net)
    st.equity += pnl
    st.curve.append((o.exit_t, st.equity))
    i = o.idea
    tr = {"id": i.id, "strategy": i.strategy, "sid": i.sid, "timeframe": i.timeframe,
          "family": i.family, "side": i.side, "cause": o.cause,
          "kind": i.kind, "t": i.t, "fill_t": o.fill_t, "exit_t": o.exit_t, "fill": o.fill,
          "exit": o.exit, "sl": i.sl, "tp": i.tp, "qty": s.qty, "notional": notional,
          "leverage": s.leverage, "margin": s.margin, "reason": o.reason, "pnl": pnl,
          "r": o.r, "roe": pnl / s.margin if s.margin else None,
          "fees": notional * (o.fee_in + o.fee_out), "slip": notional * o.slip,
          "funding": notional * o.funding, "funding_assumed": o.funding_assumed,
          "weight": s.weight, "origin": i.origin, "regime": i.regime, "why": list(i.why)}
    st.trades.append(tr)
    _ev(st, o.exit_t, EXIT_CAT[o.reason], o, f"cierre por {o.reason}", price=o.exit, pnl=pnl,
        r=o.r, equity=st.equity, cause=o.cause)


def _cancel(st: ProfileState, o: Outcome) -> None:
    s = st.slots.pop(o.idea.id)
    st.used -= s.margin
    text = ("vence sin llenarse" if o.reason == "NO_LLENADA"
            else "el precio llegó al objetivo sin tocar la entrada")
    _ev(st, o.exit_t, "cancelada", o, text)


def run_profile(p: ProfileParams, outcomes: list[Outcome], learner: Learner,
                mmr: float) -> ProfileState:
    st = ProfileState(p=p, equity=p.initial_equity)
    seq = [0]
    q: list = [(o.idea.t, PRIO["signal"], _next(seq), "signal", o) for o in outcomes]
    heapq.heapify(q)
    if outcomes:
        st.curve.append((min(o.idea.t for o in outcomes), st.equity))
    while q:
        _t, _p, _s, kind, o = heapq.heappop(q)
        if kind == "signal":
            _signal(st, o, learner, mmr, q, seq)
        elif kind == "fill":
            _fill(st, o, mmr, q, seq)
        elif kind == "close":
            _close(st, o)
        else:
            _cancel(st, o)
    return st
