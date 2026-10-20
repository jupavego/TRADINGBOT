"""Fuente «ranking» de candidatos: filtro puro, caché y fallos de la fuente (sin red)."""

import json

import httpx
import pytest

from eim.data.leader_ranking import RankingUnavailable, discover_ranking, load_rows
from eim.data.leader_store import LeaderStore
from eim.leaders.ranking import pick

A, B, C, D = ("0x" + c * 40 for c in "abcd")


def _row(addr, equity=200_000.0, m=(5_000.0, 0.10, 1e6), w=(500.0, 0.01, 2e5),
         a=(80_000.0, 0.8, 5e6)):
    perf = lambda t: {"pnl": str(t[0]), "roi": str(t[1]), "vlm": str(t[2])}  # noqa: E731
    return {"ethAddress": addr, "accountValue": str(equity),
            "windowPerformances": [["day", perf((1, 0, 1))], ["week", perf(w)],
                                   ["month", perf(m)], ["allTime", perf(a)]]}


def test_filtra_perdedores_bots_y_cuentas_chicas_y_ordena_por_roi_topado():
    rows = [_row(A), _row(B, m=(9e3, 5.0, 1e6)),            # ROI 500 % se topa en 1,0
            _row(C, m=(-10.0, -0.1, 1e6)),                     # pierde en el mes
            _row(D, m=(5e3, 0.2, 1e9)),                        # volumen/cuenta = 5000 → bot
            _row("0x" + "e" * 40, equity=1_000.0),             # cuenta chica
            _row("0x" + "f" * 40, w=(-5.0, -0.01, 1e5)),       # pierde en la semana
            {"ethAddress": "malo"}]                            # fila rota: se descarta
    out = pick(rows, now=1)
    assert [x.address for x in out] == [B, A] and out[0].origin == "ranking"
    assert out[0].evidence["month_roi"] == 5.0 and "no oficial" in out[0].source


def test_cache_en_disco_y_fuente_caida(tmp_path):
    calls = []

    def ok(req):
        calls.append(1)
        return httpx.Response(200, json={"leaderboardRows": [_row(A)]})

    cli = httpx.Client(transport=httpx.MockTransport(ok))
    assert len(load_rows(tmp_path, client=cli)) == 1 and len(load_rows(tmp_path, client=cli)) == 1
    assert len(calls) == 1  # la segunda lectura sale de la copia en disco
    bad = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"x": 1})))
    with pytest.raises(RankingUnavailable):
        load_rows(tmp_path / "otro", client=bad)
    down = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(RankingUnavailable):
        load_rows(tmp_path / "otro2", client=down)


def test_descubrimiento_registra_candidatos_nuevos_una_vez(tmp_path):
    store = LeaderStore.at_root(tmp_path)
    (tmp_path / "leaders").mkdir(exist_ok=True)
    cache = tmp_path / "leaders" / "ranking_cache.json"
    cache.write_text(json.dumps([_row(A)]), encoding="utf-8")
    assert [x.address for x in discover_ranking(store, tmp_path)] == [A]
    assert discover_ranking(store, tmp_path) == []  # ya registrado: no se duplica
    store.close()
