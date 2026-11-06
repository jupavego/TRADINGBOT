"""Lo que la pasada del diario de la protección (T110) lee de los libros: cada operación de origen
`vivo` con escalera, tal como la dejó el recálculo."""

from __future__ import annotations

from dataclasses import dataclass

from eim.paper.book import ProfileState
from eim.paper.params import ExecParams
from eim.paper.protection import op_key


@dataclass(frozen=True)
class Cur:
    """Operación de origen `vivo` con escalera, tal como la dejó el recálculo."""

    op_id: str
    profile: str
    symbol: str
    idea_id: str
    side: int
    entry: float
    qty: float
    initial_sl: float
    fill_t: int
    info: dict                    # estado de la escalera (`Outcome.ladder`)
    costs: dict
    close: dict | None = None     # {"reason", "exit", "exit_t", "pnl"} si cerró


def current_ops(symbol: str, books: dict[str, ProfileState], ep: ExecParams) -> dict[str, Cur]:
    out: dict[str, Cur] = {}
    for pid, st in books.items():
        lp = st.p.ladder
        if not st.p.stop_driven:
            continue
        # la salida adaptativa (T135) no reserva escalones: su fase, motivo, fuente y versión van
        # en el historial de cada fila (`adaptive.decorate`), sin columnas nuevas
        res = ({"fee_out_est": ep.costs.taker_fee, "slip_reserve_bars": lp.slip_lookback,
                "funding_reserve": lp.funding_reserve} if lp is not None
               else {"fee_out_est": ep.costs.taker_fee})
        for s in st.slots.values():
            o, i = s.o, s.o.idea
            if s.filled and o.ladder and i.origin == "vivo":
                k = op_key(pid, symbol, i.id)
                out[k] = Cur(k, pid, symbol, i.id, i.side, o.fill, s.qty, i.sl, o.fill_t, o.ladder,
                             {"fee_in": o.fee_in, "slip_in": o.slip, "funding": o.funding,
                              "funding_assumed": o.funding_assumed,
                              "cost_usd": s.qty * o.fill * (o.fee_in + o.slip + o.funding), **res})
        for t in st.trades:
            if t.get("ladder") and t.get("origin") == "vivo":
                k = op_key(pid, symbol, t["id"])
                out[k] = Cur(k, pid, symbol, t["id"], t["side"], t["fill"], t["qty"], t["sl"],
                             t["fill_t"], t["ladder"],
                             {"fees_usd": t["fees"], "slip_usd": t["slip"],
                              "funding_usd": t["funding"],
                              "funding_assumed": t["funding_assumed"], **res},
                             {"reason": t["reason"], "exit": t["exit"], "exit_t": t["exit_t"],
                              "pnl": t["pnl"]})
    return out
