"""Etiquetas y particiones de T80: Δmid con reacción, triple barrera, cola y purga/embargo."""

from __future__ import annotations

import numpy as np

from eim.hft.evaluation import labels as L
from eim.hft.evaluation import splits as SP
from tests.hft.t80_helpers import panel

STEP = 1000


def _t(n: int) -> np.ndarray:
    return (np.arange(n) * STEP).astype(np.int64)


def test_delta_mid_con_y_sin_reaccion():
    mid = np.full(20, 100.0)
    mid[5:] = 101.0                                     # salto de +100 pb en el cubo 5
    t = _t(20)
    d, ok = L.forward_mid_bps(t, mid, 3000)
    assert abs(d[2] - 100.0) < 1e-6                     # de 2 a 5
    assert d[1] == 0.0 and d[5] == 0.0
    # con 1 s de reacción la entrada es un cubo después: la fila 1 ya captura el salto
    d2, ok2 = L.forward_window_bps(t, mid, 1000, 3000)
    assert abs(d2[1] - 100.0) < 1e-6
    assert abs(d2[2] - 100.0) < 1e-6
    assert not ok[-1] and not ok2[-1]                   # al final no hay destino: inválido


def test_cubos_incompletos_invalidan_el_tramo():
    mid = np.linspace(100.0, 101.0, 20)
    t = _t(20)
    complete = np.ones(20, bool)
    complete[7] = False
    _d, ok = L.forward_mid_bps(t, mid, 3000, complete)
    assert not ok[5] and not ok[6] and not ok[7]        # el hueco está dentro del tramo
    assert ok[8]


def test_destino_rancio_no_vale():
    t = np.array([0, 1000, 2000, 30_000], dtype=np.int64)
    mid = np.array([100.0, 100.0, 100.0, 101.0])
    _d, ok = L.forward_mid_bps(t, mid, 5000, max_stale_ms=2000)
    assert not ok.any()                                 # el último dato está a 28 s


def test_direccion_neta_de_costos():
    d = np.array([12.0, -12.0, 3.0, np.nan])
    assert list(L.net_direction(d, 7.0)) == [1.0, -1.0, 0.0, 0.0]


def test_triple_barrera():
    mid = np.full(30, 100.0)
    mid[10:] = 100.6                                    # +60 pb en el cubo 10
    t = _t(30)
    lab, valid = L.triple_barrier(t, mid, 10_000, 50.0, STEP)
    assert lab[5] == 1.0                                # toca la barrera de arriba
    assert lab[0] == 1.0                                # a 10 s llega justo al salto
    assert lab[15] == 0.0                               # después del salto, expira sin tocar
    assert valid[5]
    down = L.triple_barrier(t, 200.0 - mid, 10_000, 50.0, STEP)[0]
    assert down[5] == -1.0
    # con la reacción, la señal del cubo 9 entra en el 10 y ya no captura el salto
    lag = L.triple_barrier(t, mid, 3_000, 50.0, STEP, lag_steps=1)[0]
    assert lag[9] == 0.0
    assert lab[9] == 1.0


def test_llenado_pasivo_con_cola_pesimista():
    n = 10
    bid_q = np.full(n, 2.0)
    ask_q = np.full(n, 2.0)
    bid_p = np.full(n, 100.0)
    ask_p = np.full(n, 100.1)
    sell_v = np.full(n, 1.0)                            # 1 BTC agresor vendedor por cubo
    buy_v = np.zeros(n)
    assert not L.passive_fill(bid_q, ask_q, bid_p, ask_p, buy_v, sell_v, 1, 1)[0]
    assert L.passive_fill(bid_q, ask_q, bid_p, ask_p, buy_v, sell_v, 2, 1)[0]
    # si el bid mejora, la orden deja de estar al frente: no se llena
    mejor = bid_p.copy()
    mejor[1:] = 100.05
    assert not L.passive_fill(bid_q, ask_q, mejor, ask_p, buy_v, sell_v, 5, 1)[0]
    # del otro lado hace falta flujo comprador
    assert not L.passive_fill(bid_q, ask_q, bid_p, ask_p, buy_v, sell_v, 5, -1)[0]


def test_dias_contiguos_y_walk_forward():
    days = [10, 11, 12, 13, 14, 15, 16, 20, 21]
    assert SP.runs_of_days(days) == [[10, 11, 12, 13, 14, 15, 16], [20, 21]]
    folds = SP.walk_forward(days, train_days=3, test_days=1, embargo_days=1)
    assert [f.test for f in folds] == [(14,), (15,), (16,)]
    assert folds[0].train == (10, 11, 12)               # el día 13 es el embargo
    assert SP.walk_forward(days, train_days=3, embargo_days=1, expanding=True)[-1].train[0] == 10


def test_purga_quita_las_filas_cuya_etiqueta_entra_en_la_prueba():
    t = np.arange(0, 3 * SP.DAY_MS, 3_600_000, dtype=np.int64)   # una fila por hora, 3 días
    fold = SP.Fold(train=(0, 1), test=(2,))
    train, test = SP.fold_masks(t, fold, horizon_ms=3_600_000)
    assert test.sum() == 24
    assert train.sum() == 47                            # la última hora del día 1 se purga
    assert SP.day_table(t) == {0: 24, 1: 24, 2: 24}


def test_etiquetas_sobre_un_panel_sintetico():
    p = panel(600, seed=2)
    d, ok = L.forward_window_bps(p.t, p.mid, 1000, 30_000, p.complete)
    assert ok.sum() > 500
    assert np.isfinite(d[ok]).all()
    assert abs(float(np.mean(d[ok]))) < 50.0            # retornos de pb, no de porcentaje
