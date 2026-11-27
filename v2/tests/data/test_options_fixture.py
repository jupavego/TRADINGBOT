"""T213: el colector sobre un recorte REAL de Deribit, grabado en la laptop (sin red).

`fixtures/options/deribit_btc_book_summary.json` lo graba `aplicar_t213` con
`python -m eim.data.options_chain record-fixture`: todas las filas de dos vencimientos de BTC, tal
cual llegaron (◆ T213: uso personal; el recorte vive en el repositorio privado del proyecto).
Aquí no se fija ninguna cifra de mercado: solo propiedades que cualquier toma real debe cumplir.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eim.data import options_chain as oc
from eim.data.options_parse import parse_name
from tests.data.options_helpers import provider_for

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "options" / "deribit_btc_book_summary.json"
DOC = json.loads(FIX.read_text(encoding="utf-8"))
RAW, TAKEN = DOC["result"], int(DOC["recorded_ms"])
REQUIRED = ("mark_price", "mark_iv", "underlying_price", "interest_rate", "open_interest",
            "creation_timestamp")


def _complete(r: dict) -> bool:
    return parse_name(r["instrument_name"]) is not None and all(
        isinstance(r.get(k), int | float) for k in REQUIRED) and r["underlying_price"] > 0


def test_fixture_is_a_real_untouched_cut():
    assert DOC["endpoint"].endswith("/public/get_book_summary_by_currency")
    assert DOC["params"] == {"currency": "BTC", "kind": "option"}
    assert 1 <= len(DOC["expiries_kept"]) <= 2 and len(RAW) <= DOC["n_live_total"]
    assert all(r["instrument_name"].startswith("BTC-") for r in RAW)


def test_real_cut_becomes_a_complete_snapshot(tmp_path):
    out = oc.take_snapshot(tmp_path, "BTC", provider_for(RAW, now=TAKEN), clock=lambda: TAKEN)
    n_ok = sum(_complete(r) for r in RAW)
    assert out["rows"] == n_ok and out["dropped"] == len(RAW) - n_ok and n_ok > 0
    data, quality = oc.snapshot_paths(tmp_path, "BTC", TAKEN)
    rows = oc.read_rows(data)
    assert len(rows) == n_ok
    assert all(r["expiry"] > TAKEN and r["strike"] > 0 and r["kind"] in ("call", "put")
               for r in rows)
    assert all(r["mark"] >= 0 and r["mark_iv"] > 0 and r["underlying"] > 0 for r in rows)
    assert all(r["bid"] is None or r["ask"] is None or r["bid"] > 0 for r in rows)
    q = json.loads(quality.read_text(encoding="utf-8"))
    assert q["n_expiries"] == len(DOC["expiries_kept"])
    assert set(q["by_status"]) <= {"ok", "degradado", "no_data"}


def test_real_cut_iv_matches_deribit_mark_iv_near_the_money(tmp_path):
    """Si las unidades estuvieran mal (BTC frente a USD), la IV desde bid/ask no se parecería
    a la IV de marca de Deribit, o ni existiría."""
    oc.take_snapshot(tmp_path, "BTC", provider_for(RAW, now=TAKEN), clock=lambda: TAKEN)
    _, quality = oc.snapshot_paths(tmp_path, "BTC", TAKEN)
    exps = json.loads(quality.read_text(encoding="utf-8"))["expiries"]
    both = [e for e in exps if e.get("atm_iv") is not None and e.get("mark_atm_iv") is not None]
    assert both, "ningún vencimiento del recorte dio σ ATM: revisar el recorte"
    for e in both:
        assert 0.05 < e["atm_iv"] < 5.0
        assert e["atm_iv"] == pytest.approx(e["mark_atm_iv"], abs=0.2)
