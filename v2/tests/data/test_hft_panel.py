"""Panel muestreado de T80: reproduce el libro de la captura y marca lo que no se puede usar."""

from __future__ import annotations

import numpy as np

from eim.data.collectors.hft_panel import (
    build_hour,
    columns,
    ensure_hour,
    hours_in_range,
    load_panel,
    panel_file,
    read_hours,
)
from eim.data.collectors.hft_schema import HOUR_NS
from eim.data.collectors.qc import run_hour
from eim.hft.features import build_matrix, valid_rows
from tests.data.hft_helpers import SYM, T0, full_hour

H = T0 // HOUR_NS


def test_panel_de_una_hora_completa(tmp_path):
    full_hour(tmp_path)
    df = build_hour(tmp_path, SYM, H)
    assert list(df.columns) == columns()
    assert len(df) == 3600                                  # un diff por segundo
    t = df["t"].to_numpy()
    assert (np.diff(t) == 1000).all()                       # cubos contiguos de 1 s
    assert t[0] == T0 // 1_000_000 + 1000                   # el sello es el CIERRE del cubo
    # solo el primer cubo queda fuera: el diff llega antes del snapshot que sincroniza
    assert not df["complete"].iloc[0]
    assert df["complete"].iloc[1:].all()
    assert (df["bp0"] < df["ap0"]).all()                    # libro sin cruzar
    assert np.isfinite(df[[f"ofi{k}" for k in range(5)]].to_numpy()).all()
    # un trade de 0,5 por segundo, agresor comprador (maker=False)
    assert df["n_trades"].sum() == 3600
    assert abs(df["buy_v"].sum() - 1800.0) < 1e-6
    assert df["sell_v"].sum() == 0.0


def test_niveles_ordenados_y_profundidad(tmp_path):
    full_hour(tmp_path)
    df = build_hour(tmp_path, SYM, H)
    bp = df[[f"bp{k}" for k in range(5)]].to_numpy()
    ap = df[[f"ap{k}" for k in range(5)]].to_numpy()
    assert (np.diff(bp, axis=1) <= 0).all()                 # compras de mayor a menor
    assert (np.diff(ap, axis=1) >= 0).all()                 # ventas de menor a mayor
    assert (df[[f"bq{k}" for k in range(5)]].to_numpy() >= 0).all()


def test_hueco_marca_los_cubos(tmp_path):
    full_hour(tmp_path, lose_at=1800)
    df = build_hour(tmp_path, SYM, H)
    bad = df.loc[~df["complete"], "t"].to_numpy()
    assert bad.size > 0
    centro = T0 // 1_000_000 + 1800 * 1000
    assert bad.min() <= centro + 2000               # el tramo marcado toca el segundo perdido
    assert df["complete"].mean() > 0.9              # y solo ese tramo


def test_cache_ida_y_vuelta_y_matriz(tmp_path):
    full_hour(tmp_path)
    f, rows = ensure_hour(tmp_path, SYM, H)
    assert rows == 3600
    assert panel_file(tmp_path, SYM, H).exists()
    assert ensure_hour(tmp_path, SYM, H)[1] == 0            # ya estaba: no se reconstruye
    panel = read_hours(tmp_path, SYM, [H])
    assert len(panel) == 3600
    assert panel.levels == 5
    assert (panel.mid > 0).all()
    same = load_panel(tmp_path, SYM, [H - 1, H, H + 1])
    assert len(same) == len(panel)
    names, x = build_matrix(panel)
    assert len(names) == x.shape[1] == 15
    # el calentamiento más largo es el del VPIN (50 cubos de volumen); el resto son filas útiles
    assert valid_rows(x, panel.complete).sum() > 1500


def test_horas_en_rango_usa_el_control_de_calidad(tmp_path):
    full_hour(tmp_path)
    run_hour(tmp_path, SYM, H)
    assert hours_in_range(tmp_path, SYM, H, H) == [H]
    assert hours_in_range(tmp_path, SYM, H + 1, H + 2) == []
