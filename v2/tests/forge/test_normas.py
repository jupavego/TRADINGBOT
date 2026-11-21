"""Las normas de la cuenta de T208 se cumplen en todas las operaciones.

10 000 $ sin interés compuesto · riesgo 1 % · apalancamiento máximo 1:10 · entrada en la vela
siguiente a la señal · nada abierto entre sesiones.
"""

from __future__ import annotations

import numpy as np
import pytest

from eim.forge import examine, space
from eim.forge.engine import Rules, simulate

EXITS = [e.id for e in space.EXITS]


def _sig(rasgos, sesiones, trig_id="rsi14_30_70"):
    trig = next(t for t in space.TRIGGERS if t.id == trig_id)
    return trig, space.signal(trig, "ambos", "ninguno", rasgos, sesiones.can_signal)


@pytest.mark.parametrize("exit_id", EXITS)
def test_nada_abierto_entre_sesiones(serie, sesiones, rasgos, exit_id):
    mk = examine.market(serie, sesiones, rasgos)
    ex = next(e for e in space.EXITS if e.id == exit_id)
    _, sig = _sig(rasgos, sesiones)
    tr = simulate(mk, sig, ex, Rules())
    assert len(tr) > 10
    assert np.all(sesiones.sid[tr.entry] == sesiones.sid[tr.exit])
    assert np.all(tr.exit <= sesiones.last[tr.entry])
    assert np.all(sesiones.sid[tr.entry] >= 0)


def test_entrada_en_la_vela_siguiente(serie, sesiones, rasgos):
    mk = examine.market(serie, sesiones, rasgos)
    _, sig = _sig(rasgos, sesiones)
    tr = simulate(mk, sig, space.EXITS[0], Rules())
    assert np.all(sig[tr.entry - 1] != 0)                  # la señal es la vela ANTERIOR
    assert np.all(sesiones.can_signal[tr.entry - 1])


def test_riesgo_y_apalancamiento(serie, sesiones, rasgos):
    """Nocional ≤ 1:10 siempre; el stop nunca arriesga más de 1 R de precio (los costos aparte)."""
    rules = Rules()
    mk = examine.market(serie, sesiones, rasgos)
    ex = next(e for e in space.EXITS if e.id == "atr1_2")
    _, sig = _sig(rasgos, sesiones)
    tr = simulate(mk, sig, ex, rules)
    idx = tr.entry - 1
    d = ex.atr_k * mk.atr[idx]
    side = sig[idx].astype(float)
    p_e = mk.o[tr.entry] * (1 + side * rules.costs.slip_entry_base_bps / 1e4)
    q = np.minimum(rules.r_dollar / d, rules.max_notional / p_e)
    assert np.all(q * p_e <= rules.max_notional * (1 + 1e-12))     # 1:10, sin excepción
    assert np.all(q * d <= rules.r_dollar * (1 + 1e-12))           # riesgo de precio ≤ 1 R
    # una salida por stop pierde exactamente 1 R de precio MÁS los costos (que en 5 m no son
    # pequeños: con el stop a 1 ATR el nocional ronda los 85 000 $ y la ida y vuelta
    # se lleva ~0,9 R)
    stop = tr.kind == 0
    assert stop.sum() > 5
    riesgo = q * d / rules.r_dollar                                 # 1 R, o menos si se recortó
    slip_in = q * mk.o[tr.entry] * rules.costs.slip_entry_base_bps / 1e4 / rules.r_dollar
    esperado = -riesgo - tr.cost_r + slip_in       # el deslizamiento de entrada ya va en el precio
    np.testing.assert_allclose(tr.r[stop], esperado[stop], rtol=0, atol=1e-9)
    assert np.all(riesgo <= 1 + 1e-12)
    assert 0.3 < float(np.median(tr.cost_r[stop])) < 1.5


def test_sin_interes_compuesto(serie, sesiones, rasgos):
    """El tamaño sale siempre de 10 000 $: una operación no depende de las anteriores."""
    mk = examine.market(serie, sesiones, rasgos)
    ex = next(e for e in space.EXITS if e.id == "tiempo12")
    _, sig = _sig(rasgos, sesiones)
    todo = simulate(mk, sig, ex, Rules())
    corte = len(serie.t) // 2
    media = sig.copy()
    media[:corte] = 0                                   # se tiran las señales anteriores
    luego = simulate(mk, media, ex, Rules())
    comunes = np.isin(todo.entry, luego.entry)
    sel = np.isin(luego.entry, todo.entry)
    assert comunes.sum() > 5
    np.testing.assert_allclose(todo.r[comunes], luego.r[sel], rtol=1e-12)


def test_cuenta_de_recortes_por_apalancamiento(serie, sesiones, rasgos):
    """Si el stop es tan estrecho que pasaría de 1:10, se recorta el tamaño y se cuenta."""
    mk = examine.market(serie, sesiones, rasgos)
    _, sig = _sig(rasgos, sesiones)
    estrecha = space.Exit("prueba", "objetivo", 0.001, tp_r=2.0)
    tr = simulate(mk, sig, estrecha, Rules())
    assert tr.capped > 0
    ancha = space.Exit("prueba2", "objetivo", 3.0, tp_r=2.0)
    assert simulate(mk, sig, ancha, Rules()).capped == 0
