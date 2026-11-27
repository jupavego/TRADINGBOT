"""Ninguna variable de la forja mira el futuro (T208, criterio de aceptación).

La prueba es de truncado: si se corta la serie en la vela `i`, el valor de **todas** las variables
en `i` tiene que ser exactamente el mismo que con la serie completa. Si alguna usara una vela
posterior, el corte lo cambiaría.
"""

from __future__ import annotations

import numpy as np

from eim.forge import features, session
from eim.forge.data import Series


def _cut(s: Series, n: int) -> Series:
    return Series(t=s.t[:n], o=s.o[:n], h=s.h[:n], l=s.l[:n], c=s.c[:n], v=s.v[:n],
                  taker_buy_v=s.taker_buy_v[:n], trades=s.trades[:n], funding=s.funding[:n])


def test_variables_causales(serie, sesiones, rasgos):
    dentro = np.flatnonzero((sesiones.sid >= 0) & (rasgos["bars_in"] > 3))
    cortes = [int(i) + 1 for i in dentro[::max(1, len(dentro) // 6)][:5]]
    assert len(cortes) >= 4
    for n in cortes:
        sub = _cut(serie, n)
        f = features.build(sub, session.build(sub.t))
        i = n - 1
        for k, v in f.items():
            np.testing.assert_allclose(v[i], rasgos[k][i], rtol=1e-12, atol=0,
                                       equal_nan=True, err_msg=f"{k} en el corte {n}")


def test_donchian_excluye_la_vela_en_curso(serie, rasgos):
    """El canal de N velas es el de las N ANTERIORES: si no, una ruptura se vería a sí misma."""
    i = 500
    assert rasgos["dc_hi20"][i] == serie.h[i - 20:i].max()
    assert rasgos["dc_lo20"][i] == serie.l[i - 20:i].min()


def test_rango_de_apertura_solo_tras_cerrar_sus_velas(serie, sesiones, rasgos):
    i0 = int(sesiones.starts[1])
    assert np.isnan(rasgos["or_hi6"][i0 + 5])              # aún no han cerrado las 6
    assert rasgos["or_hi6"][i0 + 6] == serie.h[i0:i0 + 6].max()
    assert rasgos["or_lo6"][i0 + 6] == serie.l[i0:i0 + 6].min()


def test_sesion_anterior_es_la_anterior(serie, sesiones, rasgos):
    i0, i1 = int(sesiones.starts[1]), int(sesiones.starts[2])
    prev = serie.h[i0:int(sesiones.last[i0]) + 1].max()
    assert rasgos["prev_hi"][i1 + 10] == prev
    assert np.isnan(rasgos["prev_hi"][int(sesiones.starts[0])])   # la 1.ª no tiene anterior


def test_vwap_de_sesion_se_reinicia(serie, sesiones, rasgos):
    i0 = int(sesiones.starts[3])
    tp = (serie.h[i0] + serie.l[i0] + serie.c[i0]) / 3
    np.testing.assert_allclose(rasgos["vwap_s"][i0], tp, rtol=1e-12)
    j = i0 + 10
    w = slice(i0, j + 1)
    esperado = (((serie.h[w] + serie.l[w] + serie.c[w]) / 3) * serie.v[w]).sum() / serie.v[w].sum()
    np.testing.assert_allclose(rasgos["vwap_s"][j], esperado, rtol=1e-10)
