"""Fusión de posturas entre carpetas de datos: solo añade, idempotente, conserva created_ms."""

import subprocess
import sys

import duckdb

from eim.api.reports_db import ReportStore
from eim.bots.merge_signals import main, merge
from eim.data.bots.store import BotSignalStore
from tests.bots.score_helpers import T0, H, signal


def _fill(folder, rows):
    folder.mkdir(parents=True, exist_ok=True)
    rs = ReportStore(folder / "reports.duckdb")
    st = BotSignalStore(*rs.connection)
    for s, created in rows:
        st.append(s, created)
    rs.connection[0].close()


def _created(folder):
    con = duckdb.connect(str(folder / "reports.duckdb"), read_only=True)
    out = con.execute("SELECT bot_id, count(*), min(created_ms) FROM bot_signals GROUP BY 1 "
                      "ORDER BY 1").fetchall()
    con.close()
    return out


def test_merge_adds_only_missing_rows_and_keeps_created_ms(tmp_path):
    new = [(signal(T0 + k * H, 1.0, bot="jesse-example-strategies"), T0 + 500 * H)
           for k in range(1, 6)]
    old = [(signal(T0 + k * H, 1.0), T0 + 99 * H) for k in range(1, 4)]
    src, dst = tmp_path / "copia", tmp_path / "vivo"
    _fill(src, new + old)
    _fill(dst, old[:2])
    dry = merge(src, dst, dry_run=True)
    assert sum(r["nuevas"] for r in dry.values()) == 0 and _created(dst)[0][1] == 2
    res = merge(src, dst)
    assert {k[0]: r["nuevas"] for k, r in res.items()} == {
        "jesse-example-strategies": 5, "hummingbot-directional": 1}
    assert all(r["faltan"] == 0 for r in res.values())
    assert _created(dst) == [("hummingbot-directional", 3, T0 + 99 * H),
                             ("jesse-example-strategies", 5, T0 + 500 * H)]
    again = merge(src, dst)
    assert sum(r["nuevas"] for r in again.values()) == 0          # idempotente


def test_bots_filter_and_locked_destination_message(tmp_path, capsys):
    src, dst = tmp_path / "a", tmp_path / "b"
    _fill(src, [(signal(T0 + H, 1.0, bot="x-bot"), T0 + 9 * H),
                (signal(T0 + H, 1.0), T0 + 9 * H)])
    _fill(dst, [])
    assert set(k[0] for k in merge(src, dst, ("x-bot",))) == {"x-bot"}
    assert _created(dst) == [("x-bot", 1, T0 + 9 * H)]
    holder = subprocess.Popen(                                    # otro proceso = la «API»
        [sys.executable, "-c", "import duckdb,sys,time;"
         f"c=duckdb.connect(r'{dst / 'reports.duckdb'}');print('ok',flush=True);time.sleep(60)"],
        stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "ok"
        assert main(["--from", str(src), "--into", str(dst)]) == 2
    finally:
        holder.kill()
        holder.wait()
    assert "no se pudo abrir" in capsys.readouterr().out
