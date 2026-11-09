"""T124: `repetir` reproduce un resultado y, si no, distingue datos, código y parámetros."""

from __future__ import annotations

import duckdb

from eim.data.results import ResultStore
from eim.data.snapshots import SnapshotStore
from eim.data.store import Store
from eim.repro import kinds as K
from eim.repro.code import fingerprint
from eim.repro.replay import DATA_ONLY, FAIL, OK, repetir
from tests.data.test_snapshots import T0, H, candles, make_store

END = T0 + 40 * H


def toy(snaps, params) -> dict:
    """Cálculo de juguete: depende de todas las velas y de un parámetro."""
    cs = snaps[0].candles
    return {"total": sum(c.c for c in cs) * params["k"], "n": len(cs),
            "funding": sum(x for _, x in snaps[0].funding)}


CURRENT = {"k": 2.0}
KINDS = {"toy": K.Kind("toy", "juguete", toy, lambda p: {**p, **CURRENT}),
         "solo": K.Kind("solo", "sin recálculo", None, lambda p: p, "no se recalcula")}


def setup(tmp_path, kind: str = "toy") -> tuple[Store, str]:
    store = make_store(tmp_path)
    snap = SnapshotStore(tmp_path).create(store, "BTCUSDT", "1h", start=T0, end=END)
    params = {"k": 2.0}
    rec = ResultStore(tmp_path).register(kind, "prueba", [snap.info.id], params, fingerprint(),
                                         toy([snap], params))
    return store, rec.id


def alter_by_hand(tmp_path, t: int) -> None:
    """Edita el Parquet del almacén sin pasar por `Store` (cambio fuera del sistema)."""
    p = (tmp_path / "candles" / "symbol=BTCUSDT" / "timeframe=1h" / "data.parquet").as_posix()
    con = duckdb.connect()
    con.execute(f"CREATE TABLE x AS SELECT * FROM read_parquet('{p}', hive_partitioning=false)")
    con.execute("UPDATE x SET c = (h + l) / 2 WHERE t = ?", [t])
    con.execute(f"COPY x TO '{p}' (FORMAT PARQUET)")


def test_unchanged_result_repeats_exactly(tmp_path):
    _, rid = setup(tmp_path)
    chk = repetir(tmp_path, rid, kinds=KINDS)
    assert (chk.verdict, chk.causes, chk.exit_code) == (OK, [], 0)
    assert any("todas iguales, exactas" in x for x in chk.lines)
    assert ResultStore(tmp_path).checks(rid)[0]["verdict"] == OK


def test_hand_altered_candle_fails_and_blames_data(tmp_path):
    _, rid = setup(tmp_path)
    alter_by_hand(tmp_path, T0 + 12 * H)
    chk = repetir(tmp_path, rid, kinds=KINDS)
    assert (chk.verdict, chk.causes, chk.exit_code) == (FAIL, ["datos"], 1)
    assert chk.detail["data"][0]["diff"]["changed"] == [T0 + 12 * H]
    assert chk.detail["data"][0]["diff"]["noted"] == []          # nadie la anotó
    assert any("1 sin anotar" in x for x in chk.lines)
    assert not K.compare(chk.result.figures, chk.detail["figures"]["base"])  # la copia sí repite


def test_revision_through_sync_is_noted_and_blames_data(tmp_path):
    store, rid = setup(tmp_path)
    c = candles()[20]
    store.upsert_candles("BTCUSDT", "1h", [c.model_copy(update={"c": (c.h + c.l) / 2})], "binance")
    chk = repetir(tmp_path, rid, kinds=KINDS)
    assert chk.causes == ["datos"] and chk.detail["data"][0]["diff"]["noted"] == [c.t]


def test_data_change_without_effect_on_the_figure_still_repeats(tmp_path):
    store, rid = setup(tmp_path)
    c = candles()[20]
    store.upsert_candles("BTCUSDT", "1h", [c.model_copy(update={"v": 1.0})], "binance")
    chk = repetir(tmp_path, rid, kinds=KINDS)        # el juguete no usa el volumen
    assert chk.verdict == OK and chk.causes == []
    assert any("almacén de hoy: DISTINTO" in x for x in chk.lines)


def test_altered_frozen_copy_blames_data(tmp_path):
    _, rid = setup(tmp_path)
    sid = ResultStore(tmp_path).get(rid).snapshots[0]
    p = (tmp_path / "snapshots" / "frozen" / sid / "candles.parquet").as_posix()
    con = duckdb.connect()
    con.execute(f"CREATE TABLE x AS SELECT * FROM read_parquet('{p}')")
    con.execute("UPDATE x SET c = (h + l) / 2 WHERE t = ?", [T0 + 5 * H])
    con.execute(f"COPY x TO '{p}' (FORMAT PARQUET)")
    chk = repetir(tmp_path, rid, kinds=KINDS)
    assert chk.verdict == FAIL and chk.causes == ["datos"]
    assert chk.detail["data"][0]["intact"] is False


def test_code_change_is_told_apart(tmp_path, monkeypatch):
    _, rid = setup(tmp_path)
    changed = {**KINDS, "toy": K.Kind("toy", "juguete", lambda s, p: {**toy(s, p), "n": 0},
                                      lambda p: p)}
    chk = repetir(tmp_path, rid, kinds=changed)
    assert (chk.verdict, chk.causes) == (FAIL, ["código"])


def test_params_change_is_told_apart(tmp_path, monkeypatch):
    _, rid = setup(tmp_path)
    monkeypatch.setitem(CURRENT, "k", 3.0)
    chk = repetir(tmp_path, rid, kinds=KINDS)
    assert (chk.verdict, chk.causes) == (FAIL, ["parámetros"])
    assert any("cambiaron k" in x for x in chk.lines)


def test_three_causes_at_once(tmp_path, monkeypatch):
    _, rid = setup(tmp_path)
    alter_by_hand(tmp_path, T0 + 3 * H)
    monkeypatch.setitem(CURRENT, "k", 5.0)
    changed = {"toy": K.Kind("toy", "juguete", lambda s, p: {**toy(s, p), "funding": -1.0},
                             KINDS["toy"].current)}
    chk = repetir(tmp_path, rid, kinds=changed)
    assert chk.verdict == FAIL and chk.causes == ["código", "datos", "parámetros"]


def test_data_only_kind(tmp_path):
    _, rid = setup(tmp_path, "solo")
    chk = repetir(tmp_path, rid, kinds=KINDS)
    assert (chk.verdict, chk.causes, chk.exit_code) == (DATA_ONLY, [], 0)
    alter_by_hand(tmp_path, T0 + 3 * H)
    chk = repetir(tmp_path, rid, kinds=KINDS)
    assert chk.causes == ["datos"] and chk.exit_code == 1


def test_light_snapshot_cannot_rebuild_but_names_data(tmp_path):
    store = make_store(tmp_path)
    snap = SnapshotStore(tmp_path).create(store, "BTCUSDT", "1h", start=T0, end=END, freeze=False)
    rid = ResultStore(tmp_path).register("toy", "ligera", [snap.info.id], {"k": 2.0}, {},
                                         toy([snap], {"k": 2.0})).id
    assert repetir(tmp_path, rid, kinds=KINDS).verdict == OK
    alter_by_hand(tmp_path, T0 + 3 * H)
    chk = repetir(tmp_path, rid, kinds=KINDS)
    assert chk.causes == ["datos"] and "base" not in chk.detail["figures"]


def test_a_recompute_that_fails_is_attributed_not_raised(tmp_path):
    _, rid = setup(tmp_path)
    good = candles()[12].c

    def fragile(snaps, params):
        if snaps[0].candles[12].c != good:
            raise ValueError("vela inesperada")
        return toy(snaps, params)
    alter_by_hand(tmp_path, T0 + 12 * H)
    chk = repetir(tmp_path, rid, kinds={"toy": K.Kind("toy", "frágil", fragile, lambda p: p)})
    assert (chk.verdict, chk.causes) == (FAIL, ["datos"])
    assert any("Error al recalcular (datos): ValueError: vela inesperada" in x for x in chk.lines)
