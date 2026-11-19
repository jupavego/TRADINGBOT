"""Informe mensual de la cantera (T172): cifras, retroalimentación y reparto, con datos sintéticos.

Sin red ni bases: el libro se arma como filas de `nursery_trades` con el pre-registro publicado.
Cada operación lleva su d (R − media de los gemelos) y su R; el P&L es pequeño para que ningún
tope de drawdown interfiera salvo donde se busca.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from eim.data.library_digital import DigitalPaths, read_nursery_facts
from eim.nursery.ladder_stats import DAY_MS, H_MS
from eim.nursery.prereg import load_prereg
from eim.nursery.report import feedback, haircut, render, run, source
from eim.nursery.report.rows import Snapshot

PR = load_prereg()
ALTA = 1_800_000_000_000
DAY31 = ALTA + 31 * DAY_MS
STRONG, NEG, FLAT = "ema_precio_200", "pa_bos", "lit_consenso"   # bases, con historia


def _account(pid: str) -> str:
    fp = next(x.fingerprint for x in PR.family.members if x.id == pid)
    return f"{pid}@{fp}"


def _trades(pid: str, d, r=None, cost=0.1, days=29) -> list[dict]:
    d = np.asarray(d, float)
    r = d if r is None else np.asarray(r, float)
    step = days * DAY_MS // len(d)
    out = []
    for i in range(len(d)):
        t = ALTA + i * step + H_MS
        out.append({"account_id": _account(pid), "t": t, "side": 1 if i % 2 else -1,
                    "booked": True, "status": "CERRADA", "fill_t": t, "exit_t": t + H_MS,
                    "pnl_usd": 5.0 * float(r[i]), "r": float(r[i]), "cost_r": cost,
                    "d_r": float(d[i])})
    return out


def _snap(asof: int = DAY31, trades: list[dict] | None = None) -> Snapshot:
    rng = np.random.default_rng(172)
    accounts = [{"account_id": _account(x.id), "kind": "prospecto", "prospect_id": x.id,
                 "fingerprint": x.fingerprint, "timeframe": x.timeframe}
                for x in PR.family.members]
    accounts += [{"account_id": g, "kind": "control", "prospect_id": None, "fingerprint": None,
                  "timeframe": g.split("@")[1]} for g in sorted({x.generic
                                                                 for x in PR.family.members})]
    if trades is None:
        trades = (_trades(STRONG, rng.normal(0.9, 1.0, 200))
                  + _trades(NEG, rng.normal(-0.6, 1.0, 80))
                  + _trades(FLAT, rng.normal(0.0, 0.5, 700), cost=0.0, days=29))
        flat = [t for t in trades if t["account_id"] == _account(FLAT)]
        for t in flat:
            t["r"] = t["d_r"] - 0.05
    ev = [{"t": ALTA, "kind": "puerta_costo", "timeframe": "15m", "value_r": None,
           "source": "sin medir", "threshold_r": 0.3, "before": None, "after": "abierto",
           "accounts": ["x"]}]
    bh = {"return_pct": 2.0, "r_long": 1.2, "r_short": -1.2, "basis": "prueba"}
    return Snapshot(PR, ALTA, asof, accounts, trades, ev, bh, None, "prueba", [])


def test_first_review_ladder_library_and_feedback():
    r = run.build(_snap(), run.literature_of())
    stage = {p["id"]: p["stage"] for p in r["prospects"]}
    assert r["reviews_done"] == 1
    assert stage[STRONG] == "promesa"
    assert stage[NEG] == "baja" and stage[FLAT] == "baja"
    verdicts = {f["prospect"]: f["verdict"] for f in r["library"]["items"]}
    assert verdicts[STRONG] == feedback.SOSTENIDA
    assert verdicts[NEG] == feedback.REFUTADA and verdicts[FLAT] == feedback.REFUTADA
    assert verdicts["bots_mayoria"] == feedback.NO_CONCLUYENTE      # sin operaciones
    causes = {d["id"]: d["cause"] for d in r["improvement"]["drops"]}
    assert causes[NEG] == "teoría contraria"
    assert causes[FLAT] == "variable sin información"
    assert any(f"`{FLAT}`" in ln for ln in r["improvement"]["backlog"])
    assert all(p["requires"] == "◆ del usuario" for p in r["improvement"]["proposals"])
    assert r["informativity"]["agents"]["ema"]["state"] == "informativo"
    assert r["graduations"] == [] and r["closure"] is None
    assert r["family"]["with_trades"] == 3 and r["family"]["n_effective"] >= 1
    md = render.markdown(r)
    for head in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6.", "SIMULADO"):
        assert head in md


def test_before_first_review_nothing_goes_to_the_library():
    r = run.build(_snap(asof=ALTA + 10 * DAY_MS), run.literature_of())
    assert r["reviews_done"] == 0 and r["library"]["items"] == []
    assert {p["stage"] for p in r["prospects"]} == {"guarderia"}
    assert r["moves"] == []


def test_write_is_idempotent_and_due_follows_the_reviews(tmp_path):
    snap = _snap()
    r = run.build(snap, run.literature_of())
    backlog = tmp_path / "BACKLOG.md"
    backlog.write_text("# BACKLOG\n", encoding="utf-8")
    s = run.write(r, tmp_path / "out", tmp_path / "data", backlog=backlog)
    assert (tmp_path / "out" / f"cantera_{r['date']}.md").exists()
    latest = json.loads((tmp_path / "out" / "latest.json").read_text(encoding="utf-8"))
    assert latest["reviews_done"] == 1 and s["library"]["added"] == r["library"]["facts"] > 0
    facts = read_nursery_facts(DigitalPaths(tmp_path / "data" / "library" / "digital"))
    assert len(facts) == r["library"]["facts"]
    r2 = run.build(snap, run.literature_of())
    run.write(r2, tmp_path / "out", tmp_path / "data", backlog=backlog)
    assert r2["library"]["added"] == 0
    assert backlog.read_text(encoding="utf-8").count(f"el prospecto `{FLAT}`") == 1
    assert not run.due(tmp_path / "out", ALTA, PR.ladder, DAY31 + DAY_MS)
    assert run.due(tmp_path / "out", ALTA, PR.ladder, ALTA + 62 * DAY_MS)
    assert not run.due(tmp_path / "nada", ALTA, PR.ladder, ALTA + DAY_MS)


def test_closure_at_the_deadline_says_none_graduated():
    end = ALTA + PR.ladder.deadline_days * DAY_MS + DAY_MS
    r = run.build(_snap(asof=end), run.literature_of())
    assert r["closure"]["headline"] == "ninguno se graduó"
    assert r["reviews_done"] == len(PR.ladder.reviews_days)
    assert all(v["stage"] in ("baja", "promesa", "primer_equipo")
               for v in r["closure"]["per_prospect"].values())


def test_harvey_liu_cuts_marginal_sharpes_more_than_strong_ones():
    rng = np.random.default_rng(19)
    strong = rng.normal(0.5, 1.0, 400)
    weak = rng.normal(0.12, 1.0, 400)
    fam = [0.5] * 40
    hs, hw = haircut.haircut(strong, fam, 50), haircut.haircut(weak, fam, 50)
    assert 0 <= hs["haircut_mean"] < hw["haircut_mean"] <= 1
    assert hs["live_edge_r"] < hs["mean_r"]
    adj = haircut.adjusted(0.01, fam, 50)
    assert adj["bonferroni"] == pytest.approx(0.5)
    assert adj["holm"] <= adj["bonferroni"]


def test_open_book_falls_back_to_the_newest_copy(tmp_path):
    live = tmp_path / "data"
    live.mkdir()
    (live / source.DB_NAME).write_text("x")
    old, new = (tmp_path / "bk" / f"eim_2026120{i}-030000" for i in (1, 2))
    for p in (old, new):
        p.mkdir(parents=True)
        (p / source.DB_NAME).write_text("x")

    def opener(p):
        if p.parent == live:
            raise OSError("bloqueada por otro proceso")
        return p

    paths = source.candidates(live, tmp_path / "bk", None)
    con, used = source.open_book(paths, opener)
    assert used == new / source.DB_NAME
    assert source.copy_time(used) == 1_796_180_400_000      # 2026-12-02 03:00 UTC
    with pytest.raises(FileNotFoundError):
        source.open_book([tmp_path / "nada.duckdb"], opener)


def test_read_book_with_duckdb(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    from eim.data.paper_store import PaperStore
    from eim.nursery.store import NurseryStore

    db = tmp_path / source.DB_NAME
    ps = PaperStore(db)
    st = NurseryStore(ps)
    st.alta(PR.version, PR.sha256, ALTA)
    ps.executemany("INSERT INTO nursery_accounts VALUES (?,?,?,?,?,?)",
                   [(_account(STRONG), "prospecto", STRONG, None, "4h", ALTA)])
    ps.executemany("INSERT INTO nursery_trades (account_id, t, side, booked, status, fill_t, "
                   "exit_t, pnl_usd, r, cost_r, d_r) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   [(_account(STRONG), ALTA + H_MS, 1, True, "CERRADA", ALTA + H_MS,
                     ALTA + 2 * H_MS, 5.0, 1.0, 0.1, 0.8)])
    ps.close()
    con = duckdb.connect(str(db), read_only=True)
    alta, accounts, trades, events = source.read_book(con, PR)
    con.close()
    assert alta == ALTA and accounts[0]["prospect_id"] == STRONG
    assert trades[0]["d_r"] == pytest.approx(0.8) and events == []
