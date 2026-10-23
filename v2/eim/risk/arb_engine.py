"""Motor de riesgo del arbitraje (T45): dimensiona o veta un plan de dos patas; determinista.

Corre todas las reglas (para listar todos los motivos), dimensiona si pasan y sella la
decisión con el mismo HMAC de proceso que T29. El arbitraje cuenta contra el margen y la
exposición de TODA la cuenta: el margen inicial en uso y el nocional bruto vienen del exchange
(incluyen el carril direccional) y una operación direccional activa en el mismo futuro veta
(en modo one-way las dos se netearían en una sola posición).
"""

from __future__ import annotations

import hmac
from collections.abc import Callable

from eim.core.authority import TradeProposal
from eim.observability import hooks
from eim.risk.arb_config import ArbRiskConfig
from eim.risk.arb_models import ArbAccount, ArbDecision, ArbPlan
from eim.risk.authority import gate_checks
from eim.risk.engine import DECISION_TTL_MS, _digest
from eim.risk.killswitch import KillSwitch, global_kill_switch
from eim.risk.models import Check

AUTHORITY = "risk.arb_engine"


def _c(rule: str, ok: bool, detail: str) -> Check:
    return Check(rule=rule, ok=ok, detail=detail)


def liq_move(leverage: float, mmr: float) -> float:
    """Movimiento adverso hasta la liquidación de una pata aislada a `leverage` (≈ 1/L − mmr)."""
    return 1.0 / leverage - mmr


def checks(plan: ArbPlan, acct: ArbAccount, cfg: ArbRiskConfig, kill: KillSwitch,
           now: int) -> list[Check]:
    ks = kill.state()
    markets = sorted(lg.market for lg in plan.legs)
    age = now - plan.asof
    same_asset = sum(1 for k in acct.open_arbs if k.endswith(f":{plan.asset}"))
    loss = 1 - acct.equity / acct.day_start_equity if acct.day_start_equity > 0 else 1.0
    move = liq_move(plan.leverage, cfg.mmr)
    out = [
        _c("kill-switch", not ks["active"],
           f"activo: {ks['reason']}" if ks["active"] else "inactivo"),
        _c("modo", plan.mode.value in cfg.allowed_modes, f"modo {plan.mode.value}"
           + ("" if plan.mode.value in cfg.allowed_modes else " no permitido (solo TESTNET)")),
        _c("estrategia", plan.strategy in cfg.strategies and markets == ["spot", "usdm"]
           and plan.spot.side > 0,
           f"{plan.strategy} · {plan.variant}" + (
               "" if plan.strategy in cfg.strategies else " no habilitada (T43)") + (
               "" if markets == ["spot", "usdm"] else " (T45 solo ejecuta spot + futuros)") + (
               "" if plan.spot.side > 0 else " (corto spot exige préstamo: fuera de T45)")),
        _c("vigencia", age <= cfg.max_quote_age_ms and now <= plan.valid_until,
           f"fotografía de hace {age / 1000:.0f} s (máx. {cfg.max_quote_age_ms / 1000:.0f} s)"
           + ("" if now <= plan.valid_until else "; oportunidad vencida")),
        _c("neto", plan.net_bps >= cfg.min_net_bps,
           f"neto estimado {plan.net_bps:.1f} pb (mín. {cfg.min_net_bps:g} pb)"),
        _c("abiertos", len(acct.open_arbs) < cfg.max_open_arbs and plan.key not in acct.open_arbs
           and same_asset < cfg.max_per_asset,
           f"{len(acct.open_arbs)} abiertos (máx. {cfg.max_open_arbs})" + (
               f"; ya hay {plan.key}" if plan.key in acct.open_arbs else "") + (
               f"; {same_asset} en {plan.asset} (máx. {cfg.max_per_asset})"
               if same_asset >= cfg.max_per_asset else "")),
        _c("conflicto direccional", plan.futures.symbol not in acct.directional_symbols,
           f"operación direccional activa en {plan.futures.symbol} (one-way: se netearían)"
           if plan.futures.symbol in acct.directional_symbols else "sin conflicto"),
        _c("pérdida diaria", loss < cfg.max_daily_loss,
           f"resultado del día {-loss:+.2%} (límite −{cfg.max_daily_loss:.2%})"),
        _c("liquidación", plan.leverage <= cfg.max_leverage and move >= cfg.min_liq_move,
           f"×{plan.leverage}: liquidación a {move:.1%} (mín. {cfg.min_liq_move:.0%}, "
           f"máx. ×{cfg.max_leverage})"),
    ]
    return out


def size(plan: ArbPlan, acct: ArbAccount, cfg: ArbRiskConfig) -> tuple[float, list[str]]:
    """Cantidad base aprobada (≤ la propuesta) y las notas de cada recorte."""
    s_px, f_px, lev = plan.spot.ref_price, plan.futures.ref_price, plan.leverage
    caps = {
        "propuesta del escáner": plan.qty,
        "nocional máximo por arbitraje": cfg.max_notional_usd / s_px,
        "margen total de la cuenta": (cfg.max_margin_frac * acct.futures_equity
                                      - acct.initial_margin) * lev / f_px,
        "saldo disponible en futuros": acct.futures_available * lev / f_px,
        "USDT disponible en spot": acct.spot_quote_free / (s_px * cfg.spot_cash_buffer),
        "exposición bruta total": (cfg.max_gross_frac * acct.equity - acct.gross_exposure)
        / (s_px + f_px),
        "tope de pérdida por pata incompleta": cfg.max_incident_loss_frac * acct.equity
        / (s_px * cfg.max_leg_loss_bps / 1e4),
    }
    qty = max(0.0, min(caps.values()))
    notes = [f"recortado por {k}: {plan.qty:.6g} → {v:.6g}" for k, v in caps.items()
             if k != "propuesta del escáner" and v < plan.qty and abs(v - qty) < 1e-12]
    return qty, notes


class ArbRiskEngine:
    def __init__(self, config: ArbRiskConfig, sink: Callable[[ArbDecision], None],
                 kill_switch: KillSwitch | None = None) -> None:
        self.config, self._sink = config, sink
        self.kill_switch = kill_switch or global_kill_switch()

    def evaluate(self, plan: ArbPlan, acct: ArbAccount, now: int,
                 proposal: TradeProposal | None = None) -> ArbDecision:
        """Con la `TradeProposal` (T114, toda ruta real) corren antes las reglas de la puerta."""
        cfg = self.config
        cs = checks(plan, acct, cfg, self.kill_switch, now)
        if proposal is not None:
            cs[:0] = gate_checks(proposal, AUTHORITY, now, symbol=plan.futures.symbol,
                                 side=plan.spot.side, stop=None, asof=plan.asof)
        fields: dict = {}
        reasons = [f"{c.rule}: {c.detail}" for c in cs if not c.ok]
        if not reasons:
            qty, notes = size(plan, acct, cfg)
            ok = qty > 0
            cs.append(_c("tamaño", ok, f"{qty:.6g} {plan.asset}" if ok else
                         "sin margen, saldo o exposición disponibles"))
            if ok:
                notional = qty * plan.spot.ref_price
                fields = dict(qty=qty, notional=notional, leverage=plan.leverage,
                              margin=qty * plan.futures.ref_price / plan.leverage,
                              max_leg_loss=notional * cfg.max_leg_loss_bps / 1e4,
                              max_leg_loss_bps=cfg.max_leg_loss_bps)
                reasons = notes
            else:
                reasons = ["tamaño: sin margen, saldo o exposición disponibles"]
        d = ArbDecision(approved=bool(fields), plan=plan, mode=plan.mode, decided_at=now,
                        reasons=tuple(reasons), checks=tuple(cs), config_version=cfg.version,
                        config_sha256=cfg.sha256, account_source=acct.source,
                        proposal=proposal, **fields)
        d = d.model_copy(update={"seal": _digest(d)})
        self._sink(d)
        hooks.risk_decided(d.as_record())
        return d

    def verify_arb(self, d: ArbDecision, now: int) -> None:
        """Lanza `PermissionError` si la decisión no autoriza abrir el arbitraje ahora."""
        if not hmac.compare_digest(d.seal or "", _digest(d)):
            raise PermissionError("decisión de arbitraje sin sello válido del motor de riesgo")
        if d.config_sha256 != self.config.sha256:
            raise PermissionError("decisión emitida con otra configuración de riesgo")
        if not d.approved or d.qty <= 0:
            raise PermissionError("arbitraje vetado por el motor de riesgo")
        if self.kill_switch.active:
            raise PermissionError("kill-switch activo: no se aceptan órdenes nuevas")
        if now < d.decided_at or now - d.decided_at > DECISION_TTL_MS:
            raise PermissionError("decisión de riesgo caducada")
