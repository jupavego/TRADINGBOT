"""Operación de la captura HFT (T78): QC de horas cerradas, compactación ZSTD, retención,
resumen con MB/día y proyección, informe semanal, copia diaria (solo el resumen) y vigilante."""
from __future__ import annotations

import json
import shutil

import duckdb

from eim.data import backup
from eim.data.collectors import hft_ops, qc
from eim.data.collectors.hft_read import read_hour
from eim.data.collectors.hft_schema import AREA, HOUR_NS
from eim.data.collectors.hft_supervise import HftMaintenance
from eim.data.collectors.hft_verify import verify_hour
from eim.data.collectors.hft_writer import hour_dir
from eim.operation import report, weekly
from eim.operation.notify import JsonLog
from tests.data.hft_helpers import SYM, T0, full_hour

H = T0 // HOUR_NS
T0_S = T0 / 1e9


def test_mantenimiento_audita_compacta_y_resume(tmp_path):
    full_hour(tmp_path, flush_rows=1500)
    d = hour_dir(tmp_path, "bbo", SYM, H)
    assert len(list(d.glob("part-*.parquet"))) >= 3
    early = hft_ops.maintain(tmp_path, SYM, T0_S + 3600 + 60)        # aún sin margen
    assert early["qc_horas"] == []
    res = hft_ops.maintain(tmp_path, SYM, T0_S + 3 * 3600)
    assert res["qc_horas"] == [qc.load(tmp_path, SYM, H)["hour"]] and res["no_detectados"] == 0
    assert res["compactadas"] >= 4 and res["carpetas_podadas"] == 0
    parts = list(d.glob("part-*.parquet"))
    assert len(parts) == 1 and parts[0].name.startswith("part-compact-")
    meta = duckdb.connect().execute(
        f"SELECT DISTINCT compression FROM parquet_metadata('{parts[0].as_posix()}')").fetchall()
    assert meta == [("ZSTD",)]
    bbo = read_hour(tmp_path, SYM, "bbo", H)
    assert len(bbo) == 3600 and bbo["seq"].is_monotonic_increasing
    assert verify_hour(tmp_path, SYM, H)["ok"]                       # compactado sigue igual
    s = json.loads(hft_ops.summary_path(tmp_path, SYM).read_text(encoding="utf-8"))
    assert s["hours"] == 2 and s["hours_complete"] == 1 and s["hours_without_data"] == 1
    assert s["longest_complete_streak_h"] == 1
    assert s["checks"]["match_rate"] == 1.0 and s["undetected"] == 0
    assert s["disk"]["mb_per_day_total"] > 0
    assert s["disk"]["projection_30d_gb"] == round(s["disk"]["mb_per_day_total"] * 30 / 1000, 2)


def test_retencion_borra_crudos_viejos_y_conserva_el_qc(tmp_path):
    full_hour(tmp_path)
    hft_ops.maintain(tmp_path, SYM, T0_S + 3 * 3600)
    res = hft_ops.maintain(tmp_path, SYM, T0_S + 50 * 86400, keep_days=45)
    assert res["carpetas_podadas"] >= 8
    assert not hour_dir(tmp_path, "depth", SYM, H).exists()
    assert qc.load(tmp_path, SYM, H)["complete"]


def test_racha_contigua_y_resumen_semanal_en_el_informe(tmp_path):
    reps = [{"hour": f"h{i}", "hour_index": i, "complete": i != 3,
             "checks": {"comparable": 12, "matched": 12 - (i == 5)},
             "holes": {"found": 0, "undetected": 0}, "gaps_marked": {"by_cause": {"silencio": 1}},
             "restarts": 0, "overflow_dropped": 0, "clock": {"jumps": 0}} for i in range(8)]
    agg = hft_ops.aggregate(reps)
    assert agg["hours_complete"] == 7 and agg["longest_complete_streak_h"] == 4
    assert agg["checks"]["match_rate"] == round(95 / 96, 4)
    assert agg["gaps_by_cause"]["silencio"] == 8
    gap = hft_ops.aggregate(reps[:2], missing=[2])                  # una hora sin ningún dato
    assert gap["hours"] == 3 and gap["hours_without_data"] == 1 and gap["pct_complete"] == 0.6667
    full_hour(tmp_path / "dead")                                      # y luego la captura murió
    hft_ops.maintain(tmp_path / "dead", SYM, T0_S + 3 * 3600)
    late = hft_ops.summarize(tmp_path / "dead", SYM, T0_S + 6 * 3600)
    assert late["hours"] == 5 and late["hours_complete"] == 1 and late["hours_without_data"] == 4
    full_hour(tmp_path)
    hft_ops.maintain(tmp_path, SYM, T0_S + 3 * 3600)
    week = hft_ops.week_summary(tmp_path, SYM, T0 // 10**6, T0 // 10**6 + 7 * 86_400_000)
    assert week["hours"] == 1 and week["mb_per_day"] > 0
    assert hft_ops.week_summary(tmp_path, SYM, 0, 1000) is None
    rep = weekly.compose(t0=T0 // 10**6, t1=T0 // 10**6 + weekly.WEEK_MS, mode="SIMULADO",
                         symbols=(SYM,), trades=[], fee_rate=0.0004, equity=[], alerts=[],
                         active_alerts=[], decisions=[], edge=None,
                         calib={SYM: weekly.calibration([], {}, 25)}, started_at=T0 // 10**6,
                         hft_qc={SYM: week})
    md = report.render_md(rep)
    assert "## Captura HFT (calidad de datos)" in md and "1/1 horas completas" in md
    assert "6/6 (100.00%)" in md
    rep["hft_qc"] = {}
    assert "Sin captura HFT en el periodo" in report.render_md(rep)


def test_copia_diaria_lleva_el_resumen_pero_no_los_crudos(tmp_path):
    data = tmp_path / "data"
    full_hour(data)
    hft_ops.maintain(data, SYM, T0_S + 3 * 3600)
    out = backup.create(data, tmp_path / "copias", clock=lambda: T0_S + 4 * 3600)
    files = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["files"]
    qc_files = [f for f in files if f.startswith("state/micro_hft_qc/")]
    assert any(f.endswith("summary.json") for f in qc_files) and len(qc_files) == 2
    assert not any(f.endswith(".parquet") for f in files)
    assert backup.verify(out) == []


def test_vigilante_hft_registra_el_mantenimiento(tmp_path):
    full_hour(tmp_path)
    log = JsonLog(tmp_path / AREA / "logs")
    now = [T0_S + 3 * 3600]
    m = HftMaintenance(tmp_path, log, 45, lambda a: None, clock=lambda: now[0], symbol=SYM,
                       area=AREA, label="Captura HFT")
    m.prune(now[0])
    now[0] += 3 * 3600                                                # toca otra pasada

    def rows():
        return [json.loads(x) for f in (tmp_path / AREA / "logs").glob("*.jsonl")
                for x in f.read_text(encoding="utf-8").splitlines()]

    hft = [r for r in rows() if r["event"] == "mantenimiento_hft"]
    assert hft and hft[0]["horas_completas"] == 1 and hft[0]["coincidencia_top10"] == 1.0
    assert hft[0]["mb_dia"] > 0 and hft[0]["proyeccion_30d_gb"] >= 0
    shutil.rmtree(tmp_path / AREA / "qc")                             # resumen ilegible
    (tmp_path / AREA / "qc").write_text("no es carpeta", encoding="utf-8")
    m.tick()                                                          # falla y no tumba nada
    assert [r["paso"] for r in rows() if r["event"] == "mantenimiento_fallido"] == ["poda"]


def test_compactacion_sin_reordenar_acota_grupos_y_verifica_el_orden(tmp_path):
    full_hour(tmp_path, flush_rows=700)
    d = hour_dir(tmp_path, "depth", SYM, H)
    assert len(list(d.glob("part-*.parquet"))) >= 5
    hft_ops.maintain(tmp_path, SYM, T0_S + 3 * 3600)
    (part,) = d.glob("part-*.parquet")
    con = duckdb.connect()
    groups = con.execute(f"SELECT row_group_id, max(row_group_num_rows) FROM parquet_metadata("
                         f"'{part.as_posix()}') GROUP BY ALL").fetchall()
    assert len(groups) >= 2                                           # DuckDB redondea (≈ 2 100)
    assert max(n for _, n in groups) < 2 * hft_ops.LIST_ROW_GROUP
    seq = con.execute(f"SELECT seq FROM read_parquet('{part.as_posix()}')").fetchnumpy()["seq"]
    assert len(seq) == 3601 and (seq[1:] > seq[:-1]).all()           # mismo orden de proceso


def test_partes_solapadas_no_se_compactan(tmp_path):
    from eim.data.collectors.compact import compact_dir
    from eim.data.collectors.hft_writer import write_rows

    row = lambda s: (T0 + s, s, T0, s, 1, 1, s, 99.9, 1.0, 100.1, 2.0)  # noqa: E731
    write_rows(tmp_path, "bbo", SYM, H, [row(1), row(5)])
    write_rows(tmp_path, "bbo", SYM, H, [row(3), row(7)])             # se intercala: no válido
    d = hour_dir(tmp_path, "bbo", SYM, H)
    try:
        compact_dir(d, key="seq", order="run, seq", codec="ZSTD", presorted=True)
        raise AssertionError("debió negarse")
    except RuntimeError as e:
        assert "fuera de orden" in str(e)
    assert len(list(d.glob("part-*.parquet"))) == 2 and not list(d.glob("*.tmp"))


def test_un_fallo_de_compactacion_no_frena_el_resumen(tmp_path, monkeypatch):
    full_hour(tmp_path, flush_rows=1500)

    def sin_memoria(*a, **k):
        raise MemoryError("Out of Memory Error: failed to allocate data of size 64.0 MiB")

    monkeypatch.setattr(hft_ops, "compact_dir", sin_memoria)
    res = hft_ops.maintain(tmp_path, SYM, T0_S + 3 * 3600)
    assert res["compactadas"] == 0 and len(res["compactacion_fallida"]) >= 4
    assert "MemoryError" in res["compactacion_fallida"][0][1]
    assert res["qc_horas"] and res["summary"]["hours_complete"] == 1
    assert json.loads(hft_ops.summary_path(tmp_path, SYM).read_text(encoding="utf-8"))["hours"]
