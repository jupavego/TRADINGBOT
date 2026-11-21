"""T206: `micro/` se lee solo por los días UTC de la ventana, no el árbol entero.

Antes `_glob` devolvía `date=*/hour=*/part-*.parquet` y el filtro por `t` iba después: con
`hive_partitioning=false` DuckDB abre todos los archivos listados, así que el costo crecía con
cada hora guardada por la captura. Lo que devuelve `read_micro` no cambia: el escritor reparte
cada fila por su propia hora UTC, así que los días de fuera no aportan ninguna.
"""

import shutil
import time

import duckdb
import pytest

from eim.data.collectors.writer import SCHEMAS
from eim.data.micro import _old_files, read_micro

HOUR = 3_600_000
DAY = 86_400_000
T0 = 1_794_528_000_000          # 2026-11-13 00:00 UTC, principio de día exacto
SYM = "BTCUSDT"


def _dir(root, kind, t):
    tm = time.gmtime(t // 1000)
    return (root / "micro" / kind / f"symbol={SYM}" /
            time.strftime("date=%Y-%m-%d", tm) / f"hour={tm.tm_hour:02d}")


def _part(root, kind, t, rows, name="part-1.parquet"):
    """Escribe una parte en la partición que le toca a `t` (como `collectors/writer.py`)."""
    d = _dir(root, kind, t)
    d.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"CREATE TABLE x ({SCHEMAS[kind]})")
    con.executemany(f"INSERT INTO x VALUES ({', '.join('?' * len(rows[0]))})", rows)
    con.execute(f"COPY x TO '{(d / name).as_posix()}' (FORMAT parquet)")
    return d / name


def _top(t, bid_p=100.0, ask_p=101.0, bid_q=2.0, ask_q=3.0):
    return (t, bid_p, bid_q, ask_p, ask_q, f"[[{bid_p}, {bid_q}]]", f"[[{ask_p}, {ask_q}]]")


def _llena(root):
    """Tres días con datos: el de antes, el de la ventana y el de después."""
    for day, price in ((T0 - DAY, 90.0), (T0, 100.0), (T0 + DAY, 110.0)):
        _part(root, "top", day + HOUR, [_top(day + HOUR + 1, bid_p=price),
                                        _top(day + HOUR + 2, bid_p=price + 0.5)])
        _part(root, "trades", day + HOUR,
              [(day + HOUR + 1, 1, price, 1.5, False), (day + HOUR + 2, 2, price, 0.5, True)])


def test_solo_lista_los_archivos_de_los_dias_de_la_ventana(tmp_path):
    _llena(tmp_path)
    files = _old_files(tmp_path, "top", SYM, T0, T0 + DAY)
    assert "date=2026-11-13" in files
    assert "date=2026-11-12" not in files and "date=2026-11-14" not in files


def test_una_ventana_de_horas_no_lista_el_resto_del_dia_siguiente(tmp_path):
    _llena(tmp_path)
    files = _old_files(tmp_path, "top", SYM, T0 + HOUR, T0 + 2 * HOUR)
    assert files.count("part-") == 1 and "date=2026-11-13" in files


def test_sin_partes_en_la_ventana_devuelve_None(tmp_path):
    _llena(tmp_path)
    assert _old_files(tmp_path, "top", SYM, T0 + 10 * DAY, T0 + 11 * DAY) is None


def test_los_dias_de_fuera_no_cambian_las_barras(tmp_path):
    """Mismo resultado con y sin los días vecinos en disco: la poda no se lleva nada."""
    _llena(tmp_path)
    con_vecinos, book1 = read_micro(tmp_path, SYM, T0, HOUR, 24)
    for day in (T0 - DAY, T0 + DAY):
        shutil.rmtree(_dir(tmp_path, "top", day + HOUR).parent)
        shutil.rmtree(_dir(tmp_path, "trades", day + HOUR).parent)
    solos, book2 = read_micro(tmp_path, SYM, T0, HOUR, 24)
    assert con_vecinos == solos
    assert (book1 and book1.bids) == (book2 and book2.bids)
    assert [b.t for b in solos] == [T0 + HOUR]          # la hora con datos, y solo esa


def test_una_parte_ilegible_fuera_de_la_ventana_no_estorba(tmp_path):
    """Con el árbol entero esto reventaba: ahora ese día ni se abre."""
    _llena(tmp_path)
    rota = _dir(tmp_path, "top", T0 + DAY + HOUR) / "part-rota.parquet"
    rota.write_bytes(b"esto no es parquet")
    bars, _ = read_micro(tmp_path, SYM, T0, HOUR, 24)
    assert [b.t for b in bars] == [T0 + HOUR]
    with pytest.raises(duckdb.Error):                   # sigue rota si se la pide de verdad
        read_micro(tmp_path, SYM, T0 + DAY, HOUR, 24)
