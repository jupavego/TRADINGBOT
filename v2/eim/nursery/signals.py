"""Cuentas de la cantera y sus señales vela a vela (T168). Puro.

Cada **prospecto** tiene su cuenta (`prospecto@huella`). Los **controles** no cuentan como
prospectos ni en la familia: el `agente_{id}` genérico de hoy (`paper/strategies_ind.py`: sigue al
agente si |sesgo| ≥ 0,3 y confianza ≥ 20 %), uno por agente y marco en que su agente tiene
prospectos, con la plantilla `atr_ladder`, que es su salida de siempre. Los gemelos aleatorios
pareados viven dentro de cada operación (`book.py`), no como cuenta.

La señal de la vela `i` se calcula solo con los contextos `0…i` del mismo marco.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from eim.data.timeframes import tf_ms
from eim.nursery.params import NurseryParams
from eim.nursery.prospect import Prospect
from eim.nursery.rules.base import NONE, Signal, View, sign, steady
from eim.nursery.sim import Order
from eim.paper.strategies_ind import AGENT_BIAS, AGENT_CONF

PROSPECT, CONTROL = "prospecto", "control"


@dataclass(frozen=True)
class Account:
    id: str
    kind: str                    # prospecto | control
    agent_id: str
    timeframe: str
    exit_template: str
    prospect: Prospect | None = None
    max_bars: int | None = None

    @property
    def label(self) -> str:
        return self.prospect.id if self.prospect else self.id


def accounts_for(prospects: Sequence[Prospect]) -> list[Account]:
    out = [Account(p.account, PROSPECT, p.agent_id, p.timeframe, p.exit_template, p,
                   p.max_bars) for p in prospects]
    pairs = sorted({(p.agent_id, p.timeframe) for p in prospects})
    out += [Account(f"control:agente_{a}@{tf}", CONTROL, a, tf, "atr_ladder") for a, tf in pairs]
    return out


def _generic(aid: str) -> Callable[[dict], Signal]:
    def fn(ctx: dict) -> Signal:
        row = (ctx.get("agents") or {}).get(aid)
        if not row or row[2] != "ok" or abs(row[0]) < AGENT_BIAS or row[1] < AGENT_CONF:
            return NONE
        return steady(sign(row[0]))
    return fn


def signals(acc: Account, ctxs: Sequence[dict], hist: int) -> list[Signal]:
    """Señal de la cuenta en cada contexto de su marco (sin mirar contextos posteriores)."""
    if acc.prospect is None:
        gen = _generic(acc.agent_id)
        return [gen(c) for c in ctxs]
    p = acc.prospect
    declared = frozenset(p.variables)
    rows = [(c.get("nat") or {}).get(p.agent_id) for c in ctxs]
    out: list[Signal] = []
    for i, c in enumerate(ctxs):
        view = View(p.agent_id, declared, tuple(rows[max(0, i - hist):i + 1]),
                    close=c.get("close"), atr=c.get("atr"))
        if rows[i] is None:
            out.append(NONE)
            continue
        try:
            out.append(p.rule(view, dict(p.params)))
        except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
            out.append(NONE)      # contexto incompleto: la regla no decide
    return out


def horizon_of(ctx: dict, agent: str) -> int | None:
    h = ((ctx.get("nat") or {}).get(agent) or {}).get("_h")
    return int(h) if isinstance(h, (int, float)) and h > 0 else None


def build_order(acc: Account, i: int, side: int, ctxs: Sequence[dict], sigs: Sequence[Signal],
                np_: NurseryParams) -> Order | None:
    """La orden de la plantilla de salida de la cuenta, decidida en el cierre del contexto `i`."""
    c = ctxs[i]
    ref, a = c.get("close"), c.get("atr")
    if not ref or not a or a <= 0 or side == 0:
        return None
    t, tf, bar = int(c["t"]), acc.timeframe, tf_ms(acc.timeframe)
    ep = np_.exec
    maker = tf in np_.maker_tfs and ep.maker_entry_bars > 0
    o = Order(side=side, t=t, ref=float(ref), sl=float(ref) - side * np_.sl_atr * a,
              maker=maker, fill_ms=int(ep.maker_entry_bars * bar) if maker else 0,
              be=tf in ep.be_timeframes)
    bars = acc.max_bars or horizon_of(c, acc.agent_id) or np_.default_hold_bars
    cap = t + acc.max_bars * bar if acc.max_bars else None   # tope de velas (scalping, nota §3)
    tpl = acc.exit_template
    if tpl == "atr_ladder":
        return replace(o, tp=float(ref) + side * np_.tp_atr * a, protect=True, forced_t=cap)
    if tpl == "time_stop":
        return replace(o, forced_t=t + bars * bar)
    if tpl == "mean_target":
        tgt = sigs[i].target
        tp = float(tgt) if tgt is not None and (tgt - ref) * side > 0 else None
        if tgt is not None and tp is None:
            return None           # la media ya quedó del otro lado: no hay recorrido
        return replace(o, tp=tp, forced_t=t + bars * bar)
    if tpl == "rule_flip":
        for k in range(i + 1, len(ctxs)):
            h = sigs[k].hold
            if h is not None and h != side:
                flip = int(ctxs[k]["t"])
                if cap is None or flip <= cap:
                    return replace(o, forced_t=flip, forced_reason="REGLA")
                break
        return replace(o, forced_t=cap) if cap else o
    raise ValueError(f"plantilla de salida desconocida: {tpl}")
