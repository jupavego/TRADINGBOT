"""Regresión: la salida actual de F7/ debe coincidir con el golden (RTOL/ATOL explícitos)."""
from __future__ import annotations

import json

import numpy as np
import pytest

from tests.legacy import _runner as r


def assert_same(actual, expected, path="$"):
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert actual.keys() == expected.keys(), f"{path}: claves distintas"
        for k in expected:
            assert_same(actual[k], expected[k], f"{path}.{k}")
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), f"{path}: longitud"
        nums = all(isinstance(x, (int, float)) and not isinstance(x, bool) or x is None
                   for x in expected + actual)
        if nums and expected:
            a = np.array([np.nan if x is None else x for x in actual], dtype=float)
            e = np.array([np.nan if x is None else x for x in expected], dtype=float)
            bad = ~np.isclose(a, e, rtol=r.RTOL, atol=r.ATOL, equal_nan=True)
            assert not bad.any(), f"{path}: difiere en índices {np.flatnonzero(bad)[:5].tolist()}"
        else:
            for i, (x, y) in enumerate(zip(actual, expected, strict=True)):
                assert_same(x, y, f"{path}[{i}]")
    elif isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=r.RTOL, abs=r.ATOL), path
    else:
        assert actual == expected, path


@pytest.mark.parametrize("name", list(r.GENERATORS))
def test_matches_golden(name):
    golden = json.loads((r.GOLDEN / f"{name}.json").read_text(encoding="utf-8"))
    assert_same(r.canon(r.GENERATORS[name]()), golden)


def test_golden_is_not_trivial():
    g = json.loads((r.GOLDEN / "frm_brm_irm.json").read_text(encoding="utf-8"))
    assert len(g["data"]["close"]) == 1000
    assert any(v is not None for v in g["data"]["EMA_200"])
    assert len(set(g["data"]["STRUCTURAL_STATE"])) > 1


def test_frm_reproduces_csv_historical_columns():
    """El CSV histórico trae las salidas FRM de la corrida original (BRM/IRM cambiaron luego)."""
    import pandas as pd

    df = r.run_frm_brm_irm()
    ref = pd.read_csv(r.CSV)
    for col in ("STACK_SCORE", "COHERENCE_SCORE", "FRICTION_INDEX", "ELASTICITY"):
        a = df[col].to_numpy(float)
        b = ref[col].to_numpy(float)
        np.testing.assert_allclose(a, b, rtol=1e-6, atol=1e-6, equal_nan=True)
