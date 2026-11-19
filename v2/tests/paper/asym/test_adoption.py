"""Fase 3: el primer veredicto no se revisa, solo se adopta costo y riesgo, y nunca hacia atrás."""

from __future__ import annotations

import json

from eim.paper.asym import adoption as A
from eim.paper.asym import prereg as P
from eim.paper.params import PROFILES, ExecParams

CP = P.checkpoints_ms()


def test_first_verdict_is_written_once(tmp_path):
    path = tmp_path / "verdicts.json"
    A.settle(path, {"t187b": {"state": "EN CURSO"}}, CP[0])
    assert not path.exists()
    A.settle(path, {"t187b": {"state": "PASA", "why": "x"}}, CP[0])
    A.settle(path, {"t187b": {"state": "NO PASA", "why": "y"}}, CP[1])
    done = json.loads(path.read_text(encoding="utf-8"))
    assert done["t187b"]["state"] == "PASA" and done["t187b"]["at"] == CP[0]
    assert done["t187b"]["fingerprint"] == P.FINGERPRINT


def test_adoption_instant_is_the_next_midnight_and_never_before_t31():
    assert A.instant_after(P.START_MS) == P.T31_CLOSE_MS
    assert A.instant_after(CP[0]) == CP[0] + P.DAY_MS
    assert A.instant_after(CP[0] + 5) == CP[0] + P.DAY_MS


def test_only_cost_and_risk_rules_are_adopted(tmp_path):
    verdicts = {r: {"state": "PASA", "at": CP[0], "why": "ok"}
                for r in ("t187b", "t188", "t189_1h")}
    verdicts["t187c"] = {"state": "NO PASA", "at": CP[0]}
    adopted = A.adopt(tmp_path / "adopted.json", verdicts)
    assert set(adopted) == {"t187b", "t189_1h"}            # T188 lo decide el usuario
    assert adopted["t187b"]["from_ms"] == CP[0] + P.DAY_MS
    assert A.adopt(tmp_path / "off.json", verdicts, enabled=False) == {}


def test_adoption_reaches_params_without_changing_anything_else():
    inst = {"t187b": 10, "t189_15m": 20, "t188": 30}
    ep = A.exec_params_with(ExecParams(), inst)
    assert ep.maker_from_ms == (("15m", 20),) and ep.maker_entry_timeframes == ()
    assert A.exec_params_with(ExecParams(), {}) == ExecParams()
    ps = A.profiles_with(PROFILES, inst, 99)
    assert all(p.asym_from_ms == (("t187b", 10),) and p.phase2_from_ms == 99 for p in ps)
    assert A.profiles_with(PROFILES, {}, None) == PROFILES      # mismos objetos, sin copias
    assert ps[0].adopted("t187b", 10) and not ps[0].adopted("t187b", 9)
    assert not ps[0].adopted("t187c", 10**15)


def test_adopted_file_is_read_only_when_it_changes(tmp_path):
    f = A.AdoptedFile(tmp_path / "adopted.json")
    assert f.instants() == {}
    A.write_json(tmp_path / "adopted.json", {"t187c": {"from_ms": 5}, "roto": {}})
    assert f.instants() == {"t187c": 5}
    assert A.AdoptedFile(None).instants() == {}
