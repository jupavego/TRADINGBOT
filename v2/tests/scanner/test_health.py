"""T102 — salud multiactivo: por clase y por fuente, «sin datos» nunca sano y avisos que
avisan al entrar y al resolverse."""

from __future__ import annotations

from eim.scanner import health as H
from eim.scanner import health_alerts as HA
from tests.scanner._t102 import ASOF, DAY, NOW, STATUS, make_view

EXCL = {"crypto": {"liquidez": 2}, "equity": {"liquidez": 2, "pocas_velas": 2}}


def _cls(h: dict, name: str) -> dict:
    return next(c for c in h["classes"] if c["asset_class"] == name)


def test_healthy_view_reports_what_is_watched_with_which_data():
    h = H.build(make_view(), STATUS, NOW, excl_by_class=EXCL)
    assert h["mode"] == "ANALISIS" and h["overall"] == H.OK
    assert h["watching"] == {"classes": ["crypto", "equity"], "n_instruments": 8}
    c = _cls(h, "crypto")
    assert c["plan"] == H.ENABLED and c["alerting"] and c["state"] == H.OK
    assert c["coverage"] == 0.75 and c["n_excluded"] == 2 and c["stale_rows"] == 0
    assert c["markets"] == {"abierto": 6, "cerrado": 0, "sin_calendario": 0}
    assert c["candidates"] == 3 and len(c["top"]) == 3
    eq = _cls(h, "equity")
    assert eq["plan"] == H.WATCH and not eq["alerting"] and eq["coverage"] == 0.3333
    assert _cls(h, "bond")["state"] == H.PLANNED and _cls(h, "option")["state"] == H.PLANNED
    assert h["scanner"]["budget"]["within_budget"] is True
    assert h["scanner"]["ranking"]["threshold_status"] == "vigente"


def test_provider_health_declares_level_licence_and_usage_ceiling():
    h = H.build(make_view(), STATUS, NOW)
    bf = next(p for p in h["providers"] if p["name"] == "binance-futures")
    assert bf["used"] and bf["classes"] == ["crypto", "equity"] and bf["level"] == 2
    assert bf["usage_share"] == round(60 / 1.5 * 5 / 2400, 4)   # techo declarado de la cola
    assert "no se mide" in bf["usage_note"] and bf["state"] == H.OK
    others = [p for p in h["providers"] if not p["used"]]
    assert others and all(p["state"] == H.PLANNED for p in others)


def test_no_data_is_never_healthy():
    h = H.build(None, None, NOW)
    assert h["overall"] == H.NO_DATA and h["view"]["state"] == H.NO_DATA
    assert _cls(h, "crypto")["state"] == H.NO_DATA
    assert all(c["state"] != H.OK for c in h["classes"])
    assert "no se vigila ningún mercado" in h["blind_spots"][0]
    only_equity = H.build(make_view({"equity": 3}), STATUS, NOW)
    assert _cls(only_equity, "crypto")["state"] == H.NO_DATA
    assert only_equity["overall"] == H.NO_DATA


def test_freshness_degrades_then_goes_stale():
    v = make_view()
    assert H.build(v, STATUS, NOW + 2 * DAY)["overall"] == H.DEGRADED     # > 36 h
    stale = H.build(v, STATUS, NOW + 4 * DAY)                              # > 72 h
    assert stale["overall"] == H.STALE and _cls(stale, "crypto")["state"] == H.STALE


def test_old_data_and_incomplete_quality_degrade_a_class():
    h = H.build(make_view(last_t=ASOF - 10 * DAY), STATUS, NOW)
    c = _cls(h, "crypto")
    assert c["state"] == H.DEGRADED and c["stale_rows"] == 6
    assert any("datos viejos" in r for r in c["reasons"])
    q = _cls(H.build(make_view(quality=0.8), STATUS, NOW), "crypto")
    assert q["state"] == H.DEGRADED and q["quality_incomplete"] == 6


def test_failed_jobs_and_missing_ranking_degrade_the_scanner():
    v = make_view()
    v["runs"][0]["detail"]["failed"] = [{"instrument_id": "x", "error": "boom"}]
    v["ranking"] = {"available": False, "error": "RuntimeError: x"}
    h = H.build(v, STATUS, NOW)
    assert h["scanner"]["state"] == H.DEGRADED and h["scanner"]["failed_jobs"] == 1
    assert any("sin ranking" in r for r in h["scanner"]["reasons"])
    assert next(p for p in h["providers"] if p["used"])["errors"] == 1


def test_coverage_is_unmeasured_without_exclusions_never_invented():
    c = _cls(H.build(make_view(), STATUS, NOW), "crypto")
    assert c["coverage"] is None and c["n_excluded"] is None


def test_blind_spots_name_what_cannot_be_seen():
    spots = H.build(make_view(), STATUS, NOW, excl_by_class=EXCL)["blind_spots"]
    assert any("liquidez" in s for s in spots) and any("pocas_velas" in s for s in spots)
    assert any("no hay funding" in s for s in spots)


def test_alerts_fire_on_entry_once_and_resolve():
    bad = H.build(None, None, NOW)
    alerts, active = HA.transitions({}, HA.conditions(bad), NOW)
    keys = {a.key for a in alerts}
    assert {"multiactivo:clase:crypto", "multiactivo:escaner"} <= keys
    assert "multiactivo:clase:equity" not in keys          # en observación: no despierta a nadie
    again, active2 = HA.transitions(active, HA.conditions(bad), NOW + 1)
    assert again == [] and active2 == active
    good = H.build(make_view(), STATUS, NOW)
    done, active3 = HA.transitions(active2, HA.conditions(good), NOW + 2)
    assert active3 == {} and done and all(a.resolved and a.title.startswith("Resuelta")
                                          for a in done)
