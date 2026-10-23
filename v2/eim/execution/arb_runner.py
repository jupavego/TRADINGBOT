"""Selector automático de arbitraje en testnet (T45): un ciclo cada `interval_s`.

1. Reconciliación (órdenes, descubiertos, funding, margen, liquidación). Sin conexión: nada más.
2. Gestión de lo abierto (`manage.decide`): rebalanceo, cierre por rentabilidad agotada,
   vencimiento, tenencia o riesgo. Con el kill-switch activo: cierre urgente de todo.
3. Apertura: toma la fotografía vigente del escáner T38 (`ArbStore`), repite `select` a la hora
   real, filtra por estrategias habilitadas (Viable/Marginal en T43) y sin posición de la misma
   estrategia y activo; evalúa cada candidato con el motor de riesgo (cuenta total: margen y
   exposición de toda la cuenta) en orden de puntuación y ejecuta el primero aprobado — el de
   mayor neto ajustado por riesgo que el riesgo admite. Como mucho uno por ciclo.
Todo queda en la bitácora (`journal`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from eim.arbitrage import DEFAULT_PARAMS, ArbParams, select
from eim.arbitrage.common import mid
from eim.arbitrage.live.manage import PositionView, decide
from eim.arbitrage.live.plan import candidates
from eim.arbitrage.scan import STRATEGIES
from eim.core import ArbMarket, CostModel
from eim.core.authority import params_fingerprint
from eim.data.arb_store import ArbStore
from eim.execution.arb_book import CLOSING, FAILED, OPEN, ArbPosition
from eim.execution.arb_executor import ArbExecutor
from eim.execution.arb_recon import ArbReconciler
from eim.execution.broker import BrokerError
from eim.execution.gateway import ArbGateway
from eim.risk.arb_engine import ArbRiskEngine
from eim.risk.arb_models import ArbAccount, ArbDecision

DAY_MS = 86_400_000
FAIL_COOLDOWN_MS = 3_600_000   # tras una apertura fallida, esa estrategia y activo esperan


def decision_row(d: ArbDecision) -> dict[str, Any]:
    p = d.plan
    return {"arb": p.arb_id, "strategy": p.strategy, "variant": p.variant, "asset": p.asset,
            "approved": d.approved, "qty": d.qty, "notional": round(d.notional, 2),
            "net_bps": round(p.net_bps, 2), "score": round(p.score, 3),
            "reasons": list(d.reasons), "config": d.config_version}


class ArbAutopilot:
    def __init__(self, ex: ArbExecutor, recon: ArbReconciler, engine: ArbRiskEngine,
                 store: ArbStore, journal: Callable[[str, dict], None],
                 params: ArbParams = DEFAULT_PARAMS, cost_model: CostModel | None = None,
                 directional_symbols: Callable[[], tuple[str, ...]] = tuple,
                 clock: Callable[[], int] = lambda: int(time.time() * 1000)) -> None:
        self.ex, self.recon, self.engine, self.store = ex, recon, engine, store
        self.journal, self.params, self.cm = journal, params, cost_model or CostModel()
        self.directional_symbols, self.clock = directional_symbols, clock
        self.gateway = ArbGateway(engine, ex)
        self.version = f"selector {params_fingerprint(params)}"   # versión de la fuente (T114)
        self.last: dict[str, Any] | None = None

    # --- cuenta total ------------------------------------------------------------
    def account(self, now: int, mkt: ArbMarket | None) -> ArbAccount:
        ex = self.ex
        fs = ex.fut.account_summary()
        usdt = ex.spot.free("USDT")
        spot_val = 0.0
        for p in ex.active():
            book = mkt.spot_books.get(p.spot.symbol) if mkt else None
            ref = next(lg for lg in p.plan["legs"] if lg["market"] == "spot")["ref_price"]
            px = p.spot_px or (mid(book) if book else None) or float(ref)
            spot_val += max(p.spot.held, 0.0) * px
        equity = fs["equity"] + usdt + spot_val
        d0 = now - now % DAY_MS
        if ex.day is None or ex.day[0] != d0:          # persistido con el libro
            ex.day = (d0, equity)
        return ArbAccount(
            equity=equity, day_start_equity=ex.day[1], futures_equity=fs["equity"],
            futures_available=fs["available"], spot_quote_free=usdt,
            initial_margin=fs["initial_margin"], gross_exposure=fs["gross"] + spot_val,
            open_arbs=tuple(sorted(ex.open_keys())),
            directional_symbols=tuple(self.directional_symbols()),
            source="TESTNET: futuros (cuenta completa) + spot USDT + spot de arbitrajes")

    # --- gestión de lo abierto ---------------------------------------------------
    def _view(self, pos: ArbPosition, mkt: ArbMarket | None) -> PositionView:
        basis = None
        if mkt is not None:
            sb, fb = mkt.spot_books.get(pos.spot.symbol), mkt.futures_books.get(pos.fut.symbol)
            s, f = (mid(sb) if sb else None), (mid(fb) if fb else None)
            basis = (f - s) / s * 1e4 if s and f else None
            prem = mkt.premium.get(pos.fut.symbol)
            if (prem is not None and pos.strategy == "funding_carry"
                    and mkt.asof > pos.funding_seen_t):    # una vez por fotografía nueva
                pos.funding_seen_t = mkt.asof
                pos.negative_funding_streak = (pos.negative_funding_streak + 1
                                               if prem.funding_rate < 0 else 0)
        pl = pos.plan
        return PositionView(
            strategy=pos.strategy, opened_at=pos.opened_at or pos.created_at,
            horizon_h=float(pl["horizon_h"]), delivery_t=pl.get("delivery_t"), qty=pos.hedged,
            leverage=pos.leverage, mark=pos.mark, margin_equity=pos.margin_equity,
            liq_move=pos.liq_move, basis_bps=basis,
            exit_cost_bps=float(pl.get("exit_cost_bps") or 0.0),
            negative_funding_streak=pos.negative_funding_streak,
            kill_active=self.ex.kill.active)

    def manage(self, mkt: ArbMarket | None, now: int, rep: dict[str, Any]) -> None:
        cfg = self.engine.config
        for pos in list(self.ex.active()):
            if pos.status == CLOSING:                   # cierre interrumpido: se reanuda
                self.ex.close(pos, pos.exit_reason or "reanudar cierre")
                rep["actions"].append(f"{pos.key}: cierre reanudado")
                continue
            if pos.status != OPEN:
                continue
            act = decide(self._view(pos, mkt), cfg, now)
            if act.kind == "close":
                flat = self.ex.close(pos, act.reason, act.urgent)
                rep["actions"].append(f"{pos.key}: cierre ({act.reason}) → "
                                      f"{'plano' if flat else 'pendiente'}")
            elif act.kind == "rebalance":
                self.ex.rebalance(pos, act)
                rep["actions"].append(f"{pos.key}: rebalanceo ({act.reason})")
        self.ex.persist()

    # --- ciclo -------------------------------------------------------------------
    def cycle(self, now: int | None = None) -> dict[str, Any]:
        now = self.clock() if now is None else now
        rep: dict[str, Any] = {"t": now, "actions": [], "decisions": [], "opened": None,
                               "skipped": None}
        r = self.recon.run(now)
        rep["recon"] = r.to_json()
        try:
            if not r.connected:
                rep["skipped"] = "sin conexión con el exchange"
                return self._end(rep)
            mkt = self.store.latest()
            self.manage(mkt, now, rep)
            if self.ex.kill.active:
                rep["skipped"] = "kill-switch activo: no se abre nada"
                return self._end(rep)
            self.open_best(mkt, now, rep)
        except BrokerError as e:
            rep["skipped"] = f"fallo del exchange: {e}"
        return self._end(rep)

    def open_best(self, mkt: ArbMarket | None, now: int, rep: dict[str, Any]) -> None:
        cfg, p = self.engine.config, self.params
        if mkt is None or now - mkt.asof > cfg.max_quote_age_ms:
            rep["skipped"] = "sin fotografía vigente del escáner"
            return
        opps = [o for fn in STRATEGIES for o in fn(mkt, self.cm, p).opportunities]
        failed = {f"{x.strategy}:{x.asset}" for x in self.ex.positions.values()
                  if x.status == FAILED and now - (x.closed_at or 0) < FAIL_COOLDOWN_MS}
        plans = candidates(select(opps, p, now), mkt, cfg.strategies,
                           self.ex.open_keys() | failed, int(p.perp_leverage))
        if not plans:
            rep["skipped"] = "ninguna oportunidad seleccionada y ejecutable"
            return
        acct = self.account(now, mkt)
        for plan in plans:
            d = self.engine.evaluate(plan, acct, now,
                                     proposal=plan.as_proposal("arb.scanner", self.version))
            rep["decisions"].append(decision_row(d))
            if d.approved:
                rep["opened"] = self.gateway.submit(d, now)
                return
        rep["skipped"] = "el riesgo vetó todos los candidatos"

    def _end(self, rep: dict[str, Any]) -> dict[str, Any]:
        self.last = rep
        self.journal("ciclo", {k: rep[k] for k in ("actions", "decisions", "opened", "skipped")}
                     | {"recon_ok": rep.get("recon", {}).get("ok")})
        return rep
