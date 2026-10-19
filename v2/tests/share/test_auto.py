"""T61: experiencia compartida AUTOMÁTICA — agentes dentro de la API y del servicio de líderes
que importan y exportan solos sobre las bases abiertas."""

import json
from contextlib import contextmanager

from eim.api.reports_db import ReportStore
from eim.data.leader_store import LeaderStore
from eim.data.paper_store import PaperStore
from eim.data.share_auto import Live, ShareAgent, make_agent, save_config
from eim.data.share_export import prune_own
from eim.data.share_import import import_all
from tests.share.helpers import M15, T0, build


class Clock:
    def __init__(self) -> None:
        self.t = 1_792_000_000.0

    def __call__(self) -> float:
        return self.t


@contextmanager
def machine(d, shared, name, clock, hits=None):
    """Una máquina con sus almacenes ABIERTOS (como en producción) y sus dos agentes."""
    ps, rs, ls = (PaperStore(d / "paper.duckdb"), ReportStore(d / "reports.duckdb"),
                  LeaderStore(d / "leaders.duckdb"))
    kw = {"clock": clock, "backup_dir": d.parent / "bk"}
    api = ShareAgent("api", d, shared, name, {"reports.duckdb": Live(*rs.connection),
                                              "paper.duckdb": Live(*ps.connection)},
                     on_imported=(lambda: hits.append(1)) if hits is not None else None, **kw)
    lead = ShareAgent("leaders", d, shared, name,
                      {"leaders.duckdb": Live(*ls.connection, ls.snapshot)}, **kw)
    try:
        yield ps, rs, ls, api, lead
    finally:
        for s in (ps, rs, ls):
            s.close()


def _scenario(tmp_path):
    a = build(tmp_path, "a", asofs=[T0 + i * M15 for i in range(1, 4)], fills=[1, 2],
              report_asofs=[T0], versions=[("trend@15m", 1, "aaa", None, None)])
    b = build(tmp_path, "b", asofs=[T0 + i * M15 for i in range(3, 7)], fills=[2, 3],
              report_asofs=[T0, T0 + 1], versions=[("trend@15m", 1, "aaa", None, None),
                                                   ("trend@15m", 2, "bbb", 1, None)])
    (tmp_path / "cloud").mkdir()                       # la nube ya está sincronizada
    return a, b, tmp_path / "cloud"


def test_agents_share_automatically(tmp_path):
    a, b, shared = _scenario(tmp_path)
    clock, hits = Clock(), []
    with machine(b, shared, "b", clock) as (_, _, _, b_api, b_lead):
        b_api.tick()
        b_lead.tick()
        assert b_api.error == "" and b_lead.error == ""
    names = sorted(p.name for p in (shared / "b").iterdir())
    assert len(names) == 2 and names[0].endswith("-api") and names[1].endswith("-leaders")
    assert not list((b / "share").glob("_stage_*"))                     # sin restos

    with machine(a, shared, "a", clock, hits) as (ps, rs, ls, a_api, a_lead):
        a_api.tick()
        a_lead.tick()
        assert a_api.error == "" and a_lead.error == ""
        assert hits == [1]                                  # derivados recalculados una vez
        assert len(ps.execute("SELECT * FROM paper_ctx")) == 6               # unión de ctx
        assert len(ps.execute("SELECT * FROM val_versions")) == 2
        con, lock = rs.connection
        assert con.execute("SELECT count(*) FROM reports").fetchone()[0] == 2
        assert [r[0] for r in ls.query("SELECT tid FROM leader_fills ORDER BY 1")] == [1, 2, 3]
        ps.save("BTCUSDT", "15m", {"t": T0 + 99 * M15, "v": 1}, "vivo", 1)    # sigue escribiendo
        # nada nuevo en la nube: no se vuelve a importar ni (sin cambios propios) exportar
        clock.t += 7200
        a_api.next_export = 0
        a_api.tick()
        assert hits == [1] and a_api.status()["last_report"]
        assert len(ps.execute("SELECT * FROM share_origin")) == 4            # 4 ctx nuevos de b
    assert list((a / "share").glob("import_*.json"))
    assert (tmp_path / "a" / "bk").exists()                                  # copia previa


def test_both_machines_converge_and_manual_import_agrees(tmp_path):
    a, b, shared = _scenario(tmp_path)
    clock = Clock()
    with machine(a, shared, "a", clock) as (_, _, _, a_api, _), \
            machine(b, shared, "b", clock) as (_, _, _, b_api, _):
        a_api.tick()                  # a exporta lo suyo (aún no hay nada de b)
        b_api.tick()                  # b importa a y exporta (con la unión)
        clock.t += 7200
        a_api.next_import = a_api.next_export = 0
        a_api.tick()                  # a importa lo de b
        q = "SELECT asof_ms FROM paper_ctx ORDER BY 1"
        assert a_api.live["paper.duckdb"].con.execute(q).fetchall() == \
            b_api.live["paper.duckdb"].con.execute(q).fetchall()
    new = tmp_path / "n" / "data"
    new.mkdir(parents=True)
    rep = import_all(new, shared, "n", apply=True)               # colaborador nuevo, a mano
    assert rep.totals()["paper_ctx"]["new"] == 6 and not rep.rejected


def test_errors_never_raise_and_retry(tmp_path):
    a, _, _ = _scenario(tmp_path)
    clock = Clock()
    with machine(a, tmp_path / "no_existe", "a", clock) as (_, _, _, api, _):
        api.tick()
        assert "no existe" in api.status()["error"]
        assert api.next_import == clock.t + 600                  # reintenta en 10 min


def test_rejected_export_is_reported_not_imported(tmp_path):
    a, b, shared = _scenario(tmp_path)
    clock = Clock()
    with machine(b, shared, "b", clock) as (_, _, _, b_api, _):
        b_api.tick()
    f = next((shared / "b").iterdir()) / "paper_ctx.parquet"
    f.write_bytes(f.read_bytes() + b"x")
    with machine(a, shared, "a", clock) as (ps, _, _, a_api, _):
        a_api.tick()
        assert "hash distinto" in a_api.status()["error"]
        assert len(ps.execute("SELECT * FROM paper_ctx")) == 3


def test_make_agent_needs_config(tmp_path):
    d = tmp_path / "data"
    live = {}
    assert make_agent("api", d, live, env={}) is None
    save_config(d, str(tmp_path / "cloud"), "mi-pc")
    ag = make_agent("api", d, live, env={})
    assert ag is not None and ag.machine == "mi-pc" and ag.shared_dir == tmp_path / "cloud"
    assert make_agent("api", d, live, env={"EIM_SHARE_AUTO": "0"}) is None
    env = {"EIM_SHARED_DIR": str(tmp_path / "otra"), "EIM_SHARE_EXPORT_S": "60"}
    ag = make_agent("api", d, live, env=env)
    assert ag.shared_dir == tmp_path / "otra" and ag.export_every_s == 60.0
    assert json.loads((d / "share_config.json").read_text())["machine"] == "mi-pc"


def test_prune_own_keeps_latest_per_kind(tmp_path):
    for n in ("20261001T000000Z-api", "20261002T000000Z-api", "20261003T000000Z-api",
              "20261004T000000Z-api", "20261001T000000Z-leaders", "20261001T000000Z"):
        (tmp_path / "m" / n).mkdir(parents=True)
    gone = prune_own(tmp_path, "m", "api", 2)
    assert sorted(p.name for p in gone) == ["20261001T000000Z-api", "20261002T000000Z-api"]
    assert (tmp_path / "m" / "20261001T000000Z-leaders").exists()
    assert (tmp_path / "m" / "20261001T000000Z").exists()


def test_status_route(tmp_path):
    from fastapi import FastAPI

    from eim.api.share import build_share_router
    from tests.local_client import LocalClient

    a, _, shared = _scenario(tmp_path)
    with machine(a, shared, "a", Clock()) as (ps, rs, _, api, _):
        app = FastAPI()
        app.include_router(build_share_router(rs, ps, a, lambda: api))
        off = FastAPI()
        off.include_router(build_share_router(rs, ps, a))
        with LocalClient(app) as c:
            api.tick()
            got = c.get("/v2/share/status").json()
        with LocalClient(off) as c:
            assert c.get("/v2/share/status").json() == {"mode": "SIMULADO", "enabled": False}
    assert got["enabled"] and got["machine"] == "a" and got["last_export"] and got["error"] == ""
