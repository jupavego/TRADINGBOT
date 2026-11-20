"""Variables de microestructura de T80: valores, ventanas hacia atrás y AUSENCIA DE LOOK-AHEAD."""

from __future__ import annotations

import numpy as np

from eim.data.micro import _ofi_step
from eim.hft.features import FeatureParams, build_matrix, valid_rows
from eim.hft.features import book as B
from eim.hft.features import flow as F
from eim.hft.features import sampling as S
from eim.hft.features import vol as V
from eim.hft.features.baseline import baseline_v1
from tests.hft.t80_helpers import panel, scramble_after


def test_microprecio_y_spread():
    bp, ap = np.array([100.0]), np.array([100.2])
    assert B.mid(bp, ap)[0] == 100.1
    # con la misma cola el microprecio es el mid; con más cola vendedora, se acerca al bid
    assert B.microprice(bp, np.array([2.0]), ap, np.array([2.0]))[0] == 100.1
    assert B.microprice(bp, np.array([1.0]), ap, np.array([9.0]))[0] < 100.1
    assert B.tilt_bps(bp, np.array([1.0]), ap, np.array([9.0]))[0] < 0
    assert abs(B.relative_spread_bps(bp, ap)[0] - 0.2 / 100.1 * 1e4) < 1e-9


def test_desequilibrio_de_profundidad():
    bq = np.array([[3.0, 2.0, 1.0]])
    aq = np.array([[1.0, 1.0, 1.0]])
    assert B.depth_imbalance(bq, aq, 3)[0] == (6 - 3) / 9
    assert B.depth_imbalance(bq, aq, 1)[0] == (3 - 1) / 4
    assert B.depth_imbalance(np.zeros((1, 2)), np.zeros((1, 2)), 2)[0] == 0.0


def test_ofi_multinivel_reutiliza_el_de_t23():
    prev = (np.array([100.0, 99.9]), np.array([2.0, 1.0]),
            np.array([100.1, 100.2]), np.array([3.0, 1.0]))
    cur = (np.array([100.0, 99.9]), np.array([5.0, 1.0]),
           np.array([100.1, 100.2]), np.array([3.0, 4.0]))
    got = B.ofi_event(prev, cur, 2)
    assert got[0] == _ofi_step((100.0, 2.0, 100.1, 3.0), (100.0, 5.0, 100.1, 3.0))
    assert got[1] == _ofi_step((99.9, 1.0, 100.2, 1.0), (99.9, 1.0, 100.2, 4.0))
    assert got[0] > 0 and got[1] < 0            # más compra arriba, más venta en el nivel 2


def test_niveles_que_el_libro_no_tiene_aportan_cero():
    prev = B.pad_levels([100.0], [1.0], [100.1], [1.0], 3)
    cur = B.pad_levels([100.0], [2.0], [100.1], [1.0], 3)
    got = B.ofi_event(prev, cur, 3)
    assert got[0] == 1.0
    assert list(got[1:]) == [0.0, 0.0]


def test_ventanas_hacia_atras():
    x = np.arange(1.0, 6.0)
    got = S.trailing_sum(x, 3)
    assert np.isnan(got[:2]).all()
    assert list(got[2:]) == [6.0, 9.0, 12.0]
    assert S.trailing_mean(x, 3)[2] == 2.0
    assert abs(S.trailing_std(np.ones(5), 3)[4]) <= 1e-6   # suelo de eps, sin 0/0
    z = S.trailing_z(np.array([0.0, 0.0, 0.0, 3.0]), 4)
    assert z[3] > 1.0


def test_reloj_de_volumen_y_vpin():
    vol = np.full(10, 5.0)
    idx = S.volume_clock(vol, 10.0)
    assert list(idx) == [0, 1, 1, 2, 2, 3, 3, 4, 4, 5]
    last = S.bucket_last_rows(idx)
    assert list(last) == [0, 2, 4, 6, 8, 9]
    buy = np.full(10, 5.0)
    sell = np.zeros(10)
    got = F.vpin(buy, sell, 10.0, 2)
    assert np.isnan(got[0])                     # sin dos cubos cerrados no hay VPIN
    assert abs(got[-1] - 1.0) < 1e-9            # todo el flujo de un lado: desequilibrio máximo
    mixed = F.vpin(np.full(10, 2.5), np.full(10, 2.5), 10.0, 2)
    assert abs(np.nanmin(mixed)) < 1e-9


def test_flujo_e_intensidad():
    buy, sell = np.array([1.0, 1.0, 3.0]), np.array([1.0, 1.0, 1.0])
    assert F.trade_imbalance(buy, sell, 2)[2] == (4 - 2) / 6
    n = np.concatenate([np.ones(100), np.full(10, 5.0)])
    inten = F.arrival_intensity(n, 5, 50)
    assert inten[-1] > 2.0                      # ráfaga frente a la referencia


def test_volatilidad_realizada_y_salto():
    r = np.concatenate([[np.nan], np.full(99, 1e-4)])
    rv = V.realized_variance(r, 50)
    assert abs(rv[-1] - 50 * 1e-8) < 1e-12
    assert abs(V.realized_vol_bps(r, 50)[-1] - np.sqrt(50 * 1e-8) * 1e4) < 1e-6
    # un retorno enorme aislado: la bipotencia lo ignora y la parte de salto sube
    jumpy = np.concatenate([[np.nan], np.full(60, 1e-5)])
    jumpy[30] = 1e-2
    assert V.jump_share(jumpy, 60)[-1] > 0.9
    assert V.jump_share(np.concatenate([[np.nan], np.full(60, 1e-5)]), 60)[-1] < 0.5


def test_sin_look_ahead_en_ninguna_variable():
    p = panel(1500, seed=3)
    names, x = build_matrix(p)
    base = baseline_v1(p)
    k = 900
    q = scramble_after(p, k)
    names2, x2 = build_matrix(q)
    base2 = baseline_v1(q)
    assert names == names2
    np.testing.assert_allclose(np.nan_to_num(x[:k + 1], nan=-7),
                               np.nan_to_num(x2[:k + 1], nan=-7), rtol=1e-12, atol=0)
    np.testing.assert_allclose(np.nan_to_num(base[:k + 1], nan=-7),
                               np.nan_to_num(base2[:k + 1], nan=-7), rtol=1e-12, atol=0)
    # y el futuro sí cambia: la prueba no es trivial
    assert not np.allclose(np.nan_to_num(x[k + 50:], nan=-7),
                           np.nan_to_num(x2[k + 50:], nan=-7))


def test_matriz_y_filas_validas():
    p = panel(2000, seed=1)
    params = FeatureParams()
    names, x = build_matrix(p, params)
    assert len(names) == x.shape[1] == 15
    assert names[0] == "tilt_bps"
    ok = valid_rows(x, p.complete)
    assert ok.sum() > 0
    assert np.isfinite(x[ok]).all()
    assert not ok[:params.intensity_ref - 1].any()          # el calentamiento no se usa


def test_linea_base_v1_usa_los_pesos_del_agente():
    p = panel(1500, seed=5)
    base = baseline_v1(p)
    assert np.nanmax(np.abs(base)) <= 1.0
    assert np.isnan(base[:10]).all()                        # sin historia no hay z
    assert np.isfinite(base[1000:]).all()


def test_la_historia_tiene_que_ser_contigua():
    from eim.hft.features.matrix import contiguous_history

    t = np.concatenate([np.arange(0, 10) * 1000,
                        np.arange(20, 30) * 1000]).astype(np.int64)   # falta un tramo
    ok = contiguous_history(t, 1000, 3)
    assert not ok[:3].any()                      # calentamiento
    assert ok[3:10].all()
    assert not ok[10:13].any()                   # las que miran a través del hueco
    assert ok[13:].all()
    p = panel(800, seed=4)
    x = build_matrix(p)[1]
    params = FeatureParams()
    estricto = valid_rows(x, p.complete, p.t, p.step_ms, params.history_buckets)
    assert estricto.sum() <= valid_rows(x, p.complete).sum()
