"""T196: el libro fijo viaja entre equipos; una vela = una operación; lo vivido allí cuenta aquí."""

from __future__ import annotations

from pathlib import Path

from eim.data.paper_store import PaperStore
from eim.data.share_auto import ShareAgent, load_config, save_config, start_s
from eim.paper import accounting, ledger, provenance
from tests.share.helpers import T0, apply, build, publish, rows

H = 3_600_000


def row(idea: str, *, r: float = 0.1, pnl: float = 5.0, retro: bool = False,
        capital: float = 1000.0, recorded: int | None = None) -> tuple:
    """Una fila `perfil` del libro con la forma exacta de `ledger.COLS`."""
    exit_t = T0 + H
    v = {c: None for c in ledger.COLS}
    v.update(ledger_id=f"perfil|moderado|BTCUSDT|{idea}", scope="perfil", profile="moderado",
             symbol="BTCUSDT", idea_id=idea, strategy="s", sid="s", timeframe="15m",
             family="f", side=1, kind="market", opened_t=T0, fill_t=T0, exit_t=exit_t,
             fill=100.0, exit_price=101.0, sl=99.0, tp=103.0, reason="SLD", pnl_usdt=pnl, r=r,
             net_frac=0.001, qty=1.0, notional=100.0, leverage=1.0, fees=0.1, slip=0.1,
             funding=0.0, funding_assumed=False, weight=1.0, floor_trade=False, origin="vivo",
             regime="x", rules_version="v", mech_version="m", cost_params="{}",
             recorded_ms=recorded if recorded is not None else exit_t + 60_000, retro=retro,
             payload='{"cause": "direccion"}', capital_before=capital, capital_after=capital + pnl)
    return tuple(v[c] for c in ledger.COLS)


def _book(d: Path, rs: list[tuple]) -> None:
    ps = PaperStore(d / "paper.duckdb")
    try:
        ledger.ensure(ps)
        ledger.record(ps, rs)
    finally:
        ps.close()


def _pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    a, b = build(tmp_path, "a"), build(tmp_path, "b")
    # la misma vela vivida en los dos (otro capital: misma operación), una solo en cada uno,
    # una con otro resultado (conflicto) y una que en `b` se vivió y en `a` llegó tarde (retro)
    _book(a, [row("v1", capital=1000.0), row("a_only"), row("c1", r=0.1),
              row("late", retro=True, recorded=T0 + 50 * H)])
    _book(b, [row("v1", capital=2000.0, pnl=10.0), row("b_only"), row("c1", r=-1.0, pnl=-50.0),
              row("late", retro=False)])
    shared = tmp_path / "cloud"
    publish(b, shared, "b")
    return a, b, shared


def test_el_libro_viaja_sin_duplicar_y_declara_su_equipo(tmp_path):
    a, _b, shared = _pair(tmp_path)
    rep = apply(a, shared, "a")
    t = rep.totals()["paper_ledger"]
    assert t == {"new": 1, "dup": 1, "conflict": 2, "incompatible": 0}
    ids = [x[0] for x in rows(a, "paper.duckdb", "SELECT idea_id FROM paper_ledger ORDER BY 1")]
    assert ids == ["a_only", "b_only", "c1", "late", "v1"]           # una vela = una operación
    kept = rows(a, "paper.duckdb", "SELECT r, capital_before FROM paper_ledger "
                "WHERE idea_id IN ('c1', 'v1') ORDER BY idea_id")
    assert kept == [(0.1, 1000.0), (0.1, 1000.0)]                    # gana lo local
    conf = rows(a, "paper.duckdb", "SELECT tbl, key, differs FROM share_conflicts "
                "WHERE tbl = 'paper_ledger' ORDER BY key")
    assert [c[1].split("|")[-1] for c in conf] == ["c1", "late"]
    assert "r " in conf[0][2] and "retro" in conf[1][2]               # se ve qué difiere
    # idempotente: la misma exportación otra vez no añade nada
    again = apply(a, shared, "a").totals()
    assert "paper_ledger" not in again or again["paper_ledger"]["new"] == 0


def test_lo_vivido_en_otro_equipo_cuenta_y_se_puede_separar(tmp_path):
    a, _b, shared = _pair(tmp_path)
    apply(a, shared, "a")
    ps = PaperStore(a / "paper.duckdb")
    try:
        assert provenance.origins(ps) == {"perfil|moderado|BTCUSDT|b_only": "b"}
        central = accounting.from_store(ps, "BTCUSDT")
        local = accounting.from_store(ps, "BTCUSDT", machines="local")
        trades = accounting.balance_trades(ps, "BTCUSDT")
    finally:
        ps.close()
    assert central["ok"] and local["ok"]
    # a_only, b_only, c1 y v1 cuentan; `late` es retro aquí (gana lo local) y no suma
    assert central["n"] == 4 and central["tally"]["excluded"] == {"retro": 1}
    assert central["by_machine"]["b"]["n"] == 1 and central["by_machine"]["local"]["n"] == 3
    assert local["n"] == 3 and local["machines"] == "local"
    mod = trades["moderado"]
    assert len(mod) == 4 and {t["machine"] for t in mod} == {"local", "b"}
    assert all(t["cause"] == "direccion" for t in mod)
    assert set(trades) == {"conservador", "moderado", "agresivo", "ppp_btcusdt"}


def test_sin_importaciones_todo_es_local(tmp_path):
    d = build(tmp_path, "solo")
    _book(d, [row("x")])
    ps = PaperStore(d / "paper.duckdb")
    try:
        assert provenance.origins(ps) == {}
        out = accounting.from_store(ps, "BTCUSDT")
    finally:
        ps.close()
    assert out["n"] == 1 and out["by_machine"] == {
        "local": {"n": 1, "pnl_usdt": 5.0, "total_r": 0.1, "wins": 1, "win_rate": 1.0}}


def test_encendido_programado_duerme_hasta_su_fecha(tmp_path):
    data = tmp_path / "data"
    save_config(data, str(tmp_path / "cloud"), "lap", None, "2026-11-28T00:00:00")
    cfg = load_config(data, env={})
    assert cfg["start"] == "2026-11-28T00:00:00"
    t28 = start_s(cfg["start"])
    assert t28 == 1_795_824_000.0                                  # 2026-11-28 00:00 UTC
    assert start_s("off") is None and start_s("") is None
    assert load_config(data, env={"EIM_SHARE_FROM": "off"})["start"] == "off"
    now = {"t": t28 - 60}
    ag = ShareAgent("api", data, tmp_path / "no-existe", "lap", {}, clock=lambda: now["t"],
                    start=t28)
    assert ag.dormant() and not ag.due()
    ag.tick()                                                        # dormido: ni lo intenta
    assert ag.error == "" and ag.status()["dormant"] is True
    now["t"] = t28 + 1
    assert not ag.dormant() and ag.due()
    ag.tick()                                                        # despierto: ya trabaja
    assert "no existe" in ag.error and ag.status()["dormant"] is False
