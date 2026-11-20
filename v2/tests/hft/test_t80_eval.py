"""Marco de evaluación de T80: métricas, ridge y walk-forward con Holm sobre todos los intentos."""

from __future__ import annotations

import numpy as np

from eim.hft import edge_oos
from eim.hft.evaluation import metrics as M
from eim.hft.evaluation import ridge as R
from eim.hft.evaluation.labels import forward_window_bps
from eim.hft.evaluation.splits import DAY_MS, walk_forward
from eim.hft.features import build_matrix, valid_rows
from tests.hft.t80_helpers import panel

COSTS = {"taker": 10.0, "maker": 4.0}


def test_spearman_y_ic_por_dia():
    x = np.arange(100.0)
    assert abs(M.spearman(x, x ** 3) - 1.0) < 1e-12          # monótona: IC = 1
    assert abs(M.spearman(x, -x) + 1.0) < 1e-12
    assert np.isnan(M.spearman(np.ones_like(x), x))
    t = np.concatenate([np.zeros(200), np.full(200, DAY_MS)]).astype(np.int64)
    y = np.concatenate([np.arange(200.0), -np.arange(200.0)])
    days, ics = M.ic_by_day(np.arange(400.0), y, t, min_per_day=100)
    assert len(days) == 2
    assert ics[0] > 0.9 and ics[1] < -0.9


def test_acierto_brier_pinball_y_pb_netos():
    yt = np.array([1.0, 1.0, -1.0, -1.0, 0.0])
    yp = np.array([2.0, -1.0, -3.0, -2.0, 5.0])
    assert M.balanced_accuracy(yt, yp) == 0.75                # 1/2 arriba, 2/2 abajo
    assert M.balanced_accuracy(np.zeros(3), yp[:3]) is None
    assert M.brier(np.array([1.0, 0.0]), np.array([1.0, 0.0])) == 0.0
    assert M.pinball(np.array([0.0]), np.array([1.0]), 0.5) == 0.5
    assert M.skill(0.5, 1.0) == 0.5
    net, take = M.net_bps(np.array([20.0, -20.0, 1.0]), np.array([30.0, -30.0, 50.0]), 10.0,
                          threshold=10.0)
    assert list(take) == [True, True, False]                  # la tercera no supera el umbral
    assert list(net) == [20.0, 20.0]


def test_ic_medio_con_bootstrap_de_dias():
    days = np.arange(12, dtype=np.int64)
    got = M.mean_ci(np.full(12, 0.05), days, 2000, 0.95, "prueba")
    assert abs(got["mean"] - 0.05) < 1e-12
    assert abs(got["lo"] - 0.05) < 1e-9 and abs(got["hi"] - 0.05) < 1e-9
    assert got["positive_days"] == 1.0
    ruido = M.mean_ci(np.array([0.1, -0.1] * 6), days, 2000, 0.95, "ruido")
    assert ruido["lo"] < 0 < ruido["hi"]                      # sin señal el IC incluye el 0


def test_p_unilateral_por_dias():
    assert edge_oos.day_pvalue(np.full(12, 0.05), 2000, 0, "fuerte") < 0.05
    assert edge_oos.day_pvalue(np.array([0.1, -0.1] * 6), 2000, 0, "ruido") > 0.2
    assert edge_oos.day_pvalue(np.array([0.1]), 2000, 0, "corta") == 1.0


def test_ridge_recupera_una_relacion_lineal():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, (2000, 3))
    y = 2.0 * x[:, 0] - 1.0 * x[:, 1] + rng.normal(0, 0.1, 2000)
    model = R.fit(x, y, 1e-6)
    pred = model.predict(x)
    assert np.corrcoef(pred, y)[0, 1] > 0.98
    cv = R.fit_cv(x, y)
    assert cv.alpha in R.ALPHAS
    assert np.corrcoef(cv.predict(x), y)[0, 1] > 0.9


def _dataset(days: int = 9, per_day: int = 1200, signal: float = 1.5):
    """Panel con señal plantada en el OFI del mejor nivel, repartido en días UTC."""
    p = panel(days * per_day, seed=11, signal=signal)
    t = (np.arange(len(p)) // per_day) * DAY_MS + (np.arange(len(p)) % per_day) * 1000
    object.__setattr__(p, "t", t.astype(np.int64))
    names, x = build_matrix(p)
    y, ok = forward_window_bps(p.t, p.mid, 1000, 1000, p.complete)
    use = ok & valid_rows(x, p.complete)
    return names, x[use], y[use], p.t[use]


def test_walk_forward_encuentra_la_senal_plantada_y_corrige_por_holm():
    names, x, y, t = _dataset()
    folds = walk_forward(sorted(set(t // DAY_MS)), train_days=3, test_days=1, embargo_days=1)
    assert len(folds) >= 4
    res = edge_oos.evaluate(t, x, names, {1: y}, {1: folds}, COSTS, reps=1000, level=0.95,
                            seed=0, step_ms=1000)
    assert res["attempts"] == len(names) + 1                  # cada señal + la ridge
    block = res["horizons"]["1"]
    assert set(block) == {*names, edge_oos.RIDGE}
    ofi = block["ofi_top_1"]
    assert ofi["ic"]["mean"] > 0.05                           # la señal plantada aparece
    assert ofi["ic_p"] < 0.05
    assert ofi["ic_p_holm"] >= ofi["ic_p"]                    # Holm nunca afloja
    assert block[edge_oos.RIDGE]["ic"]["mean"] > 0.05         # la ridge también la ve
    ruido = block["jump_share"]
    assert abs(ruido["ic"]["mean"]) < ofi["ic"]["mean"]
    for name in (edge_oos.RIDGE, "ofi_top_1"):
        assert block[name]["overlap"] == 1
        assert block[name]["test_days"] >= 4
        assert block[name]["net"]["taker"]["days"] >= 0


def test_sin_senal_el_canal_plantado_no_pasa():
    """Sin señal, el canal donde se planta (OFI del mejor nivel) y la ridge no pasan Holm.

    No se exige que NINGUNA de las 16 columnas pase: el mid del panel está cuantizado al tick,
    igual que el real, y eso crea relaciones mecánicas (por ejemplo con el nivel de precio) que
    son justo las que la corrección por Holm y el IC 95 % están ahí para no confundir con edge.
    """
    names, x, y, t = _dataset(signal=0.0)
    folds = walk_forward(sorted(set(t // DAY_MS)), 3, 1, 1)
    res = edge_oos.evaluate(t, x, names, {1: y}, {1: folds}, COSTS, 1000, 0.95, 0, 1000)
    block = res["horizons"]["1"]
    for name in ("ofi_top_1", "ofi_all_1", edge_oos.RIDGE):
        s = block[name]
        assert not (s["ic_p_holm"] < 0.05 and (s["ic"]["lo"] or -1) > 0), name
