"""Del libro de la cantera a las entradas del escalafón (T170). Puro.

Solo cuentan las operaciones **contabilizadas** (no las sombras de la puerta de costo): son las que
mueven la cuenta. El régimen de cada operación es la etiqueta del agente `regime` en el contexto de
su vela de decisión, y los tramos con el marco cerrado salen de los eventos `puerta_costo`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from eim.nursery.book import Book
from eim.nursery.ladder import Standing, evaluate
from eim.nursery.ladder_final import make_first_team
from eim.nursery.ladder_stats import AccountData, Closed
from eim.nursery.prereg import Prereg

FILLED = ("CERRADA", "ABIERTA")


def account_data(book: Book, regimes: Mapping[str, Mapping[int, str]] | None = None
                 ) -> dict[str, AccountData]:
    """`AccountData` de cada cuenta (prospectos y controles), por `prospecto@huella`."""
    out: dict[str, tuple[list, list]] = {a.id: ([], []) for a in book.accounts}
    for e in book.entries:
        if not e.booked or e.trade.status not in FILLED:
            continue
        tr = e.trade
        closed, fills = out[e.account]
        fills.append((int(tr.fill_t), None if tr.exit_t is None or tr.status == "ABIERTA"
                      else int(tr.exit_t)))
        if tr.status == "CERRADA" and e.d_r is not None:
            closed.append(Closed(int(e.t), int(tr.fill_t), int(tr.exit_t), float(e.d_r),
                                 float(e.pnl_usd), tr.cost_r, tr.r,
                                 (regimes or {}).get(e.timeframe, {}).get(int(e.t))))
    return {k: AccountData(tuple(sorted(c, key=lambda x: x.exit_t)), tuple(sorted(f)))
            for k, (c, f) in out.items()}


def closed_spans(events: Sequence[dict], t_end: int) -> dict[str, list[tuple[int, int]]]:
    """Tramos con cada marco cerrado por la puerta de costo, hasta `t_end`."""
    out: dict[str, list[tuple[int, int]]] = {}
    since: dict[str, int] = {}
    for ev in sorted((e for e in events if e.get("kind") == "puerta_costo"),
                     key=lambda e: int(e["t"])):
        tf = ev["timeframe"]
        if ev["after"] == "cerrado":
            since.setdefault(tf, int(ev["t"]))
        elif tf in since:
            out.setdefault(tf, []).append((since.pop(tf), int(ev["t"])))
    for tf, t0 in since.items():
        out.setdefault(tf, []).append((t0, t_end))
    return out


def standings(book: Book, pr: Prereg, alta_ms: int, t: int,
              regimes: Mapping[str, Mapping[int, str]] | None = None) -> dict[str, Standing]:
    """Etapa de cada prospecto del pre-registro en `t`, por id de prospecto."""
    data = account_data(book, regimes)
    acc_of = {a.prospect.id: a.id for a in book.accounts if a.prospect is not None}
    members = pr.members()
    accounts = {mb.id: data.get(acc_of.get(mb.id, ""), AccountData()) for mb in members}
    controls = {a.id: data[a.id] for a in book.accounts if a.kind == "control"}
    rules = pr.ladder
    return evaluate(members, accounts, rules, alta_ms, t, pr.m, book.params.initial_equity,
                    controls=controls, closed_spans=closed_spans(book.events, t),
                    first_team=make_first_team(rules, alta_ms, pr.m,
                                               book.params.initial_equity))
