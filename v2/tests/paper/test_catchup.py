"""T182: la puesta al día automática reemplaza el botón «Reconstruir historial».

Solo con `live_first` (sin él, configuración de T31, rellenar huecos cambiaría los libros); analiza
las velas cerradas que falten en la ventana, de a lotes, las más recientes primero, las guarda como
reconstruidas y no repite cada minuto las que no dan contexto."""

from __future__ import annotations

import time

from eim.data.timeframes import tf_ms
from eim.paper import service
from eim.paper.generate import now_ms
from eim.paper.params import ExecParams
from eim.paper.service import CATCHUP_BATCH, CATCHUP_DAYS, LIVE_BARS, DeskService, Job

TF = "1h"
BAR = tf_ms(TF)


class _Store:
    def __init__(self, last: int) -> None:
        self.last = last

    def bounds(self, _sym: str, _tf: str):
        return (0, self.last)


class _PStore:
    def __init__(self, have: set[int]) -> None:
        self.have = have

    def asofs(self, _sym: str, _tf: str) -> set[int]:
        return set(self.have)


class _Gen:
    def __init__(self, ok: bool = True) -> None:
        self.ok, self.calls = ok, []

    def run(self, pstore, symbol, asofs, origin_of, stop=None, progress=None, workers=1):
        asofs = list(asofs)
        self.calls.append((symbol, asofs, [origin_of(a) for a in asofs]))
        if self.ok:
            pstore.have.update(asofs)
        if progress:
            progress(len(asofs), len(asofs))
        return len(asofs) if self.ok else 0


class _Desk(DeskService):
    def __init__(self, live_first: bool, have: set[int], last: int, ok: bool = True) -> None:
        self.ep = ExecParams(timeframes=(TF,), live_first=live_first)
        self.tfs, self.symbols = (TF,), ("BTCUSDT",)
        self.store, self.pstore = _Store(last), _PStore(have)
        self.gens = {TF: _Gen(ok)}
        self.job, self.catchup_tried = Job(), set()


def _wait(d: _Desk) -> dict:
    end = time.monotonic() + 10
    while d.job.state == "corriendo" and time.monotonic() < end:
        time.sleep(0.01)
    return d.job.to_json()


def _window(last: int) -> list[int]:
    """Lo que le toca a la puesta al día: la ventana sin las últimas velas, que son del ciclo."""
    return service.closed_asofs(last, BAR, int(CATCHUP_DAYS * 86_400_000 / BAR))[:-LIVE_BARS]


def test_apagado_no_rellena_nada_la_corrida_de_t31_no_cambia():
    last = (now_ms() // BAR - 2) * BAR
    d = _Desk(False, set(), last)
    assert d.catch_up()["state"] == "inactivo" and d.gens[TF].calls == []


def test_encendido_rellena_los_huecos_como_reconstruidos_y_se_detiene():
    last = (now_ms() // BAR - 2) * BAR
    win = _window(last)
    holes = {win[10], win[11], win[300]}
    d = _Desk(True, set(win) - holes, last)
    assert d.catch_up()["state"] in ("corriendo", "terminado")    # el lote va en otro hilo
    j = _wait(d)
    assert j["state"] == "terminado" and j["saved"] == 3 and j["total"] == 3
    (_sym, asofs, origins), = d.gens[TF].calls
    assert asofs == sorted(holes) and set(origins) == {"backtest"}   # no se decidieron en vivo
    assert d.catch_up()["state"] == "terminado" and len(d.gens[TF].calls) == 1   # nada más


def test_lo_que_no_da_contexto_no_se_repite_cada_minuto():
    last = (now_ms() // BAR - 2) * BAR
    win = _window(last)
    d = _Desk(True, set(win[1:]), last, ok=False)     # un hueco que el almacén no puede llenar
    d.catch_up()
    assert _wait(d)["saved"] == 0
    d.catch_up()
    assert len(d.gens[TF].calls) == 1


def test_de_a_lotes_y_las_mas_recientes_primero():
    last = (now_ms() // BAR - 2) * BAR
    win = _window(last)
    assert len(win) > CATCHUP_BATCH
    d = _Desk(True, set(), last)
    d.catch_up()
    assert _wait(d)["total"] == CATCHUP_BATCH
    (_sym, asofs, _o), = d.gens[TF].calls
    assert asofs == win[-CATCHUP_BATCH:]
    d.catch_up()
    _wait(d)
    assert d.gens[TF].calls[1][1] == win[-2 * CATCHUP_BATCH:-CATCHUP_BATCH]


def test_no_toca_las_velas_del_ciclo_en_vivo():
    last = (now_ms() // BAR - 2) * BAR
    full = service.closed_asofs(last, BAR, int(CATCHUP_DAYS * 86_400_000 / BAR))
    d = _Desk(True, set(full[:-LIVE_BARS]), last)      # solo faltan las del ciclo
    assert d.catch_up()["state"] == "inactivo" and d.gens[TF].calls == []


def test_detener_al_apagar_la_api():
    d = _Desk(True, set(), (now_ms() // BAR - 2) * BAR)
    assert d.stop_catchup()["state"] == "inactivo" and d.job.stop.is_set()
