"""Contextos ligeros con `nat` sobre la copia del banco, vela a vela y reanudables (T169). I/O.

Un contexto ligero es `{t, close, atr, nat, st}`: `close` y `atr` salen de `vol_inputs` como en
`make_ctx`, `nat` de `native_block` como en la mesa con `EIM_NURSERY=1`, y `st` es el estado de
cada agente que corrió. Solo corren los agentes con prospectos con historia en ese marco (el
plan): `nat` depende únicamente de sus reportes y cada agente es una función pura del snapshot, así
que el resultado es el de la mesa completa (`checks.subset_identity` lo comprueba).

Los agentes corren uno tras otro y **sin plazo**: el plazo de `run_agents` cuenta en tiempo de
reloj y la cola suspende el proceso cuando la captura sufre o falta RAM; tras una pausa, todos
saldrían degradados por un plazo que no gastaron. Un agente que revienta sale degradado, igual que
en `runner._guarded`.

Cada contexto se añade a `ctx_<marco>.jsonl` en cuanto se calcula. Al relanzar se descarta una
última línea a medio escribir y solo se calcula lo que falta; un `asof` sin vela que lo cierre
queda apuntado como `skip` para no reintentarlo.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

from eim.agents.base import degraded_report
from eim.agents.registry import default_registry
from eim.core import Agent, AgentReport, MarketSnapshot
from eim.data.snapshot import build_snapshot
from eim.data.store import Store
from eim.data.timeframes import FOCUS, tf_ms
from eim.nursery.native import native_block
from eim.paper.context import vol_inputs
from eim.paper.generate import AGENT_BARS

_R = 6


def _r(x: float | None) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), _R)


def agents_named(ids: Iterable[str]) -> list[Agent]:
    """Los agentes vigentes del registro con esos ids, en el orden pedido."""
    latest = {a.id: a for a in default_registry().latest()}
    missing = [i for i in ids if i not in latest]
    if missing:
        raise ValueError(f"agentes sin registrar: {missing}")
    return [latest[i] for i in ids]


def _report(agent: Agent, snap: MarketSnapshot) -> AgentReport:
    try:
        return agent.run(snap)
    except Exception as exc:  # noqa: BLE001 - un agente roto sale degradado, como en el bróker
        return degraded_report(agent.id, agent.version, snap.asof,
                               f"error: {type(exc).__name__}: {exc}")


class LightGen:
    """Contexto ligero de un marco, con los agentes dados y las rutas nativas del plan."""

    def __init__(self, store: Store, tf: str, agents: list[Agent],
                 native: dict[str, tuple[str, ...]], symbol: str = FOCUS[0]) -> None:
        self.store, self.tf, self.agents, self.symbol = store, tf, agents, symbol
        self.native = {a: tuple(v) for a, v in native.items()}
        self.bar = tf_ms(tf)

    def ctx_at(self, asof: int) -> dict | None:
        snap = build_snapshot(self.store, self.symbol, self.tf, AGENT_BARS, asof=asof)
        if len(snap.candles) < AGENT_BARS // 2 or snap.candles[-1].t + self.bar != asof:
            return None                 # sin la vela que cierra en `asof` no hay decisión
        reports = [_report(a, snap) for a in self.agents]
        close, atr_, _ = vol_inputs(snap, self.bar)
        return {"t": int(asof), "close": _r(close), "atr": _r(atr_),
                "nat": native_block(reports, self.native),
                "st": {r.agent_id: r.status for r in reports}}


def ctx_path(work: Path, tf: str) -> Path:
    return work / f"ctx_{tf}.jsonl"


def repair(path: Path) -> int:
    """Quita una última línea a medio escribir (corte en pleno `write`); devuelve los bytes."""
    if not path.exists():
        return 0
    data = path.read_bytes()
    if not data or data.endswith(b"\n"):
        return 0
    keep = data.rfind(b"\n") + 1
    with path.open("r+b") as f:
        f.truncate(keep)
    return len(data) - keep


def iter_rows(path: Path) -> Iterator[dict]:
    """Filas guardadas (una línea ilegible se salta: solo puede ser la última, sin reparar)."""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def load_ctxs(path: Path, start: int | None = None, end: int | None = None) -> list[dict]:
    """Contextos (sin los `skip`) con `start < t ≤ end`, ascendentes y sin repetir `t`."""
    seen: dict[int, dict] = {}
    for row in iter_rows(path):
        t = int(row["t"])
        if row.get("skip") or (start is not None and t <= start) or (end is not None and t > end):
            continue
        seen.setdefault(t, row)
    return [seen[t] for t in sorted(seen)]


def run(gen: LightGen, asofs: Iterable[int], path: Path,
        progress: Callable[[int, int, float], None] | None = None,
        limit: int | None = None) -> int:
    """Calcula y guarda los `asofs` que falten (como mucho `limit`). Devuelve cuántos calculó."""
    repair(path)
    done = {int(r["t"]) for r in iter_rows(path)}
    todo = [a for a in sorted(set(asofs)) if a not in done][:limit]
    path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for k, asof in enumerate(todo, 1):
            ctx = gen.ctx_at(asof)
            row = ctx if ctx is not None else {"t": int(asof), "skip": True}
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            f.flush()
            if progress:
                progress(k, len(todo), time.perf_counter() - t0)
    return len(todo)
