"""Puerta de riesgo de la copia (T42): toda orden que AUMENTA riesgo pasa por el motor T29.

La orden candidata se convierte en un plan: la posición propia de la moneda tras la orden,
con entrada = nuestro precio y stop de protección a `stop_frac` (el líder no declara stop; el
motor lo exige para dimensionar). Sin TP: sale cuando sale el líder. El motor corre todas sus
reglas con la configuración del carril de copia (`risk_copy_v1`, archivo versionado):
kill-switch, modo, geometría, vigencia de la señal (edad = ahora − hora de la ejecución del
líder), frescura del flujo del líder, pérdidas diaria/semanal, monedas abiertas,
enfriamiento y tamaño. Su tamaño es el MÁXIMO de la posición: el motor de copia recorta.
Reducir o cerrar no pasa por aquí: nunca se veta salir.

T114: la orden candidata entra como `TradeProposal` de la fuente `copy.leaders` (salida
`follow_leader`); la versión de la fuente y del perfil es la huella de `CopyParams`.

Cada subcuenta tiene su propio kill-switch: la simulación jamás toca el global (que detendría
la operación en papel de T31).
"""

from __future__ import annotations

from collections.abc import Callable

from eim.copytrading.copy_book import Account
from eim.copytrading.copy_params import CopyParams
from eim.core import Mode
from eim.core.authority import params_fingerprint
from eim.risk import (
    AccountState,
    KillSwitch,
    MarketContext,
    PlanRequest,
    RiskConfig,
    RiskDecision,
    RiskEngine,
    load_config,
)

TIMEFRAME = "copy"


def copy_config(p: CopyParams) -> RiskConfig:
    return load_config(version=p.risk_version)


class CopyRisk:
    def __init__(self, cfg: RiskConfig, p: CopyParams,
                 sink: Callable[[RiskDecision], None] | None = None,
                 kill: KillSwitch | None = None) -> None:
        self.cfg, self.p = cfg, p
        self.kill = kill or KillSwitch()
        self.decisions: list[RiskDecision] = []
        self.engine = RiskEngine(cfg, sink or self.decisions.append, self.kill)
        self.version = params_fingerprint(p)

    def account_state(self, acc: Account, coin: str, source: str) -> AccountState:
        return AccountState(
            equity=acc.equity(), day_start_equity=acc.day_start,
            week_start_equity=acc.week_start, peak_equity=max(acc.peak, acc.equity()),
            open_symbols=acc.open_coins(exclude=coin), consecutive_losses=acc.streak,
            last_loss_t=acc.last_loss_t, source=source)

    def check(self, *, plan_id: str, coin: str, side: int, price: float, signal_t: int,
              now: int, feed_t: int | None, acc: Account, source: str) -> RiskDecision:
        stop = price * (1 - side * self.p.stop_frac)
        plan = PlanRequest(symbol=coin, timeframe=TIMEFRAME, plan_id=plan_id, side=side,
                           entry=price, sl=stop, tp=(), rr=None, mode=Mode.SIMULADO,
                           asof=signal_t)
        market = MarketContext(now=now, bar_ms=self.p.risk_bar_ms, last_close_t=feed_t,
                               last_price=price)
        prop = plan.as_proposal("copy.leaders", f"replicador {self.version}",
                                reason=f"el líder aumentó {coin} ({source})",
                                max_age_ms=self.cfg.max_plan_age_bars * self.p.risk_bar_ms,
                                exit_mode="follow_leader")
        return self.engine.evaluate(plan, self.account_state(acc, coin, source), market,
                                    proposal=prop, profile_version=self.version)

    def check_kill(self, acc: Account, now: int) -> list[str]:
        """Regla automática de la subcuenta: caída ≥ límite → kill-switch (solo manual lo apaga)."""
        dd = 1 - acc.equity() / acc.peak if acc.peak > 0 else 0.0
        return self.kill.check_rules(self.cfg, now, drawdown=dd)
