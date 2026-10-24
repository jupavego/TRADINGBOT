"""QC por hora de la captura HFT (T78): cobertura, verificaciones, huecos marcados y no marcados."""
from __future__ import annotations

import json

from eim.data.collectors import qc
from eim.data.collectors.hft_schema import HOUR_NS
from eim.data.collectors.hft_writer import write_rows
from tests.data.hft_helpers import MS, SYM, T0, capture, full_hour, mark, send, trade

H = T0 // HOUR_NS
SEC = 10**9


def test_hora_limpia_es_completa(tmp_path):
    full_hour(tmp_path)
    rep = qc.run_hour(tmp_path, SYM, H)
    assert rep["complete"] and rep["book_usable"] >= 0.999
    assert rep["streams"]["depth"]["coverage"] == 1.0 and rep["streams"]["mark"]["msgs"] == 3600
    assert rep["streams"]["depth"]["latency_ms"]["p50"] == 110.0
    assert rep["checks"] == {"total": 6, "comparable": 6, "matched": 6, "match_rate": 1.0,
                             "failures": []}
    assert rep["holes"] == {"found": 0, "undetected": 0, "list": []}
    assert rep["runs"] == 1 and rep["restarts"] == 1 and rep["disk_mb"]["depth"] > 0
    saved = json.loads(qc.qc_path(tmp_path, SYM, H).read_text(encoding="utf-8"))
    assert saved["hour"] == rep["hour"] and qc.load(tmp_path, SYM, H)["complete"]


def test_hueco_marcado_se_detecta_y_no_queda_sin_marca(tmp_path):
    full_hour(tmp_path, lose_at=1800, seed=1)
    rep = qc.run_hour(tmp_path, SYM, H)
    assert rep["holes"]["found"] == 1 and rep["holes"]["undetected"] == 0
    causes = rep["gaps_marked"]["by_cause"]
    assert causes["secuencia"] == 1 and causes["sin_libro"] == 2
    assert 0.99 < rep["book_usable"] < 1.0 and rep["complete"]


def test_hueco_sin_marca_del_recolector_es_no_detectado(tmp_path):
    cap, _ = full_hour(tmp_path, seed=2)
    t = T0 + 3599 * SEC + 900 * MS
    write_rows(tmp_path, "depth", SYM, H, [(t, t - T0, cap.run, cap.seq + 1, t // MS, t // MS,
                                            10**9, 10**9 + 1, 10**9 - 5, [], [], [], [])])
    rep = qc.run_hour(tmp_path, SYM, H)
    assert rep["holes"]["undetected"] == 1 and not rep["complete"]
    assert rep["holes"]["list"][0]["kind"] == "secuencia"


def test_cola_llena_reinicio_y_salto_de_reloj(tmp_path):
    cap, store = capture(tmp_path)
    t = T0 + 5 * SEC
    send(cap, mark(t // MS), t)
    cap.handle(("overflow", "market", 42, t + MS, t + 2 * MS, t + 3 * MS, 0))
    cap.handle(("clock", "salto", -300 * MS, t, t + 4 * MS, 0))
    cap.handle(("clock", "ajuste", 6 * MS, t, t + 5 * MS, 0))
    store.flush()
    cap2, store2 = capture(tmp_path, run=T0 + 60 * SEC)              # el proceso se reinició
    send(cap2, mark((T0 + 61 * SEC) // MS), T0 + 61 * SEC)
    store2.flush()
    rep = qc.run_hour(tmp_path, SYM, H)
    assert rep["overflow_dropped"] == 42
    assert rep["clock"] == {"jumps": 1, "adjustments": 1, "max_abs_ms": 300.0}
    assert rep["runs"] == 2 and rep["restarts"] == 2
    assert rep["holes"]["undetected"] == 0                          # el reinicio no es «hueco»
    assert not rep["complete"]                                      # casi sin datos


def test_hueco_que_cruza_la_hora_se_enlaza_con_la_anterior(tmp_path):
    cap, store = capture(tmp_path)
    t = T0 + HOUR_NS - SEC
    send(cap, trade(1, t // MS), t)
    send(cap, trade(5, (t + 2 * SEC) // MS), t + 2 * SEC)            # hora siguiente, faltan 3
    store.flush()
    rep = qc.run_hour(tmp_path, SYM, H + 1)
    assert rep["holes"]["found"] == 1 and rep["holes"]["undetected"] == 0
    assert rep["holes"]["list"] == []
