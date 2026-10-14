"""Validación contra valores de referencia fijados y contra el catálogo (T34)."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from eim.indicators import SPECS, compute, ema, rolling_std, sma

FIX = Path(__file__).resolve().parents[1] / "fixtures"
REF = json.loads((FIX / "indicators" / "reference.json").read_text(encoding="utf-8"))
CATALOG = Path(__file__).resolve().parents[2] / "eim" / "indicators" / "CATALOG.md"
# Tolerancia declarada: ambas implementaciones en float64; solo cambia el orden de operaciones.
RTOL, ATOL = 1e-9, 1e-9


def _inputs() -> dict[str, np.ndarray]:
    d = {k: np.asarray(v, dtype=float) for k, v in REF["inputs"].items() if k != "t"}
    d["t"] = np.asarray(REF["inputs"]["t"], dtype=np.int64)
    return d


@pytest.mark.parametrize("ind", sorted(SPECS))
def test_matches_reference(ind):
    out = compute(ind, _inputs())
    exp = REF["expected"][ind]
    assert set(out) == set(exp), f"{ind}: líneas {sorted(out)} ≠ {sorted(exp)}"
    for line, values in exp.items():
        e = np.array([np.nan if x is None else x for x in values], dtype=float)
        got = out[line]
        assert got.shape == e.shape
        np.testing.assert_array_equal(np.isnan(got), np.isnan(e), err_msg=f"{ind}.{line} NaN")
        ok = ~np.isnan(e)
        assert ok.sum() > 0, f"{ind}.{line} sin valores"
        np.testing.assert_allclose(got[ok], e[ok], rtol=RTOL, atol=ATOL,
                                   err_msg=f"{ind}.{line}")


def test_every_reference_has_spec():
    assert set(REF["expected"]) == set(SPECS)


def test_catalog_lists_every_implemented_indicator():
    text = CATALOG.read_text(encoding="utf-8")
    done = set(re.findall(r"^\|\s*`([^`]+)`\s*\|.*\|\s*☑", text, flags=re.M))
    assert done == set(SPECS), f"catálogo ☑ vs registro: {done ^ set(SPECS)}"


def test_core_matches_pandas_conventions():
    c = _inputs()["close"]
    s = pd.Series(c)
    np.testing.assert_allclose(ema(c, 21), s.ewm(span=21, adjust=False).mean(), rtol=1e-12)
    np.testing.assert_allclose(sma(c, 20), s.rolling(20).mean(), rtol=1e-12)
    np.testing.assert_allclose(rolling_std(c, 20), s.rolling(20).std(ddof=0), rtol=1e-9)


def test_ema_matches_legacy_frm_golden():
    """La EMA de la biblioteca reproduce las columnas EMA_* del golden heredado (F7)."""
    with open(FIX / "ethusdt_1h_1000.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    close = np.array([float(r["close"]) for r in rows])
    for n in (9, 21, 55, 100, 200):
        gold = np.array([float(r[f"EMA_{n}"]) for r in rows])
        np.testing.assert_allclose(ema(close, n), gold, rtol=1e-9)
