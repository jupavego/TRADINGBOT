"""Entrada propia del perfil PPP: solo con confluencia completa; se abstiene si algo falla."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from eim.paper.catalog import CATALOG
from eim.paper.params import FAMILIES, PPP_ID, PROFILES
from eim.paper.strategies_ppp import SL_ATR, ppp_tendencia


def ind(side: int = 1, **over):
    base = {"adx": [30.0, 30.0], "pdi": [25.0, 25.0] if side > 0 else [10.0, 10.0],
            "mdi": [10.0, 10.0] if side > 0 else [25.0, 25.0], "st_dir": [side, side],
            "ema25": [99.0, 99.0] if side > 0 else [101.0, 101.0], "c": [100.0, 100.0],
            "hist": [side * 1.0, side * 1.0], "rsi": [60.0, 60.0] if side > 0 else [40.0, 40.0]}
    return SimpleNamespace(**{**base, **over})


def ctx(side: int = 1, **over):
    c = {"close": 100.0, "atr": 1.0, "htf_dir": side,
         "syn": {"bias": 0.5 * side, "conf": 0.6, "agree": 0.7}}
    return {**c, **over}


@pytest.mark.parametrize("side", [1, -1])
def test_full_confluence_gives_an_idea(side):
    d = ppp_tendencia(ctx(side), ind(side), 1)
    assert d is not None and d.side == side
    assert abs(d.sl - 100.0) == pytest.approx(SL_ATR) and (d.sl - 100.0) * side < 0
    assert (d.tp - 100.0) * side > 0


@pytest.mark.parametrize("c,x", [
    (ctx(htf_dir=0), ind()),                                           # sin tendencia mayor
    (ctx(htf_dir=-1), ind()),                                          # contra el marco mayor
    (ctx(syn={"bias": 0.1, "conf": 0.6, "agree": 0.7}), ind()),        # síntesis débil
    (ctx(syn={"bias": -0.5, "conf": 0.6, "agree": 0.7}), ind()),       # síntesis contraria
    (ctx(syn={"bias": 0.5, "conf": 0.2, "agree": 0.7}), ind()),        # poca confianza
    (ctx(syn={"bias": 0.5, "conf": 0.6, "agree": 0.3}), ind()),        # agentes en desacuerdo
    (ctx(), ind(adx=[10.0, 10.0])),                                    # sin tendencia (ADX)
    (ctx(), ind(pdi=[5.0, 5.0], mdi=[25.0, 25.0])),                    # +DI/−DI en contra
    (ctx(), ind(rsi=[85.0, 85.0])),                                    # agotado
    (ctx(), ind(rsi=[float("nan")] * 2)),                              # dato faltante
    (ctx(syn=None), ind()),                                            # sin síntesis
])
def test_abstains_when_anything_is_missing(c, x):
    assert ppp_tendencia(c, x, 1) is None


def test_registered_and_traded_only_by_the_ladder_profile():
    assert CATALOG["ppp_tendencia"].family == "ppp" and "ppp" in FAMILIES
    assert CATALOG["ppp_tendencia"].runs_in("1h") and not CATALOG["ppp_tendencia"].runs_in("15m")
    for p in PROFILES:
        assert ("ppp" in p.families) == (p.id == PPP_ID)
