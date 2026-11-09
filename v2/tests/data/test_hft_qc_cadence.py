"""T138: la cobertura de `mark` no depende de la fase de llegada; un hueco real se sigue viendo.

Desde T147 `mark` y `bbo` informan y no vetan: lo que decide la hora es el libro utilizable, que no
haya huecos sin detectar y la coincidencia top-10 (§Aceptación de `PLAN/T78.md`). Lo que se mide
aquí sigue igual; lo que cambia es que ya no tira la hora.
"""
from __future__ import annotations

import json
import random

import numpy as np
import pytest

from eim.data.collectors import hft_ops, qc
from eim.data.collectors.hft_schema import HOUR_NS
from eim.data.collectors.hft_writer import hour_dir
from tests.data.hft_helpers import MS, SYM, T0, full_hour

H = T0 // HOUR_NS
SEC = 10**9
PERIOD, GAP = qc.CADENCE_NS["mark"]


def _cov(recv) -> float:
    return qc.cadence_coverage(np.asarray(recv, dtype=np.int64), H, PERIOD, GAP)


def _at_boundary(lost=(), jitter_ms: float = 15.0, seed: int = 7):
    """Llegadas sobre el límite del segundo con unos ms de vaivén, como el 2026-11-05T14."""
    rng = random.Random(seed)
    gone = set(lost)

    def at(s: int) -> int | None:
        if s in gone:
            return None
        return T0 + (s + 1) * SEC + int(rng.uniform(-jitter_ms, jitter_ms) * MS)
    return at


def _downgrade(root, hour: int = H) -> dict:
    """Deja el JSON como lo escribió la versión 1: `mark` juzgado por segundo de llegada."""
    rep = qc.load(root, SYM, hour)
    rep["version"] = 1
    del rep["streams"]["mark"]["coverage_cadence"]
    rep["complete"] = rep["complete"] and rep["streams"]["mark"]["coverage"] >= qc.COVERAGE_MIN
    qc.qc_path(root, SYM, hour).write_text(json.dumps(rep), encoding="utf-8")
    return rep


@pytest.mark.parametrize("phase_ms", [0, 1, 100, 250, 500, 999])
def test_la_cobertura_no_depende_de_la_fase(phase_ms):
    recv = [T0 + s * SEC + phase_ms * MS for s in range(3600)]
    assert _cov(recv) == 1.0
    sin_40 = recv[:1000] + recv[1040:]
    assert _cov(sin_40) == pytest.approx(1 - 40 / 3600, abs=1e-4)


def test_un_mensaje_perdido_cuesta_un_segundo():
    recv = [T0 + s * SEC + 200 * MS for s in range(3600) if s != 1800]
    assert _cov(recv) == pytest.approx(1 - 1 / 3600, abs=1e-4)


def test_un_retraso_dentro_de_la_tolerancia_no_es_hueco():
    recv = [T0 + s * SEC + 200 * MS for s in range(3600)]
    recv[1800] += 400 * MS                                        # intervalo de 1,4 s
    assert _cov(recv) == 1.0


def test_flujo_mudo_o_lento_no_cubre():
    assert _cov([]) == 0.0
    lento = list(range(T0, T0 + HOUR_NS, 1_400 * MS))             # sin hueco, pero a 0,71 Hz
    assert _cov(lento) == pytest.approx(1 / 1.4, abs=1e-3)


def test_hueco_contra_los_bordes_de_la_hora():
    recv = [T0 + s * SEC for s in range(100, 3500)]
    assert _cov(recv) == pytest.approx((3600 - 99 - 99) / 3600, abs=1e-3)


def test_mark_sobre_el_limite_del_segundo_no_da_hora_incompleta(tmp_path):
    full_hour(tmp_path, mark_at=_at_boundary())
    rep = qc.run_hour(tmp_path, SYM, H)
    m = rep["streams"]["mark"]
    assert m["coverage"] < 0.85 and m["rate_max"] == 2           # la medida vieja: seg. vacíos
    assert m["coverage_cadence"] >= 0.999 and rep["complete"]
    assert rep["version"] == qc.QC_VERSION


def test_un_hueco_real_de_mark_ya_no_rompe_la_hora_pero_se_sigue_viendo(tmp_path):
    """T147: el hueco se mide y lo marca el recolector, pero `mark` no decide la hora."""
    full_hour(tmp_path / "corto", mark_at=_at_boundary(lost=range(1000, 1030)))
    full_hour(tmp_path / "largo", mark_at=_at_boundary(lost=range(1000, 1040)))
    ok = qc.run_hour(tmp_path / "corto", SYM, H)
    mal = qc.run_hour(tmp_path / "largo", SYM, H)
    assert ok["streams"]["mark"]["coverage_cadence"] >= 0.99 and ok["complete"]
    assert mal["streams"]["mark"]["coverage_cadence"] < 0.99      # el hueco se ve en la cifra
    assert mal["complete"] and mal["holes"]["undetected"] == 0    # marcado, no escondido


def test_deciden_el_libro_los_huecos_y_el_top_10_no_bbo_ni_mark(tmp_path):
    """La regla de T147, condición por condición, y una hora real que antes se tiraba."""
    assert qc._complete(1.0, 0, 1.0)
    assert not qc._complete(0.98, 0, 1.0)                        # libro utilizable < 99 %
    assert not qc._complete(1.0, 1, 1.0)                         # un hueco sin detectar
    assert not qc._complete(1.0, 0, 0.98)                        # el top-10 no coincide
    assert qc._complete(1.0, 0, None)                            # sin verificaciones, no penaliza
    full_hour(tmp_path, mark_at=_at_boundary())
    rep = qc.run_hour(tmp_path, SYM, H)
    assert rep["streams"]["mark"]["coverage"] < 0.85 and rep["complete"]


def test_recalificar_sin_escribir_no_toca_el_json(tmp_path):
    full_hour(tmp_path, mark_at=_at_boundary())
    qc.run_hour(tmp_path, SYM, H)
    assert not _downgrade(tmp_path)["complete"]
    before = qc.qc_path(tmp_path, SYM, H).read_text(encoding="utf-8")
    rep = qc.requalify(tmp_path, SYM, H)
    assert rep["complete"] and rep["requalified"]["complete_before"] is False
    assert qc.qc_path(tmp_path, SYM, H).read_text(encoding="utf-8") == before


def test_recalificar_guarda_el_veredicto_original_y_es_idempotente(tmp_path):
    full_hour(tmp_path, mark_at=_at_boundary())
    qc.run_hour(tmp_path, SYM, H)
    _downgrade(tmp_path)
    res = hft_ops.requalify(tmp_path, SYM, H, apply=True)
    assert res["requalified"] == 1 and [c["complete"] for c in res["changed"]] == [True]
    saved = qc.load(tmp_path, SYM, H)
    assert saved["complete"] and saved["version"] == qc.QC_VERSION
    assert saved["requalified"]["complete_before"] is False
    assert saved["requalified"]["from_version"] == 1
    again = hft_ops.requalify(tmp_path, SYM, H, apply=True)
    assert again == {"applied": True, "requalified": 0, "changed": []}


def test_recalificar_aplica_la_regla_nueva_a_un_hueco_de_mark(tmp_path):
    """La hora que la regla vieja tiraba por `mark` pasa a completa, y queda de dónde viene."""
    full_hour(tmp_path, mark_at=_at_boundary(lost=range(1000, 1040)))
    qc.run_hour(tmp_path, SYM, H)
    _downgrade(tmp_path)
    res = hft_ops.requalify(tmp_path, SYM, H, apply=True)
    assert res["requalified"] == 1 and [c["complete"] for c in res["changed"]] == [True]
    saved = qc.load(tmp_path, SYM, H)
    assert saved["complete"] and saved["requalified"]["complete_before"] is False


def test_recalificar_respeta_lo_demas_de_la_regla(tmp_path):
    """Lo que de verdad invalida la hora no lo salva ninguna recalificación."""
    full_hour(tmp_path, mark_at=_at_boundary())
    qc.run_hour(tmp_path, SYM, H)
    base = _downgrade(tmp_path)
    for campo, valor in (("book_usable", 0.95), ("holes", {"found": 1, "undetected": 1}),
                         ("checks", {"comparable": 100, "matched": 98, "match_rate": 0.98})):
        rep = {**base, campo: valor}
        qc.qc_path(tmp_path, SYM, H).write_text(json.dumps(rep), encoding="utf-8")
        assert not qc.requalify(tmp_path, SYM, H)["complete"], campo


def test_recalificar_funciona_sin_crudos(tmp_path):
    """T147: la regla se decide con lo que ya está en el JSON, así que una hora podada también."""
    full_hour(tmp_path, mark_at=_at_boundary())
    qc.run_hour(tmp_path, SYM, H)
    _downgrade(tmp_path)
    for part in hour_dir(tmp_path, "mark", SYM, H).glob("*.parquet"):
        part.unlink()
    rep = qc.requalify(tmp_path, SYM, H, write=True)
    assert rep["complete"] and rep["version"] == qc.QC_VERSION
    assert "coverage_cadence" not in rep["streams"]["mark"]        # sin crudos no se rellena
    assert qc.load(tmp_path, SYM, H)["version"] == qc.QC_VERSION


def test_la_racha_cuenta_las_horas_recalificadas(tmp_path, capsys):
    full_hour(tmp_path, mark_at=_at_boundary())
    qc.run_hour(tmp_path, SYM, H)
    _downgrade(tmp_path)
    now = T0 / 1e9 + 2 * 3600
    assert hft_ops.streak(tmp_path, SYM, now)["best"]["hours"] == 0
    label = qc.load(tmp_path, SYM, H)["hour"]
    assert hft_ops.main(["--root", str(tmp_path), "--requalify", label]) == 0
    assert json.loads(capsys.readouterr().out)["applied"] is False
    assert hft_ops.streak(tmp_path, SYM, now)["best"]["hours"] == 0   # sin --apply, nada cambia
    assert hft_ops.main(["--root", str(tmp_path), "--requalify", label, "--apply"]) == 0
    assert hft_ops.streak(tmp_path, SYM, now)["best"]["hours"] == 1
