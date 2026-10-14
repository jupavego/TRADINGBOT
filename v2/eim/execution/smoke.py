"""Prueba de extremo a extremo en la testnet de Binance (aceptación de T30).

    python -m eim.execution.smoke --symbol BTCUSDT [--equity-cap 1000] [--hold 20]

Abre una operación PEQUEÑA con un plan sintético (no de los agentes: es una prueba de
fontanería), pasando por el motor de riesgo y la puerta única; comprueba SL/TP en el exchange,
reconcilia, la cierra de forma ordenada y verifica que no quedan posición ni órdenes. Solo
testnet: el broker bloquea cualquier otro host. Claves en EIM_TESTNET_API_KEY/SECRET.
"""

from __future__ import annotations

import argparse
import sys
import time

from eim.core import Mode
from eim.execution.binance_testnet import BinanceTestnetBroker
from eim.execution.broker import STOP, TAKE_PROFIT
from eim.execution.gateway import OrderGateway
from eim.execution.reconcile import Reconciler
from eim.execution.service import ExecutionService
from eim.risk import (
    AccountState,
    KillSwitch,
    MarketContext,
    MemorySink,
    PlanRequest,
    RiskEngine,
    load_config,
)

BAR = 3_600_000


def _now() -> int:
    return int(time.time() * 1000)


def _say(msg: str) -> None:
    print(msg, flush=True)


def run(symbol: str, equity_cap: float, hold_s: float, sl_frac: float, side: int) -> bool:
    cfg = load_config()
    broker = BinanceTestnetBroker()
    kill = KillSwitch()                       # propio: no toca el kill-switch de la API
    svc = ExecutionService(broker, kill)
    recon = Reconciler(svc, cfg)
    engine = RiskEngine(cfg, MemorySink(), kill)
    pre = recon.run((symbol,), _now())
    if pre.symbols and pre.symbols[0].exchange != 0:
        _say(f"✖ ya hay posición abierta en {symbol} ({pre.symbols[0].exchange}); abortado")
        return False
    price = broker.last_price(symbol)
    equity = min(broker.equity(), equity_cap)
    now = _now()
    sl = price * (1 - side * sl_frac)
    tp = price * (1 + side * 2 * sl_frac)
    plan = PlanRequest(symbol=symbol, timeframe="1h", plan_id=f"smoke:{now}", side=side,
                       entry=price, sl=sl, tp=(tp,), rr=2.0, mode=Mode.TESTNET, asof=now)
    account = AccountState(equity=equity, day_start_equity=equity, week_start_equity=equity,
                           peak_equity=equity, source=f"testnet (tope {equity_cap})")
    # Plan sintético: no hay agentes; se declaran «ok» solo para esta prueba de fontanería.
    market = MarketContext(now=now, bar_ms=BAR, last_close_t=now, last_price=price,
                           agent_status={a: "ok" for a in cfg.critical_agents})
    d = engine.evaluate(plan, account, market)
    if not d.approved:
        _say(f"✖ vetado: {d.reasons}")
        return False
    _say(f"riesgo: {d.size:.6g} {symbol} a {d.leverage:.0f}× (nocional {d.notional:,.0f}) "
         f"entrada≈{price:,.2f} SL {sl:,.2f} TP {tp:,.2f}")
    key = OrderGateway(engine, svc).submit(d, _now())
    tr = svc.trades[key]
    _say(f"operación {key}: {tr.status}, llenado {tr.filled}/{tr.qty} a {tr.avg_entry}")
    orders = broker.open_orders(symbol)
    kinds = sorted(o.kind for o in orders if o.client_id.startswith(key))
    _say(f"órdenes en el exchange: {kinds}")
    ok = STOP in kinds and TAKE_PROFIT in kinds
    time.sleep(hold_s)
    rep = recon.run((symbol,), _now())
    _say(f"reconciliación: ok={rep.ok} {[(r.internal, r.exchange) for r in rep.symbols]} "
         f"{list(rep.issues)}")
    ok = ok and rep.ok
    flat = svc.flatten(symbol, "fin de la prueba") if tr.status == "ABIERTA" else True
    end = recon.run((symbol,), _now())
    left = [o.client_id for o in broker.open_orders(symbol) if o.client_id.startswith(key)]
    pos = broker.position(symbol).qty
    _say(f"cierre: plano={flat} posición={pos} órdenes restantes={left} estado={tr.status} "
         f"({tr.exit_reason})")
    ok = ok and flat and pos == 0 and not left and end.ok
    for e in tr.events:
        _say(f"  · {e}")
    _say("✔ PRUEBA SUPERADA" if ok else "✖ PRUEBA FALLIDA")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--equity-cap", type=float, default=1000.0)
    ap.add_argument("--hold", type=float, default=10.0, help="segundos con la posición abierta")
    ap.add_argument("--sl-frac", type=float, default=0.01)
    ap.add_argument("--short", action="store_true")
    a = ap.parse_args()
    sys.exit(0 if run(a.symbol, a.equity_cap, a.hold, a.sl_frac, -1 if a.short else 1) else 1)


if __name__ == "__main__":
    main()
