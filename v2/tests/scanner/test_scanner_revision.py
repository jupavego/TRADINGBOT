"""T95 ◆ — la revisión programada de T96 lee el registro de intentos y aplica su regla."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("duckdb")

from eim.data.scanner_store import ScannerStore  # noqa: E402
from eim.scanner import multiplicity as mu  # noqa: E402

DAY = 86_400_000
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "scanner_revision.py"


def _load():
    spec = importlib.util.spec_from_file_location("scanner_revision", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fill(path: Path, n_days: int, per_day: int, edge: float) -> None:
    st = ScannerStore(path / "scanner" / "scanner.duckdb")
    for d in range(n_days):
        cut = (100 + d) * DAY
        atts = [mu.Attempt(f"i{k}|sintesis@v|1d|h25", f"i{k}", f"S{k}USDT", mu.SYNTHESIS_AGENT,
                           "v", "1d", 25, 1, 100.0, 0.1, 0.002, {"quality": 0.5})
                for k in range(per_day)]
        st.record_attempts(f"r{d}", cut, DAY, atts)
        st.mature_obs([(a.key, cut, 101.0, edge + 0.01 * k, -edge - 0.02)
                       for k, a in enumerate(atts)])
    st.close()


def test_too_few_results_say_postpone(tmp_path):
    _fill(tmp_path, 3, 5, 0.5)
    out = tmp_path / "rep.md"
    assert _load().main(["--data-dir", str(tmp_path), "--out", str(out)]) == 0
    assert "POSPONER" in out.read_text(encoding="utf-8")


def test_enough_results_without_placebo_do_not_start_t96(tmp_path):
    _fill(tmp_path, 12, 20, 0.5)                         # 240 maduras que ganan al azar
    out = tmp_path / "rep.md"
    assert _load().main(["--data-dir", str(tmp_path), "--out", str(out)]) == 0
    rep = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert rep["synthesis"]["matured"] == 240 and rep["synthesis"]["p_day_clustered"] < 0.01
    assert rep["verdict"].startswith("NO ARRANCAR") and "placebo" in rep["verdict"]


def test_without_registry_exits_5(tmp_path):
    assert _load().main(["--data-dir", str(tmp_path)]) == 5
