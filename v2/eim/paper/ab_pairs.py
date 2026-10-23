"""A/B emparejado (T111): las MISMAS entradas con las dos salidas, para aislar su efecto.

El escenario A (TP/BE+/tiempo) corre su libro de perfil; cada operación que A abrió de verdad
—misma idea, mismo llenado, mismo margen, mismo apalancamiento— se vuelve a simular con la salida B
(escalera, `simulate_ladder`). La cantidad es la de A redondeada al paso del instrumento (lo que B
podría negociar) y el resultado de A se escala a esa misma cantidad, así que la única diferencia
entre las dos columnas es la regla de salida. Las entradas que el filtro de viabilidad de B (que
usa el objetivo de la idea como estimación) habría descartado se marcan y se cuentan aparte.
Función pura sobre el camino de precios: sin I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from eim.paper.account import LIQ, capped, liq_price
from eim.paper.book import ProfileState
from eim.paper.engine import Outcome
from eim.paper.ladder import floor_qty, simulate_ladder
from eim.paper.ladder_book import LadderSim, viability
from eim.paper.params import ProfileParams, spec_for
from eim.paper.summary import positions_of

PRICE_TOL = 1e-9      # el llenado de A y el de B deben coincidir (mismo modelo de entrada)


@dataclass(frozen=True)
class Pair:
    id: str
    t: int
    viable_b: bool              # el filtro de viabilidad de B la habría dejado entrar
    a: dict                     # operación cerrada de A (escalada) o posición abierta al final
    b: dict | None              # lo mismo con la salida B; None si no es negociable en B
    open_a: bool
    open_b: bool
    same_fill: bool             # mismo precio de entrada en las dos salidas (si B la negocia)


def _scaled(t: dict, k: float) -> dict:
    """La operación de A con su tamaño multiplicado por `k` (el R no cambia)."""
    keys = ("pnl", "fees", "slip", "funding", "notional", "qty", "margin", "risk_usd", "upnl",
            "cost_usd")
    return {**t, **{x: t[x] * k for x in keys if t.get(x) is not None}}


def _b_trade(o: Outcome, base: dict, qty: float, margin: float, liq: float) -> dict:
    """La operación B en el mismo formato que `book._close` (lo que lee `ladder_metrics`)."""
    i, notional = o.idea, qty * o.fill
    risk = qty * abs(o.fill - i.sl)
    if o.status == "ABIERTA":
        u, _ = capped(o.ladder["float_usd"], margin, i.side, o.mark, liq)
        return {**base, "qty": qty, "margin": margin, "upnl": u, "ladder": o.ladder,
                "risk_usd": risk, "fill": o.fill, "mark": o.mark}
    pnl, why = capped(float(notional * o.net), margin, i.side, o.exit, liq)
    return {**base, "fill_t": o.fill_t, "exit_t": o.exit_t, "fill": o.fill, "exit": o.exit,
            "qty": qty, "notional": notional, "margin": margin, "risk_usd": risk,
            "reason": LIQ if why else o.reason, "pnl": pnl, "r": pnl / risk if risk else None,
            "fees": notional * (o.fee_in + o.fee_out), "slip": notional * o.slip,
            "funding": notional * o.funding, "funding_assumed": o.funding_assumed,
            "mfe_r": o.mfe_r, "mae_r": o.mae_r, "ladder": o.ladder}


def _one(t: dict, o: Outcome, is_open: bool, p_b: ProfileParams, sim: LadderSim,
         mmr: float) -> Pair:
    i = o.idea
    spec = spec_for(i.symbol)
    q = floor_qty(t["qty"], spec.qty_step)
    k = q / t["qty"] if t["qty"] else 0.0
    a = _scaled(t, k)
    viable = viability(p_b, i, p_b.initial_equity) is None    # en R no depende del capital
    if q < spec.min_qty:
        return Pair(i.id, i.t, viable, a, None, is_open, False, False)
    ob = simulate_ladder(i, sim.path, sim.ep, p_b.ladder, q, sim.fine, spec=spec)
    lev = t["leverage"]
    liq = liq_price(i.side, ob.fill, lev, mmr) if ob.fill else 0.0
    base = {"id": i.id, "t": i.t, "side": i.side, "sid": i.sid, "timeframe": i.timeframe,
            "regime": i.regime, "origin": i.origin, "kind": i.kind, "leverage": lev}
    b = _b_trade(ob, base, q, a["margin"], liq) if ob.status in ("CERRADA", "ABIERTA") else None
    a_fill = t["entry"] if is_open else t["fill"]      # las abiertas traen el llenado en «entry»
    same = b is not None and abs(ob.fill - a_fill) <= PRICE_TOL * ob.fill
    return Pair(i.id, i.t, viable, a, b, is_open, ob.status == "ABIERTA", same)


def pair_trades(book_a: ProfileState, outcomes: dict[str, Outcome], p_b: ProfileParams,
                sim: LadderSim, mmr: float) -> list[Pair]:
    """Cada operación (cerrada o abierta al final) del libro A, con la salida B al lado.

    Solo escaleras en R: con escalones fijos en USDT la viabilidad depende del capital del
    instante de la señal, que la operación de A no guarda."""
    if p_b.ladder is None or p_b.ladder.basis != "r":
        raise ValueError(f"{p_b.id}: el emparejado necesita una escalera con basis 'r'")
    out = [_one(t, outcomes[t["id"]], False, p_b, sim, mmr) for t in book_a.trades]
    pos, _, _ = positions_of(book_a, mmr)
    out += [_one(x, outcomes[x["id"]], True, p_b, sim, mmr) for x in pos]
    return sorted(out, key=lambda x: (x.t, x.id))


def split(pairs: list[Pair], viable: bool = True) -> tuple[list, list, list, list]:
    """(cerradas A, abiertas A, cerradas B, abiertas B) de las parejas con ese `viable_b` y
    negociables en B: las dos columnas cubren exactamente las mismas entradas."""
    sel = [x for x in pairs if x.viable_b == viable and x.b is not None]
    return ([x.a for x in sel if not x.open_a], [x.a for x in sel if x.open_a],
            [x.b for x in sel if not x.open_b], [x.b for x in sel if x.open_b])


def cut_winners(pairs: list[Pair]) -> dict:
    """¿La escalera corta a las ganadoras antes de que corran? Sobre las parejas cerradas en las
    dos salidas: lo que A ganó en TP frente a lo que B se llevó de esas mismas entradas, y al revés
    las que A perdió y B salvó."""
    both = [x for x in pairs if x.viable_b and x.b is not None and not x.open_a and not x.open_b]
    tp = [x for x in both if x.a["reason"] == "TP"]
    won_a = [x for x in both if x.a["pnl"] > 0]
    lost_a = [x for x in both if x.a["pnl"] <= 0]

    def mean(xs: list[float]) -> float | None:
        return sum(xs) / len(xs) if xs else None

    return {
        "pairs": len(both),
        "a_tp": len(tp),
        "a_tp_mean_r": mean([x.a["r"] for x in tp]),
        "b_on_a_tp_mean_r": mean([x.b["r"] for x in tp]),
        "a_tp_b_less": sum(1 for x in tp if x.b["pnl"] < x.a["pnl"]),
        "a_tp_b_lost": sum(1 for x in tp if x.b["pnl"] <= 0),
        "given_up_usd": sum(x.a["pnl"] - x.b["pnl"] for x in tp if x.b["pnl"] < x.a["pnl"]),
        "a_winners": len(won_a),
        "a_win_mean_r": mean([x.a["r"] for x in won_a]),
        "b_on_a_win_mean_r": mean([x.b["r"] for x in won_a]),
        "a_losers": len(lost_a),
        "a_loss_mean_r": mean([x.a["r"] for x in lost_a]),
        "b_on_a_loss_mean_r": mean([x.b["r"] for x in lost_a]),
        "a_lost_b_won": sum(1 for x in lost_a if x.b["pnl"] > 0),
        "b_hours_mean": mean([(x.b["exit_t"] - x.b["fill_t"]) / 3_600_000 for x in both]),
        "a_hours_mean": mean([(x.a["exit_t"] - x.a["fill_t"]) / 3_600_000 for x in both]),
    }
