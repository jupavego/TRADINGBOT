"""T142 — El informe de T31 recoge las distorsiones medidas de los libros."""

from __future__ import annotations

from dataclasses import replace

from eim.operation import distortions, report, weekly

MON = 1_793_577_600_000      # 2026-11-02 00:00 UTC, lunes
FAULT = distortions.Distortion(machine="a", t0=MON + 10, t1=MON + 20, title="Fallo",
                               detail="Medido.", ref="PLAN/notas/x.md")


def _in(t0: int, t1: int, d: distortions.Distortion = FAULT) -> list[dict]:
    return distortions.overlapping(t0, t1, "a", (d,))


def test_a_distortion_shows_only_in_the_periods_it_touches():
    assert _in(MON, MON + 11)[0]["title"] == "Fallo"
    assert _in(MON + 19, MON + 30)[0]["ref"] == "PLAN/notas/x.md"
    assert _in(MON, MON + 10) == []                  # el periodo acaba cuando empieza
    assert _in(MON + 20, MON + 30) == []             # el periodo empieza cuando ya acabó


def test_a_distortion_shows_only_in_the_reports_of_the_measured_machine():
    assert distortions.overlapping(MON, MON + 11, "otro", (FAULT,)) == []
    assert distortions.overlapping(MON, MON + 11, None, (FAULT,)) == []


def test_an_unresolved_distortion_shows_in_every_later_report():
    assert _in(MON + 10**9, MON + 10**9 + 1, replace(FAULT, t1=None))


def test_report_section_says_what_where_and_until_when():
    lines = report._distortion_lines(_in(MON, MON + 11))
    assert lines[1] == "## Distorsiones conocidas de los libros"
    assert "**Fallo**" in lines[3] and "Medido." in lines[3] and "`PLAN/notas/x.md`" in lines[3]
    assert "hasta" in lines[3]
    still = _in(MON, MON + 11, replace(FAULT, t1=None))
    assert "sin resolver" in report._distortion_lines(still)[3]
    assert report._distortion_lines([]) == []


def test_t142_starts_when_the_first_operation_froze():
    (d,) = distortions.KNOWN
    assert report._d(d.t0) == "2026-11-04 00:32 UTC" and d.machine == "juanpablo-cpu"
    assert report._d(d.t1) == "2026-11-07 02:34 UTC"


def test_t142_reaches_the_report_of_its_week_and_not_the_previous_one(tmp_path, monkeypatch):
    (known,) = distortions.KNOWN
    (tmp_path / "machine_id").write_text(known.machine, encoding="utf-8")
    monkeypatch.delenv("EIM_MACHINE", raising=False)
    t0, t1 = weekly.week_bounds(known.t0)
    assert t0 == MON and t1 == MON + weekly.WEEK_MS
    rep = weekly.compose(t0=t0, t1=t1, mode="SIMULADO", symbols=("BTCUSDT",), trades=[],
                         fee_rate=0.0004, equity=[], alerts=[], active_alerts=[], decisions=[],
                         edge=None, calib={"BTCUSDT": weekly.calibration([], {}, 25)},
                         started_at=t0, data_dir=tmp_path)
    _, md = report.write(rep, tmp_path)
    text = md.read_text(encoding="utf-8")
    assert "5 posiciones fantasma" in text and "T142_posiciones_fantasma.md" in text
    assert distortions.overlapping(t0 - weekly.WEEK_MS, t0, known.machine) == []
