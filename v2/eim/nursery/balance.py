"""Balance de la cantera: ganadas frente a perdidas y capital por agente. Puro. SIMULADO.

La pestaña «Cantera» se presenta como el bróker simulado (pedido del usuario, 2026-11-20):
arriba, las operaciones ganadas frente a las perdidas con el acierto necesario para no perder;
debajo, la curva de capital de cada agente. Aquí se calculan las dos desde el libro de la
cantera.

- Solo cuentan las cuentas de los **prospectos** (los controles genéricos son la vara de
  comparación, no la cantera) y solo las operaciones **contabilizadas y cerradas** (las de sombra,
  con el marco cerrado por la puerta de costo, no mueven saldo).
- Ganada = P&L neto > 0 después de comisiones, deslizamiento y funding, como en el bróker.
- El capital de un agente es la **suma de las cuentas de sus prospectos** (10 000 USDT cada una),
  realizado al cierre de cada operación; el % es sobre la suma de sus capitales iniciales.
- Es la misma contabilidad aparte de siempre: nada de esto se suma a los cuatro perfiles ni a T144.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from eim.nursery.book import Book, Entry

DAY_MS = 86_400_000
WINDOWS = (("todo", "Todo", None), ("30d", "30 días", 30), ("7d", "7 días", 7),
           ("24h", "24 h", 1))
MAX_POINTS = 400        # tope de puntos por curva (se submuestrea, el último siempre queda)


def _r(x: float | None, d: int = 2) -> float | None:
    return None if x is None else round(float(x), d)


def _avg(xs: Sequence[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _cost_usd(e: Entry) -> float:
    return e.qty * (e.trade.fill or 0.0) * e.trade.cost


def _half(es: Sequence[Entry]) -> dict:
    usd = [e.pnl_usd for e in es]
    rs = [e.trade.r for e in es if e.trade.r is not None]
    reasons: dict[str, int] = {}
    for e in es:
        k = e.trade.reason or "—"
        reasons[k] = reasons.get(k, 0) + 1
    return {"n": len(es), "usd": _r(sum(usd)) or 0.0, "avg_usd": _r(_avg(usd)),
            "avg_r": _r(_avg(rs), 3), "by_reason": reasons}


def stats(es: Sequence[Entry]) -> dict:
    """Ganadas, perdidas, acierto y acierto necesario de un grupo de operaciones cerradas."""
    wins = [e for e in es if e.pnl_usd > 0]
    losses = [e for e in es if e.pnl_usd <= 0]
    w, lo = _half(wins), _half(losses)
    payoff = (w["avg_usd"] / -lo["avg_usd"]
              if w["avg_usd"] is not None and lo["avg_usd"] is not None and lo["avg_usd"] < 0
              else None)
    rs = [e.trade.r for e in es if e.trade.r is not None]
    return {"n": len(es), "wins": w, "losses": lo,
            "win_rate": _r(len(wins) / len(es), 4) if es else None,
            "payoff": _r(payoff, 3), "breakeven": _r(1 / (1 + payoff), 4) if payoff else None,
            "expectancy_r": _r(_avg(rs), 3),
            "pf": _r(w["usd"] / -lo["usd"], 3) if lo["usd"] < 0 else None,
            "net": _r(sum(e.pnl_usd for e in es)) or 0.0,
            "costs": _r(sum(_cost_usd(e) for e in es)) or 0.0}


def closed_prospect_entries(book: Book) -> list[Entry]:
    """Operaciones contabilizadas y cerradas de las cuentas de prospectos, por hora de cierre."""
    ids = {a.id for a in book.accounts if a.kind == "prospecto"}
    es = [e for e in book.entries if e.account in ids and e.booked
          and e.trade.status == "CERRADA" and e.trade.exit_t is not None]
    return sorted(es, key=lambda e: int(e.trade.exit_t))


def _group(es: Iterable[Entry], key) -> dict[str, list[Entry]]:
    out: dict[str, list[Entry]] = {}
    for e in es:
        out.setdefault(key(e), []).append(e)
    return out


def _window(es: Sequence[Entry], agent_of: dict[str, str], label: str) -> dict:
    by_agent = _group(es, lambda e: agent_of.get(e.account, "—"))
    by_tf = _group(es, lambda e: e.timeframe)
    return {"label": label, "all": stats(es),
            "agents": {a: {"n": len(xs), "wins": {"n": sum(1 for x in xs if x.pnl_usd > 0),
                                                  "usd": _r(sum(x.pnl_usd for x in xs
                                                                if x.pnl_usd > 0)) or 0.0},
                           "losses": {"n": sum(1 for x in xs if x.pnl_usd <= 0),
                                      "usd": _r(sum(x.pnl_usd for x in xs
                                                    if x.pnl_usd <= 0)) or 0.0}}
                       for a, xs in sorted(by_agent.items())},
            "timeframes": {tf: {"n": len(xs), "win_rate": _r(sum(1 for x in xs if x.pnl_usd > 0)
                                                             / len(xs), 4)}
                           for tf, xs in sorted(by_tf.items())}}


def _thin(points: list[dict], cap: int = MAX_POINTS) -> list[dict]:
    if len(points) <= cap:
        return points
    step = len(points) / (cap - 1)
    keep = [points[int(i * step)] for i in range(cap - 1)]
    return keep + [points[-1]]


def agent_curves(book: Book, es: Sequence[Entry], now_ms: int) -> list[dict]:
    """Capital realizado de cada agente: la suma de las cuentas de sus prospectos."""
    init = book.params.initial_equity
    accounts = _group((a for a in book.accounts if a.kind == "prospecto"), lambda a: a.agent_id)
    agent_of = {a.id: a.agent_id for a in book.accounts}
    by_agent = _group(es, lambda e: agent_of.get(e.account, "—"))
    out = []
    for aid, accs in sorted(accounts.items()):
        base = init * len(accs)
        eq = base
        pts = [{"t": int(book.params.start_ms), "equity": round(eq, 2), "pct": 0.0}]
        for e in by_agent.get(aid, []):
            eq += e.pnl_usd
            pts.append({"t": int(e.trade.exit_t), "equity": round(eq, 2),
                        "pct": round((eq / base - 1) * 100, 3)})
        if pts[-1]["t"] < now_ms:     # la curva llega hasta ahora (sin operaciones, plana)
            pts.append({**pts[-1], "t": int(now_ms)})
        out.append({"agent_id": aid, "accounts": len(accs), "initial": round(base, 2),
                    "equity": round(eq, 2), "return_pct": round((eq / base - 1) * 100, 3),
                    "n": len(by_agent.get(aid, [])), "curve": _thin(pts)})
    return out


def build_balance(book: Book, now_ms: int) -> dict:
    """Balance por ventana (todo, 30 d, 7 d, 24 h) y capital por agente de la cantera."""
    es = closed_prospect_entries(book)
    agent_of = {a.id: a.agent_id for a in book.accounts}
    windows = {}
    for key, label, days in WINDOWS:
        since = None if days is None else now_ms - days * DAY_MS
        xs = es if since is None else [e for e in es if int(e.trade.exit_t) >= since]
        windows[key] = _window(xs, agent_of, label)
    return {"mode": "SIMULADO", "scope": "prospectos de la cantera (los controles no cuentan)",
            "rule": "ganada = P&L neto > 0 después de comisiones, deslizamiento y funding",
            "windows": windows, "agents": agent_curves(book, es, now_ms),
            "initial_per_account": book.params.initial_equity}
