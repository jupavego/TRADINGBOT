"""T177: las reglas de los reemplazos hacen lo que dice su expediente, sin red ni disco.

Son 16 formulados y 15 en la familia: `elliott_tendencia_dow` cayó en el examen (4,7 operaciones al
mes en tres días) y su plaza quedó vacía.
"""

from __future__ import annotations

import pytest

from eim.nursery.prospect import load_dossiers, load_prospects
from eim.nursery.rules import MODULES
from eim.nursery.rules.base import View

NEW = {"ema_precio_200", "ema_cruce_21_55", "ema_retroceso_12h", "tec_acuerdo_tres_marcos",
       "tec_rsi_giro", "tec_compresion_bb_12h", "vwap_reversion_1h", "vwap_quincenal",
       "elliott_oscilacion", "elliott_dow",
       "estructura_ruptura_sc02", "estructura_cambio_sc04", "niveles_redondos", "lit_consenso_4h",
       "bots_contrario"}
# Los que repiten la regla de un descartado con otra plantilla o marco (lección de T169).
SAME_RULE = {"ema_retroceso_12h": "ema_retroceso", "tec_compresion_bb_12h": "tec_compresion_bb",
             "vwap_reversion_1h": "vwap_reversion", "lit_consenso_4h": "lit_consenso"}


def _view(agent: str, rows: list[dict], close: float | None = None) -> View:
    """Filas de variables con prefijo `metrics.` quitado, de la más antigua a la actual."""
    declared = frozenset(MODULES[agent].EXPOSES)
    return View(agent, declared, tuple(rows), close=close, atr=None)


def _rule(pid: str):
    return next(p for p in load_prospects() if p.id == pid).rule


def test_the_replacements_and_the_discarded_match():
    docs = load_dossiers()
    disc = {p["id"]: p for d in docs.values() for p in d.get("discarded", [])}
    news = {p["id"]: p for d in docs.values() for p in d.get("prospects", []) if "replaces" in p}
    t169 = {k: p for k, p in disc.items() if p["discarded_by"] == "T169"}
    assert set(news) == NEW and len(t169) == 16
    assert set(disc) - set(t169) == {"elliott_tendencia_dow"}
    assert {p["replaces"] for p in news.values()} == set(t169) - {"regimen_tramo"}
    for pid, p in disc.items():
        assert p["reasons"] and p["fingerprint"]
        if p["replaced_by"] in news:
            assert news[p["replaced_by"]]["replaces"] == pid
    # Su reemplazo cayó en el examen de T177: la plaza queda vacía (PLAN/T177.md, punto 8).
    assert t169["regimen_tramo"]["replaced_by"] == "elliott_tendencia_dow"
    assert disc["elliott_tendencia_dow"]["discarded_by"] == "T177"
    assert disc["elliott_tendencia_dow"]["replaced_by"] is None
    # `regime` no llega a la cadencia en ningún marco: excluido, su plaza base pasa a `elliott`.
    assert docs["regime"]["status"] == "excluido" and not docs["regime"]["prospects"]
    assert news["bots_contrario"]["replaces"] == "regimen_tramo_estable"
    ids = {p.id for p in load_prospects()}
    assert NEW <= ids and not (set(disc) & ids) and len(ids) == 42


def test_reused_rules_are_new_prospects_with_their_own_fingerprint():
    for new, old in SAME_RULE.items():
        p = next(x for x in load_prospects() if x.id == new)
        mod = MODULES[p.agent_id]
        assert mod.RULES[new] is mod.RULES[old]
        assert p.fingerprint and p.account.startswith(new + "@")


def test_ema_price_against_its_200_and_the_21_55_cross():
    r = _rule("ema_precio_200")
    assert r(_view("ema", [{"variables.EMA_200": 100.0}], close=101.0), {}).enter == 1
    assert r(_view("ema", [{"variables.EMA_200": 100.0}], close=99.0), {}).hold == -1
    c = _rule("ema_cruce_21_55")
    up = c(_view("ema", [{"variables.SPREAD_21_55": -0.2}, {"variables.SPREAD_21_55": 0.1}]), {})
    assert up.enter == 1 and up.hold == 1
    stay = c(_view("ema", [{"variables.SPREAD_21_55": 0.2}, {"variables.SPREAD_21_55": 0.1}]), {})
    assert stay.enter == 0 and stay.hold == 1


def test_three_frames_use_15m_not_the_missing_daily():
    r = _rule("tec_acuerdo_tres_marcos")
    row = {"frames.15m.bias": 0.3, "frames.1h.bias": 0.2, "frames.4h.bias": 0.4}
    assert r(_view("technical", [row]), {"mtf_neutral": 0.1}).enter == 1
    assert r(_view("technical", [row | {"frames.15m.bias": 0.05}]), {"mtf_neutral": 0.1}).enter == 0


def test_rsi_turn_needs_no_adx():
    r = _rule("tec_rsi_giro")
    assert r(_view("technical", [{"votes.RSI": 0.6}, {"votes.RSI": 0.0}]), {}).enter == 1
    assert r(_view("technical", [{"votes.RSI": -0.6}, {"votes.RSI": 0.0}]), {}).enter == -1
    assert r(_view("technical", [{"votes.RSI": 0.6}, {"votes.RSI": 0.5}]), {}).enter == 0


def test_fortnight_vwap_needs_the_slope_on_its_side():
    r = _rule("vwap_quincenal")
    row = {"close": 101.0, "periods.quincenal.vwap": 100.0, "periods.quincenal.slope_pct": 0.1}
    assert r(_view("vwap", [row]), {}).enter == 1
    flat = r(_view("vwap", [row | {"periods.quincenal.slope_pct": -0.1}]), {})
    assert flat.enter == 0 and flat.hold == 1


def test_zigzag_swing_and_dow_filter():
    osc, dow = _rule("elliott_oscilacion"), _rule("elliott_dow")
    h = {"pivots[-1].type": "H", "pivots[-1].price": 110.0, "pivots[-3].price": 120.0}
    low_hi = {"pivots[-1].type": "L", "pivots[-1].price": 95.0, "pivots[-3].price": 90.0}
    low_lo = low_hi | {"pivots[-1].price": 85.0}
    assert osc(_view("elliott", [h, low_hi]), {}).enter == 1
    assert osc(_view("elliott", [low_hi, low_hi]), {}).enter == 0
    assert osc(_view("elliott", [h, low_lo]), {}).hold == 1
    assert dow(_view("elliott", [h, low_hi]), {}).enter == 1          # mínimo más alto
    lower = dow(_view("elliott", [h, low_lo]), {})
    assert lower.enter == 0 and lower.hold == 1                       # mínimo más bajo: no entra
    pull = MODULES["elliott"].RULES["elliott_tendencia_dow"]   # dada de baja, la regla queda
    assert pull(_view("elliott", [h, low_lo]), {}).enter == -1        # mínimo más bajo: vende
    assert pull(_view("elliott", [h, low_hi]), {}).enter == 0         # mínimo más alto: nada
    hh = {"pivots[-1].type": "H", "pivots[-1].price": 130.0, "pivots[-3].price": 120.0}
    assert pull(_view("elliott", [low_hi, hh]), {}).enter == 1        # máximo más alto: compra


def test_structure_scenarios_without_the_uncalibrated_conviction():
    sc02, sc04 = _rule("estructura_ruptura_sc02"), _rule("estructura_cambio_sc04")
    prev = {"scenario": "SC-05_CONSOLIDATION", "bias": 0.2, "conviction": 47.0}
    brk = {"scenario": "SC-02_BREAKOUT", "bias": 0.3, "conviction": 47.0}
    chg = {"scenario": "SC-04_STRUCTURAL_CHANGE", "bias": -0.4, "conviction": 30.0}
    assert sc02(_view("structure", [prev, brk]), {}).enter == 1
    assert sc02(_view("structure", [brk, brk]), {}).enter == 0
    assert sc04(_view("structure", [prev, chg]), {}).enter == -1
    assert sc04(_view("structure", [chg]), {}).enter == 0             # sin vela anterior


@pytest.mark.parametrize(("lo", "hi", "enters"), [(59_950.0, 60_100.0, True),
                                                  (60_100.0, 60_400.0, False)])
def test_round_number_inside_the_support_zone(lo, hi, enters):
    r = _rule("niveles_redondos")
    row = {"atr": 400.0, "dist_support": 100.0, "dist_resistance": 900.0,
           "zones[].p_low": [lo, 61_500.0], "zones[].p_high": [hi, 61_700.0],
           "zones[].touches": [3, 3]}
    p = {"touch_atr": 0.5, "min_touches": 2, "paso_usd": 1000}
    assert r(_view("levels", [row], close=hi + 100.0), p).enter == (1 if enters else 0)


def test_against_a_freshly_formed_bot_unanimity():
    r = _rule("bots_contrario")
    p = {"min_bots": 3}
    split = {"bots[].stance": [1, -1, 1], "bots[].status": ["ok"] * 3, "disagreement": 0.4}
    longs = {"bots[].stance": [1, 1, 1], "bots[].status": ["ok"] * 3, "disagreement": 0.0}
    assert r(_view("bots", [split, longs]), p).enter == -1            # se forma: en contra
    assert r(_view("bots", [longs, longs]), p).enter == 0             # ya estaba formada
    two = longs | {"bots[].status": ["ok", "ok", "stale"]}
    assert r(_view("bots", [split, two]), p).enter == 0               # menos de min_bots
