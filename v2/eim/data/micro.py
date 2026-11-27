"""Lectura de la recolección de microestructura y agregados por vela (sin red).

Fuentes (T128): los trades y los huecos salen de la captura HFT (`micro_hft/`) cuando la hay
para la ventana; si no, del recolector viejo (`micro/`, T23). Las fotos top-10 por segundo están
en `micro/top`: las escribía el recolector viejo y ahora las escribe la captura (`micro_feed`).
Los huecos de ambas fuentes se suman: una vela con un hueco en cualquiera queda incompleta.
"""

from __future__ import annotations

import json
import os
import time
from bisect import bisect_right
from pathlib import Path

import duckdb

from eim.core import Book, MicroBar
from eim.data import micro_bars, micro_cache


def _glob(root: Path, kind: str, symbol: str) -> str | None:
    base = root / "micro" / kind / f"symbol={symbol}"
    if not any(base.glob("date=*/hour=*/part-*.parquet")):
        return None
    return (base / "date=*" / "hour=*" / "part-*.parquet").as_posix().replace("'", "''")


HFT = "micro_hft"
DAY_MS = 86_400_000
# huecos de la captura que rompen el libro o pierden trades; un silencio no pierde nada
HFT_GAP_SQL = "stream IN ('depth', 'trades') AND cause <> 'silencio'"
# T150 (BACKLOG T120 (2)): el recolector de liquidaciones (`liq_ws`) apunta sus reconexiones en la
# misma tabla `micro/gaps` con flujo `liq:<venue>`; no pierden ni un trade ni una foto del libro,
# y contarlas dejaba «degradado por huecos» el 38 % de las velas de 1 h y el 67 % de las de 4 h.
# Lo que lee el agente también lo lee el bróker simulado, y T31 no cambia hasta su cierre (◆ de
# T143): el arreglo se enciende con EIM_MICRO_IGNORE_LIQ_GAPS=1 (apagado por defecto).
OLD_GAP_SQL = "stream NOT LIKE 'liq:%'"
IGNORE_LIQ_ENV = "EIM_MICRO_IGNORE_LIQ_GAPS"
CACHE_ENV = "EIM_MICRO_CACHE"        # `0` = recalcular siempre (T206)


def _old_gap_filter() -> str:
    return OLD_GAP_SQL if os.environ.get(IGNORE_LIQ_ENV, "") == "1" else "TRUE"


def _hft_files(root: Path, kind: str, symbol: str, start: int, end: int) -> str | None:
    """Lista DuckDB de las partes de `micro_hft/<kind>` de los días que toca la ventana."""
    base = root / HFT / kind / f"symbol={symbol}"
    days = {time.strftime("%Y-%m-%d", time.gmtime(t / 1000))
            for t in range(start - start % DAY_MS, max(end, start + 1), DAY_MS)}
    files = sorted(p for d in days for p in (base / f"date={d}").glob("hour=*/part-*.parquet"))
    if not files:
        return None
    return "[" + ", ".join("'" + f.as_posix().replace("'", "''") + "'" for f in files) + "]"


def _read(root: Path, kind: str, symbol: str, cols: str, start: int, end: int,
          where: str = "TRUE") -> list[tuple]:
    g = _glob(root, kind, symbol)
    if g is None:
        return []
    q = (f"SELECT {cols} FROM read_parquet('{g}', hive_partitioning=false) "
         f"WHERE t >= ? AND t < ? AND {where} ORDER BY t")
    return duckdb.connect().execute(q, [start, end]).fetchall()


_ofi_step = micro_bars.ofi_step   # nombre de siempre (lo usa eim/hft/features/book.py)


def _trade_bars(trades: list[tuple], t0: int, step: int, n: int) -> dict[int, tuple]:
    """Reduce trades (t, p, q, maker) a {vela: (compra, venta, nº)} (versión en memoria)."""
    out: dict[int, list] = {}
    for t, _p, q, maker in trades:
        i = (t - t0) // step
        if 0 <= i < n:
            b = out.setdefault(i, [0.0, 0.0, 0])
            b[1 if maker else 0] += q   # el comprador es maker → el agresor vende
            b[2] += 1
    return {i: tuple(v) for i, v in out.items()}


def aggregate(
    trades: list[tuple], tops: list[tuple], gaps: list[int], t0: int, step: int, n: int
) -> list[MicroBar]:
    """Agrega por vela `[t0 + i·step, +step)`. Solo devuelve velas con datos.

    trades: (t, p, q, maker) · tops: (t, bid_p, bid_q, ask_p, ask_q, bids_json, asks_json) ·
    gaps: instantes (ms) de huecos de secuencia. Los pares de muestras que cruzan un hueco
    no aportan OFI (el libro se reconstruyó entre ambas).
    """
    sums = [(r[0], r[1], r[2], r[3], r[4], sum(q for _, q in json.loads(r[5])),
             sum(q for _, q in json.loads(r[6]))) for r in tops]
    return combine(_trade_bars(trades, t0, step, n), sums, gaps, t0, step, n)


def combine(
    tb: dict[int, tuple], tops: list[tuple], gaps: list[int], t0: int, step: int, n: int
) -> list[MicroBar]:
    """Como `aggregate`, con los trades ya reducidos por vela (`tb`: i → (compra, venta, nº)) y
    cada top como (t, bid_p, bid_q, ask_p, ask_q, suma_qty_bids, suma_qty_asks)."""
    idx = lambda t: (t - t0) // step  # noqa: E731
    buy = [tb.get(i, (0.0, 0.0, 0))[0] for i in range(n)]
    sell = [tb.get(i, (0.0, 0.0, 0))[1] for i in range(n)]
    cnt = [tb.get(i, (0.0, 0.0, 0))[2] for i in range(n)]
    ofi = [0.0] * n
    imb_sum = [0.0] * n
    imb_n = [0] * n
    seen = [False] * n
    bad = [False] * n
    for g in gaps:
        if 0 <= idx(g) < n:
            bad[idx(g)] = True
    gaps_sorted = sorted(gaps)
    prev = None
    for row in tops:
        t = row[0]
        i = idx(t)
        cur = row[1:5]
        if 0 <= i < n:
            seen[i] = True
            bq, aq = row[5], row[6]
            if bq + aq > 0:
                imb_sum[i] += (bq - aq) / (bq + aq)
                imb_n[i] += 1
            if prev is not None and (bisect_right(gaps_sorted, t)
                                     == bisect_right(gaps_sorted, prev[0])):  # sin hueco
                ofi[i] += _ofi_step(prev[1], cur)
        prev = (t, cur)
    return [
        MicroBar(t=t0 + i * step, ofi=ofi[i], delta=buy[i] - sell[i], buy_v=buy[i],
                 sell_v=sell[i], trades=cnt[i],
                 depth_imb=imb_sum[i] / imb_n[i] if imb_n[i] else None, complete=not bad[i])
        for i in range(n) if cnt[i] or seen[i]
    ]


def _read_trade_bars(root: Path, symbol: str, t0: int, step: int, n: int) -> dict[int, tuple]:
    """Trades reducidos por vela dentro de DuckDB (no se traen millones de filas a Python). De
    la captura HFT si la hay (un trade repetido tras reconectar cuenta una vez), si no de T23."""
    end = t0 + n * step
    if (files := _hft_files(root, "trades", symbol, t0, end)) is not None:
        src = (f"(SELECT DISTINCT ON (agg_id) t_ms AS t, q, maker FROM read_parquet({files}, "
               f"union_by_name=true, hive_partitioning=false) WHERE t_ms >= ? AND t_ms < ?)")
    elif (g := _glob(root, "trades", symbol)) is not None:
        src = (f"(SELECT t, q, maker FROM read_parquet('{g}', hive_partitioning=false) "
               f"WHERE t >= ? AND t < ?)")
    else:
        return {}
    q = (f"SELECT CAST(floor((t - ?) / ?) AS BIGINT) i, "
         f"SUM(CASE WHEN maker THEN 0 ELSE q END), SUM(CASE WHEN maker THEN q ELSE 0 END), "
         f"COUNT(*) FROM {src} GROUP BY 1")
    rows = duckdb.connect().execute(q, [t0, step, t0, end]).fetchall()
    return {int(i): (float(b), float(s), int(c)) for i, b, s, c in rows if 0 <= i < n}


def _read_tops(root: Path, symbol: str, start: int, end: int) -> list[tuple]:
    """(t, bid_p, bid_q, ask_p, ask_q, Σ qty bids, Σ qty asks): la suma de niveles se hace en
    DuckDB para no analizar el JSON de cada libro en Python."""
    g = _glob(root, "top", symbol)
    if g is None:
        return []
    q = ("SELECT t, bid_p, bid_q, ask_p, ask_q, "
         "list_sum(CAST(json_extract(bids, '$[*][1]') AS DOUBLE[])), "
         "list_sum(CAST(json_extract(asks, '$[*][1]') AS DOUBLE[])) "
         f"FROM read_parquet('{g}', hive_partitioning=false) WHERE t >= ? AND t < ? ORDER BY t")
    return [(r[0], r[1], r[2], r[3], r[4], r[5] or 0.0, r[6] or 0.0)
            for r in duckdb.connect().execute(q, [start, end]).fetchall()]


def _prev_top(root: Path, symbol: str, before: int, back_ms: int = DAY_MS):
    """La última foto **anterior** a `before` (dentro de `back_ms`), para encadenar el OFI del
    primer par de un tramo. Un día acota la lectura sin cambiar nada: un silencio más largo deja
    tramos de hueco y ese par no contaría igualmente."""
    g = _glob(root, "top", symbol)
    if g is None:
        return None
    q = (f"SELECT t, bid_p, bid_q, ask_p, ask_q FROM read_parquet('{g}', hive_partitioning=false) "
         "WHERE t >= ? AND t < ? ORDER BY t DESC LIMIT 1")
    row = duckdb.connect().execute(q, [before - back_ms, before]).fetchone()
    return (row[0], tuple(row[1:5])) if row else None


def _read_gaps(root: Path, symbol: str, start: int, end: int) -> list[tuple[int, int]]:
    """Tramos (ms) de hueco que tocan la ventana: los instantes de T23 y los tramos marcados de
    la captura HFT. Con `EIM_MICRO_IGNORE_LIQ_GAPS=1`, las reconexiones del recolector de
    liquidaciones no cuentan (`OLD_GAP_SQL`)."""
    out = [(r[0], r[0]) for r in _read(root, "gaps", symbol, "t", start, end, _old_gap_filter())]
    if (files := _hft_files(root, "gaps", symbol, start - DAY_MS, end)) is not None:
        q = (f"SELECT start_ns // 1000000, end_ns // 1000000 FROM read_parquet({files}, "
             f"union_by_name=true, hive_partitioning=false) WHERE {HFT_GAP_SQL} "
             f"AND end_ns >= ? * 1000000 AND start_ns < ? * 1000000")
        out += [(int(a), int(b)) for a, b in duckdb.connect().execute(q, [start, end]).fetchall()]
    return out


def _instants(spans: list[tuple[int, int]], t0: int, step: int, end: int) -> list[int]:
    """Cada tramo, como instantes: sus extremos dentro de la ventana y uno por vela que cruza.
    Así quedan incompletas todas las velas que toca y ningún par de fotos lo salta."""
    out: list[int] = []
    for a, b in spans:
        lo, hi = max(a, t0), min(b, end - 1)
        if lo <= hi:
            out += [lo, *range(t0 + ((lo - t0) // step + 1) * step, hi + 1, step), hi]
    return out


def _last_top_levels(root: Path, symbol: str, start: int, end: int):
    g = _glob(root, "top", symbol)
    if g is None:
        return None
    q = (f"SELECT bids, asks FROM read_parquet('{g}', hive_partitioning=false) "
         f"WHERE t >= ? AND t < ? ORDER BY t DESC LIMIT 1")
    row = duckdb.connect().execute(q, [start, end]).fetchone()
    return row


# T176: la compactación de las horas cerradas (`hft_ops.maintain`, `compact_closed`) sustituye
# las partes por una sola en milisegundos, pero una lectura que ya las había listado intenta abrir
# archivos que no existen. El 2026-11-16 a las 08:04 UTC eso tumbó un ciclo del bróker simulado
# (`IOException: Cannot open file .../hour=05/part-….parquet`) con la API lenta por falta de RAM,
# que es cuando el rato entre listar y leer se alarga. Se vuelve a listar y a leer; los datos no
# cambian (la compactación verifica filas y sumas antes de sustituir).
RETRY_WAITS_S = (0.2, 1.0)
_GONE = ("Cannot open file", "No files found")


def read_micro(
    root: str | Path, symbol: str, t0: int, step: int, n: int
) -> tuple[list[MicroBar], Book | None]:
    """Agregados por vela de las `n` velas desde `t0` y el último libro top-10 de la ventana.

    Si una parte listada desaparece a mitad de lectura (la compactó otro proceso), se reintenta
    con la lista nueva hasta `len(RETRY_WAITS_S)` veces; cualquier otro error sale tal cual."""
    for wait in (*RETRY_WAITS_S, None):
        try:
            return _read_micro_once(Path(root), symbol, t0, step, n)
        except duckdb.IOException as e:
            if wait is None or not any(m in str(e) for m in _GONE):
                raise
            time.sleep(wait)
    raise AssertionError("inalcanzable")  # pragma: no cover


def _range_aggs(root: Path, symbol: str, rs: int, step: int, m: int) -> list[micro_bars.Agg]:
    """Calcula de cero los agregados de `m` velas desde `rs`, como lo haría `combine`.

    Los huecos se leen para el tramo **y un día antes**, no para la ventana que pidió el panel:
    así una vela no depende de dónde empezaba esa ventana, que es lo que permite guardarla (la
    rejilla de `_instants` coincide porque el día es múltiplo de todos los marcos)."""
    end = rs + m * step
    tb = _read_trade_bars(root, symbol, rs, step, m)
    tops = _read_tops(root, symbol, rs, end)
    gaps = sorted(_instants(_read_gaps(root, symbol, rs - DAY_MS, end), rs - DAY_MS, step, end))
    agg = micro_bars.entries_from_tops(tops, _prev_top(root, symbol, rs), rs, step, m, gaps)
    out = []
    for j in range(m):
        buy, sell, cnt = tb.get(j, (0.0, 0.0, 0))
        ofi, ofi0, imb, imb_n, seen = agg.get(j, [0.0, 0.0, 0.0, 0, False])
        out.append((buy, sell, cnt, ofi, ofi0, imb, imb_n, seen))
    return out


def _read_micro_once(root: Path, symbol: str, t0: int, step: int,
                     n: int) -> tuple[list[MicroBar], Book | None]:
    """Las velas de la ventana, tomando de la caché las que ya estaban calculadas (T206)."""
    end = t0 + n * step
    ignore_liq = os.environ.get(IGNORE_LIQ_ENV, "") == "1"
    spans = _read_gaps(root, symbol, t0, end)
    sig = micro_bars.gap_signature(spans, t0, step, n)
    usa_cache = os.environ.get(CACHE_ENV, "") != "0"
    guardadas = (micro_cache.load(root, symbol, step, ignore_liq, t0, end) if usa_cache else {})
    aggs: list[micro_bars.Agg | None] = [None] * n
    for i in range(n):
        e = guardadas.get(t0 + i * step)
        if e is not None and e[8] == sig[i]:
            aggs[i] = e[:8]
    nuevas: dict[int, micro_cache.Entry] = {}
    for a, b in micro_bars.missing_ranges([i for i in range(n) if aggs[i] is None]):
        for j, agg in enumerate(_range_aggs(root, symbol, t0 + a * step, step, b - a + 1)):
            aggs[a + j] = agg
            nuevas[t0 + (a + j) * step] = (*agg, sig[a + j])
    if usa_cache:
        micro_cache.save(root, symbol, step, ignore_liq, nuevas)
    bad = [False] * n
    for g in _instants(spans, t0, step, end):
        if 0 <= (g - t0) // step < n:
            bad[(g - t0) // step] = True
    listas: list[micro_bars.Agg] = [a or micro_bars.EMPTY for a in aggs]
    bars = micro_bars.assemble(listas, bad, t0, step)
    book = None
    ultima = max((i for i, a in enumerate(listas) if a[7]), default=None)
    if ultima is not None:
        last = _last_top_levels(root, symbol, t0 + ultima * step, t0 + (ultima + 1) * step)
        if last:
            book = Book(bids=[tuple(x) for x in json.loads(last[0])],
                        asks=[tuple(x) for x in json.loads(last[1])],
                        source="binance_ws:top10")
    return bars, book
