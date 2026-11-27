"""La rejilla de la forja (T208): tamaño, unicidad, señales limpias y familia aparte."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from eim.forge import prereg, space

M = 18_900          # 70 disparadores × 3 direcciones × 9 filtros × 10 salidas
GRID = "86a88f612f5943ef"


def test_tamano_de_la_rejilla():
    rec = space.enumerate_recipes()
    assert len(rec) == M == len(space.TRIGGERS) * 3 * len(space.FILTERS) * len(space.EXITS)
    assert len(space.TRIGGERS) == 70
    assert {t.family for t in space.TRIGGERS} == set(space.FAMILIES)
    assert space.grid_fingerprint() == GRID        # cambiarla es otra familia, con otro m


def test_ids_y_huellas_unicos():
    rec = space.enumerate_recipes()
    assert len({r.id for r in rec}) == len(rec)
    assert len({r.fingerprint for r in rec}) == len(rec)


def test_todos_los_disparadores_funcionan(rasgos, sesiones):
    """Cada disparador se calcula sin faltarle ninguna variable y solo dice −1, 0 o +1."""
    for t in space.TRIGGERS:
        s = np.asarray(t.fn(rasgos))
        assert s.shape == rasgos["c"].shape, t.id
        assert set(np.unique(s)).issubset({-1, 0, 1}), t.id


def test_senal_solo_donde_se_puede_operar(rasgos, sesiones):
    for t in space.TRIGGERS[:12]:
        for d in space.DIRECTIONS:
            for fl in space.FILTERS:
                s = space.signal(t, d, fl, rasgos, sesiones.can_signal)
                assert not np.any(s[~sesiones.can_signal])
                if d == "largo":
                    assert np.all(s >= 0)
                if d == "corto":
                    assert np.all(s <= 0)


def test_los_filtros_quitan_senales(rasgos, sesiones):
    t = next(x for x in space.TRIGGERS if x.id == "ema_5_20")
    libre = np.count_nonzero(space.signal(t, "ambos", "ninguno", rasgos, sesiones.can_signal))
    assert libre > 0
    for fl in space.FILTERS:
        n = np.count_nonzero(space.signal(t, "ambos", fl, rasgos, sesiones.can_signal))
        assert n <= libre
        if fl != "ninguno":
            assert n < libre


def test_prereg_congelado():
    decl = prereg.declaration()
    assert prereg.fingerprint(decl) == prereg.FINGERPRINT
    assert decl["grid"]["m"] == M
    assert decl["grid"]["fingerprint"] == GRID
    assert decl["mode"] == "ANALISIS"
    assert decl["rules"]["equity"] == 10_000 and decl["rules"]["risk_frac"] == 0.01
    assert decl["rules"]["max_leverage"] == 10.0 and decl["rules"]["compounding"] is False
    guardado = json.loads(prereg.PATH.read_text(encoding="utf-8"))
    assert guardado.pop("fingerprint") == prereg.FINGERPRINT
    assert guardado == decl                         # el JSON commiteado es el del código


def test_la_forja_no_toca_la_cantera():
    """Familia aparte: nada de `eim/forge` escribe en el libro de la cantera ni en el del papel."""
    for p in sorted(Path("eim/forge").glob("*.py")):
        src = p.read_text(encoding="utf-8")
        assert "eim.nursery" not in src, p.name
        assert "paper.duckdb" not in src and "paper_cantera" not in src, p.name
