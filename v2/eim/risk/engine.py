"""Motor de riesgo determinista: dimensiona o veta cada plan. Nada llega a ejecución sin él.

`RiskEngine.evaluate` corre todas las reglas (para listar todos los motivos), calcula el tamaño
si todas pasan, registra la decisión en el `sink` (siempre) y la firma con un sello HMAC de
proceso. `verify` es la única puerta que acepta la ejecución (`eim/execution/gateway.py`): una
decisión fabricada, alterada, vetada, vieja o emitida con el kill-switch activo se rechaza.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable

from eim.risk import rules
from eim.risk.config import RiskConfig
from eim.risk.killswitch import KillSwitch, global_kill_switch
from eim.risk.models import AccountState, Check, MarketContext, PlanRequest, RiskDecision
from eim.risk.sizing import Sizing, size_position

_KEY = secrets.token_bytes(32)          # vive solo en este proceso; no se persiste
DECISION_TTL_MS = 60_000                 # una aprobación caduca en 1 min


def _digest(d: RiskDecision) -> str:
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
            rules.check_data(market, cfg),
            rules.check_event(market),
            rules.check_daily_loss(account, cfg),
            rules.check_weekly_loss(account, cfg),
            rules.check_open_trades(plan, account, cfg),
            rules.check_cooldown(account, market, cfg),
        ]

    def evaluate(self, plan: PlanRequest, account: AccountState,
                 market: MarketContext) -> RiskDecision:
        checks = self._checks(plan, account, market)
        sized: Sizing | str | None = None
        if all(c.ok for c in checks):
            sized = ("capital ≤ 0" if account.equity <= 0 else
                     size_position(plan.side, plan.entry, plan.sl, account.equity, self.config))
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
            decided_at=market.now, reasons=tuple(reasons), checks=tuple(checks),
            config_version=self.config.version, config_sha256=self.config.sha256,
            account_source=account.source, **fields)
        d = d.model_copy(update={"seal": _digest(d)})
        self._sink(d)
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
