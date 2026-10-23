"""Motor de riesgo determinista: dimensiona o veta cada plan. Nada llega a ejecución sin él.

`RiskEngine.evaluate` corre todas las reglas (para listar todos los motivos), calcula el tamaño
si todas pasan, registra la decisión en el `sink` (siempre) y la firma con un sello HMAC de
proceso. Con la `TradeProposal` de la fuente (T114, toda ruta real) corren antes las reglas de la
puerta única (`authority.gate_checks`: fuente registrada, plan = propuesto, caducidad).
`verify` es la única puerta que acepta la ejecución (`eim/execution/gateway.py`): una
decisión fabricada, alterada, vetada, vieja o emitida con el kill-switch activo se rechaza.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable

from pydantic import BaseModel

from eim.core.authority import TradeProposal
from eim.observability import hooks
from eim.risk import rules
from eim.risk.authority import gate_checks
from eim.risk.config import RiskConfig
from eim.risk.killswitch import KillSwitch, global_kill_switch
from eim.risk.models import AccountState, Check, MarketContext, PlanRequest, RiskDecision
from eim.risk.sizing import Sizing, size_position

_KEY = secrets.token_bytes(32)          # vive solo en este proceso; no se persiste
DECISION_TTL_MS = 60_000                 # una aprobación caduca en 1 min
AUTHORITY = "risk.engine"                # id de esta autoridad en `eim/risk/authority.py`


def _digest(d: BaseModel) -> str:
    """Sello HMAC de proceso de una decisión (también la de arbitraje, T45)."""
    body = d.model_dump_json(exclude={"seal"}).encode()
    return hmac.new(_KEY, body, hashlib.sha256).hexdigest()


class MemorySink:
    """Registro en memoria (tests y uso sin base de datos)."""

    def __init__(self) -> None:
        self.decisions: list[RiskDecision] = []

    def __call__(self, d: RiskDecision) -> None:
        self.decisions.append(d)


class RiskEngine:
    def __init__(self, config: RiskConfig, sink: Callable[[RiskDecision], None],
                 kill_switch: KillSwitch | None = None) -> None:
        self.config = config
        self._sink = sink
        self.kill_switch = kill_switch or global_kill_switch()

    def _checks(self, plan: PlanRequest, account: AccountState,
                market: MarketContext) -> list[Check]:
        cfg, ks = self.config, self.kill_switch
        kill = ks.state()
        return [
            Check(rule="kill-switch", ok=not kill["active"],
                  detail=f"activo: {kill['reason']}" if kill["active"] else "inactivo"),
            rules.check_mode(plan, cfg),
            rules.check_plan(plan, cfg),
            rules.check_freshness(plan, market, cfg),
            rules.check_data(market, cfg),
            rules.check_event(market),
            rules.check_daily_loss(account, cfg),
            rules.check_weekly_loss(account, cfg),
            rules.check_open_trades(plan, account, cfg),
            rules.check_cooldown(account, market, cfg),
        ]

    def evaluate(self, plan: PlanRequest, account: AccountState, market: MarketContext,
                 proposal: TradeProposal | None = None,
                 profile_version: str | None = None) -> RiskDecision:
        checks = self._checks(plan, account, market)
        if proposal is not None:
            checks[:0] = gate_checks(proposal, AUTHORITY, market.now, symbol=plan.symbol,
                                     side=plan.side, stop=plan.sl, asof=plan.asof)
        sized: Sizing | str | None = None
        if all(c.ok for c in checks):
            entry = market.last_price or plan.entry    # se ejecutaría al precio actual
            scale = self.config.event_size_factor if market.event_window else 1.0
            why = market.event_reason
            ask = proposal.max_risk_frac if proposal else None
            if ask is not None and ask < self.config.risk_per_trade * scale:
                # la fuente pide menos riesgo: se concede el menor (nunca más que la política)
                scale = ask / self.config.risk_per_trade
                why = "tope pedido por la fuente" + (f" (y {why})" if why else "")
            sized = ("capital ≤ 0" if account.equity <= 0 else
                     size_position(plan.side, entry, plan.sl, account.equity, self.config,
                                   scale, why))
            checks.append(Check(rule="tamaño", ok=isinstance(sized, Sizing),
                                detail=sized if isinstance(sized, str) else
                                f"{sized.size:.6g} a {sized.leverage:.0f}×"))
        reasons = [f"{c.rule}: {c.detail}" for c in checks if not c.ok]
        fields: dict = {}
        if isinstance(sized, Sizing):
            fields = dict(size=sized.size, notional=sized.notional, leverage=sized.leverage,
                          margin=sized.margin, risk_amount=sized.risk_amount,
                          risk_frac=sized.risk_amount / account.equity,
                          liquidation_price=sized.liquidation_price)
            reasons = list(sized.notes)
        d = RiskDecision(
            approved=isinstance(sized, Sizing), symbol=plan.symbol, timeframe=plan.timeframe,
            plan_id=plan.plan_id, side=plan.side, mode=plan.mode, asof=plan.asof,
            decided_at=market.now, entry=plan.entry, sized_at=market.last_price or plan.entry,
            sl=plan.sl, tp=plan.tp,
            reasons=tuple(reasons), checks=tuple(checks),
            config_version=self.config.version, config_sha256=self.config.sha256,
            account_source=account.source, proposal=proposal, authority=AUTHORITY,
            profile_version=profile_version,
            exit_mode=proposal.exit_mode if proposal else None, **fields)
        d = d.model_copy(update={"seal": _digest(d)})
        self._sink(d)
        hooks.risk_decided(d)
        return d

    def verify(self, d: RiskDecision, now: int) -> None:
        """Lanza `PermissionError` si la decisión no autoriza una orden ahora mismo."""
        if not hmac.compare_digest(d.seal or "", _digest(d)):
            raise PermissionError("decisión sin sello válido del motor de riesgo")
        if d.config_sha256 != self.config.sha256:
            raise PermissionError("decisión emitida con otra configuración de riesgo")
        if not d.approved or d.size <= 0:
            raise PermissionError("plan vetado por el motor de riesgo")
        if self.kill_switch.active:
            raise PermissionError("kill-switch activo: no se aceptan órdenes nuevas")
        if now < d.decided_at or now - d.decided_at > DECISION_TTL_MS:
            raise PermissionError("decisión de riesgo caducada")
