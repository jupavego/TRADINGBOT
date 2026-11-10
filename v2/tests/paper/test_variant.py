"""T143 (◆ 2026-11-10): la corrida aparte usa la misma decisión y otra ejecución, sin tocar T31."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from eim.api.paper_variant import build_variant_router, make_variants
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.paper import ledger
from eim.paper.desk import PaperDesk
from eim.paper.params import PROFILES, ExecParams
from eim.paper.t143_config import AUTO_ADAPT, EXEC_T143, PROFILES_T143
from tests.local_client import LocalClient
from tests.paper.test_strategies import ctx_for, walk

SYM = "BTCUSDT"


@pytest.fixture
def world(tmp_path):
    cs = walk(700)
    st = Store(tmp_path)
    st.upsert_candles(SYM, "1h", cs, "test")
    st.upsert_candles(SYM, "15m", cs, "test")
    ps = PaperStore(tmp_path / "p.duckdb")
    for c in cs[450:500]:
        ps.save(SYM, "1h", ctx_for(c), "backtest", 0)
    variants = make_variants(("t143",), st, tmp_path, ps, None)
    yield st, ps, variants["t143"], tmp_path
    variants["t143"].pstore.close()
    ps.close()


def test_los_valores_por_defecto_siguen_siendo_t31():
    ep = ExecParams()
    assert ep.maker_entry_timeframes == () and ep.tf_max_cost_r is None
    assert not any(p.risk_includes_costs for p in PROFILES)


def test_la_corrida_aparte_lleva_las_tres_palancas_y_solo_esas():
    assert EXEC_T143.maker_entry_timeframes == ("1h", "4h") and EXEC_T143.tf_max_cost_r == 0.15
    assert all(p.risk_includes_costs for p in PROFILES_T143)
    assert [p.model_copy(update={"risk_includes_costs": False}) for p in PROFILES_T143] \
        == list(PROFILES)
    assert set(AUTO_ADAPT) == {"tf_max_cost_r", "maker_entry_timeframes", "risk_includes_costs"}


def test_lee_los_contextos_de_la_principal_y_escribe_en_su_base(world):
    st, ps, var, tmp = world
    assert (tmp / "paper_t143.duckdb").exists()
    v = var.view(SYM)
    assert v.summary["coverage"]["contexts"] == 50          # los de la principal
    with pytest.raises(RuntimeError):
        var.pstore.save(SYM, "1h", {"t": 1}, "vivo", 0)      # nunca escribe contextos
    main = PaperDesk(st, ps)
    main.view(SYM)
    # cada una su libro: las tablas de la variante viven en su base, no en la de T31
    assert ledger.counts(var.pstore) == ledger.counts(var.pstore.own)
    assert var.pstore.own is not ps


def test_su_tick_no_genera_contextos(world):
    _, ps, var, _ = world
    before = ps.asofs(SYM, "1h")
    assert var.tick() == 0
    assert ps.asofs(SYM, "1h") == before
    assert var.heartbeat_path().name == "heartbeat_t143.json"


def test_rutas_de_solo_lectura(world):
    _, _, var, _ = world
    app = FastAPI()
    app.include_router(build_variant_router({"t143": var}))
    with LocalClient(app) as c:
        assert c.get("/v2/paper/variant").json()["variants"][0]["name"] == "t143"
        assert c.get("/v2/paper/variant/otra").status_code == 404
        r = c.get(f"/v2/paper/variant/t143?symbol={SYM}")
        assert r.status_code in (200, 503)
        assert c.get("/v2/paper/variant/t143/ledger.csv").status_code == 200


def test_variante_desconocida_no_arranca(tmp_path):
    with pytest.raises(ValueError):
        make_variants(("nada",), None, tmp_path, None, None)
