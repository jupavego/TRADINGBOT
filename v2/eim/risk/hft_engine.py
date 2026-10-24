"""Motor de riesgo del carril HFT (T83): una decisión sellada por orden; determinista.

`evaluate` corre todas las reglas (`hft_rules`), sella la `HftDecision` con el mismo HMAC de
proceso que T29 y la deja en el `sink` (siempre). `verify_hft` es la única puerta que acepta el
ejecutor HFT (`HftGateway`): una decisión fabricada, alterada, vetada, de otra configuración,
caducada (`decision_ttl_ms`, 1 s en v1) o emitida con un kill-switch activo se rechaza; una que
reduce de verdad pasa aunque haya kill-switch (cerrar inventario siempre debe poder hacerse).

Dos kill-switches (`killswitch.py`): el global del proceso (T29) y el propio del carril, que solo
se apagan a mano. El del carril lo activan la reconciliación (divergencia), un 418 o el operador.
Sin observabilidad en la ruta caliente: el sink recibe cada decisión y el carril registra sus
incidentes (`hooks_service`). El coste p99 de decidir + verificar se mide en las pruebas contra
`HftRiskConfig.decision_budget_ms` (2 % de los 310 ms de T77).
"""

from __future__ import annotations

import hmac
from collections.abc import Callable

from eim.risk import hft_rules
from eim.risk.engine import _digest
from eim.risk.hft_config import HftRiskConfig
from eim.risk.hft_models import (
    AUTHORITY,
    HftAccount,
    HftDecision,
    HftMarket,
    HftOrder,
    hft_client_id,
)
from eim.risk.killswitch import KillSwitch, global_kill_switch
from eim.risk.models import Check

__all__ = ["AUTHORITY", "HftRiskEngine", "hft_kill_switch"]

_LANE = KillSwitch()


def hft_kill_switch() -> KillSwitch:
    """Kill-switch propio del carril HFT (uno por proceso; `attach` lo persiste)."""
    return _LANE


class HftRiskEngine:
    def __init__(self, config: HftRiskConfig, sink: Callable[[HftDecision], None] | None = None,
                 kill_switch: KillSwitch | None = None,
                 lane_kill: KillSwitch | None = None) -> None:
        self.config, self._sink = config, sink or (lambda _d: None)
        self.kill_switch = kill_switch or global_kill_switch()
        self.lane_kill = lane_kill or hft_kill_switch()

    def kills(self) -> tuple[hft_rules.Kill, hft_rules.Kill]:
        g, lane = self.kill_switch.state(), self.lane_kill.state()
        return (g["active"], g["reason"]), (lane["active"], lane["reason"])

    def blockers(self, market: HftMarket, account: HftAccount, now: int) -> list[Check]:
        """Bloqueos vigentes (solo los que fallan): el carril cancela todo si hay alguno."""
        kill, lane = self.kills()
        return [c for c in hft_rules.blockers(market, account, self.config, now, kill, lane)
                if not c.ok]

    def evaluate(self, order: HftOrder, market: HftMarket, account: HftAccount,
                 now: int) -> HftDecision:
        cfg = self.config
        kill, lane = self.kills()
        checks, reducing = hft_rules.evaluate(order, market, account, cfg, now, kill, lane)
        bad = [c for c in checks if not c.ok]
        px = order.price or market.mid or 0.0
        d = HftDecision(
            approved=not bad, order=order, mode=order.mode, decided_at=now,
            client_id=hft_client_id(order.order_id, order.symbol), notional=order.qty * px,
            reducing=reducing, rule=bad[0].rule if bad else "",
            reasons=tuple(f"{c.rule}: {c.detail}" for c in bad), checks=tuple(checks),
            config_version=cfg.version, config_sha256=cfg.sha256, account_source=account.source)
        d = d.model_copy(update={"seal": _digest(d)})
        self._sink(d)
        return d

    def verify_hft(self, d: HftDecision, now: int) -> None:
        """Lanza `PermissionError` si la decisión no autoriza enviar esa orden ahora mismo."""
        if not hmac.compare_digest(d.seal or "", _digest(d)):
            raise PermissionError("decisión HFT sin sello válido del motor de riesgo")
        if d.config_sha256 != self.config.sha256:
            raise PermissionError("decisión emitida con otra configuración de riesgo")
        if not d.approved:
            raise PermissionError(f"orden vetada por el riesgo HFT ({d.rule})")
        if not d.reducing and (self.kill_switch.active or self.lane_kill.active):
            raise PermissionError("kill-switch activo: solo se aceptan órdenes que reducen")
        if now < d.decided_at or now - d.decided_at > self.config.decision_ttl_ms:
            raise PermissionError("decisión de riesgo HFT caducada")
