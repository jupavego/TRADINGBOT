"""Control de calidad por hora de la captura HFT (T78): un JSON por hora cerrada en
`micro_hft/qc/symbol=S/date=D/hour=HH.json`.

Mide, desde los datos crudos y sin fiarse del recolector: mensajes por segundo y cobertura de cada
flujo, latencia aparente (recepción − `E`), reordenamientos, huecos de secuencia (`pu`), ids de
`aggTrade` que faltan, silencios de los flujos continuos, saltos del reloj local, mensajes
descartados por cola llena, reinicios y el % de verificaciones top-10 que coinciden con el snapshot
REST. Después cruza cada hueco que encuentra con los tramos que el recolector MARCÓ: uno sin marca
es un «hueco no detectado» (debe ser 0). Los tramos con hueco se marcan, no se arreglan.

Una hora es **completa** si ≥ 99 % de sus segundos tienen libro utilizable (diffs recibidos y fuera
de un tramo marcado), `bookTicker` y `markPrice` cubren ≥ 99 % y no hay huecos sin detectar.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from eim.data.collectors.hft_capture import SILENCE_NS
from eim.data.collectors.hft_read import hour_label, read_hour, tail_row
from eim.data.collectors.hft_schema import HOUR_NS, KINDS
from eim.data.collectors.hft_writer import hour_dir

QC_VERSION = 1
COVERAGE_MIN = 0.99
TOL_NS = 1_000_000_000            # holgura al casar un hueco con una marca del recolector
CONN = {"depth": "depth", "bbo": "bbo", "trades": "market", "mark": "market", "liq": "market"}
BOOK_CAUSES = ("secuencia", "sin_libro", "silencio", "cola_llena", "desconexion")
ID_COL = {"depth": "last_id", "bbo": "upd_id", "trades": "agg_id"}
_COLS = {"depth": "recv_ns, run, seq, e_ms, first_id, last_id, prev_id",
         "bbo": "recv_ns, run, seq, e_ms, upd_id", "trades": "recv_ns, run, seq, e_ms, agg_id",
         "mark": "recv_ns, run, seq, e_ms", "liq": "recv_ns, run, seq, e_ms"}
MAX_LIST = 50


def qc_path(root: str | Path, symbol: str, hour: int) -> Path:
    d = hour_dir(root, "qc", symbol, hour)
    return d.parent / f"{d.name}.json"


def _per_second(recv: np.ndarray, hour: int) -> np.ndarray:
    sec = (recv - hour * HOUR_NS) // 1_000_000_000
    return np.bincount(sec[(sec >= 0) & (sec < 3600)], minlength=3600)


def _same_run(df: pd.DataFrame) -> np.ndarray:
    run = df["run"].to_numpy(np.int64)
    return run[1:] == run[:-1]


def stream_stats(df: pd.DataFrame, kind: str, hour: int) -> dict:
    if df.empty:
        return {"msgs": 0, "coverage": 0.0, "reorders": 0}
    recv = df["recv_ns"].to_numpy(np.int64)
    cnt = _per_second(recv, hour)
    out = {"msgs": len(df), "rate_mean": round(len(df) / 3600, 2), "rate_max": int(cnt.max()),
           "coverage": round(float((cnt > 0).mean()), 4)}
    e = df["e_ms"].to_numpy(np.int64)
    ok = e > 0
    if ok.any():
        lat = recv[ok] // 1_000_000 - e[ok]
        out["latency_ms"] = {f"p{q}": round(float(np.percentile(lat, q)), 1) for q in (50, 99)}
        out["latency_ms"]["max"] = int(lat.max())
    back = np.diff(e) < 0
    if kind in ID_COL:
        back |= np.diff(df[ID_COL[kind]].to_numpy(np.int64)) < 0
    out["reorders"] = int((back & _same_run(df)).sum())
    return out


def _pairs(df: pd.DataFrame, tail: dict | None, col: str) -> tuple[np.ndarray, ...]:
    """(recv previo, recv, valor previo, valor) de pares consecutivos de la misma corrida,
    incluido el par que enlaza con la última fila de la hora anterior."""
    recv = df["recv_ns"].to_numpy(np.int64)
    val = df[col].to_numpy(np.int64)
    run = df["run"].to_numpy(np.int64)
    if tail is not None and len(df) and int(tail["run"]) == run[0]:
        recv = np.concatenate([[int(tail["recv_ns"])], recv])
        val = np.concatenate([[int(tail[col])], val])
        run = np.concatenate([[run[0]], run])
    same = run[1:] == run[:-1]
    return recv[:-1][same], recv[1:][same], val[:-1][same], val[1:][same]


def detect_holes(frames: dict[str, pd.DataFrame], tails: dict[str, dict | None]) -> list[dict]:
    """Huecos vistos en los datos crudos (dentro de una corrida; un reinicio se cuenta aparte)."""
    holes: list[dict] = []
    d = frames["depth"]
    if not d.empty:
        recv = d["recv_ns"].to_numpy(np.int64)
        prev, last = d["prev_id"].to_numpy(np.int64), d["last_id"].to_numpy(np.int64)
        same = _same_run(d)
        tail = tails.get("depth")
        if tail is not None and int(tail["run"]) == int(d["run"].iloc[0]) \
                and prev[0] != int(tail["last_id"]):
            holes.append({"stream": "depth", "kind": "secuencia",
                          "start_ns": int(tail["recv_ns"]), "end_ns": int(recv[0])})
        for i in np.flatnonzero((prev[1:] != last[:-1]) & same):
            holes.append({"stream": "depth", "kind": "secuencia", "start_ns": int(recv[i]),
                          "end_ns": int(recv[i + 1])})
    t = frames["trades"]
    if not t.empty:
        r0, r1, a0, a1 = _pairs(t, tails.get("trades"), "agg_id")
        for i in np.flatnonzero(a1 > a0 + 1):
            holes.append({"stream": "trades", "kind": "ids_trades", "start_ns": int(r0[i]),
                          "end_ns": int(r1[i])})
    for kind, limit in SILENCE_NS.items():
        df = frames[kind]
        if df.empty:
            continue
        r0, r1, _, _ = _pairs(df, tails.get(kind), "recv_ns")
        for i in np.flatnonzero(r1 - r0 > limit):
            holes.append({"stream": kind, "kind": "silencio", "start_ns": int(r0[i]),
                          "end_ns": int(r1[i])})
    return holes


def covered(hole: dict, gaps: pd.DataFrame) -> bool:
    """¿Hay un tramo marcado por el recolector, del mismo flujo o conexión, que lo solape?"""
    if gaps.empty:
        return False
    streams = {hole["stream"], CONN[hole["stream"]]}
    g = gaps[gaps["stream"].isin(streams)]
    return bool(((g["start_ns"] - TOL_NS <= hole["end_ns"])
                 & (g["end_ns"] + TOL_NS >= hole["start_ns"])).any())


def _unusable_seconds(gaps: pd.DataFrame, hour: int) -> np.ndarray:
    """Segundos de la hora dentro de un tramo marcado que deja al libro sin uso."""
    mask = np.zeros(3600, bool)
    g = gaps[gaps["cause"].isin(BOOK_CAUSES) & gaps["stream"].isin(("depth",))]
    h0 = hour * HOUR_NS
    for s, e in zip(g["start_ns"], g["end_ns"], strict=True):
        a, b = max(int(s) - h0, 0) // 10**9, min(int(e) - h0, HOUR_NS - 1) // 10**9
        if b >= 0 and a < 3600:
            mask[a:b + 1] = True
    return mask


def qc_hour(hour: int, frames: dict[str, pd.DataFrame], tails: dict[str, dict | None],
            gaps: pd.DataFrame, checks: pd.DataFrame, clock: pd.DataFrame, book: pd.DataFrame,
            disk_mb: dict[str, float] | None = None) -> dict:
    """Informe de calidad de una hora. Puro: recibe las tablas ya leídas.

    `gaps` debe traer los tramos de la hora y de la siguiente (los «sin libro» se cierran al
    cambiar de hora); aquí se filtran por solape."""
    h0, h1 = hour * HOUR_NS, (hour + 1) * HOUR_NS
    gaps = gaps[(gaps["end_ns"] >= h0) & (gaps["start_ns"] < h1)] if not gaps.empty else gaps
    streams = {k: stream_stats(frames[k], k, hour) for k in ("depth", "bbo", "trades", "mark")}
    streams["liq"] = {"msgs": len(frames["liq"])}
    holes = detect_holes(frames, tails)
    missing = [h for h in holes if not covered(h, gaps)]
    depth_sec = (_per_second(frames["depth"]["recv_ns"].to_numpy(np.int64), hour) > 0
                 if not frames["depth"].empty else np.zeros(3600, bool))
    usable = float((depth_sec & ~_unusable_seconds(gaps, hour)).mean())
    comp = checks[checks["comparable"]] if not checks.empty else checks
    n_comp, n_ok = len(comp), int(comp["match"].sum()) if len(comp) else 0
    jumps = clock[clock["kind"] == "salto"] if not clock.empty else clock
    by_cause = gaps["cause"].value_counts().to_dict() if not gaps.empty else {}
    complete = (usable >= COVERAGE_MIN and not missing
                and all(streams[k]["coverage"] >= COVERAGE_MIN for k in ("bbo", "mark")))
    return {
        "version": QC_VERSION, "hour": hour_label(hour), "hour_index": hour,
        "generated_at": int(time.time() * 1000), "complete": bool(complete),
        "book_usable": round(usable, 4), "streams": streams,
        "checks": {"total": len(checks), "comparable": n_comp, "matched": n_ok,
                   "match_rate": round(n_ok / n_comp, 4) if n_comp else None,
                   "failures": [str(x) for x in comp.loc[~comp["match"], "detail"]][:MAX_LIST]
                   if n_comp else []},
        "holes": {"found": len(holes), "undetected": len(missing), "list": missing[:MAX_LIST]},
        "gaps_marked": {"by_cause": {str(k): int(v) for k, v in by_cause.items()},
                        "list": json.loads(gaps.drop(columns=["mono_ns"], errors="ignore")
                                           .head(MAX_LIST).to_json(orient="records"))
                        if not gaps.empty else []},
        "overflow_dropped": int(gaps.loc[gaps["cause"] == "cola_llena", "n"].sum())
        if not gaps.empty else 0,
        "clock": {"jumps": len(jumps), "adjustments": int(len(clock) - len(jumps)),
                  "max_abs_ms": round(float(clock["jump_ns"].abs().max()) / 1e6, 2)
                  if not clock.empty else 0.0},
        "runs": int(pd.concat([f["run"] for f in frames.values() if not f.empty]).nunique())
        if any(not f.empty for f in frames.values()) else 0,
        "restarts": int((book["purpose"] == "arranque").sum()) if not book.empty else 0,
        "disk_mb": disk_mb or {},
    }


def _dir_mb(d: Path) -> float:
    return round(sum(f.stat().st_size for f in d.glob("*.parquet")) / 1e6, 3) if d.exists() else 0.0


def run_hour(root: str | Path, symbol: str, hour: int, write: bool = True) -> dict:
    """Lee la hora (y la anterior/siguiente para enlazar), calcula y escribe el JSON."""
    frames = {k: read_hour(root, symbol, k, hour, c) for k, c in _COLS.items()}
    tails = {k: tail_row(root, symbol, k, hour - 1, c)
             for k, c in _COLS.items() if k in ("depth", "trades", *SILENCE_NS)}
    gaps = pd.concat([read_hour(root, symbol, "gaps", h) for h in (hour, hour + 1)],
                     ignore_index=True)
    rep = qc_hour(hour, frames, tails, gaps, read_hour(root, symbol, "checks", hour),
                  read_hour(root, symbol, "clock", hour),
                  read_hour(root, symbol, "book", hour, "run, seq, purpose"),
                  {k: _dir_mb(hour_dir(root, k, symbol, hour)) for k in KINDS})
    rep["symbol"] = symbol
    if write:
        p = qc_path(root, symbol, hour)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str),
                       encoding="utf-8")
        tmp.replace(p)
    return rep


def load(root: str | Path, symbol: str, hour: int) -> dict | None:
    try:
        return json.loads(qc_path(root, symbol, hour).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

