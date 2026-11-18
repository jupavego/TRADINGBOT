"""T182: la API enciende «lo vivo manda» sola al cerrar T31 (sin reiniciar), y se puede mover o
apagar por el entorno; en las pruebas queda apagado."""

from __future__ import annotations

from eim.api.config import T31_CLOSE_UTC, Settings, _when


def test_la_api_lo_programa_para_el_cierre_de_t31_y_se_puede_mover_o_apagar(monkeypatch):
    close = _when(T31_CLOSE_UTC)
    assert close == 1795824000000                    # 2026-11-28 00:00 UTC
    assert _when("2026-11-28T00:00:00") == close     # sin zona = UTC
    assert _when("off") is None and _when("") is None
    assert Settings().paper_live_first_from_ms is None          # pruebas: apagado
    monkeypatch.delenv("EIM_PAPER_LIVE_FIRST_FROM", raising=False)
    assert Settings.from_env().paper_live_first_from_ms == close
    monkeypatch.setenv("EIM_PAPER_LIVE_FIRST_FROM", "off")
    assert Settings.from_env().paper_live_first_from_ms is None
