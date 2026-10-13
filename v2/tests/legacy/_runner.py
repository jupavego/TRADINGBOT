"""Ejecuta los módulos legados de F7/ sobre el CSV fixture y produce salidas canónicas.

Solo lectura sobre F7/: se añade a sys.path, no se modifica.
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

V2 = Path(__file__).resolve().parents[2]
# EIM_LEGACY_DIR permite apuntar a una copia modificada (comprobación de sensibilidad).
F7 = Path(os.environ.get("EIM_LEGACY_DIR", V2.parent / "F7"))
FIXTURES = V2 / "tests" / "fixtures"
GOLDEN = FIXTURES / "golden"
CSV = FIXTURES / "ethusdt_1h_1000.csv"
OHLCV = ["timestamp", "open", "high", "low", "close", "volume"]
VWAP_PERIODS = ("daily", "weekly", "quincenal", "monthly")

# Tolerancia numérica explícita de la comparación contra el golden.
RTOL = 1e-9
ATOL = 1e-9


def _legacy_path() -> None:
    if str(F7) not in sys.path:
        sys.path.insert(0, str(F7))


def load_ohlcv() -> pd.DataFrame:
    return pd.read_csv(CSV, parse_dates=["timestamp"])[OHLCV]


def _quiet(fn, *args, **kwargs):
    """Los módulos legados imprimen progreso; se silencia."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def canon(obj):
    """Convierte a estructura JSON canónica (NaN→None, Timestamp→str, numpy→python)."""
    if isinstance(obj, pd.DataFrame):
        return {"columns": [str(c) for c in obj.columns],
                "data": {str(c): canon(obj[c].tolist()) for c in obj.columns}}
    if isinstance(obj, dict):
        return {str(k): canon(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [canon(v) for v in obj]
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if obj is pd.NaT or obj is None:
        return None
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return None if math.isnan(obj) else float(obj)
    return obj if isinstance(obj, str) else str(obj)


def run_frm_brm_irm() -> pd.DataFrame:
    _legacy_path()
    from eim_brm_irm import EIMBRM, EIMIRM, BRMThresholds
    from eim_frm import EIMFRM

    df = _quiet(EIMFRM(load_ohlcv()).run_all)
    df = _quiet(EIMBRM(BRMThresholds()).run_all, df)
    return _quiet(EIMIRM().run_all, df)


def run_frm() -> pd.DataFrame:
    _legacy_path()
    from eim_frm import EIMFRM

    return _quiet(EIMFRM(load_ohlcv()).run_all)


def run_vwap() -> pd.DataFrame:
    _legacy_path()
    from eim_vwap import EIMVWAP

    return _quiet(EIMVWAP(load_ohlcv()).run_all, periods=VWAP_PERIODS)


def run_price_action() -> dict:
    _legacy_path()
    from eim_price_action import EIMPriceAction

    df, zones = _quiet(EIMPriceAction(load_ohlcv()).run_all)
    return {"frame": df, "sr_zones": zones}


def run_elliott() -> dict:
    _legacy_path()
    from eim_elliott import EIMElliott

    return _quiet(EIMElliott(load_ohlcv()).run_all)


def synthetic_monthly_closes() -> pd.DataFrame:
    """Cierres mensuales sintéticos y deterministas (el CSV cubre solo ~6 semanas).

    Ejercita el cálculo de la matriz Año×Mes, no datos de mercado reales.
    """
    ts = pd.date_range("2022-01-31", periods=40, freq="ME", tz="UTC")
    close = 1000.0 * np.cumprod(1.0 + 0.05 * np.sin(np.arange(40) * 0.7) + 0.01)
    df = pd.DataFrame({"timestamp": ts, "close": close})
    return df.drop(index=[17]).reset_index(drop=True)  # hueco → retorno NaN


def run_seasonality() -> dict:
    _legacy_path()
    from eim_seasonality import EIMSeasonality

    sea = EIMSeasonality(synthetic_monthly_closes())
    return {"all": sea.matrix(), "range": sea.matrix(start_year=2023, end_year=2024)}


GENERATORS = {
    "frm_brm_irm": run_frm_brm_irm,
    "vwap": run_vwap,
    "price_action": run_price_action,
    "elliott": run_elliott,
    "seasonality": run_seasonality,
}


def generate() -> None:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for name, fn in GENERATORS.items():
        out = canon(fn())
        (GOLDEN / f"{name}.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        print(f"golden: {name}.json")
