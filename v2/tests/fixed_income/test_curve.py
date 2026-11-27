"""T100: curva de tipos contra referencias publicadas.

- *Bootstrap*: Hull, §4.5 (tablas 4.3–4.4). Bonos de 100: 0,25 años a 97,5; 0,5 a 94,9; 1 a
  90,0 (cupón cero); 1,5 años con cupón 8 % semestral a 96,0; 2 años con cupón 12 % a 101,6 →
  tipos cero continuos 10,127 %, 10,469 %, 10,536 %, 10,681 % y 10,808 %.
- Nelson–Siegel: Diebold y Li (2006) fijan λ = 0,0609 (m en meses) para que la carga de la
  curvatura sea máxima hacia los 30 meses; el máximo de L2(x) está en x ≈ 1,7933.
"""

import math

import numpy as np
import pytest

from eim.fixed_income import curve as c
from eim.fixed_income.bond import par_yield


def test_hull_bootstrap():
    bonds = [(0.25, 0.0, 97.5, 4), (0.5, 0.0, 94.9, 2), (1.0, 0.0, 90.0, 1),
             (1.5, 0.08, 96.0, 2), (2.0, 0.12, 101.6, 2)]
    ts, zs = c.bootstrap_bonds(bonds)
    assert ts == (0.25, 0.5, 1.0, 1.5, 2.0)
    expected = [10.127, 10.469, 10.536, 10.681, 10.808]
    assert [round(z * 100, 3) for z in zs] == expected


def test_diebold_li_curvature_peak():
    m = np.linspace(1, 120, 119_001)
    peak = m[np.argmax(c._l2(m * 0.0609))]
    assert peak == pytest.approx(30, abs=1.0)
    x = np.linspace(0.5, 4, 350_001)
    assert x[np.argmax(c._l2(x))] == pytest.approx(1.7933, abs=1e-3)


def test_loadings_limits_level_and_short_rate():
    b0, b1, b2, tau = 0.05, -0.02, 0.01, 2.0
    assert c.nelson_siegel(1e-9, b0, b1, b2, tau) == pytest.approx(b0 + b1, abs=1e-8)
    assert c.nelson_siegel(1e5, b0, b1, b2, tau) == pytest.approx(b0, abs=1e-4)
    assert c.svensson(3.0, b0, b1, b2, 0.0, tau, 9.0) == pytest.approx(
        c.nelson_siegel(3.0, b0, b1, b2, tau))


def test_fits_recover_known_parameters():
    m = np.array([0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30])
    y = c.svensson(m, 4.5, -1.0, 2.0, -1.5, 1.5, 6.0)
    sv = c.fit_svensson(m, y)
    assert sv.rmse < 1e-10
    assert (sv.params["tau1"], sv.params["tau2"]) == (1.5, 6.0)
    assert sv.params["b3"] == pytest.approx(-1.5, abs=1e-8)
    ns = c.fit_nelson_siegel(m, c.nelson_siegel(m, 4.0, 1.0, -0.5, 2.25))
    assert ns.rmse < 1e-10 and ns.params["tau1"] == 2.25
    assert ns.level == pytest.approx(4.0) and ns.slope == pytest.approx(-1.0)
    assert ns(10.0) == pytest.approx(c.nelson_siegel(10.0, 4.0, 1.0, -0.5, 2.25))


def test_fit_rejects_bad_input():
    with pytest.raises(ValueError):
        c.fit_svensson([1, 2, 3], [1, 2, 3])
    with pytest.raises(ValueError):
        c.fit_nelson_siegel([0, 1, 2, 3], [1, 2, 3, 4])


def test_par_to_zero_flat_curve_and_round_trip():
    t, z = c.par_to_zero([1, 2, 3, 5, 10], [0.05] * 5)
    assert all(v == pytest.approx(2 * math.log(1.025), abs=1e-12) for v in z)
    # Una curva con pendiente: el cupón par recalculado sobre los ceros devuelve la par.
    tenors = [1 / 12, 0.25, 0.5, 1, 2, 3, 5, 7, 10]
    par = [0.042, 0.043, 0.044, 0.045, 0.046, 0.0465, 0.047, 0.048, 0.049]
    t, z = c.par_to_zero(tenors, par)
    zero = c.linear(t, z)
    for mat, y in ((2, 0.046), (5, 0.047), (10, 0.049)):
        assert par_yield(zero, mat) == pytest.approx(y, abs=1e-10)
    assert t[0] == pytest.approx(1 / 12)          # las letras quedan como cupón cero


def test_forward_rate_consistency():
    zero = c.linear([1, 2], [0.03, 0.04])
    assert c.forward_rate(zero, 1, 2) == pytest.approx(0.05)
    assert c.forward_rate(zero, 0, 1) == pytest.approx(0.03)
    with pytest.raises(ValueError):
        c.forward_rate(zero, 2, 1)
