"""Adoptar resultados anteriores a T124: instantánea a posteriori de una ventana de T27.

La puerta de edge de T27 (2026-10-13) no fijó sus datos. Adoptar una ventana es tomar HOY una
instantánea congelada de su rango (las `lookback` velas de contexto + la ventana) y registrar la
cifra grabada en `edge_results.json` como resultado `edge_window` con código «desconocido». No
se recalcula nada ni se toca el veredicto de T27: eso lo hace `repetir`, que dirá si los datos y
el código de hoy reproducen la cifra. La nota lo deja dicho: la instantánea es posterior.
"""

from __future__ import annotations

import json
from pathlib import Path

from eim.calibration.gate_cli import FIGURES
from eim.data.results import ResultRecord, ResultStore
from eim.data.snapshots import SnapshotStore
from eim.data.timeframes import tf_ms
from eim.repro.code import UNKNOWN
from eim.repro.text import ts

DEFAULT_EDGE = Path("reports/edge/edge_results.json")


def adopt_t27(root: str | Path, store, edge: Path = DEFAULT_EDGE, assets: list[str] | None = None,
              windows: list[int] | None = None, log=print) -> list[ResultRecord]:
    """Registra ventanas de T27 (índices desde 1) con una instantánea tomada de `store`."""
    data = json.loads(Path(edge).read_text(encoding="utf-8"))
    meta, tf = data["meta"], data["meta"]["timeframe"]
    lookback, step = meta["backtest"]["lookback"], tf_ms(tf)
    snaps, results, out = SnapshotStore(root), ResultStore(root), []
    for sym, r in data["assets"].items():
        if assets and sym not in assets:
            continue
        for k, w in enumerate(r["windows"], start=1):
            if windows and k not in windows:
                continue
            ctx = store.read_candles(sym, tf, end=w["from_t"], last=lookback)
            if len(ctx) < lookback:
                log(f"{sym} ventana {k}: el almacén {store.root} no tiene las {lookback} velas de "
                    f"contexto antes de {ts(w['from_t'])} (tiene {len(ctx)}): no se adopta")
                continue
            snap = snaps.create(store, sym, tf, start=ctx[0].t, end=w["to_t"] + step,
                                origin="adoptar-t27 (instantánea a posteriori)")
            want = lookback + (w["to_t"] - w["from_t"]) // step + 1
            if snap.info.n_candles != want:
                log(f"{sym} ventana {k}: {snap.info.n_candles} velas de {want} esperadas "
                    f"({snap.info.gaps} huecos); se registra igual y `repetir` lo dirá")
            params = {"symbol": sym, "timeframe": tf, "from_t": w["from_t"], "to_t": w["to_t"],
                      "values": meta["params"], "backtest": meta["backtest"]}
            note = (f"Cifra de T27 producida sin instantánea; datos fijados a posteriori el "
                    f"{ts(snap.info.created_ms)} desde {store.root} (fuente {snap.info.source}). "
                    f"Fuente original: {r.get('source')}, hash de la serie {r.get('data_hash')}.")
            rec = results.register("edge_window", f"T27 {sym} {tf} ventana {k} (adoptada)",
                                   [snap.info.id], params, UNKNOWN,
                                   {f: w[f] for f in FIGURES if f in w}, str(edge), note)
            log(f"{sym} ventana {k}: {rec.id} · instantánea {snap.info.id} "
                f"({snap.info.n_candles} velas, {snap.info.n_funding} de funding)")
            out.append(rec)
    return out
