"""Prueba de techo de T80: cota con previsión perfecta, cola, pre-registro, veredicto e informe."""

from __future__ import annotations

import json

import numpy as np
import pytest

from eim.hft import ceiling, ceiling_gate, ceiling_report
from eim.hft.evaluation.attempts import rows_from, write_attempts
from eim.hft.evaluation.prereg import PREREG_DIR, PUBLISHED, load_prereg
from tests.hft.t80_helpers import panel

COSTS = {"taker": 10.0, "mixto": 7.0, "maker": 4.0}


def _saw(n: int = 2000, amp_bps: float = 20.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mid en diente de sierra: sube `amp_bps` un cubo y los baja el siguiente."""
    t = (np.arange(n) * 1000).astype(np.int64)
    mid = 100_000.0 * (1 + (np.arange(n) % 2) * amp_bps / 1e4)
    return t, mid, np.ones(n, bool)


def test_techo_con_prevision_perfecta():
    t, mid, ok = _saw()
    got = ceiling.bound_table(t, mid, ok, (1, 5), COSTS, reaction_ms=0)
    row = got["horizons"]["1"]["no_reaction"]
    assert row["n"] > 1900
    assert abs(row["mean_abs_bps"] - 20.0) < 0.1          # todas las ventanas mueven 20 pb
    taker = row["styles"]["taker"]
    assert taker["frac_pays"] == 1.0                      # 20 pb > 10 pb de ida y vuelta
    assert abs(taker["ceiling_bps_per_window"] - 10.0) < 0.1
    assert abs(taker["cost_share_when_pays"] - 0.5) < 0.01
    maker = row["styles"]["maker"]
    assert maker["ceiling_bps_per_window"] > taker["ceiling_bps_per_window"]


def test_si_el_movimiento_no_paga_el_techo_es_cero():
    t, mid, ok = _saw(amp_bps=2.0)
    got = ceiling.bound_table(t, mid, ok, (1,), COSTS, reaction_ms=0)
    for style in COSTS:
        row = got["horizons"]["1"]["no_reaction"]["styles"][style]
        assert row["frac_pays"] == 0.0
        assert row["ceiling_bps_per_window"] == 0.0
        assert row["cost_share_when_pays"] is None


def test_la_reaccion_cambia_lo_que_se_puede_capturar():
    t, mid, ok = _saw()
    got = ceiling.bound_table(t, mid, ok, (1,), COSTS, reaction_ms=1000)
    sin_r = got["horizons"]["1"]["no_reaction"]["styles"]["taker"]
    con_r = got["horizons"]["1"]["with_reaction"]["styles"]["taker"]
    assert sin_r["frac_pays"] == 1.0
    assert con_r["frac_pays"] == 1.0                      # el diente sigue dando 20 pb
    assert got["reaction_ms"] == 1000


def test_llenado_y_contexto_de_la_cola():
    p = panel(500, seed=4)
    fills = ceiling.fill_table(p, wait_steps=(1, 30))
    assert set(fills) == {"1", "30"}
    assert 0.0 <= fills["1"]["buy"] <= 1.0
    assert fills["30"]["both"] >= fills["1"]["both"]       # más espera, más llenado
    q = ceiling.queue_summary(p)
    assert q["front_qty_p50"] > 0
    assert q["spread_bps_p50"] > 0
    assert q["volume_per_s_mean"] > 0


def test_pre_registro_congelado_y_familia_declarada():
    pr = load_prereg()
    assert pr.task == "T80"
    assert pr.sha256 == PUBLISHED[pr.version]
    assert pr.attempts.family == pr.n_signals * len(pr.horizons_s)
    assert pr.horizons_s == (1, 5, 30, 60)
    assert pr.data.min_days >= 14
    assert pr.gates["C3_net_bps"]["threshold_bps"] == 1.0  # el H2 de hft_v1 (T77)


def test_un_pre_registro_editado_no_carga(tmp_path):
    raw = json.loads((PREREG_DIR / "hft_ceiling_v1.json").read_text(encoding="utf-8"))
    raw["gates"]["C3_net_bps"]["threshold_bps"] = 0.1      # aflojar un umbral
    f = tmp_path / "hft_ceiling_v1.json"
    f.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="versión nueva"):
        load_prereg(path=f)


def _oos(ic: float, net: float, p: float = 0.001) -> dict:
    sig = {"test_days": 10, "ic": {"mean": ic, "lo": ic / 2, "hi": ic * 2, "n_days": 10,
                                   "positive_days": 0.9},
           "gross": {"mean": net + 4.0, "lo": net, "hi": net + 8.0, "n_days": 10},
           "gross_top": {"mean": net + 6.0, "lo": net + 1, "hi": net + 9.0, "n_days": 10},
           "ic_p": p, "ic_p_holm": p, "overlap": 1,
           "net": {k: {"mean": net, "lo": net / 2, "hi": net * 2, "days": 10, "trades": 500,
                       "share_of_rows": 0.01, "p": p, "n_days": 10, "positive_days": 0.8}
                   for k in COSTS}}
    return {"attempts": 68, "holm": {}, "horizons": {"30": {"ofi_top_5": sig}}}


def _ceiling(frac: float) -> dict:
    styles = {k: {"cost_bps": v, "frac_pays": frac, "ceiling_bps_per_window": 1.0,
                  "gross_bps_when_pays": 20.0, "net_bps_when_pays": 20.0 - v,
                  "cost_share_when_pays": v / 20.0, "cost_share_of_mean_move": 2.0}
              for k, v in COSTS.items()}
    block = {"n": 1000, "mean_abs_bps": 5.0, "p50_abs_bps": 4.0, "p90_abs_bps": 9.0,
             "p95_abs_bps": 11.0, "p99_abs_bps": 20.0, "styles": styles}
    return {"costs_bps": COSTS, "reaction_ms": 1000,
            "horizons": {"30": {"horizon_s": 30, "no_reaction": block, "with_reaction": block}}}


def test_veredicto_supera_no_supera_y_sin_potencia():
    pr = load_prereg()
    sample = {"days": 18, "test_days": 12}
    assert ceiling_gate.decide(pr, _ceiling(0.1), _oos(0.05, 2.0), sample)["verdict"] == "SUPERA"
    flojo = ceiling_gate.decide(pr, _ceiling(0.1), _oos(0.05, 0.4), sample)
    assert flojo["verdict"] == "NO SUPERA"                 # pasa C2 pero no los +1,0 pb
    assert flojo["by_horizon"]["30"]["c2_signals"] == ["ofi_top_5"]
    sin_ic = ceiling_gate.decide(pr, _ceiling(0.1), _oos(0.05, 2.0, p=0.9), sample)
    assert sin_ic["verdict"] == "NO SUPERA"
    sin_oportunidad = ceiling_gate.decide(pr, _ceiling(0.0001), _oos(0.05, 2.0), sample)
    assert sin_oportunidad["verdict"] == "NO SUPERA"
    corta = ceiling_gate.decide(pr, _ceiling(0.1), _oos(0.05, 2.0), {"days": 9, "test_days": 3})
    assert corta["verdict"] == "SIN POTENCIA"


def test_informe_y_registro_de_intentos(tmp_path):
    pr = load_prereg()
    rep = {"task": "T80", "prereg": pr.version, "prereg_sha256": pr.sha256, "symbol": "BTCUSDT",
           "step_ms": 1000, "reaction_ms": 1000, "seconds": 12.0,
           "sample": {"days": 18, "test_days": 12, "rows": 1_000_000, "rows_panel": 1_200_000,
                      "hours": 386, "first_day_utc": "2026-11-02", "last_day_utc": "2026-11-19",
                      "rows_per_day": {}},
           "queue": ceiling.queue_summary(panel(300, seed=1)),
           "fills": ceiling.fill_table(panel(300, seed=1), wait_steps=(1, 5)),
           "ceiling": _ceiling(0.1), "oos": _oos(0.05, 2.0)}
    rep["gate"] = ceiling_gate.decide(pr, rep["ceiling"], rep["oos"],
                                      {"days": 18, "test_days": 12})
    md = ceiling_report.render(rep, pr)
    for piece in ("# T80", "## 1. Criterios", "## 3. (a) Techo", "## 4. (b) IC",
                  "## 5. (c) pb brutos", "pb netos por operación", "## 6. (d) Qué parte",
                  "## 7. Veredicto", "SUPERA",
                  "`ofi_top_5`", "0,05"):
        assert piece in md
    assert "None" not in md and "nan" not in md
    # el registro de intentos exige que la familia calculada sea la declarada
    with pytest.raises(ValueError, match="familia declarada"):
        write_attempts(tmp_path / "a.json", pr, rep["oos"], {})
    assert rows_from(rep["oos"])[0]["signal"] == "ofi_top_5"
