"""Conversor de la captura HFT (T78) a eventos del simulador: formato propio `eim_hft_events` v1.

T77 fijó «motor propio; HftBacktest solo como contraste aislado»: un `.npz` por hora con `events`
(registros de 64 B con el MISMO diseño que `event_dtype` de HftBacktest: `ev, exch_ts, local_ts,
px, qty, order_id, ival, fval`) y `meta` (JSON). Los códigos de `ev` son propios (abajo); el
contraste de T79 los traduce. `local_ts` = recepción (ns UTC); `exch_ts` = `T` (o `E`) del
exchange en ns, −1 en las marcas sin hora del exchange.

Cada hora empieza con el libro exacto del recolector (fila `book` → `CLEAR` + `SNAPSHOT`), así que
cada archivo se reproduce solo. Después, en el orden de proceso del recolector (`run`, `seq`): los
diffs que su libro aplicó (`DEPTH`; `DEPTH|PRUNED` = nivel fantasma podado), `CLEAR` si el libro se
perdió, `BBO`, `TRADE` (lado = agresor), `MARK`, `LIQ`, las marcas de tramo (`GAP`, causa en el
byte 2 de `ev`) y las verificaciones REST (`CHECK`).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from eim.data.collectors.book import LocalBook
from eim.data.collectors.hft_book import book_hash
from eim.data.collectors.hft_read import hour_label, read_hour
from eim.data.collectors.hft_schema import CAUSES

FORMAT, VERSION = "eim_hft_events", 1
EVENT_DTYPE = np.dtype([("ev", "<u8"), ("exch_ts", "<i8"), ("local_ts", "<i8"), ("px", "<f8"),
                        ("qty", "<f8"), ("order_id", "<u8"), ("ival", "<i8"), ("fval", "<f8")])
DEPTH, TRADE, CLEAR, SNAPSHOT, BBO, MARK, LIQ, GAP, CHECK = 1, 2, 3, 4, 5, 20, 21, 30, 31
BUY, SELL, PRUNED = 1 << 29, 1 << 28, 1 << 27
TYPE_MASK = 0xFF
CAUSE_CODE = {c: i + 1 for i, c in enumerate(CAUSES)}


def _ev(n: int, ev, local, exch=-1) -> np.ndarray:
    a = np.zeros(n, EVENT_DTYPE)
    a["ev"], a["local_ts"], a["exch_ts"] = ev, local, exch
    return a


def _levels(ev: int, side: int, px, qty, local: int, exch: int, ival: int) -> np.ndarray:
    a = _ev(len(px), ev | side, local, exch)
    a["px"], a["qty"], a["ival"] = px, qty, ival
    return a


def _book_events(book: pd.DataFrame, depth: pd.DataFrame) -> list[tuple[int, int, np.ndarray]]:
    """Reproduce el libro del recolector: filas `book` (reinicios exactos) y diffs en orden."""
    bk = {c: book[c].tolist() for c in book.columns}
    dp = {c: depth[c].tolist() for c in depth.columns}
    order = sorted([(r, s, 0, i) for i, (r, s) in enumerate(zip(bk["run"], bk["seq"], strict=True))]
                   + [(r, s, 1, i) for i, (r, s) in enumerate(zip(dp["run"], dp["seq"],
                                                                  strict=True))])
    out: list[tuple[int, int, np.ndarray]] = []
    lb = LocalBook()
    for run, seq, tag, i in order:
        t = bk if tag == 0 else dp
        bp, bq, ap, aq = (np.asarray(t[c][i], float) for c in ("bp", "bq", "ap", "aq"))
        loc = int(t["recv_ns"][i])
        if tag == 0:
            lb = LocalBook(bids=dict(zip(bp.tolist(), bq.tolist(), strict=True)),
                           asks=dict(zip(ap.tolist(), aq.tolist(), strict=True)),
                           last_id=int(bk["last_id"][i]),
                           last_u=None if int(bk["last_u"][i]) < 0 else int(bk["last_u"][i]),
                           synced=bool(bk["synced"][i]))
            out.append((run, seq, np.concatenate([
                _ev(1, CLEAR, loc), _levels(SNAPSHOT, BUY, bp, bq, loc, -1, lb.last_id),
                _levels(SNAPSHOT, SELL, ap, aq, loc, -1, lb.last_id)])))
            continue
        u = int(dp["last_id"][i])
        res = lb.apply(int(dp["first_id"][i]), u, int(dp["prev_id"][i]),
                       list(zip(bp.tolist(), bq.tolist(), strict=True)),
                       list(zip(ap.tolist(), aq.tolist(), strict=True)))
        if res == "gap":
            out.append((run, seq, _ev(1, CLEAR, loc)))
        elif res == "ok":
            tx = int(dp["t_ms"][i])
            exch = (tx if tx > 0 else int(dp["e_ms"][i])) * 1_000_000
            parts = [_levels(DEPTH, BUY, bp, bq, loc, exch, u),
                     _levels(DEPTH, SELL, ap, aq, loc, exch, u)]
            if lb.last_pruned:
                pr = _ev(len(lb.last_pruned), 0, loc, exch)
                pr["ev"] = [DEPTH | PRUNED | (BUY if s == "b" else SELL) for s, _ in lb.last_pruned]
                pr["px"], pr["ival"] = [p for _, p in lb.last_pruned], u
                parts.append(pr)
            out.append((run, seq, np.concatenate(parts)))
    return out


def _vector(df: pd.DataFrame, build: Callable[[pd.DataFrame], list[np.ndarray]]):
    """Eventos de una tabla sin libro: cada fila da 1+ eventos con su (run, seq)."""
    if df.empty:
        return []
    arrs = build(df)
    k = len(arrs)
    ev = np.empty(len(df) * k, EVENT_DTYPE)
    for j, a in enumerate(arrs):
        ev[j::k] = a
    run = np.repeat(df["run"].to_numpy(np.int64), k)
    seq = np.repeat(df["seq"].to_numpy(np.int64), k)
    return [(run, seq, ev)]


def _exch(df: pd.DataFrame) -> np.ndarray:
    t = df["t_ms"].to_numpy(np.int64) if "t_ms" in df else np.full(len(df), -1)
    return np.where(t > 0, t, df["e_ms"].to_numpy(np.int64)) * 1_000_000


def _bbo(df):
    loc, ex, u = df["recv_ns"].to_numpy(np.int64), _exch(df), df["upd_id"].to_numpy(np.int64)
    return [_levels(BBO, BUY, df["bid_p"], df["bid_q"], loc, ex, u),
            _levels(BBO, SELL, df["ask_p"], df["ask_q"], loc, ex, u)]


def _trades(df):
    a = _ev(len(df), np.where(df["maker"].to_numpy(bool), TRADE | SELL, TRADE | BUY),
            df["recv_ns"].to_numpy(np.int64), _exch(df))
    a["px"], a["qty"], a["order_id"] = df["p"], df["q"], df["agg_id"].to_numpy(np.int64)
    return [a]


def _mark(df):
    a = _ev(len(df), MARK, df["recv_ns"].to_numpy(np.int64), _exch(df))
    a["px"], a["qty"], a["fval"] = df["mark_p"], df["index_p"], df["funding"]
    a["ival"] = df["next_funding_ms"].to_numpy(np.int64)
    return [a]


def _liq(df):
    side = np.where(df["side"].to_numpy(str) == "BUY", LIQ | BUY, LIQ | SELL)
    a = _ev(len(df), side, df["recv_ns"].to_numpy(np.int64), _exch(df))
    avg, fill = df["avg_p"].to_numpy(float), df["filled_q"].to_numpy(float)
    a["px"] = np.where(avg > 0, avg, df["p"].to_numpy(float))
    a["qty"] = np.where(fill > 0, fill, df["q"].to_numpy(float))
    return [a]


def _gaps(df):
    code = np.array([CAUSE_CODE.get(c, 0) for c in df["cause"]], np.uint64)
    a = _ev(len(df), GAP | (code << np.uint64(8)), df["recv_ns"].to_numpy(np.int64))
    start, end = df["start_ns"].to_numpy(np.int64), df["end_ns"].to_numpy(np.int64)
    a["ival"], a["fval"], a["order_id"] = start, (end - start) / 1e9, df["n"].to_numpy(np.int64)
    return [a]


def _checks(df):
    a = _ev(len(df), CHECK, df["recv_ns"].to_numpy(np.int64))
    a["ival"], a["order_id"], a["qty"] = df["snap_id"], df["seq"].to_numpy(np.int64), df["n_diff"]
    a["fval"] = np.where(~df["comparable"].to_numpy(bool), -1.0,
                         df["match"].to_numpy(bool).astype(float))
    return [a]


BUILDERS = {"bbo": _bbo, "trades": _trades, "mark": _mark, "liq": _liq, "gaps": _gaps,
            "checks": _checks}


def convert_hour(root: str | Path, symbol: str, hour: int) -> tuple[np.ndarray, dict]:
    """Eventos de la hora en el orden de proceso del recolector, y su `meta`."""
    chunks = [(np.full(len(a), r, np.int64), np.full(len(a), s, np.int64), a)
              for r, s, a in _book_events(read_hour(root, symbol, "book", hour),
                                          read_hour(root, symbol, "depth", hour))]
    for kind, build in BUILDERS.items():
        chunks += _vector(read_hour(root, symbol, kind, hour), build)
    if not chunks:
        return np.zeros(0, EVENT_DTYPE), {"format": FORMAT, "version": VERSION, "n": 0}
    run = np.concatenate([c[0] for c in chunks])
    seq = np.concatenate([c[1] for c in chunks])
    ev = np.concatenate([c[2] for c in chunks])
    ev = ev[np.lexsort((seq, run))]          # estable: conserva el orden dentro de cada fila
    types, n = np.unique(ev["ev"] & TYPE_MASK, return_counts=True)
    names = {DEPTH: "depth", TRADE: "trade", CLEAR: "clear", SNAPSHOT: "snapshot", BBO: "bbo",
             MARK: "mark", LIQ: "liq", GAP: "gap", CHECK: "check"}
    meta = {"format": FORMAT, "version": VERSION, "symbol": symbol, "hour": hour_label(hour),
            "n": len(ev), "counts": {names.get(int(t), str(t)): int(c) for t, c in zip(types, n,
                                                                                         strict=True)},
            "source": "micro_hft: captura propia de Binance USDⓈ-M (T78), datos reales",
            "dtype": [[n, t] for n, t in EVENT_DTYPE.descr]}
    return ev, meta


def save_npz(path: str | Path, events: np.ndarray, meta: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, events=events, meta=np.array(json.dumps(meta, default=str)))
    return path


def load_npz(path: str | Path) -> tuple[np.ndarray, dict]:
    with np.load(path, allow_pickle=False) as z:
        return z["events"], json.loads(str(z["meta"]))


def replay(events: np.ndarray, on_check: Callable[[int, str], None] | None = None
           ) -> tuple[dict[float, float], dict[float, float]]:
    """Libro reconstruido SOLO desde los eventos (lo que verá el simulador)."""
    bids: dict[float, float] = {}
    asks: dict[float, float] = {}
    sel = np.isin(events["ev"] & TYPE_MASK, (DEPTH, CLEAR, SNAPSHOT, CHECK))
    e = events[sel]
    for ev, px, qty, oid in zip(e["ev"].tolist(), e["px"].tolist(), e["qty"].tolist(),
                                e["order_id"].tolist(), strict=True):
        t = ev & TYPE_MASK
        if t == CLEAR:
            bids, asks = {}, {}
        elif t == CHECK:
            if on_check is not None:
                on_check(oid, book_hash(bids, asks))
        else:
            side = bids if ev & BUY else asks
            if qty == 0:
                side.pop(px, None)
            else:
                side[px] = qty
    return bids, asks
