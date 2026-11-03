"""Aceptación de T78 por racha de horas completas seguidas (T126): se lee de los JSON de QC."""
from __future__ import annotations

import json

from eim.data.collectors import hft_ops, qc
from eim.data.collectors.hft_read import hour_label, parse_hour
from tests.data.hft_helpers import SYM

H0 = parse_hour("2026-10-31T08")


def _qc(root, h, complete=True, comparable=12, matched=12, undetected=0):
    p = qc.qc_path(root, SYM, h)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"hour": hour_label(h), "hour_index": h, "complete": complete,
                             "checks": {"comparable": comparable, "matched": matched},
                             "holes": {"undetected": undetected}}), encoding="utf-8")


def _now(h):
    """Instante en que `h` es la última hora auditable."""
    return (h + 1) * 3600 + hft_ops.QC_MARGIN_S + 1


def test_la_racha_mayor_decide_y_una_hora_incompleta_la_corta(tmp_path):
    for i in range(8):
        _qc(tmp_path, H0 + i, complete=i != 3)
    s = hft_ops.streak(tmp_path, SYM, _now(H0 + 7), need_h=4)
    assert s["best"]["hours"] == 4 and s["best"]["first_hour"] == hour_label(H0 + 4)
    assert s["passed"] and s["remaining_h"] == 0 and s["current"]["hours"] == 4
    s = hft_ops.streak(tmp_path, SYM, _now(H0 + 7), need_h=5)
    assert not s["passed"] and s["remaining_h"] == 1 and s["audited_hours"] == 8


def test_una_hora_sin_auditar_corta_y_la_racha_actual_caduca(tmp_path):
    for i in (0, 1, 3, 4, 5):                       # la hora 2 no tiene QC: captura caída
        _qc(tmp_path, H0 + i)
    s = hft_ops.streak(tmp_path, SYM, _now(H0 + 5), need_h=72)
    assert s["best"]["hours"] == 3 and s["best"]["first_hour"] == hour_label(H0 + 3)
    assert s["current"]["hours"] == 3 and s["remaining_h"] == 69
    s = hft_ops.streak(tmp_path, SYM, _now(H0 + 6), need_h=72)   # QC de la 6 aún pendiente
    assert s["current"]["hours"] == 3
    s = hft_ops.streak(tmp_path, SYM, _now(H0 + 9), need_h=72)   # ya no llega nada
    assert s["current"]["hours"] == 0 and s["remaining_h"] == 72 and s["best"]["hours"] == 3


def test_hueco_sin_detectar_o_coincidencia_baja_no_pasan(tmp_path):
    for i in range(4):
        _qc(tmp_path, H0 + i, undetected=int(i == 2))
    assert not hft_ops.streak(tmp_path, SYM, _now(H0 + 3), need_h=4)["passed"]
    for i in range(4):
        _qc(tmp_path, H0 + i, comparable=100, matched=98)
    s = hft_ops.streak(tmp_path, SYM, _now(H0 + 3), need_h=4)
    assert s["best"]["match_rate"] == 0.98 and not s["passed"]


def test_desde_una_hora_y_cli_de_solo_lectura(tmp_path, capsys):
    for i in range(6):
        _qc(tmp_path, H0 + i)
    s = hft_ops.streak(tmp_path, SYM, _now(H0 + 5), since_h=H0 + 4)
    assert s["audited_hours"] == 2 and s["since"] == hour_label(H0 + 4)
    assert hft_ops.main(["--root", str(tmp_path), "--symbol", SYM, "--streak",
                         "--since", hour_label(H0 + 2)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["audited_hours"] == 4 and out["need_h"] == hft_ops.T78_NEED_H
    assert not hft_ops.summary_path(tmp_path, SYM).exists()      # no escribe nada


def test_el_resumen_lleva_la_racha(tmp_path):
    for i in range(3):
        _qc(tmp_path, H0 + i)
    out = hft_ops.summarize(tmp_path, SYM, _now(H0 + 2))
    assert out["t78_streak"]["best"]["hours"] == 3 and not out["t78_streak"]["passed"]
