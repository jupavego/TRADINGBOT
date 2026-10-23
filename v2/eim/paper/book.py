"""Libro de un perfil: toma (o rechaza) las ideas sombra, dimensiona en USDT y lleva la cuenta.

Orden de eventos por tiempo: cierres → cancelaciones → llenados → señales. El tamaño usa el
capital REALIZADO en el instante de la señal y el peso de la retroalimentación con lo cerrado
hasta entonces (por estrategia@marco y, desde T48, por contexto: un contexto que pierde de forma
consistente se pausa). Margen aislado; apalancamiento entero tal que la liquidación quede a ≥
`liq_buffer` veces la distancia del SL. La contabilidad (liquidación, suelo del capital y cuenta
agotada) está en `account.py` y los motivos de rechazo en `vetoes.py`. Siempre SIMULADO.

Con salida por escalera (los cuatro perfiles desde T109) solo cierran el stop inicial, el stop
dinámico, la liquidación y una salvaguarda independiente (`ladder_audit.ALLOWED_CLOSE`); cualquier
otro cierre se registra como violación y NO se ejecuta. Una señal contraria a una posición abierta
solo informa: queda anotada en el evento de esa señal (`against`) y contada en el resumen.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field, replace

from eim.paper.account import LIQ, capped, exhausted, leverage_for, liq_price
from eim.paper.book_events import ev, learned_bad
from eim.paper.caps import Brake, fit_risk
from eim.paper.engine import Outcome
from eim.paper.feedback import Learner, context_key
from eim.paper.ladder_audit import SAFEGUARD, audit_outcome, check_close_request
from eim.paper.ladder_book import LadderRisk, LadderSim, open_ladder
from eim.paper.params import ProfileParams
from eim.paper.vetoes import vetoes

PRIO = {"close": 0, "cancel": 1, "fill": 2, "signal": 3}
EXIT_CAT = {"TP": "tp", "SL": "sl", "SLD": "sl", "BE": "be", "TIEMPO": "tiempo",
            LIQ: "liquidacion", SAFEGUARD: "salvaguarda"}


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
    liq: float | None = None     # precio de liquidación (se conoce al llenar)
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
    contrary: int = 0          # señales contrarias a una posición abierta (solo informan, T109)
    lrisk: LadderRisk = field(default_factory=LadderRisk)  # PPP: memoria propia y freno
    brake: Brake = field(default_factory=Brake)            # freno por drawdown (caps)
    exhausted_t: int | None = None     # cuándo se agotó la cuenta (deja de abrir; no se recarga)


def _open_count(st: ProfileState) -> int:
    """Operaciones abiertas: posiciones llenadas y órdenes a mercado (se llenan a la apertura)."""
    return sum(1 for s in st.slots.values() if s.filled or s.o.idea.kind == "market")


def _pending_count(st: ProfileState) -> int:
    """Órdenes de entrada pendientes: límites colocados y aún sin llenar."""
    return sum(1 for s in st.slots.values() if not s.filled and s.o.idea.kind == "limit")


def _signal(st: ProfileState, o: Outcome, learner: Learner, mmr: float, q: list,
            seq: list[int], sim: LadderSim | None) -> None:
    i, p = o.idea, st.p
    if o.status == "RECHAZADA" or i.family not in p.families:
        return
    if p.symbols and i.symbol not in p.symbols:
        return
    # señal contraria a posiciones abiertas: en la escalera solo informa (nadie cierra por ella)
    against = ([x.o.idea.id for x in st.slots.values() if x.filled and x.side != i.side]
               if p.exit_mode == "ladder" else [])
    tag = {"against": against} if against else {}
    st.contrary += bool(against)
    if p.exit_mode == "ladder":      # la escalera aprende de SUS cierres, no de la sombra con TP
        j, jc = st.lrisk.own(i.sid, context_key(i), p)
    else:
        j = learner.at(i.sid, i.t, p.feedback)
        jc = learner.context_at(i, i.t, p.feedback)
    if st.states.get(i.sid, "observacion") != j.state:
        ev(st, i.t, "aprendizaje", o, f"{st.states.get(i.sid, 'observacion')} → {j.state}",
            weight=j.weight, m=j.m, n=j.n)
        st.states[i.sid] = j.state
    ck = context_key(i)
    if (st.ctx_states.get(ck) == "pausa") != (jc.state == "pausa"):
        ev(st, i.t, "aprendizaje", o, "contexto en pausa" if jc.state == "pausa"
            else "contexto reactivado", weight=jc.weight, m=jc.m, n=jc.n,
            context=ck.split("|", 1)[1])
    st.ctx_states[ck] = jc.state
    vs = vetoes(st, i, j, jc, ck)
    floor, skipped = False, ()
    if vs:
        # los mínimos solo saltan vetos blandos: a mercado cubren las posiciones abiertas y a
        # límite las órdenes pendientes (sin elegir por el resultado de la idea)
        keys = tuple(k for _, k in vs)
        short = (_open_count(st) < p.min_open if i.kind == "market"
                 else _pending_count(st) < p.min_pending)
        if None in keys or not short or learned_bad(st, keys, i.t, o):
            ev(st, i.t, "rechazada", o, vs[0][0], **tag)
            return
        floor, skipped = True, keys
    weight = p.floor_weight if floor else j.weight
    entry = o.fill if i.kind == "market" and o.fill else i.entry
    want = st.equity * p.risk_pct * weight
    risk_usd = fit_risk(p.caps, st.equity, sum(x.risk_usd for x in st.slots.values()
                                              if x.side == i.side), want)
    if risk_usd <= 0:
        ev(st, i.t, "rechazada", o, f"capital insuficiente: {st.equity:.2f} USDT realizados"
           if want <= 0 else
           f"tope de riesgo abierto por dirección ({p.caps.max_dir_risk:.1%})", **tag)
        return
    qty = risk_usd / abs(entry - i.sl)
    lev = leverage_for(p, entry, i.sl, mmr)
    margin = qty * entry / lev
    free = st.equity - st.used
    if margin > free:
        scale = max(0.0, free * 0.98 / margin)
        if scale < p.min_risk_fill:
            ev(st, i.t, "rechazada", o, f"margen insuficiente (libre {free:.2f} USDT)", **tag)
            return
        qty, margin, risk_usd = qty * scale, margin * scale, risk_usd * scale
    if sim is not None and p.exit_mode == "ladder":
        qty, o = open_ladder(p, sim, i, qty)
        if o.status == "RECHAZADA":
            ev(st, i.t, "rechazada", o, "cantidad bajo el paso mínimo o geometría inválida",
               **tag)
            return
        margin, risk_usd = qty * entry / lev, qty * abs(entry - i.sl)
    st.slots[i.id] = Slot(o, qty, lev, margin, weight, risk_usd, floor=floor, skipped=skipped)
    st.used += margin
    text = "límite" if i.kind == "limit" else "a mercado"
    if floor:
        what = f"{p.min_open} abierta(s)" if i.kind == "market" else f"{p.min_pending} pendiente(s)"
        text += f" · mínimo de {what}: se omitió «{vs[0][0]}»"
    ev(st, i.t, "orden", o, text, price=entry, qty=qty, leverage=lev, margin=margin, sl=i.sl,
        tp=None if p.exit_mode == "ladder" else i.tp, weight=weight, risk_usd=risk_usd,
        why=list(i.why), floor=floor, **tag)
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
    s.liq = liq_price(o.idea.side, o.fill, s.leverage, mmr)
    ev(st, o.fill_t, "llenada", o, "posición abierta", price=o.fill, qty=s.qty,
        leverage=s.leverage, liq=s.liq)
    if o.status == "CERRADA":
        heapq.heappush(q, (o.exit_t, PRIO["close"], _next(seq), "close", o))


def _reject(st: ProfileState, o: Outcome, why: str) -> None:
    """Cierre que no es del stop, ni liquidación, ni salvaguarda (T109): NO se ejecuta. Queda como
    violación y la posición sigue abierta con su stop vigente; el capital y el margen no se mueven
    (así tampoco desaparece dinero, T106 A5)."""
    s = st.slots[o.idea.id]
    s.o = replace(o, status="ABIERTA", reason="", exit_t=None, exit=None,
                  ladder=o.ladder and {**o.ladder, "rejected_close": why})
    st.violations.append({"id": o.idea.id, "t": o.exit_t, "reasons": [why], "executed": False})
    ev(st, o.exit_t, "violacion", o, f"cierre rechazado, no se ejecuta: {why}; la posición sigue "
       "abierta con su stop vigente", reason=o.reason)


def _close(st: ProfileState, o: Outcome) -> None:
    if st.p.exit_mode == "ladder" and (why := check_close_request(o.reason)):
        _reject(st, o, why)
        return
    s = st.slots.pop(o.idea.id)
    st.used -= s.margin
    bad = audit_outcome(o) if st.p.exit_mode == "ladder" else []
    if bad:
        # cierre por el stop con un historial anómalo: el precio tocó el stop, así que se ejecuta
        # y el dinero SÍ se contabiliza (descartarlo lo hacía desaparecer, T106 A5), auditado aparte
        st.violations.append({"id": o.idea.id, "t": o.exit_t, "reasons": bad, "executed": True})
        ev(st, o.exit_t, "violacion", o, "cierre inválido (se contabiliza, se audita): "
           + "; ".join(bad))
    notional = s.qty * o.fill
    pnl, liq_why = capped(float(notional * o.net), s.margin, o.idea.side, o.exit, s.liq)
    reason = LIQ if liq_why else o.reason
    r = pnl / s.risk_usd if liq_why and s.risk_usd else o.r
    st.equity += pnl
    st.curve.append((o.exit_t, st.equity))
    i = o.idea
    if st.exhausted_t is None and (why := exhausted(st.p, st.equity)):
        st.exhausted_t = o.exit_t
        ev(st, o.exit_t, "cuenta", o, why, equity=st.equity)
    if why := st.brake.closed(st.p.caps, st.equity, st.p.initial_equity, o.exit_t):
        ev(st, o.exit_t, "aprendizaje", o,
           f"freno de entradas {st.p.caps.dd_pause_hours:g} h: {why}")
    if o.ladder and st.p.ladder and (why := st.lrisk.closed(
            i, r, pnl, st.equity, o.exit_t, st.p.ladder, st.p.initial_equity)):
        ev(st, o.exit_t, "aprendizaje", o, f"freno de entradas {st.p.ladder.pause_hours:g} h: "
            f"{why} (no cierra posiciones)")
    tr = {"id": i.id, "strategy": i.strategy, "sid": i.sid, "timeframe": i.timeframe,
          "family": i.family, "side": i.side, "cause": o.cause,
          "kind": i.kind, "t": i.t, "fill_t": o.fill_t, "exit_t": o.exit_t, "fill": o.fill,
          "exit": o.exit, "sl": i.sl, "tp": None if o.ladder else i.tp, "qty": s.qty,
          "notional": notional,
          "leverage": s.leverage, "margin": s.margin, "reason": reason, "pnl": pnl,
          "r": r, "roe": pnl / s.margin if s.margin else None,
          "fees": notional * (o.fee_in + o.fee_out), "slip": notional * o.slip,
          "funding": notional * o.funding, "funding_assumed": o.funding_assumed,
          "weight": s.weight, "floor": s.floor, "skipped": list(s.skipped),
          "origin": i.origin, "regime": i.regime, "why": list(i.why),
          # trazabilidad de la liquidación: lo que el camino dio y lo que la cuenta pudo perder
          **({"liq": s.liq, "pnl_path": float(notional * o.net), "liq_why": liq_why,
              "reason_path": o.reason} if liq_why else {}),
          **({"violation": bad} if bad else {}),
          **({"ladder": o.ladder} if o.ladder else {})}
    st.trades.append(tr)
    if s.floor and r is not None:
        for k in s.skipped:
            st.floor_r.setdefault(k, []).append(r)
    what = (f"liquidada a {s.liq:g}: {liq_why}; se pierde el margen ({s.margin:.2f} USDT)"
            if liq_why else _exit_text(o))
    ev(st, o.exit_t, EXIT_CAT[reason], o, what, price=s.liq if liq_why else o.exit, pnl=pnl,
        r=r, equity=st.equity, cause=o.cause, reason=reason,      # motivo exacto (panel, T112)
        **({"liq": s.liq} if liq_why else {}))


def _exit_text(o: Outcome) -> str:
    lad = o.ladder
    if o.reason == "SLD" and lad.get("stop_source") in ("be", "recuperado"):
        what = "BE+" if lad["stop_source"] == "be" else "SL recuperado del diario"
        return (f"cierre por SL dinámico ({what}, nivel protegido "
                f"{lad['protected_est_usd']:.2f} USDT estimado)")
    if o.reason == "SLD":       # el nivel es del stop, estimado: lo realizado puede diferir
        return (f"cierre por SL dinámico (escalón {lad['level']}, nivel protegido "
                f"{lad['nominal_usd']:.2f} USDT estimado)")
    if o.reason == SAFEGUARD:
        return "cierre ordenado por una salvaguarda independiente (kill-switch)"
    return "cierre por SL inicial" if lad else f"cierre por {o.reason}"


def _cancel(st: ProfileState, o: Outcome) -> None:
    s = st.slots.pop(o.idea.id)
    st.used -= s.margin
    text = ("vence sin llenarse" if o.reason == "NO_LLENADA"
            else "el precio llegó al objetivo sin tocar la entrada")
    ev(st, o.exit_t, "cancelada", o, text)


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
