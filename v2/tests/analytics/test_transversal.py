"""T164 (`transversal_v1`): se mide como dice el pre-registro y la puerta va primero."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from eim.analytics import transversal as tv

D0 = pd.Timestamp("2020-01-01")


def panel(years: float = 7.0, n: int = 40, seed: int = 1, carry_edge: float = 0.0) -> tv.Panel:
    """Universo sintético: `n` perpetuos con 10 M de volumen diario y alta en D0."""
    rng = np.random.default_rng(seed)
    days = pd.date_range(D0, periods=int(years * 365), freq="D")
    fund = pd.DataFrame(rng.normal(0.0001, 0.0002, (len(days), n)) * 3, index=days,
                        columns=[f"S{i}USDT" for i in range(n)])
    noise = rng.normal(0, 0.03, (len(days), n))
    # con `carry_edge`, el funding alto de ayer anticipa caída de precio (lo que el carry cobra)
    drift = -carry_edge * (fund.shift(1).fillna(0) - 0.0003).values
    close = pd.DataFrame(100 * np.exp(np.cumsum(noise + drift, axis=0)), index=days,
                         columns=fund.columns)
    close["BTCUSDT"] = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, len(days))))
    fund["BTCUSDT"] = 0.0001
    qvol = pd.DataFrame(1e7, index=days, columns=close.columns)
    cols = close.columns
    return tv.Panel(close, qvol, fund[cols], pd.Series(D0, index=cols),
                    pd.Series([c[:-4] for c in cols], index=cols))


def test_la_puerta_cierra_sin_tocar_un_solo_retorno(monkeypatch):
    p = panel(years=3.0)
    monkeypatch.setattr(tv, "week_return", lambda *a, **k: pytest.fail("calculó retornos"))
    out = tv.run(p)
    assert out["measured"] is False and out["verdict"] == "SIN POTENCIA"
    assert out["gate"]["years"] < tv.T_NEEDED_Y and out["gate"]["passes"] is False


def test_el_universo_aplica_cada_filtro_del_preregistro():
    p = panel(years=1.0, n=5)
    t = p.close.index[200]
    p.qvol.loc[:, "S0USDT"] = 1e6                       # poco volumen
    p.close.loc[t - 10 * tv.DAY:t - tv.DAY, "S1USDT"] = np.nan   # faltan velas
    p.onboard["S2USDT"] = t - 30 * tv.DAY              # alta reciente
    p.base["S3USDT"] = "USDC"                           # estable
    assert tv.eligible(p, t) == ["BTCUSDT", "S4USDT"]


def test_las_carteras_van_contra_el_funding_y_con_el_momentum():
    p = panel(years=1.0, n=10)
    t = p.close.index[300]
    syms = tv.eligible(p, t)
    p.funding.loc[t - 7 * tv.DAY:t - tv.DAY, "S9USDT"] = 0.01      # funding enorme
    lg = tv.legs(p, t, syms)
    assert "S9USDT" in lg["carry"]["short"].index                   # se vende y se cobra
    for side in ("long", "short"):
        assert lg["carry"][side].sum() == pytest.approx(1.0)
    k = len(syms) // 5
    assert len(lg["momentum"]["long"]) == k


def test_el_funding_lo_paga_el_largo_y_lo_cobra_el_corto():
    p = panel(years=1.0, n=3)
    t = p.close.index[100]
    p.close.loc[t - tv.DAY:t + 7 * tv.DAY, :] = 100.0                # precio plano
    p.funding.loc[:, :] = 0.0
    p.funding.loc[t + tv.DAY, "S0USDT"] = 0.001
    w = {"long": pd.Series({"S0USDT": 1.0}), "short": pd.Series({"S1USDT": 1.0})}
    r = tv.week_return(p, t, w, prev=w)                               # sin rotación: sin costo
    assert r == pytest.approx(-0.001 / 2)
    w2 = {"long": pd.Series({"S1USDT": 1.0}), "short": pd.Series({"S0USDT": 1.0})}
    r2 = tv.week_return(p, t, w2, prev=w2)
    assert r2 == pytest.approx(+0.001 / 2)
    first = tv.week_return(p, t, w2, prev=None)                       # entrar cuesta 10 pb por lado
    assert first == pytest.approx(r2 - tv.COST_SIDE)


def test_newey_west_da_cero_con_ruido_y_mucho_con_una_media_clara():
    rng = np.random.default_rng(3)
    assert abs(tv.newey_west_t(rng.normal(0, 1, 2000))[0]) < 3
    assert tv.newey_west_t(rng.normal(0.5, 1, 2000))[0] > 10


def test_con_historia_suficiente_mide_una_vez_la_combinada():
    out = tv.run(panel(years=7.0, carry_edge=30.0))
    assert out["measured"] and out["gate"]["passes"]
    assert set(out["stats"]) == {"carry", "momentum", "combinada"}
    assert out["verdict"] in ("PASA", "NO PASA") and out["beta_btc"] is not None
    assert out["stats"]["carry"]["sharpe"] > 0                        # el efecto plantado se ve


def test_el_informe_dice_sin_potencia_sin_cifras_de_retorno():
    from eim.analytics.transversal_report import markdown
    out = tv.run(panel(years=3.0))
    md = markdown(out, {"n": 41, "by_status": {"TRADING": 41}})
    assert "SIN POTENCIA" in md and "Sharpe" not in md and "supervivencia" in md
