"""T120: una sola tabla de estados, la unidad de datos que desaparece, de dónde corre cada servicio,
contexto que dice si falta el motor o las noticias y OI de 4 h sin «sin datos»."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from eim.agents.context.agent import ENGINE_BUSY, ENGINE_DOWN, NO_ENGINE, ContextAgent
from eim.api.micro import build_micro_router
from eim.core import Candle, MarketSnapshot, NewsItem
from eim.data import Store, build_snapshot
from eim.data.collectors import health
from eim.data.providers.claude_context import CachedContextAnalyzer
from eim.data.providers.local_context import LocalContextAnalyzer
from eim.operation import components as comp
from eim.operation.notify import JsonLog
from eim.operation.origin import CHECKOUT, same_checkout, stamp
from eim.operation.watchdog import Watchdog

NOW = 1_800_000_000_000
H = 3_600_000
RUNBOOK = Path(__file__).resolve().parents[2] / "docs" / "RUNBOOK.md"


def _beat(root: Path, **kw) -> None:
    health.write_heartbeat(root, {"last_heartbeat": NOW, "last_msg_ms": NOW, "symbol": "BTCUSDT",
                                  "started_at": NOW - 10 * H, **kw})


# ------------------------------------------------------------- 1. una sola fuente de verdad

def test_runbook_lists_exactly_the_collector_states_of_the_code():
    text = RUNBOOK.read_text(encoding="utf-8")
    sec = text[text.index("## 19."):]
    rows = re.findall(r"^\| `(\w+)` \| ([^|]+) \|", sec, flags=re.M)
    assert {k: v.strip() for k, v in rows if k != "state"} == health.LABELS


def test_collector_state_api_and_alerts_share_labels(tmp_path):
    assert health.collector_state(tmp_path, NOW)["label"] == "recolector apagado"
    _beat(tmp_path)
    st = health.collector_state(tmp_path, NOW)
    assert st == {"state": "capturando", "label": "capturando", "reason": "ok", "age_s": 0.0}
    st = health.collector_state(tmp_path, NOW + 400_000, free_gb_min=0)
    assert st["state"] == "apagado" and st["age_s"] == 400.0
    msgs = health.problems(tmp_path, NOW + 400_000)
    assert any(health.LABELS["apagado"] in m for m in msgs)
    app = FastAPI()
    app.include_router(build_micro_router(tmp_path, clock=lambda: NOW))
    body = TestClient(app).get("/v2/micro/status").json()
    assert body["state"] == "capturando" and body["label"] == health.LABELS["capturando"]
    light = TestClient(app).get("/v2/micro/status?disk=false").json()
    assert body["disk"] and light["disk"] is None


def test_low_disk_is_its_own_state(tmp_path):
    _beat(tmp_path)
    st = health.collector_state(tmp_path, NOW, free_gb_min=1e9)
    assert st["state"] == "disco_bajo" and st["label"] == "disco bajo"


# ----------------------------------------------------------- 4. la unidad de datos desaparece

def test_missing_drive_is_one_clear_state_not_a_trace(monkeypatch, tmp_path):
    monkeypatch.setattr(health, "drive_missing", lambda root: "la unidad Q:\\ no está conectada")
    st = health.collector_state(tmp_path, NOW)
    assert st["state"] == "unidad_ausente" and "Q:" in st["reason"]
    (msg,) = health.problems(tmp_path, NOW)
    assert "en pausa" in msg and "unidad de datos ausente" in msg


def test_drive_missing_only_for_the_drive_not_a_new_folder(tmp_path):
    assert health.drive_missing(tmp_path / "aún" / "no" / "existe") is None
    assert health.drive_missing("Q:\\datos") in (None, "la unidad Q:\\ no está conectada")


class _Proc:
    def __init__(self, die_after: int | None = None):
        self.polls, self.die_after, self.terminated = 0, die_after, False

    def poll(self):
        self.polls += 1
        return 1 if self.die_after is not None and self.polls >= self.die_after else None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def _rows(path: Path) -> list[dict]:
    return [json.loads(x) for f in sorted(path.glob("*.jsonl"))
            for x in f.read_text(encoding="utf-8").splitlines()]


def test_watchdog_pauses_while_the_drive_is_gone_and_resumes_alone(tmp_path):
    """Se va la unidad: se detiene el hijo, UNA línea `en_pausa`, ningún reinicio ni aviso; al
    volver, `reanudado` y se relanza. Si el hijo cae por la unidad, tampoco cuenta como caída."""
    clock = {"t": 1_000.0}
    gone = [(1_030.0, 1_100.0), (1_125.0, 1_200.0)]
    procs = [_Proc(), _Proc(die_after=3)]
    notes: list = []

    def hold():
        t = clock["t"]
        return "la unidad X: no está conectada" if any(a <= t < b for a, b in gone) else None

    def sleep(s):
        clock["t"] += s

    log = JsonLog(tmp_path / "logs", lambda: int(clock["t"] * 1000))
    wd = Watchdog(["x"], {}, tmp_path / "hb.json", log, stale_s=1e9, check_s=10,
                  spawn=lambda c, e: procs.pop(0), clock=lambda: clock["t"], sleep=sleep,
                  notify=notes.append, hold=hold)
    wd.run(max_starts=2)     # 1.º: lo para la pausa; 2.º: cae justo cuando se va otra vez la unidad
    events = [r["event"] for r in _rows(tmp_path / "logs")]
    assert events == ["proceso_lanzado", "en_pausa", "reanudado", "proceso_lanzado"]
    assert wd.restarts == 0 and not notes and not procs


def test_json_log_keeps_lines_while_its_drive_is_gone(tmp_path, monkeypatch):
    log = JsonLog(tmp_path / "logs", lambda: NOW)
    real_open = Path.open

    def broken(self, *a, **k):
        raise OSError("unidad desconectada")

    monkeypatch.setattr(Path, "open", broken)
    log.write("en_pausa", reason="sin unidad")              # no lanza
    monkeypatch.setattr(Path, "open", real_open)
    log.write("reanudado")
    assert [r["event"] for r in _rows(tmp_path / "logs")] == ["en_pausa", "reanudado"]


# ------------------------------------------------------- 2. de qué checkout y desde cuándo

def test_heartbeats_carry_their_checkout_and_start(tmp_path):
    _beat(tmp_path)
    hb = health.read_heartbeat(tmp_path)
    assert same_checkout(hb["checkout"], CHECKOUT) and hb["proc_started_at"] > 0
    assert stamp({"checkout": "otro"})["checkout"] == "otro"        # lo del latido manda


def test_components_flag_a_service_running_from_another_checkout(tmp_path):
    t = 1_800_000_000.0
    (tmp_path / "operation").mkdir()
    (tmp_path / "operation" / "heartbeat.json").write_text(json.dumps(
        {"last_heartbeat": int(t * 1000), "pid": 7, "proc_started_at": 1,
         "checkout": "C:/otro/worktree/v2"}), encoding="utf-8")
    rows = {r["name"]: r for r in comp.components(tmp_path, t)}
    api = rows["API"]
    assert api["alive"] and api["pid"] == 7 and api["checkout"] == "C:/otro/worktree/v2"
    assert not rows["líderes"]["alive"] and rows["líderes"]["checkout"] is None
    assert [r["name"] for r in comp.foreign(list(rows.values()), CHECKOUT)] == ["API"]
    assert comp.foreign(list(rows.values()), "C:/otro/worktree/v2") == []


# --------------------------------------------------------------------- 5. contexto «degraded»

def _snap() -> MarketSnapshot:
    heads = [NewsItem(id=f"n{i}", t=NOW - i * 60_000, title=f"titular {i}", source="rss")
             for i in range(5)]
    return MarketSnapshot(symbol="BTCUSDT", timeframe="1h", asof=NOW, headlines=heads,
                          candles=[Candle(t=NOW - H, o=1, h=1, l=1, c=1, v=1)])


def test_context_says_whether_the_engine_or_the_news_is_missing():
    r = ContextAgent().run(_snap())
    assert r.status == "no_data" and r.warnings[-1].startswith(NO_ENGINE)

    class Down:
        last_problem = "Ollama no responde en http://127.0.0.1:11434 (¿apagado?)"

        def __call__(self, items):
            return None

    cached = CachedContextAnalyzer(Down())
    r = ContextAgent(analyzer=cached).run(_snap())
    assert r.warnings[-1].startswith(ENGINE_DOWN) and "11434" in r.warnings[-1]

    class NoClaims:
        def __call__(self, items):
            return {"tema": "x", "sentimiento": 0, "riesgo_evento": "bajo", "catalizadores": [],
                    "fuentes": []}

    r = ContextAgent(analyzer=NoClaims()).run(_snap())
    assert r.status == "degraded" and any("no es el motor caído" in w for w in r.warnings)


def test_background_engine_still_computing_is_not_down():
    import threading

    gate = threading.Event()

    class Slow:
        last_problem = None

        def __call__(self, items):
            gate.wait(5)
            return None

    cached = CachedContextAnalyzer(Slow(), background=True)
    r = ContextAgent(analyzer=cached).run(_snap())
    gate.set()
    assert r.warnings[-1].startswith(ENGINE_BUSY)


def test_local_engine_records_why_it_failed():
    import httpx

    def refuse(req):
        raise httpx.ConnectError("rechazada", request=req)

    a = LocalContextAnalyzer(client=httpx.Client(transport=httpx.MockTransport(refuse)))
    assert a(_snap().headlines) is None and "no responde" in a.last_problem


# ------------------------------------------------------------- derivados en 4 h, sin inventar

def test_four_hour_snapshot_samples_hourly_levels_at_its_boundaries(tmp_path):
    store = Store(tmp_path)
    h4 = 4 * H
    base = NOW - NOW % h4 - 40 * h4
    store.upsert_candles("BTCUSDT", "4h", [Candle(t=base + k * h4, o=1, h=2, l=0.5, c=1.5, v=1)
                                           for k in range(40)], "s4h")
    store.upsert_series("open_interest", "BTCUSDT", "1h",
                        [(base + k * H, 100.0 + k) for k in range(160)], "binance")
    snap = build_snapshot(store, "BTCUSDT", "4h", 30, asof=base + 40 * h4)
    assert snap.open_interest and all(t % h4 == 0 for t, _ in snap.open_interest)
    assert dict(snap.open_interest)[base + 12 * h4] == 100.0 + 48   # nivel de 1 h, tal cual
    assert "muestreo de 1h" in snap.sources["open_interest"]
    store.upsert_candles("BTCUSDT", "15m", [Candle(t=base + k * H // 4, o=1, h=2, l=0.5, c=1.5,
                                                   v=1) for k in range(80)], "s15")
    assert build_snapshot(store, "BTCUSDT", "15m", 40, asof=base + 20 * H).open_interest is None
