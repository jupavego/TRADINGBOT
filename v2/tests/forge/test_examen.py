"""El examen completo de la forja corre de punta a punta en una rejilla diminuta (T208).

No mide nada de verdad (la serie es sintética): comprueba que la cadena entera —simular todas las
recetas, acumular por día, Romano-Wolf, Sharpe deflactado, PBO, control al azar e informe— no se
rompe y respeta la reserva.
"""

from __future__ import annotations

import numpy as np
import pytest

from eim.forge import examine, prereg, report, space
from eim.forge.engine import Rules


@pytest.fixture
def rejilla(monkeypatch):
    trig = tuple(t for t in space.TRIGGERS if t.id in ("ema_5_20", "rsi14_30_70", "donchian20"))
    salidas = tuple(e for e in space.EXITS if e.id in ("atr1_2", "tiempo12"))
    filtros = {k: v for k, v in space.FILTERS.items() if k in ("ninguno", "adx20")}
    monkeypatch.setattr(space, "TRIGGERS", trig)
    monkeypatch.setattr(space, "EXITS", salidas)
    monkeypatch.setattr(space, "FILTERS", filtros)
    return len(trig) * 3 * len(filtros) * len(salidas)


def test_cadena_completa(serie, sesiones, rasgos, rejilla, tmp_path):
    hold_day = len(sesiones.dates) - 3            # las tres últimas sesiones, de reserva
    fam = examine.simulate_all(serie, sesiones, rasgos, hold_day, Rules(), log=False)
    assert len(fam.recipes) == rejilla
    assert fam.n.sum() > 0
    assert fam.s.shape == (rejilla, hold_day)
    # nada de la reserva entra en lo que se mide
    assert fam.hold[:, 0].sum() > 0

    decl = prereg.declaration()
    decl["criteria"] = {**decl["criteria"], "min_trades": 5}
    res = examine.screen(fam, decl, reps=60, seed=1)
    assert res["m"] == rejilla
    assert res["with_min_trades"] >= 2
    assert all(0 < r["p_raw"] <= 1 for r in res["rows"])
    assert all(r["p_rw"] >= r["p_raw"] - 1e-9 for r in res["rows"])      # corregir solo sube el p
    assert res["expected_max_z"] > 0

    control = examine.random_control(serie, sesiones, rasgos, Rules(), 60, series=2)
    rep = report.build(res, {**decl, "fingerprint": prereg.FINGERPRINT},
                       {"candles": len(serie.t), "gaps": 0}, control, None, None)
    j, m = report.write(rep, tmp_path, tag="prueba")
    assert j.exists() and m.exists()
    texto = m.read_text(encoding="utf-8")
    assert "Forja 5 m" in texto and "umbral del azar" in texto.lower()


def test_la_reserva_no_se_mira_si_no_hay_supervivientes(serie, sesiones, rasgos, rejilla):
    fam = examine.simulate_all(serie, sesiones, rasgos, len(sesiones.dates) - 3, Rules(),
                               log=False)
    assert examine.holdout(fam, []) == {}
    uno = fam.recipes[0].id
    got = examine.holdout(fam, [uno])
    assert set(got[uno]) == {"n", "mean_r"}


def test_gemelas_se_copian_y_cuentan_una_vez(serie, sesiones, rasgos, monkeypatch):
    """Dos recetas con la MISMA serie de señales dan lo mismo y solo se simulan una vez."""
    monkeypatch.setattr(space, "TRIGGERS", tuple(t for t in space.TRIGGERS if t.id == "ema_5_20"))
    monkeypatch.setattr(space, "EXITS", space.EXITS[:1])
    monkeypatch.setattr(space, "FILTERS", {"ninguno": space.FILTERS["ninguno"],
                                           "copia": space.FILTERS["ninguno"]})
    fam = examine.simulate_all(serie, sesiones, rasgos, len(sesiones.dates) - 3, Rules(),
                               log=False)
    assert len(fam.recipes) == 6 and fam.distinct_signals == 3      # 3 direcciones, no 6
    por = {r.id: i for i, r in enumerate(fam.recipes)}
    for d in space.DIRECTIONS:
        a = por[f"ema_5_20|{d}|ninguno|{space.EXITS[0].id}"]
        b = por[f"ema_5_20|{d}|copia|{space.EXITS[0].id}"]
        np.testing.assert_array_equal(fam.s[a], fam.s[b])
        np.testing.assert_array_equal(fam.c[a], fam.c[b])
