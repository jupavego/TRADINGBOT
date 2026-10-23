"""Constructores para los tests del diario de la protección (T110), sin red ni API.

Perfil Moderado real (escalera en R) con costos cero: con el peso de una estrategia nueva la
operación compra 0,017 BTC, el primer escalón protege +140 de precio y cada uno más +70. `rise(n)`
sube 75 por vela, así que cada vela confirma exactamente un escalón nuevo: `rise(6)` termina en el
escalón 5 con el SL en 70 420.
"""

from __future__ import annotations

from dataclasses import replace

from eim.backtest.params import ZERO_COSTS
from eim.data.paper_store import PaperStore
from eim.paper import protection
from eim.paper.book import run_profile
from eim.paper.engine import Path, simulate
from eim.paper.feedback import Learner
from eim.paper.ladder_book import LadderSim
from eim.paper.params import PROFILES, ExecParams
from eim.paper.protection_sync import run_pass
from tests.paper.helpers import M15, T0, bar, idea

E = 70_000.0
SYM = "BTCUSDT"
EP = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)
MOD = next(p for p in PROFILES if p.id == "moderado")
TOP = 70_420.0                       # SL del escalón 5 tras `rise(6)`
NOW = T0 + 400 * M15


def btc(side: int = 1, t: int = T0, strategy: str = "s"):
    i = idea(side=side, entry=E, sl=E - side * 1400, tp=E + side * 2200, t=t, strategy=strategy,
             syn_bias=0.5 * side, iid=f"{SYM}:15m:{t}:{strategy}")
    return replace(i, symbol=SYM, htf=1, origin="vivo")


OP = protection.op_key("moderado", SYM, btc().id)


def rise(n: int, flat: int = 3) -> list[tuple]:
    """Vela de entrada, `n` velas que suben 75 cada una y `flat` velas quietas arriba."""
    rows, p = [(E, E + 20, E - 20, E + 10)], E + 10
    for _ in range(n):
        rows.append((p, p + 80, p - 5, p + 75))
        p += 75
    return rows + [(p, p + 5, p - 10, p)] * flat


def pullback(rows: list[tuple], low: float) -> list[tuple]:
    """Una vela más que baja hasta `low` desde el último cierre."""
    c = rows[-1][3]
    return [*rows, (c, c + 2, low, low + 5)]


def path_of(rows: list[tuple]) -> Path:
    return Path([bar(T0 + k * M15, *r) for k, r in enumerate(rows)])


def sim_book(rows: list[tuple], p=MOD, ideas=None, guards=None):
    """Libro del perfil sobre `rows` con el suelo `guards` (lo que la mesa lee del diario)."""
    path = path_of(rows)
    ideas = [btc()] if ideas is None else ideas
    sh = [simulate(i, path, EP) for i in ideas]
    return run_profile(p, sh, Learner(sh), 0.004, LadderSim(path, EP, guards=guards or {}))


def book(ps: PaperStore | None, rows: list[tuple], p=MOD, ideas=None):
    """(libro del perfil, diario leído antes de simular) con el suelo del diario aplicado."""
    j = protection.load(ps, SYM) if ps is not None else None
    return sim_book(rows, p, ideas, j.guards if j else None), j


def step(ps: PaperStore, rows: list[tuple], now: int = NOW, p=MOD, ideas=None,
         startup: bool = False, seen: set | None = None):
    """Una pasada como la de la mesa: lee el diario, recalcula y lo pone al día."""
    st, j = book(ps, rows, p, ideas)
    return st, run_pass(ps, j, {p.id: st}, EP, now, startup=startup, seen=seen)


def store() -> PaperStore:
    ps = PaperStore(":memory:")
    protection.ensure(ps)
    return ps


def stops(ps: PaperStore, op_id: str = OP) -> list[float]:
    return [r["stop"] for r in protection.history(ps, op_id)]


def insert_copy(ps: PaperStore, **changes) -> dict:
    """Añade a mano una fila vigente alterada (simula una instantánea corrupta o ajena)."""
    last = protection.history(ps, OP)[-1]
    seq = last["seq"] + 1
    row = {**last, "row_id": f"{OP}|{seq}", "seq": seq, **changes}
    protection.append(ps, [row])
    return row
