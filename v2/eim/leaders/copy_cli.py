"""Órdenes de la copia simulada (T42) para `python -m eim.leaders`:

  copy-sim [--leaders all|approved|0x…,0x…] [--equity 10000] [--offline] [--db RUTA]
      reproduce la copia sobre el historial capturado y escribe `reports/copytrading_sim.md`
      (+ bitácora completa en `data/copytrading/replay_journal.jsonl`). Si el servicio tiene
      abierta `leaders.duckdb`, le pide una instantánea y trabaja sobre ella.
  copy-status [--json]        resumen de las subcuentas en vivo (`data/leaders/copy_sim.json`)
  copy-resume 0xDIR…|--all    reanuda a mano subcuentas en pausa (las recoge el servicio)

Todo en modo SIMULADO: no hay claves ni órdenes.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb

from eim.copytrading.copy_attrib import attribute
from eim.copytrading.copy_params import CopyParams
from eim.copytrading.copy_report import LeaderSim, render
from eim.copytrading.copy_risk import copy_config
from eim.copytrading.stats import quantile
from eim.core.leaders import leader_id
from eim.data.copy_replay import ReplayResult, funding_rates, replay
from eim.data.copy_store import read_summary, request_resume, request_snapshot
from eim.data.hl_market import candles_1m, exchange_spec
from eim.data.leader_store import DB_NAME, LeaderStore
from eim.data.providers.leaders import HyperliquidInfo, now_ms

SNAPSHOT_WAIT_S = 90.0


def add_parsers(sub) -> None:
    p = sub.add_parser("copy-sim")
    p.add_argument("--leaders", default="all", help="all | approved | 0x…,0x…")
    p.add_argument("--equity", type=float, default=CopyParams().initial_equity)
    p.add_argument("--offline", action="store_true", help="sin red: velas y meta de la caché")
    p.add_argument("--db", default=None, help="copia de leaders.duckdb a usar")
    p.add_argument("--out", default="reports/copytrading_sim.md")
    p.add_argument("--journal", default="data/copytrading/replay_journal.jsonl")
    p = sub.add_parser("copy-status")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("copy-resume")
    p.add_argument("addresses", nargs="*")
    p.add_argument("--all", action="store_true")


def main(a: argparse.Namespace) -> str:
    if a.cmd == "copy-status":
        return _status(a)
    if a.cmd == "copy-resume":
        live = read_summary(a.root) or {}
        ids = ([x["leader_id"] for x in live.get("accounts", []) if x.get("paused")
                or x.get("kill", {}).get("active")] if a.all else
               [leader_id("hyperliquid", x.strip()) for x in a.addresses])
        if not ids:
            return "Nada que reanudar."
        request_resume(a.root, ids, now_ms())
        return f"Reanudación pedida para {len(ids)} subcuentas (el servicio la aplica en ≤ 1 min)."
    return _sim(a)


def _open(a: argparse.Namespace) -> tuple[LeaderStore, str]:
    path = Path(a.db) if a.db else Path(a.root) / DB_NAME
    try:
        return LeaderStore(path), str(path)
    except duckdb.IOException:
        if a.db:
            raise
    snap = request_snapshot(a.root, now_ms())
    before = snap.stat().st_mtime if snap.exists() else 0.0
    deadline = time.monotonic() + SNAPSHOT_WAIT_S
    while time.monotonic() < deadline:
        time.sleep(1.0)
        if snap.exists() and snap.stat().st_mtime > before:
            time.sleep(1.0)
            return LeaderStore(snap), f"{snap} (instantánea del servicio)"
    raise SystemExit("leaders.duckdb está en uso y el servicio no respondió a la instantánea "
                     f"en {SNAPSHOT_WAIT_S:.0f} s: usa --db con una copia")


def _select(store: LeaderStore, which: str) -> list:
    tracked = [ld for ld in store.leaders() if ld.venue == "hyperliquid" and ld.tracked]
    if which == "all":
        return tracked
    if which == "approved":
        return [ld for ld in tracked if ld.status == "approved"]
    want = {leader_id("hyperliquid", x.strip()) for x in which.split(",") if x.strip()}
    return [ld for ld in tracked if ld.id in want]


def _end(store: LeaderStore) -> int:
    rows = store.query("SELECT max(observed_at) FROM leader_positions")
    return int(rows[0][0] or now_ms())


def _coins(store: LeaderStore, lid: str, start: int) -> set[str]:
    rows = store.query("SELECT DISTINCT symbol FROM leader_fills WHERE leader_id = ? AND t > ?",
                       [lid, start])
    out = {r[0] for r in rows}
    near = store.positions_near(lid, start + 1)
    return out | {x.symbol for x in (near[1] if near else [])}


def _sim_of(res: ReplayResult) -> LeaderSim:
    eng = res.engine
    att = attribute(eng.leader_id, res.trips, eng.fills, eng.closed, eng.trip_info,
                    {c: p.trip_t for c, p in eng.account.positions.items()})
    lat = [float(e.data["latency_ms"]) for e in eng.journal
           if e.kind == "signal" and e.code == "ws"]
    acc = eng.summary(journal_tail=0)
    acc.pop("curve", None)
    return LeaderSim(leader_id=eng.leader_id, label=res.leader.label, status=res.leader.status,
                     measure=eng.measure, start=res.start, end=res.end, attribution=att,
                     account=acc, price_src=res.price_src,
                     latency={"p50": quantile(lat, 0.5), "p90": quantile(lat, 0.9)},
                     funding_missing=res.funding_missing, warnings=res.warnings)


def _sim(a: argparse.Namespace) -> str:
    store, src = _open(a)
    info = HyperliquidInfo()
    try:
        p = CopyParams(initial_equity=a.equity)
        spec = exchange_spec(_NoNet() if a.offline else info, a.root)
        cfg = copy_config(p)
        leaders = _select(store, a.leaders)
        end = _end(store)
        firsts = [ts[0] for ld in leaders if (ts := store.photo_times(ld.id, end))]
        start = min(firsts, default=end)
        rates = funding_rates(store, start, end)
        cache = Path(a.root) / "cache" / "hl_candles"
        sims, journal = [], []
        for ld in leaders:
            t0 = (store.photo_times(ld.id, end) or [end])[0]
            bars = {c: candles_1m(info, c, t0, end, cache, offline=a.offline)
                    for c in sorted(_coins(store, ld.id, t0))}
            res = replay(store, ld, p, spec, cfg, bars, rates, end)
            if res is None:
                continue
            sims.append(_sim_of(res))
            journal += res.engine.journal
    finally:
        store.close()
    now = now_ms()
    md = render(sims, read_summary(a.root), p, cfg.version, now, spec.source)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    jpath = Path(a.journal)
    jpath.parent.mkdir(parents=True, exist_ok=True)
    with jpath.open("w", encoding="utf-8") as f:
        for e in journal:
            f.write(e.model_dump_json() + "\n")
    return (f"{len(sims)} líderes reproducidos desde {src}\ninforme: {out}\n"
            f"bitácora: {jpath} ({len(journal)} entradas)")


class _NoNet:
    def meta(self) -> dict:
        raise OSError("sin red (--offline)")


def _status(a: argparse.Namespace) -> str:
    live = read_summary(a.root)
    if live is None:
        return "Sin copia en vivo (data/leaders/copy_sim.json): ¿servicio con EIM_COPY_SIM=off?"
    if a.json:
        return json.dumps(live, indent=1, ensure_ascii=False)
    age = (now_ms() - live["asof"]) / 1000
    lines = [f"Copia simulada · modo {live['mode']} ({live.get('sim_mode')}) · hace {age:.0f} s"]
    for x in live.get("accounts", []):
        st = "PAUSA: " + x["paused"] if x.get("paused") else (
            "KILL" if x.get("kill", {}).get("active") else "ok")
        lines.append(f"  {x.get('label') or x['leader_id'][12:22]:<14} capital "
                     f"{x['equity']:>10,.2f}  resultado {x['pnl']:>+9,.2f}  órdenes "
                     f"{x['counts'].get('orders', 0):>4}  posiciones "
                     f"{sum(1 for q in x['positions'] if q['size'])}  {st}")
    return "\n".join(lines)
