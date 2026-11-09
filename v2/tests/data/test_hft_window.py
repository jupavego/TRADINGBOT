"""Aceptación de T78 por ventana (T147): calidad sostenida, no horas perfectas seguidas.

Lo que decide es lo que pide §Aceptación de `PLAN/T78.md`: ≥ 99 % de horas completas, ningún hueco
sin detectar y ≥ 99 % de coincidencia top-10 en un tramo contiguo de ≥ 72 h. Las dos condiciones
duras no se aflojan nunca; lo que cambia es que una hora al 98,x % ya no manda la cuenta a cero.
"""
from __future__ import annotations

import json

from eim.data.collectors import hft_ops, hft_window, qc
from eim.data.collectors.hft_read import hour_label, parse_hour
from tests.data.hft_helpers import SYM

H0 = parse_hour("2026-10-31T08")


def _qc(root, h, complete=True, undetected=0, matched=12, comparable=12, book=0.999, causes=None,
        restarts=0):
    p = qc.qc_path(root, SYM, h)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "version": qc.QC_VERSION, "hour": hour_label(h), "hour_index": h, "complete": complete,
        "book_usable": book, "restarts": restarts, "runs": 1, "overflow_dropped": 0,
        "clock": {"jumps": 0}, "gaps_marked": {"by_cause": causes or {}},
        "checks": {"comparable": comparable, "matched": matched,
                   "match_rate": round(matched / comparable, 4) if comparable else None},
        "holes": {"found": undetected, "undetected": undetected},
    }), encoding="utf-8")


def _horas(root, n, incompletas=(), **kw):
    for i in range(n):
        _qc(root, H0 + i, complete=i not in incompletas, **kw)


def _ventana(root, n, **kw):
    """Veredicto leyendo los JSON, con la última hora escrita como hora fresca."""
    return hft_window.window(hft_ops.qc_reports(root, SYM), H0 + n - 1,
                             hft_window.load_maint(root, SYM), **kw)


def test_una_hora_incompleta_en_72_no_cumple_pero_en_125_si(tmp_path):
    """99 % de 72 h no deja margen para ninguna; con el tramo más largo, una cabe."""
    _horas(tmp_path, 72, incompletas=(30,))
    v = _ventana(tmp_path, 72)
    assert not v["passed"] and v["best"]["hours"] == 41        # el tramo de después, al 100 %
    _horas(tmp_path, 125, incompletas=(30,))
    v = _ventana(tmp_path, 125)
    assert v["passed"] and v["best"]["hours"] == 125
    assert v["best"]["pct_complete"] == 0.992 and v["remaining_h"] == 0


def test_la_ventana_no_vuelve_a_cero_con_un_tropiezo(tmp_path):
    """El cambio de T147: la misma hora mala corta la racha y solo roza la ventana."""
    _horas(tmp_path, 100, incompletas=(50,))
    assert _ventana(tmp_path, 100)["passed"]
    assert hft_window.streak(hft_ops.qc_reports(tmp_path, SYM), H0 + 99)["best"]["hours"] == 50


def test_un_hueco_sin_detectar_corta_el_tramo_y_no_se_afloja(tmp_path):
    """Condición dura: esa hora no entra en ninguna ventana, por buenas que sean las demás."""
    _horas(tmp_path, 100)
    _qc(tmp_path, H0 + 50, complete=False, undetected=1)
    v = _ventana(tmp_path, 100)
    assert not v["passed"] and v["best"]["hours"] == 50
    assert v["broken_by_undetected"] == [hour_label(H0 + 50)]
    assert v["best"]["undetected"] == 0


def test_el_top_10_por_debajo_del_99_no_cumple(tmp_path):
    """La otra condición dura: el libro puede estar completo y el veredicto sigue siendo no."""
    _horas(tmp_path, 100, comparable=100, matched=98)
    v = _ventana(tmp_path, 100)
    assert not v["passed"] and v["best"]["hours"] == 0
    _horas(tmp_path, 100, comparable=100, matched=100)
    assert _ventana(tmp_path, 100)["passed"]


def test_el_mantenimiento_declarado_no_cuenta_ni_corta(tmp_path):
    """Sin declararlo, el despliegue parte la corrida en dos tramos cortos; declarado, no."""
    _horas(tmp_path, 40)
    for i in range(42, 82):
        _qc(tmp_path, H0 + i)
    assert not _ventana(tmp_path, 82)["passed"]               # dos tramos de 40
    res = hft_window.declare_maint(tmp_path, SYM, H0 + 40, H0 + 41, "despliegue de T123/T124")
    assert res["windows"] == 1 and res["declared"]["hours"] == 2
    v = _ventana(tmp_path, 82)
    assert v["passed"] and v["best"]["hours"] == 80 and v["best"]["maintenance_h"] == 2
    hft_window.declare_maint(tmp_path, SYM, H0 + 40, H0 + 41, "otra vez")
    assert len(hft_window.load_maint(tmp_path, SYM)) == 1     # idempotente por tramo


def test_la_atribucion_separa_lo_nuestro_de_lo_ajeno(tmp_path):
    _horas(tmp_path, 10)
    _qc(tmp_path, H0 + 2, complete=False, causes={"silencio": 3})
    _qc(tmp_path, H0 + 4, complete=False, causes={"desconexion": 1})
    _qc(tmp_path, H0 + 6, complete=False, restarts=1)
    _qc(tmp_path, H0 + 8, complete=False)
    qc.qc_path(tmp_path, SYM, H0 + 7).unlink()               # proceso caído: sin JSON
    att = _ventana(tmp_path, 10)["attribution"]
    assert att == {"ajena": 2, "nuestra": 2, "sin causa": 1}
    hft_window.declare_maint(tmp_path, SYM, H0 + 6, H0 + 6, "reinicio anunciado")
    assert _ventana(tmp_path, 10)["attribution"]["mantenimiento"] == 1


def test_la_ventana_viva_dice_lo_que_falta(tmp_path):
    _horas(tmp_path, 10)
    v = _ventana(tmp_path, 10)
    assert v["current"]["hours"] == 10 and v["remaining_h"] == 62
    assert v["current"]["book_usable_pct"] == 0.999
    assert v["current"]["worst_hour"]["hour"] == hour_label(H0)
    v = hft_window.window(hft_ops.qc_reports(tmp_path, SYM), H0 + 99)   # ya no llega nada
    assert v["current"]["hours"] == 0 and v["remaining_h"] == 72


def test_sin_horas_auditadas_no_revienta(tmp_path):
    v = hft_window.window([], H0)
    assert not v["passed"] and v["best"]["hours"] == 0 and v["remaining_h"] == 72


def test_el_resumen_lleva_la_ventana_y_la_racha(tmp_path):
    _horas(tmp_path, 3)
    out = hft_ops.summarize(tmp_path, SYM, (H0 + 3) * 3600 + hft_ops.QC_MARGIN_S + 1)
    assert out["t78_window"]["best"]["hours"] == 3 and not out["t78_window"]["passed"]
    assert out["t78_streak"]["best"]["hours"] == 3
    assert out["t78_window"]["rule"].startswith("ventana")


def test_cli_de_solo_lectura_y_declaracion_de_mantenimiento(tmp_path, capsys):
    _horas(tmp_path, 4)
    assert hft_ops.main(["--root", str(tmp_path), "--symbol", SYM, "--window"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["audited_hours"] == 4 and out["need_h"] == hft_ops.T78_NEED_H
    assert not hft_ops.summary_path(tmp_path, SYM).exists()   # no escribe nada
    assert hft_ops.main(["--root", str(tmp_path), "--symbol", SYM, "--maintenance",
                         hour_label(H0 + 1), hour_label(H0 + 2), "--nota", "despliegue"]) == 0
    assert json.loads(capsys.readouterr().out)["declared"]["note"] == "despliegue"
    assert hft_window.load_maint(tmp_path, SYM)[0]["from"] == hour_label(H0 + 1)
