"""Comprobaciones del examen físico (T169): no anticipación e identidad del subconjunto. I/O.

**No anticipación** (ficha T169): en cada corte T se hace una copia del banco con solo lo que se
sabía en T (velas que cierran ≤ T y funding con t < T, la misma frontera que `build_snapshot`), se
recalculan los últimos contextos hasta T y se comparan, campo a campo, con los que generó la
corrida sobre el banco entero; después se comparan las **ideas** (`Signal`) de cada prospecto en
esa ventana. Una diferencia es anticipación: el prospecto (o su agente) miró el futuro.

**Identidad del subconjunto:** en unos contextos reales, el `nat` de la corrida (solo los agentes
con historia) ha de ser idéntico al de la mesa con todos los agentes (`CtxGenerator`, el de
T168), y los agentes sin historia no han de aportar nada.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from pathlib import Path

import duckdb

from eim.data.store import Store
from eim.data.timeframes import FOCUS, tf_ms
from eim.nursery.exam.gen import LightGen, agents_named, ctx_path, load_ctxs
from eim.nursery.exam.physical import account_of
from eim.nursery.exam.plan import BLOCK_DAYS, DAY_MS, HISTORYLESS, block_start
from eim.nursery.prospect import Prospect, native_paths
from eim.nursery.signals import signals

CANDLE_TFS = ("15m", "1h", "4h")
CUT_BLOCKS = (0, 9, 18, 27, 36, 45)
WINDOW = 9


def _norm(x: object) -> object:
    return json.loads(json.dumps(x, sort_keys=True))


def truncate_bank(src: Path, dst: Path, cut: int, symbol: str = FOCUS[0]) -> None:
    """Copia de `src` con lo sabido en `cut`: velas con cierre ≤ cut y funding con t < cut."""
    con = duckdb.connect()
    jobs = [(f"candles/symbol={symbol}/timeframe={tf}", f"t + {tf_ms(tf)} <= {int(cut)}")
            for tf in CANDLE_TFS]
    jobs.append((f"funding/symbol={symbol}/timeframe=-", f"t < {int(cut)}"))
    for rel, cond in jobs:
        a, b = src / rel, dst / rel
        b.mkdir(parents=True, exist_ok=True)
        shutil.copy2(a / "meta.json", b / "meta.json")
        con.execute(f"COPY (SELECT * FROM read_parquet('{(a / 'data.parquet').as_posix()}') "
                    f"WHERE {cond} ORDER BY t) TO '{(b / 'data.parquet').as_posix()}' "
                    "(FORMAT PARQUET)")
    con.close()


def cuts_for(tf: str, stretches: dict[str, list]) -> list[int]:
    """Cortes del marco: el final de los tramos de los bloques de `CUT_BLOCKS`."""
    if tf == "4h":
        return [block_start(k) + BLOCK_DAYS * DAY_MS for k in CUT_BLOCKS]
    return [int(e) for b, _s, e in stretches[tf] if int(b) in CUT_BLOCKS]


def _ideas(p: Prospect, ctxs: Sequence[dict], hist: int) -> list[tuple]:
    return [(s.enter, s.hold, s.target) for s in signals(account_of(p), ctxs, hist)]


def lookahead(plan: dict, work: Path, prospects: Sequence[Prospect], tmp: Path,
              hist: int = 4) -> list[dict]:
    """Un renglón por (marco, corte): contextos y prospectos cuyas ideas cambian al truncar."""
    bank, out = Path(plan["bank"]), []
    native = {a: tuple(v) for a, v in plan["native"].items()}
    for tf in CANDLE_TFS:
        ids = plan["agents"].get(tf) or []
        if not ids:
            continue
        agents, bar = agents_named(ids), tf_ms(tf)
        mine = [p for p in prospects if p.timeframe == tf and p.id in plan["prospects"]]
        for cut in cuts_for(tf, plan["stretches"]):
            full = load_ctxs(ctx_path(work, tf), cut - WINDOW * bar, cut)
            if len(full) < WINDOW:
                out.append({"tf": tf, "cut": cut, "missing": WINDOW - len(full)})
                continue
            dst = tmp / f"corte_{tf}_{cut}"
            shutil.rmtree(dst, ignore_errors=True)
            truncate_bank(bank, dst, cut)
            try:
                gen = LightGen(Store(dst), tf, agents, native)
                trunc = [gen.ctx_at(int(c["t"])) for c in full]
            finally:
                shutil.rmtree(dst, ignore_errors=True)
            ctx_diff = [int(a["t"]) for a, b in zip(full, trunc, strict=True)
                        if b is None or _norm(a) != _norm(b)]
            ok = [c for c in trunc if c is not None]
            idea_diff = [p.id for p in mine
                         if len(ok) != len(full) or _ideas(p, full, hist) != _ideas(p, ok, hist)]
            out.append({"tf": tf, "cut": cut, "contexts": len(full), "ctx_diff": ctx_diff,
                        "prospects": len(mine), "idea_diff": idea_diff})
    return out


def subset_identity(plan: dict, work: Path, prospects: Sequence[Prospect],
                    per_tf: int = 3) -> list[dict]:
    """`nat` de la corrida frente al de la mesa con todos los agentes, en contextos ya generados.

    La mesa guarda en cada marco las variables de **todos** los agentes con prospectos; la corrida
    solo las de los agentes con prospectos de ese marco. Se compara lo de esos agentes y se exige
    que ningún agente sin historia aporte nada en el banco."""
    from eim.paper.generate import CtxGenerator

    store, out = Store(Path(plan["bank"])), []
    every = native_paths(tuple(prospects))           # también los agentes sin historia
    for tf in CANDLE_TFS:
        rows = load_ctxs(ctx_path(work, tf))
        mine = set(plan["agents"].get(tf) or [])
        if not rows:
            continue
        step = max(1, len(rows) // per_tf)
        gen = CtxGenerator(store, timeframe=tf, native=every)
        for c in rows[::step][:per_tf]:
            ref = gen.ctx_at(plan["symbol"], int(c["t"]))
            full = (ref or {}).get("nat") or {}
            same = ref is not None and ref["close"] == c["close"] and ref["atr"] == c["atr"] \
                and _norm({a: v for a, v in full.items() if a in mine}) == _norm(c["nat"])
            out.append({"tf": tf, "t": int(c["t"]), "identical": bool(same),
                        "historyless_with_data": sorted(set(full) & HISTORYLESS),
                        "full_nat_agents": sorted(full), "run_nat_agents": sorted(c["nat"])})
    return out
