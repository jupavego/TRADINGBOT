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
from eim.paper.feedback import Judgement, Learner, context_key, judge
from eim.paper.ideas import Idea
from eim.paper.ladder_audit import audit_outcome
from eim.paper.ladder_book import LadderRisk, LadderSim, open_ladder, viability
from eim.paper.params import ProfileParams

PRIO = {"close": 0, "cancel": 1, "fill": 2, "signal": 3}
FLOOR_LABEL = {"observacion": "solo lo probado", "costo": "costo", "confianza": "confianza",
               "rr": "R:B", "sintesis": "síntesis"}
EXIT_CAT = {"TP": "tp", "SL": "sl", "SLD": "sl", "BE": "be", "TIEMPO": "tiempo"}


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
    floor: bool = False          # entró por el mínimo de operaciones abiertas
    skipped: tuple[str, ...] = ()    # filtros blandos que se saltó (se aprende de su resultado)

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
    # R de lo cerrado por el mínimo de abiertas, por filtro blando saltado: el perfil aprende
    # cuáles filtros puede seguir saltándose (pausa = saltarlo rinde claramente negativo)
    floor_r: dict[str, list[float]] = field(default_factory=dict)
    floor_states: dict[str, str] = field(default_factory=dict)
    violations: list[dict] = field(default_factory=list)   # PPP: cierres que rompen las reglas
    lrisk: LadderRisk = field(default_factory=LadderRisk)  # PPP: memoria propia y freno


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


def _open_count(st: ProfileState) -> int:
    """Operaciones abiertas: posiciones llenadas y órdenes a mercado (se llenan a la apertura)."""
    return sum(1 for s in st.slots.values() if s.filled or s.o.idea.kind == "market")


def _pending_count(st: ProfileState) -> int:
    """Órdenes de entrada pendientes: límites colocados y aún sin llenar."""
    return sum(1 for s in st.slots.values() if not s.filled and s.o.idea.kind == "limit")


def _vetoes(st: ProfileState, i: Idea, j: Judgement, jc: Judgement,
            ck: str) -> list[tuple[str, str | None]]:
    """Motivos de rechazo en orden de prioridad: (texto, clave del filtro blando o None si es
    duro). Los blandos pueden saltarse para cumplir el mínimo de operaciones abiertas, mientras
    saltarlos no rinda con expectativa claramente negativa; los duros, nunca."""
    p, out = st.p, []
    cost_r = p.est_cost_frac / ((abs(i.entry - i.sl) / i.entry) or 1e-9)
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
    if len(st.slots) >= p.max_open:
        out.append((f"cupo lleno ({p.max_open} abiertas)", None))
    if not p.allow_hedge and any(s.side != i.side for s in st.slots.values()):
        out.append(("hay una posición u orden del lado opuesto (sin cobertura)", None))
    return out


def _learned_bad(st: ProfileState, keys: tuple[str | None, ...], t: int, o: Outcome) -> bool:
    """True si algún filtro blando a saltar ya demostró (con lo cerrado hasta ahora) que saltarlo
    rinde con expectativa claramente negativa en este perfil. Registra el cambio en la bitácora."""
    bad = False
    for k in keys:
        jk = judge(st.floor_r.get(k, []), st.p.feedback)
        if st.floor_states.get(k, "observacion") != jk.state and (
                jk.state == "pausa" or st.floor_states.get(k) == "pausa"):
            _ev(st, t, "aprendizaje", o, f"saltar «{FLOOR_LABEL[k]}» para el mínimo de abiertas: "
                f"{'bloqueado' if jk.state == 'pausa' else 'reactivado'} "
                f"(expectativa {jk.m:+.2f} R con {jk.n} operaciones)", m=jk.m, n=jk.n)
        st.floor_states[k] = jk.state
        bad = bad or jk.state == "pausa"
    return bad


def _signal(st: ProfileState, o: Outcome, learner: Learner, mmr: float, q: list,
            seq: list[int], sim: LadderSim | None) -> None:
    i, p = o.idea, st.p
    if o.status == "RECHAZADA" or i.family not in p.families:
        return
    if p.symbols and i.symbol not in p.symbols:
        return
    if p.exit_mode == "ladder":      # la escalera aprende de SUS cierres, no de la sombra con TP
        j, jc = st.lrisk.own(i.sid, context_key(i), p)
    else:
        j = learner.at(i.sid, i.t, p.feedback)
        jc = learner.context_at(i, i.t, p.feedback)
    if st.states.get(i.sid, "observacion") != j.state:
        _ev(st, i.t, "aprendizaje", o, f"{st.states.get(i.sid, 'observacion')} → {j.state}",
            weight=j.weight, m=j.m, n=j.n)
        st.states[i.sid] = j.state
    ck = context_key(i)
    if (st.ctx_states.get(ck) == "pausa") != (jc.state == "pausa"):
        _ev(st, i.t, "aprendizaje", o, "contexto en pausa" if jc.state == "pausa"
            else "contexto reactivado", weight=jc.weight, m=jc.m, n=jc.n,
            context=ck.split("|", 1)[1])
    st.ctx_states[ck] = jc.state
    vetoes = _vetoes(st, i, j, jc, ck)
    floor, skipped = False, ()
    if vetoes:
        # los mínimos solo saltan vetos blandos: a mercado cubren las posiciones abiertas y a
        # límite las órdenes pendientes (sin elegir por el resultado de la idea)
        keys = tuple(k for _, k in vetoes)
        short = (_open_count(st) < p.min_open if i.kind == "market"
                 else _pending_count(st) < p.min_pending)
        if None in keys or not short or _learned_bad(st, keys, i.t, o):
            _ev(st, i.t, "rechazada", o, vetoes[0][0])
            return
        floor, skipped = True, keys
    weight = p.floor_weight if floor else j.weight
    entry = o.fill if i.kind == "market" and o.fill else i.entry
    risk_usd = st.equity * p.risk_pct * weight
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
    if sim is not None and p.exit_mode == "ladder":
        qty, o = open_ladder(p, sim, i, qty)
        if o.status == "RECHAZADA":
            _ev(st, i.t, "rechazada", o, "cantidad bajo el paso mínimo o geometría inválida")
            return
        margin, risk_usd = qty * entry / lev, qty * abs(entry - i.sl)
    st.slots[i.id] = Slot(o, qty, lev, margin, weight, risk_usd, floor=floor, skipped=skipped)
    st.used += margin
    text = "límite" if i.kind == "limit" else "a mercado"
    if floor:
        what = f"{p.min_open} abierta(s)" if i.kind == "market" else f"{p.min_pending} pendiente(s)"
        text += f" · mínimo de {what}: se omitió «{vetoes[0][0]}»"
    _ev(st, i.t, "orden", o, text, price=entry, qty=qty, leverage=lev, margin=margin, sl=i.sl,
        tp=None if p.exit_mode == "ladder" else i.tp, weight=weight, risk_usd=risk_usd,
        why=list(i.why), floor=floor)
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
    if st.p.exit_mode == "ladder" and (bad := audit_outcome(o)):
        # no es un cierre válido de la estrategia: se audita y no entra en el resultado normal
        st.violations.append({"id": o.idea.id, "t": o.exit_t, "reasons": bad})
        _ev(st, o.exit_t, "violacion", o, "cierre inválido (no contabilizado): " + "; ".join(bad))
        return
    notional = s.qty * o.fill
    pnl = float(notional * o.net)
    st.equity += pnl
    st.curve.append((o.exit_t, st.equity))
    i = o.idea
    if o.ladder and st.p.ladder and (why := st.lrisk.closed(
            i, o.r, pnl, st.equity, o.exit_t, st.p.ladder, st.p.initial_equity)):
        _ev(st, o.exit_t, "aprendizaje", o, f"freno de entradas {st.p.ladder.pause_hours:g} h: "
            f"{why} (no cierra posiciones)")
    tr = {"id": i.id, "strategy": i.strategy, "sid": i.sid, "timeframe": i.timeframe,
          "family": i.family, "side": i.side, "cause": o.cause,
          "kind": i.kind, "t": i.t, "fill_t": o.fill_t, "exit_t": o.exit_t, "fill": o.fill,
          "exit": o.exit, "sl": i.sl, "tp": None if o.ladder else i.tp, "qty": s.qty,
          "notional": notional,
          "leverage": s.leverage, "margin": s.margin, "reason": o.reason, "pnl": pnl,
          "r": o.r, "roe": pnl / s.margin if s.margin else None,
          "fees": notional * (o.fee_in + o.fee_out), "slip": notional * o.slip,
          "funding": notional * o.funding, "funding_assumed": o.funding_assumed,
          "weight": s.weight, "floor": s.floor, "skipped": list(s.skipped),
          "origin": i.origin, "regime": i.regime, "why": list(i.why),
          **({"ladder": o.ladder} if o.ladder else {})}
    st.trades.append(tr)
    if s.floor and o.r is not None:
        for k in s.skipped:
            st.floor_r.setdefault(k, []).append(o.r)
    what = (f"cierre por SL dinámico (escalón {o.ladder['level']}, "
            f"+{o.ladder['nominal_usd']:g} USDT protegidos)" if o.reason == "SLD"
            else "cierre por SL inicial" if o.ladder else f"cierre por {o.reason}")
    _ev(st, o.exit_t, EXIT_CAT[o.reason], o, what, price=o.exit, pnl=pnl,
        r=o.r, equity=st.equity, cause=o.cause)


def _cancel(st: ProfileState, o: Outcome) -> None:
    s = st.slots.pop(o.idea.id)
    st.used -= s.margin
    text = ("vence sin llenarse" if o.reason == "NO_LLENADA"
            else "el precio llegó al objetivo sin tocar la entrada")
    _ev(st, o.exit_t, "cancelada", o, text)


def run_profile(p: ProfileParams, outcomes: list[Outcome], learner: Learner,
                mmr: float, sim: LadderSim | None = None) -> ProfileState:
    if p.exit_mode == "ladder" and sim is None:
        raise ValueError(f"el perfil {p.id} (escalera) necesita el camino de precios (`sim`)")
    st = ProfileState(p=p, equity=p.initial_equity)
    seq = [0]
    q: list = [(o.idea.t, PRIO["signal"], _next(seq), "signal", o) for o in outcomes]
    heapq.heapify(q)
    if outcomes:
        st.curve.append((min(o.idea.t for o in outcomes), st.equity))
    while q:
        _t, _p, _s, kind, o = heapq.heappop(q)
        if kind == "signal":
            _signal(st, o, learner, mmr, q, seq, sim)
        elif kind == "fill":
            _fill(st, o, mmr, q, seq)
        elif kind == "close":
            _close(st, o)
        else:
            _cancel(st, o)
    return st
