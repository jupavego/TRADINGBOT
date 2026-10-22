"""T108 — Escalones por perfil (casos L y M del encargo) y fichas de instrumento por símbolo.

Caso L: cada perfil usa SUS umbrales y no contamina a los demás.
Caso M: una configuración inválida se detecta al construirla o al arrancar la mesa, nunca opera.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from eim.backtest.params import ZERO_COSTS
from eim.data.timeframes import FOCUS
from eim.paper.engine import Path
from eim.paper.ladder import LadderCosts, floor_qty, level_of, protect_price, simulate_ladder
from eim.paper.params import (
    LADDER_BY_PROFILE,
    PROFILES,
    ExecParams,
    LadderParams,
    ProfileParams,
    SymbolSpec,
    check_profiles,
    spec_for,
)
from tests.paper.helpers import M15, T0, bar, idea

E = 70_000.0
QTY = 0.1                      # 0,1 BTC: cada 100 USDT de precio = 10 USDT de beneficio
RISK_UNIT = 500.0              # distancia al SL
RISK_USD = QTY * RISK_UNIT     # 50 USDT arriesgados
ZERO = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)
BTC = spec_for("BTCUSDT")
BY_ID = {p.id: p for p in PROFILES}


def profile(pid: str) -> ProfileParams:
    return BY_ID[pid]


# --- caso L: cada perfil con lo suyo -------------------------------------------------------
def test_L_each_profile_resolves_its_own_steps_in_usdt():
    """Con el capital inicial, los umbrales en R dan exactamente los USDT del encargo."""
    got = {pid: profile(pid).ladder.steps(profile(pid).initial_equity * profile(pid).risk_pct)
           for pid in ("conservador", "moderado", "agresivo")}
    assert got["conservador"] == pytest.approx((5.0, 2.5))
    assert got["moderado"] == pytest.approx((10.0, 5.0))
    assert got["agresivo"] == pytest.approx((15.0, 7.5))


def test_L_steps_follow_the_risk_of_each_trade_not_a_fixed_amount():
    lp = LADDER_BY_PROFILE["moderado"]
    assert lp.steps(100.0) == pytest.approx((10.0, 5.0))
    assert lp.steps(250.0) == pytest.approx((25.0, 12.5))   # el doble y medio de riesgo


def test_L_control_profile_keeps_fixed_usdt_steps():
    """`ppp_btcusdt` es el control de T105 (◆5): sus escalones no dependen del riesgo."""
    lp = profile("ppp_btcusdt").ladder
    assert lp.basis == "usdt"
    assert lp.steps(50.0) == lp.steps(5_000.0) == (10.0, 5.0)


def test_L_same_trade_reaches_a_different_level_in_each_profile():
    """Con el MISMO riesgo (50 USDT) y +10 USDT de beneficio neto, cada perfil va por su escalón.

    Conservador y Moderado coinciden a propósito: en R sus umbrales son iguales (0,100 / 0,050) y
    lo que los separa es el riesgo que abren (0,5 % frente a 1 % del capital), no la escalera.
    """
    levels = {pid: level_of(10.0, *profile(pid).ladder.steps(RISK_USD))
              for pid in ("conservador", "moderado", "agresivo", "ppp_btcusdt")}
    assert levels == {"conservador": 3, "moderado": 3, "agresivo": 4, "ppp_btcusdt": 1}


def test_L_simulation_uses_the_profile_steps():
    """La simulación protege en los escalones del perfil, no en los del control."""
    bars = [(E, E + 100, E - 10, E + 90), (E + 90, E + 95, E + 60, E + 70)]
    path = Path([bar(T0 + i * M15, o, h, lo, c) for i, (o, h, lo, c) in enumerate(bars)])
    i = idea(side=1, entry=E, sl=E - RISK_UNIT, tp=E + 1500)
    cons = simulate_ladder(i, path, ZERO, profile("conservador").ladder, QTY, spec=BTC)
    ctrl = simulate_ladder(i, path, ZERO, profile("ppp_btcusdt").ladder, QTY, spec=BTC)
    assert cons.reason == "SLD" and cons.ladder["level"] == 3
    assert cons.ladder["first_usd"] == pytest.approx(5.0)
    assert ctrl.reason == "SLD" and ctrl.ladder["level"] == 1    # mismo camino, otro escalón
    assert ctrl.ladder["first_usd"] == pytest.approx(10.0)


def test_L_profiles_do_not_share_the_same_parameters():
    ids = ("conservador", "moderado", "agresivo")
    assert len({(profile(p).ladder.first_r, profile(p).ladder.step_r) for p in ids}) == 2
    assert all(profile(p).ladder.basis == "r" for p in ids)
    assert all(profile(p).ladder.be_with_ladder for p in ids)   # ◆3: BE+ convive


# --- fichas de instrumento (A6 de T106) ----------------------------------------------------
def test_symbol_specs_round_with_their_own_tick():
    """El SL se redondea con el tick del símbolo y siempre EN CONTRA del operador."""
    c = LadderCosts(0.0, 0.0, 0.0, 0.0)
    eth = spec_for("ETHUSDT")
    btc_price = protect_price(1, 1.0, 3_000.0, 10.137, 0.0, c, BTC.tick)
    eth_price = protect_price(1, 1.0, 3_000.0, 10.137, 0.0, c, eth.tick)
    assert btc_price == pytest.approx(3_010.2)      # tick 0,1: sube al siguiente décimo
    assert eth_price == pytest.approx(3_010.14)     # tick 0,01: mucho más fino
    assert eth_price <= btc_price


def test_symbol_specs_floor_quantity_with_their_own_step():
    assert floor_qty(0.0349, spec_for("BTCUSDT").qty_step) == pytest.approx(0.034)
    assert floor_qty(0.0349, 0.01) == pytest.approx(0.03)


def test_unknown_symbol_fails_with_its_reason():
    with pytest.raises(ValueError, match="SOLUSDT no declara tick"):
        spec_for("SOLUSDT")


# --- caso M: configuración inválida --------------------------------------------------------
@pytest.mark.parametrize("kw", [
    {"basis": "r", "first_r": 0.0, "step_r": 0.05},        # umbral nulo
    {"basis": "r", "first_r": 0.1, "step_r": -0.05},       # incremento negativo
    {"basis": "r"},                                        # sin umbrales en R
    {"basis": "usdt", "first_usdt": 0.0},                  # umbral nulo en USDT
    {"basis": "usdt", "step_usdt": -5.0},
    {"fixed_take_profit": True},                           # los tres prohibidos siguen vetados
    {"time_exit": True},
    {"real_money": True},
    {"slip_lookback": 0},
    {"max_drawdown": 1.5},
])
def test_M_invalid_ladder_params_are_rejected(kw):
    with pytest.raises(ValidationError):
        LadderParams(**kw)


@pytest.mark.parametrize("kw", [{"tick": 0.0}, {"qty_step": -1.0}, {"min_qty": 0.0}])
def test_M_invalid_symbol_spec_is_rejected(kw):
    with pytest.raises(ValidationError):
        SymbolSpec(**{"tick": 0.1, "qty_step": 0.001, "min_qty": 0.001, **kw})


def test_M_ladder_profile_without_params_is_rejected():
    base = {**profile("moderado").model_dump(), "exit_mode": "ladder", "ladder": None}
    with pytest.raises(ValidationError, match="exige parámetros de escalera"):
        ProfileParams(**base)


def test_M_profile_with_a_symbol_without_spec_is_rejected():
    with pytest.raises(ValidationError, match="no declara tick"):
        ProfileParams(**{**profile("moderado").model_dump(), "symbols": ("SOLUSDT",)})


def test_M_startup_check_fails_on_desk_symbol_without_spec():
    with pytest.raises(ValueError, match="conservador: SOLUSDT no declara tick"):
        check_profiles(PROFILES, ("BTCUSDT", "SOLUSDT"))


def test_M_startup_check_fails_on_repeated_ids():
    with pytest.raises(ValueError, match="identificador repetido"):
        check_profiles((profile("moderado"), profile("moderado")), ("BTCUSDT",))


def test_M_startup_check_passes_with_the_real_desk():
    check_profiles(PROFILES, FOCUS)


def test_eth_gets_fine_candles_because_a_ladder_profile_can_trade_it():
    """◆2: con escalera en los tres perfiles, el servicio sincroniza 1 min también de ETHUSDT
    (misma expresión que `desk._fine` y `service._sync`); sin ellas, las velas de 15 m ambiguas
    de ETH se resolverían solo con la regla conservadora."""
    for sym in FOCUS:
        fine = {p.ladder.fine_tf for p in PROFILES if p.ladder and sym in (p.symbols or (sym,))}
        assert fine == {"1m"}, sym
