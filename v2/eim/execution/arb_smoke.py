"""Prueba de extremo a extremo del arbitraje en la testnet de Binance (aceptación de T45).

    python -m eim.execution.arb_smoke [--symbol BTCUSDT] [--notional 300] [--hold 30]
                                      [--steps carry,fail,cut]

Pasos (cada uno debe terminar con la posición neta en cero y sin órdenes `eia-` abiertas):
- `carry`: abre un carry pequeño (largo spot / corto perpetuo) por el motor de riesgo y la
  puerta única, lo mantiene `--hold` segundos (reconciliación: margen, liquidación, funding) y
  lo cierra.
- `fail`: la segunda pata (futuros) se rechaza aquí mismo, sin llegar al exchange; la pata
  spot sí se ejecuta en la testnet y el ejecutor debe deshacerla.
- `cut`: la red hacia futuros se corta justo después de comprar spot; al volver, la
  reconciliación no debe dejar ninguna posición huérfana.
Plan sintético (no del escáner): es una prueba de fontanería. Solo testnet: los brokers
bloquean cualquier otro host. Claves: EIM_TESTNET_API_KEY/SECRET (futuros) y
EIM_SPOT_TESTNET_API_KEY/SECRET (spot; si faltan, las de futuros, válidas en la cuenta demo).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import httpx

from eim.core import Mode
from eim.execution.arb_book import ArbPosition
from eim.execution.arb_executor import ArbExecutor
from eim.execution.arb_recon import ArbReconciler
from eim.execution.arb_runner import ArbAutopilot
from eim.execution.binance_spot_testnet import DEFAULT_URL as SPOT_URL
from eim.execution.binance_spot_testnet import ENV_URL as SPOT_ENV_URL
from eim.execution.binance_spot_testnet import BinanceSpotTestnetBroker
from eim.execution.binance_testnet import DEFAULT_URL as FUT_URL
from eim.execution.binance_testnet import ENV_URL as FUT_ENV_URL
from eim.execution.binance_testnet import BinanceTestnetBroker
from eim.execution.broker import BrokerError
from eim.execution.gateway import ArbGateway
from eim.risk import KillSwitch
from eim.risk.arb_config import load_arb_config
from eim.risk.arb_engine import ArbRiskEngine
from eim.risk.arb_models import ArbLegPlan, ArbPlan

ORDER_SUFFIX = "/order"


class Faults(httpx.BaseTransport):
    """Transporte con fallos a pedido: `reject` rechaza los envíos de órdenes sin reenviarlos
    al exchange; `down` corta la red; `no_depth` simula la profundidad caída (orden del plan)."""

    def __init__(self) -> None:
        self.inner = httpx.HTTPTransport()
        self.reject = self.down = self.no_depth = False
        self.on_post: list = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("red cortada (prueba)", request=request)
        path = request.url.path
        if self.no_depth and path.endswith("/depth"):
            return httpx.Response(503, json={"code": -1001, "msg": "prueba"}, request=request)
        if self.reject and request.method == "POST" and path.endswith(ORDER_SUFFIX):
            return httpx.Response(400, json={"code": -2019, "msg": "rechazo simulado (prueba)"},
                                  request=request)
        resp = self.inner.handle_request(request)
        if request.method == "POST" and path.endswith(ORDER_SUFFIX):
            for fn in self.on_post:
                fn(request)
        return resp


def _say(msg: str) -> None:
    print(msg, flush=True)


class Smoke:
    def __init__(self, symbol: str, notional: float) -> None:
        self.symbol, self.notional = symbol, notional
        self.sf, self.ff = Faults(), Faults()
        self.spot = BinanceSpotTestnetBroker(client=httpx.Client(
            base_url=os.environ.get(SPOT_ENV_URL, SPOT_URL), transport=self.sf, timeout=10.0))
        self.fut = BinanceTestnetBroker(client=httpx.Client(
            base_url=os.environ.get(FUT_ENV_URL, FUT_URL), transport=self.ff, timeout=10.0))
        self.kill = KillSwitch()                  # propio: no toca el de la API
        self.cfg = load_arb_config()
        self.ex = ArbExecutor(self.spot, self.fut, self.kill,
                              journal=lambda k, d: _say(f"  [{k}] {d.get('msg', d)}"))
        self.engine = ArbRiskEngine(self.cfg, lambda d: _say(
            f"  [riesgo] {'aprobado' if d.approved else 'vetado'} {d.qty:.6g}: {list(d.reasons)}"),
            self.kill)
        self.gw = ArbGateway(self.engine, self.ex)
        self.recon = ArbReconciler(self.ex, self.cfg)
        self.pilot = ArbAutopilot(self.ex, self.recon, self.engine, store=None,  # type: ignore
                                  journal=lambda k, d: None)
        self.base = self.spot.base_asset(symbol)
        self.start_spot = self.spot.position(symbol).qty

    def plan(self, tag: str) -> ArbPlan:
        now = int(time.time() * 1000)
        sb, sa = self.spot.book_top(self.symbol) or (0.0, 0.0)
        fb, fa = self.fut.book_top(self.symbol) or (0.0, 0.0)
        if not sb or not fb:
            raise SystemExit(f"✖ libro vacío en la testnet ({self.symbol})")
        s_px, f_px = (sb + sa) / 2, (fb + fa) / 2
        qty = self.notional / s_px
        return ArbPlan(
            arb_id=f"smoke:{tag}:{now}", strategy="funding_carry",
            variant="largo spot / corto perpetuo", asset=self.base,
            legs=(ArbLegPlan(market="spot", symbol=self.symbol, side=1, ref_price=s_px,
                             depth_frac=1.0),
                  ArbLegPlan(market="usdm", symbol=self.symbol, side=-1, ref_price=f_px,
                             depth_frac=0.0)),
            qty=qty, notional=self.notional, leverage=3, net_edge=0.0, net_bps=10.0,
            score=1.0, horizon_h=24.0, funding_rate=1e-4, interval_h=8.0, exit_cost_bps=20.0,
            asof=now, valid_until=now + 15_000, source="plan sintético (prueba)",
            mode=Mode.TESTNET)

    def open(self, tag: str) -> ArbPosition:
        now = int(time.time() * 1000)
        plan = self.plan(tag)
        d = self.engine.evaluate(plan, self.pilot.account(now, None), now,
                                 proposal=plan.as_proposal("ops.smoke", "humo T45"))
        if not d.approved:
            raise SystemExit(f"✖ vetado: {d.reasons}")
        return self.ex.positions[self.gw.submit(d, int(time.time() * 1000))]

    def flat(self, label: str) -> bool:
        fut = self.fut.position(self.symbol).qty
        spot = self.spot.position(self.symbol).qty - self.start_spot
        left = [o.client_id for b in (self.spot, self.fut)
                for o in b.open_orders(self.symbol) if o.client_id.startswith("eia-")]
        step = self.spot.round_qty(self.symbol, abs(spot))
        ok = fut == 0 and step * (self.spot.book_top(self.symbol) or (0, 0))[0] < \
            self.spot.min_notional(self.symbol) and not left
        _say(f"{'✔' if ok else '✖'} {label}: futuros {fut:+.6g} · spot {spot:+.8g} {self.base} "
             f"(polvo bajo el mínimo tolerado) · órdenes eia- abiertas {left}")
        return ok

    def carry(self, hold: float) -> bool:
        pos = self.open("carry")
        _say(f"abierto {pos.key}: {pos.status} spot {pos.spot.held:+.6g} / futuros "
             f"{pos.fut.held:+.6g}")
        ok = pos.status == "ABIERTA"
        time.sleep(hold)
        rep = self.recon.run(int(time.time() * 1000))
        _say(f"reconciliación ok={rep.ok} · marca {pos.mark} · liquidación {pos.liq_price} "
             f"({pos.liq_move}) · margen {pos.margin_equity} · funding {pos.funding_received}")
        ok = ok and rep.ok and self.ex.close(pos, "fin de la prueba")
        return self.flat("carry abierto, mantenido y cerrado") and ok

    def fail(self) -> bool:
        self.ff.reject = self.ff.no_depth = True              # spot primero; futuros rechaza
        try:
            pos = self.open("fail")
        finally:
            self.ff.reject = self.ff.no_depth = False
        _say(f"pata fallida: {pos.status} · {pos.exit_reason} · pérdida {pos.incident_loss:.4f} "
             f"USD (tope {pos.max_leg_loss:.4f})")
        return self.flat("unwind de la pata fallida") and pos.status == "FALLIDA"

    def cut(self) -> bool:
        self.ff.no_depth = True

        def cut_after_buy(req: httpx.Request) -> None:
            if b"side=BUY" in req.content:
                self.ff.down = True
        self.sf.on_post.append(cut_after_buy)
        try:
            pos = self.open("cut")
        finally:
            self.sf.on_post.clear()
            self.ff.down = self.ff.no_depth = False
        _say(f"tras el corte: {pos.status} (spot {pos.spot.held:+.6g}, futuros "
             f"{pos.fut.held:+.6g})")
        rep = self.recon.run(int(time.time() * 1000))
        _say(f"reconciliación: {list(rep.actions)} {list(rep.issues)} → {pos.status}")
        return self.flat("sin posición huérfana tras cortar la red")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--notional", type=float, default=300.0,
                    help="USD por arbitraje (≥ 2 pasos de 0,001 BTC: mínimo de futuros 100 USDT)")
    ap.add_argument("--hold", type=float, default=30.0, help="segundos con el carry abierto")
    ap.add_argument("--steps", default="carry,fail,cut")
    a = ap.parse_args()
    try:
        s = Smoke(a.symbol, a.notional)
    except BrokerError as e:
        sys.exit(f"✖ testnet no disponible: {e}")
    if s.fut.position(a.symbol).qty:
        sys.exit(f"✖ ya hay posición de futuros en {a.symbol}: abortado")
    results = {}
    for step in a.steps.split(","):
        _say(f"— {step} —")
        results[step] = {"carry": lambda: s.carry(a.hold), "fail": s.fail, "cut": s.cut}[step]()
    _say("✔ PRUEBA SUPERADA" if all(results.values()) else f"✖ PRUEBA FALLIDA: {results}")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
