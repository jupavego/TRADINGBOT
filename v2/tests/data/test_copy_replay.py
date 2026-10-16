"""Reproducción de la copia sobre un historial capturado (T42), sin red: almacén con fotos,
ejecuciones, precio del seguidor grabado, funding, reconciliaciones y velas → mismo motor que
en vivo → atribución aparente vs copiable → informe y CLI `copy-sim`."""

from __future__ import annotations

import json

import pytest

from eim.copytrading.copy_attrib import CAUSES
from eim.copytrading.copy_params import CopyParams
from eim.copytrading.copy_report import render
from eim.copytrading.copy_risk import copy_config
from eim.core.leaders import LeaderFunding
from eim.data.copy_replay import funding_rates, replay
from eim.data.leader_store import LeaderStore
from eim.leaders.cli import main as cli
from eim.leaders.copy_cli import _sim_of
from tests.copytrading import helpers as H
from tests.copytrading.copy_helpers import SPEC

LID, T0 = H.LID, H.T0
S = 1_000
FILLS = [  # (moneda, de, a, precio, t)
    ("ETH", 10.0, 0.0, 2_520.0, 300 * S),  # cierra lo preexistente: no se copia
    ("BTC", 0.0, 4.0, 50_000.0, 60 * S), ("BTC", 4.0, 6.0, 50_100.0, 120 * S),
    ("BTC", 6.0, 3.0, 50_300.0, 600 * S), ("BTC", 3.0, 0.0, 50_400.0, 1_200 * S),
    ("BTC", 0.0, -2.0, 50_200.0, 1_500 * S), ("BTC", -2.0, 2.0, 49_900.0, 1_800 * S),
    ("BTC", 2.0, 0.0, 50_050.0, 2_400 * S)]
PHOTOS = [(0, {"ETH": 10.0}), (700 * S, {"BTC": 3.0}), (1_300 * S, {}),
          (1_600 * S, {"BTC": -2.0}), (2_500 * S, {})]
END = T0 + 3_600 * S


def _store(path) -> LeaderStore:
    store = LeaderStore(path)
    store.upsert_leader(H.leader(status="watch"), 0)
    fills = []
    for k, (coin, a, b, px, dt) in enumerate(sorted(FILLS, key=lambda x: x[4])):
        pnl = 0.0 if abs(b) >= abs(a) and (a == 0 or (a > 0) == (b > 0)) else \
            (px - (50_000.0 if coin == "BTC" else 2_500.0)) * min(abs(a), abs(a - b)) * \
            (1 if a > 0 else -1)
        fills.append(H.fill(coin, a, b, px, T0 + dt, k + 1, pnl=pnl, fee=abs(b - a) * px * 2e-4))
    store.add_fills(fills)
    store.add_follow(list(H.quotes(fills, adverse_bps=2.0).values()))
    for dt, pos in PHOTOS:
        ps = [H.position(c, "long" if v > 0 else "short", abs(v),
                         50_000.0 if c == "BTC" else 2_500.0, T0 + dt) for c, v in pos.items()]
        store.save_positions(LID, T0 + dt, T0 + dt + 100, ps, keep_ms=0)
    for dt in range(30 * S, 3_600 * S, 30 * S):
        store.query("INSERT INTO leader_recon VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [LID, T0 + dt, T0 + dt, 1, 0, True, True, False, None, 0, 0])
    h = T0 - T0 % 3_600_000 + 3_600_000
    store.add_funding([LeaderFunding(leader_id=LID, address=LID.split(":")[1], symbol="BTC",
                                     usdc=-2.0, rate=0.0001, size=0.4, t=h, observed_at=h + 60,
                                     source="test")])
    store.save_portfolio(LID, T0, H.portfolio(60, av=1_000_000.0, t_end=T0))
    return store


def _bars() -> dict:
    t = T0 - T0 % 60_000
    return {"BTC": [(t + k * 60_000, 50_000.0, 50_200.0, 49_800.0, 50_000.0, 100.0)
                    for k in range(61)]}


def test_replay_runs_the_live_engine_on_recorded_history(tmp_path):
    store = _store(tmp_path / "leaders.duckdb")
    p = CopyParams()
    rates = funding_rates(store, T0, END)
    res = replay(store, H.leader(status="watch"), p, SPEC, copy_config(p), _bars(), rates, END)
    eng = res.engine
    assert res.price_src == {"bbo": 8} and eng.measure  # 8 señales (la de ETH no se copia)
    assert [f.kind for f in eng.fills] == ["open", "increase", "reduce", "close", "open",
                                           "close", "open", "close"]
    assert all(f.src == "bbo" and f.latency_ms == 500 for f in eng.fills)
    assert eng.counts.get("pauses", 0) == 0 and eng.counts["recon"] == len(PHOTOS) - 1
    assert eng.journal[-1].kind in ("order", "funding", "recon") and eng.account.positions == {}
    sim = _sim_of(res)
    a = sim.attribution
    assert (a.trips, a.copied, a.skipped) == (3, 3, 0)
    assert a.follower - a.apparent == pytest.approx(sum(a.causes[k] for k in CAUSES))
    assert a.causes["latencia"] < 0 and a.causes["diferencial"] < 0  # 2 pb en contra + libro
    md = render([sim], None, p, "risk_copy_v1", END, SPEC.source)
    assert "SIMULADO" in md and "Copiable vs aparente" in md and "solo para medir" in md
    store.close()


def test_cli_copy_sim_writes_report_and_full_journal(tmp_path, capsys):
    db = tmp_path / "copia.duckdb"
    _store(db).close()
    (tmp_path / "leaders").mkdir()
    (tmp_path / "leaders" / "hl_meta.json").write_text(json.dumps(
        {"universe": [{"name": "BTC", "szDecimals": 5}, {"name": "ETH", "szDecimals": 4}]}),
        encoding="utf-8")
    out, jr = tmp_path / "informe.md", tmp_path / "j.jsonl"
    assert cli(["--root", str(tmp_path), "copy-sim", "--db", str(db), "--offline",
                "--out", str(out), "--journal", str(jr)]) == 0
    assert "1 líderes reproducidos" in capsys.readouterr().out
    md = out.read_text(encoding="utf-8")
    assert "Resultado por líder" in md and "sin velas de 1 min" in md
    kinds = {json.loads(x)["kind"] for x in jr.read_text(encoding="utf-8").splitlines()}
    assert kinds >= {"start", "signal", "decision", "risk", "order"}
    assert cli(["--root", str(tmp_path), "copy-status"]) == 0
    assert "Sin copia en vivo" in capsys.readouterr().out
