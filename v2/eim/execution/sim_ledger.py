"""Libro de operaciones SIMULADAS: reconstruye operaciones desde los planes persistidos.

Sin exchange ni órdenes: toda operación es `mode=SIMULADO`. El libro es una función
determinista de (reportes del agente `plan`, velas), así que siempre se puede reconstruir.

Reglas: el plan entra al cierre de la vela que lo emite (su `entry`); salida por SL (con el SL
vigente, que solo se acerca), TP (TP2 si la misma vela lo alcanza, si no TP1), o por el cierre
de la vela en que el plan se invalida/expira. SL y TP en la misma vela → SL (conservador).
Costos: comisión taker por lado y funding constante (supuesto, no dato de mercado).
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, replace

from eim.core import AgentReport, Candle, Mode, Overlay
from eim.data.timeframes import tf_ms

FUNDING_MS = 8 * 3_600_000


@dataclass(frozen=True)
class LedgerParams:
    fee_rate: float = 0.0005          # taker por lado (supuesto)
    funding_rate_8h: float = 0.0001   # constante (supuesto); largo paga, corto cobra


@dataclass(frozen=True)
class Trade:
    id: str
    symbol: str
    timeframe: str
    plan_id: str
    side: int                    # +1 largo, −1 corto
    entry_t: int                 # apertura de la vela que emite el plan; entra a su cierre
    entry: float
    sl0: float
    tp1: float
    tp2: float | None
    status: str = "ABIERTA"      # ABIERTA | SL | TP1 | TP2 | INVALIDADO | EXPIRADO
    exit_t: int | None = None    # apertura de la vela de salida
    exit: float | None = None
    r: float | None = None       # resultado neto en R (riesgo inicial = |entry − sl0|)
    fees_r: float | None = None
    funding_r: float | None = None
    mode: str = Mode.SIMULADO.value
    evidence: tuple[str, ...] = ()
    funding_source: str = "supuesto constante"

    def to_json(self) -> dict:
        return asdict(self)


def _plans(reports: list[AgentReport]) -> dict[str, list[tuple[AgentReport, Overlay]]]:
    """plan_id → [(reporte, overlay)] en orden de asof."""
    out: dict[str, list[tuple[AgentReport, Overlay]]] = {}
    for r in sorted(reports, key=lambda x: x.asof):
        if r.agent_id != "plan":
            continue
        for o in r.overlays:
            if o.kind == "trade_plan":
                out.setdefault(o.id, []).append((r, o))
    return out


def _close(tr: Trade, c: Candle, bar: int, px: float, status: str, p: LedgerParams) -> Trade:
    risk = abs(tr.entry - tr.sl0)
    held = (c.t - tr.entry_t) / FUNDING_MS   # de cierre de entrada a cierre de la vela de salida
    fees = tr.entry * p.fee_rate * 2
    funding = tr.entry * p.funding_rate_8h * held * tr.side
    gross = (px - tr.entry) * tr.side
    return replace(tr, status=status, exit_t=c.t, exit=px, r=(gross - fees - funding) / risk,
                   fees_r=fees / risk, funding_r=funding / risk)


def build_trades(symbol: str, timeframe: str, reports: list[AgentReport],
                 candles: list[Candle], params: LedgerParams | None = None) -> list[Trade]:
    p = params or LedgerParams()
    bar = tf_ms(timeframe)
    cs = sorted(candles, key=lambda c: c.t)
    out: list[Trade] = []
    for plan_id, seq in _plans(reports).items():
        first = seq[0][1]
        g = first.geometry
        side = 1 if g["side"] == "long" else -1
        tps = g["tp"]
        tr = Trade(
            id=f"{symbol}:{timeframe}:{plan_id}", symbol=symbol, timeframe=timeframe,
            plan_id=plan_id, side=side, entry_t=first.t_from, entry=float(g["entry"]),
            sl0=float(g["sl"]), tp1=float(tps[0]),
            tp2=float(tps[1]) if len(tps) > 1 else None, evidence=tuple(first.evidence))
        final = seq[-1][1]
        for c in cs:
            if c.t <= tr.entry_t:
                continue
            known = [o for r, o in seq if r.asof <= c.t]   # lo que el plan sabía al abrir
            sl = float((known[-1] if known else first).geometry["sl"])
            if (c.l <= sl) if side > 0 else (c.h >= sl):
                tr = _close(tr, c, bar, min(c.o, sl) if side > 0 else max(c.o, sl), "SL", p)
                break
            reach = c.h if side > 0 else c.l
            if (reach - tr.tp1) * side >= 0:
                hit2 = tr.tp2 is not None and (reach - tr.tp2) * side >= 0
                tr = _close(tr, c, bar, tr.tp2 if hit2 else tr.tp1, "TP2" if hit2 else "TP1", p)
                break
            st = final.geometry.get("status")
            if st in ("INVALIDADO", "EXPIRADO") and final.t_to == c.t:
                tr = _close(tr, c, bar, c.c, str(st), p)
                break
        out.append(tr)
    return out


def trade_at(tr: Trade, asof: int) -> Trade | None:
    """Vista de la operación en el instante `asof` (None si aún no había entrado)."""
    bar = tf_ms(tr.timeframe)
    if tr.entry_t + bar > asof:
        return None
    if tr.exit_t is not None and tr.exit_t + bar > asof:
        return replace(tr, status="ABIERTA", exit_t=None, exit=None, r=None, fees_r=None,
                       funding_r=None)
    return tr


_DDL = """
CREATE TABLE IF NOT EXISTS sim_trades (
    id VARCHAR PRIMARY KEY, symbol VARCHAR, timeframe VARCHAR, entry_t BIGINT,
    status VARCHAR, trade VARCHAR
)
"""


class SimLedger:
    """Persistencia DuckDB de las operaciones simuladas (misma conexión que `ReportStore`)."""

    def __init__(self, con, lock: threading.Lock) -> None:
        self._con, self._lock = con, lock
        with lock:
            con.execute(_DDL)

    def replace(self, symbol: str, timeframe: str, trades: list[Trade]) -> None:
        rows = [(t.id, t.symbol, t.timeframe, t.entry_t, t.status, json.dumps(t.to_json()))
                for t in trades]
        with self._lock:
            self._con.execute("DELETE FROM sim_trades WHERE symbol = ? AND timeframe = ?",
                              [symbol, timeframe])
            if rows:
                self._con.executemany("INSERT INTO sim_trades VALUES (?,?,?,?,?,?)", rows)

    def trades(self, symbol: str, timeframe: str) -> list[Trade]:
        with self._lock:
            rows = self._con.execute(
                "SELECT trade FROM sim_trades WHERE symbol = ? AND timeframe = ? "
                "ORDER BY entry_t", [symbol, timeframe]).fetchall()
        out = []
        for (raw,) in rows:
            d = json.loads(raw)
            d["evidence"] = tuple(d["evidence"])
            out.append(Trade(**d))
        return out
