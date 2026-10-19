"""Servicio de validación (T49): evidencia por versión, persistencia y `GET /v2/validation`."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pytest

from eim.api.config import Settings
from eim.api.main import create_app
from eim.core import Candle
from eim.data.paper_store import PaperStore
from eim.data.store import Store
from eim.data.validation_store import ValidationStore
from eim.paper.catalog import CATALOG
from eim.paper.engine import Path, simulate
from eim.paper.params import ExecParams
from eim.validation.gate import OBSERVACION, RECHAZADA, VALIDADA
from eim.validation.service import Validator
from tests.local_client import LocalClient
from tests.paper.helpers import H1, M15, T0, idea
from tests.paper.test_strategies import ctx_for, walk

SID = "consenso_sintesis@1h"


def n_versions(*tfs: str) -> int:
    """Versiones vigentes: cada estrategia en los marcos donde corre (T54: algunas solo en 4 h)."""
    return sum(i.runs_in(tf) for tf in tfs for i in CATALOG.values())


def _path(n: int = 4000, seed: int = 1) -> Path:
    rng = np.random.default_rng(seed)
    p, cs = 100.0, []
    for i in range(n):
        o = p
        p = o * float(np.exp(rng.normal(0, 0.003)))
        cs.append(Candle(t=T0 + i * M15, o=o, h=max(o, p) * 1.001, l=min(o, p) * 0.999, c=p,
                         v=1.0))
    return Path(cs)


@dataclass
class FakeView:
    outcomes: list
    path: Path
    summary: dict = field(default_factory=lambda: {"coverage": None})


class FakeDesk:
    tfs = ("1h",)
    symbols = ("X",)

    def __init__(self, ep: ExecParams, view: FakeView) -> None:
        self.ep, self._view = ep, view

    def view(self, _symbol):
        return self._view


def _outcomes(path: Path, version: str, every_h: int = 6, n: int = 120) -> list:
    out = []
    for k in range(n):
        t = T0 + k * every_h * H1
        j = int(np.searchsorted(path.t, t))
        px = float(path.o[j])
        i = replace(idea(side=1 if k % 2 else -1, entry=px, sl=px * (0.99 if k % 2 else 1.01),
                         tp=px * (1.02 if k % 2 else 0.98), t=t, strategy="consenso_sintesis",
                         iid=f"X:1h:{t}"), timeframe="1h", version=version, regime="range")
        out.append(simulate(i, path, ExecParams()))
    return out


@pytest.fixture
def vstore():
    ps = PaperStore(":memory:")
    yield ValidationStore(ps)
    ps.close()


def test_only_current_version_counts_and_new_version_inherits_nothing(vstore, tmp_path):
    path, ep = _path(), ExecParams()
    cur = CATALOG["consenso_sintesis"].version("1h", ep)
    outs = _outcomes(path, cur) + _outcomes(path, "huella_vieja", every_h=7)
    desk = FakeDesk(ep, FakeView(outs, path))
    val = Validator(desk, vstore, lineage=tmp_path / "sin_declaraciones.json")
    now = T0 - H1                          # alta antes de los datos: todo es fuera de muestra
    p = val.compute("X", now)
    v = next(x for x in p["verdicts"] if x["sid"] == SID)
    closed = sum(o.status == "CERRADA" for o in outs if o.idea.version == cur)
    assert v["id"] == f"{SID}@v1" and v["n_oos"] == closed > 0
    assert v["fingerprint"] == cur and v["verdict"] in (OBSERVACION, RECHAZADA)
    assert p["attempts"] == len(p["verdicts"]) == n_versions("1h")
    # cambia la mecánica → versión nueva: alta automática, no hereda la evidencia anterior
    ep2 = ExecParams(cooldown_bars=2)
    cur2 = CATALOG["consenso_sintesis"].version("1h", ep2)
    outs2 = [replace(o, idea=replace(o.idea, version=cur2)) for o in outs[:120]]
    later = path.end + H1
    val2 = Validator(FakeDesk(ep2, FakeView(outs2, path)), vstore,
                     lineage=tmp_path / "sin_declaraciones.json")
    p2 = val2.compute("X", later)
    v2 = next(x for x in p2["verdicts"] if x["sid"] == SID)
    assert v2["id"] == f"{SID}@v2" and v2["origin"] == "auto"
    assert v2["n_oos"] == 0 and v2["oos"]["excluded_in_windows"] == closed
    # Holm cuenta también las versiones retiradas (v1 de cada estrategia)
    assert p2["attempts"] == 2 * n_versions("1h")
    old = next(x for x in p2["versions"] if x["id"] == f"{SID}@v1")
    assert old["retired"] == later


def test_due_every_4h_close(vstore, tmp_path):
    val = Validator(FakeDesk(ExecParams(), FakeView([], _path(10))), vstore,
                    lineage=tmp_path / "x.json")
    four = 4 * H1
    assert val.due(T0)
    val.last_run = T0 // four * four + 1
    assert not val.due(T0 // four * four + 3 * H1)
    assert val.due(T0 // four * four + four + 1)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("validation")
    cs = walk(700)
    st = Store(tmp)
    st.upsert_candles("BTCUSDT", "1h", cs, "test")
    m15 = [Candle(t=c.t + k * M15, o=c.o, h=c.h, l=c.l, c=c.c, v=c.v / 4)
           for c in cs for k in range(4)]
    st.upsert_candles("BTCUSDT", "15m", m15, "test")

    class Idle:
        name = "idle"

        async def stream(self, symbol, timeframe):
            import asyncio
            yield {"type": "status", "state": "up", "detail": ""}
            await asyncio.sleep(3600)

    with LocalClient(create_app(Settings(data_dir=tmp, heartbeat_s=0.2), source=Idle())) as c:
        ps = c.app.state.paper.pstore
        for i in range(450, 650):
            ps.save("BTCUSDT", "1h", ctx_for(cs[i]), "backtest", 0)
        yield c


def test_get_validation_returns_current_verdicts(client):
    r = client.get("/v2/validation?symbol=BTCUSDT")
    assert r.status_code == 200
    v = r.json()
    assert v["mode"] == "SIMULADO" and v["criteria"]["version"] == "validation_v1"
    assert v["criteria"]["sha256"] and v["asof"] and v["computed"]
    assert len(v["verdicts"]) == n_versions("15m", "1h", "4h") == v["attempts"]
    assert {x["verdict"] for x in v["verdicts"]} <= {VALIDADA, OBSERVACION, RECHAZADA}
    assert all(len(x["checks"]) == 6 for x in v["verdicts"])
    again = client.get("/v2/validation?symbol=BTCUSDT").json()      # vigentes guardados
    assert again["asof"] == v["asof"] and again["computed"] == v["computed"]
    sid = v["verdicts"][0]["sid"]
    h = client.get(f"/v2/validation/history?sid={sid}&symbol=BTCUSDT").json()
    assert h["history"] and h["history"][0]["asof"] == v["asof"]
    assert client.get("/v2/validation?symbol=XRPUSDT").status_code == 400
    assert client.post("/v2/validation?symbol=BTCUSDT").status_code == 405     # sin POST


def test_report_says_plainly_when_none_validated(client, tmp_path):
    from eim.validation.report import write

    p = client.get("/v2/validation?symbol=BTCUSDT").json()
    md, js = write(p, tmp_path, ["nota de prueba"], "abc1234")
    text = md.read_text(encoding="utf-8")
    assert md.name.startswith("validation_v1_") and js.exists()
    assert "## 2. Criterios (fijados antes de calcular)" in text and "abc1234" in text
    assert text.count("| `") >= len(p["verdicts"])          # una fila por versión
    if not p["summary"]["validated"]:
        assert "**Ninguna estrategia validada.**" in text
    assert "nota de prueba" in text
