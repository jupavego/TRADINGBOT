"""Libro de la cantera (T168, entregable 4): cuentas propias, gemelos pareados y puerta de costo.

Puro: recibe contextos, el camino de 15 m con su funding y los prospectos, y devuelve el libro. Se
recalcula entero en cada ciclo (determinista: mismos datos, mismo libro).

- **Una cuenta por prospecto y por control**, con el mismo capital inicial; cada operación arriesga
  el `risk_pct` de su saldo realizado, costos incluidos (`risk_budget.qty_for_risk`), con el tope
  de apalancamiento del perfil Moderado. Una posición a la vez y una vela de espera al cerrar.
- **Gemelos aleatorios pareados** (rec. 1): por cada operación cerrada, `twins_k` entradas de lado
  al azar en la misma vela, con la misma plantilla y los mismos costos, saliendo como mucho cuando
  sale la real. El lado sale de una semilla fija por (cuenta, vela), sin mirar precios. Como solo
  hay dos lados posibles, basta simular el largo y el corto una vez y ponderar por cuántos gemelos
  sacó cada uno. Se guarda `d = R real − media de los gemelos`.
- **Puerta de costo por marco** (`AUTO_ADAPT`, `paper/tf_gate.py`): el costo medio en R de lo
  cerrado **hasta ese instante** en el marco, con todas las cuentas (prospectos y controles); con
  el marco cerrado nadie abre en él y lo que la regla pide se simula como sombra (sigue midiendo el
  costo, así que el marco vuelve solo). Cada cambio de estado es un evento del libro.
"""

from __future__ import annotations

import hashlib
import heapq
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from eim.data.timeframes import tf_ms
from eim.nursery.params import NurseryParams
from eim.nursery.prospect import Prospect
from eim.nursery.signals import Account, accounts_for, build_order, signals
from eim.nursery.sim import Order, Trade, funding_step, simulate
from eim.paper import risk_budget, tf_gate
from eim.paper.engine import Path


@dataclass(frozen=True)
class Twins:
    k: int
    n_long: int
    r_long: float
    r_short: float

    @property
    def mean_r(self) -> float:
        return (self.n_long * self.r_long + (self.k - self.n_long) * self.r_short) / self.k

    @property
    def sd_r(self) -> float:
        m, p = self.mean_r, self.n_long / self.k
        return float(np.sqrt(p * (self.r_long - m) ** 2 + (1 - p) * (self.r_short - m) ** 2))


@dataclass(frozen=True)
class Entry:
    account: str
    kind: str
    timeframe: str
    t: int
    side: int
    order: Order
    trade: Trade
    booked: bool                 # False = sombra (marco cerrado por la puerta de costo)
    qty: float = 0.0
    risk_usd: float = 0.0
    balance_before: float = 0.0
    twins: Twins | None = None

    @property
    def pnl_usd(self) -> float:
        tr = self.trade
        return self.qty * tr.fill * tr.net if self.booked and tr.status == "CERRADA" else 0.0

    @property
    def d_r(self) -> float | None:
        r = self.trade.r
        return None if r is None or self.twins is None or self.trade.status != "CERRADA" \
            else r - self.twins.mean_r

    @property
    def twin_pnl_usd(self) -> float:
        return self.twins.mean_r * self.risk_usd if self.twins and self.booked else 0.0


@dataclass
class Book:
    params: NurseryParams
    accounts: list[Account]
    entries: list[Entry] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    @property
    def prospect_count(self) -> int:
        return sum(1 for a in self.accounts if a.kind == "prospecto")

    def of(self, account: str) -> list[Entry]:
        return [e for e in self.entries if e.account == account]

    def balance(self, account: str) -> float:
        return self.params.initial_equity + sum(e.pnl_usd for e in self.of(account))


def twin_seed(seed: int, account: str, t: int) -> int:
    h = hashlib.sha256(f"{seed}:{account}:{t}".encode()).digest()
    return int.from_bytes(h[:8], "little")


def make_twins(e_order: Order, real: Trade, account: str, path: Path, np_: NurseryParams,
               fstep: int) -> Twins | None:
    """Gemelos de una operación cerrada; None si alguno de los dos lados sigue sin resolver."""
    if real.status != "CERRADA":
        return None
    sides = np.random.default_rng(twin_seed(np_.seed, account, e_order.t)).choice(
        (-1, 1), size=np_.twins_k)
    rs = {}
    for s in (1, -1):
        tr = simulate(e_order.twin(s, real.exit_t), path, np_.exec, fstep)
        rs[s] = tr.r
    if rs[1] is None or rs[-1] is None:
        return None
    return Twins(np_.twins_k, int((sides > 0).sum()), float(rs[1]), float(rs[-1]))


class _Gate:
    """Costo cerrado por marco hasta el instante de cada decisión (sin mirar el futuro)."""

    def __init__(self, np_: NurseryParams, events: list[dict], accounts: list[Account]) -> None:
        self.np, self.events = np_, events
        self.pending: dict[str, list[tuple[int, float]]] = {}
        self.acc: dict[str, list[float]] = {}
        self.state: dict[str, bool] = {}
        self.ids = {tf: [a.id for a in accounts if a.timeframe == tf]
                    for tf in {a.timeframe for a in accounts}}

    def push(self, tf: str, exit_t: int, cost_r: float) -> None:
        heapq.heappush(self.pending.setdefault(tf, []), (exit_t, cost_r))

    def open_at(self, tf: str, t: int) -> bool:
        heap, acc = self.pending.setdefault(tf, []), self.acc.setdefault(tf, [0.0, 0])
        while heap and heap[0][0] <= t:
            acc[0] += heapq.heappop(heap)[1]
            acc[1] += 1
        thr, n_min = self.np.tf_max_cost_r, self.np.exec.tf_cost_min_n
        measured = {tf: (acc[0] / acc[1], int(acc[1]))} if acc[1] else {}
        value, src = tf_gate.reference(tf, measured, n_min)
        is_open = thr is None or value is None or value < thr
        prev = self.state.get(tf)
        if prev is None or prev != is_open:
            self.events.append({"t": t, "kind": "puerta_costo", "timeframe": tf,
                                "value_r": value, "source": src, "threshold_r": thr,
                                "before": None if prev is None else ("abierto" if prev else
                                                                     "cerrado"),
                                "after": "abierto" if is_open else "cerrado",
                                "accounts": self.ids.get(tf, [])})
            self.state[tf] = is_open
        return is_open


def run_book(ctxs: Mapping[str, Sequence[dict]], path: Path, prospects: Sequence[Prospect],
             np_: NurseryParams | None = None,
             registered: Mapping[str, int] | None = None) -> Book:
    """El libro completo de la cantera con los contextos `ctxs[marco]` (ascendentes)."""
    np_ = np_ or NurseryParams()
    accounts = accounts_for(prospects)
    book = Book(np_, accounts)
    book.events.append({"t": np_.start_ms, "kind": "config", "auto_adapt": np_.auto_adapt(),
                        "accounts": [a.id for a in accounts]})
    gate = _Gate(np_, book.events, accounts)
    fstep = funding_step(path)
    by_tf = {tf: [c for c in cs if int(c["t"]) >= np_.start_ms] for tf, cs in ctxs.items()}
    sigs = {a.id: signals(a, by_tf.get(a.timeframe, []), np_.history_bars) for a in accounts}
    busy: dict[str, int | None] = {a.id: 0 for a in accounts}
    balance = {a.id: np_.initial_equity for a in accounts}
    floor = np_.initial_equity * np_.min_equity_frac
    sweep = sorted((int(c["t"]), tf, i) for tf, cs in by_tf.items() for i, c in enumerate(cs))
    by_acc_tf = {tf: [a for a in accounts if a.timeframe == tf] for tf in by_tf}
    for t, tf, i in sweep:
        accs = by_acc_tf.get(tf, [])
        if not accs:
            continue
        is_open = gate.open_at(tf, t)
        for a in accs:
            free = busy[a.id]
            if free is None or t < free or t < (registered or {}).get(a.id, 0):
                continue
            sig = sigs[a.id][i]
            if not sig.enter:
                continue
            o = build_order(a, i, sig.enter, by_tf[tf], sigs[a.id], np_)
            if o is None:
                continue
            tr = simulate(o, path, np_.exec, fstep)
            booked = is_open and balance[a.id] > floor
            qty = risk_usd = 0.0
            if booked:
                risk_usd = np_.risk_pct * balance[a.id]
                qty = risk_budget.qty_for_risk(risk_usd, o.ref, o.sl, np_.est_cost_frac,
                                               np_.risk_includes_costs)
                qty = min(qty, balance[a.id] * np_.max_leverage / o.ref)
            e = Entry(a.id, a.kind, tf, t, o.side, o, tr, booked, qty, risk_usd, balance[a.id],
                      make_twins(o, tr, a.id, path, np_, fstep))
            book.entries.append(e)
            balance[a.id] += e.pnl_usd
            if tr.status == "CERRADA" and tr.cost_r is not None:
                gate.push(tf, int(tr.exit_t), tr.cost_r)
            if tr.status == "RECHAZADA":
                continue
            end = tr.busy_until
            busy[a.id] = None if end is None or tr.status == "PENDIENTE" else \
                end + np_.exec.cooldown_bars * tf_ms(tf)
    return book
