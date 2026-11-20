"""Costo por agente (T87): tiempo y memoria de cada agente y del ciclo completo.

Mide, sobre snapshots REALES del almacén, lo que cuesta correr cada agente registrado en
1 h / 4 h / 1 d, y extrapola a un universo de 1 000 y 10 000 instrumentos con 1 y 4 procesos.
Alimenta el diseño del embudo de T93: cuánto cuesta la etapa barata (los agentes que solo piden
`candles`) frente al ciclo entero.

Uso (desde `v2/`):
  python scripts/agents_cost.py --data-dir data --out reports/t87_agents_cost.md
  python scripts/agents_cost.py --repeat 7 --frames 1h,4h,1d

No toca `eim/`, no pide red y no escribe en el almacén. El agente `context` se mide SIN su
analizador LLM (un banco no debe llamar a una API externa): sale `no_data`, y su costo real es
el de la llamada al modelo, no el de este proceso.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eim.agents.context import ContextAgent  # noqa: E402
from eim.agents.registry import default_registry  # noqa: E402
from eim.agents.runner import run_agents  # noqa: E402
from eim.core import MarketSnapshot  # noqa: E402
from eim.data.snapshot import build_snapshot  # noqa: E402
from eim.data.store import Store  # noqa: E402
from eim.data.timeframes import TF_MS  # noqa: E402

CHEAP_REQUIRES = {"candles"}         # portables por dato: nada más que la serie OHLCV
CHEAP_MS = 20.0                      # umbral de «barato por costo» para el embudo de T93
DEFAULT_FRAMES = ("1h", "4h", "1d")
UNIVERSE_SUBDIR = "universe_perps"   # 1 d: almacén del universo de perpetuos (T181)


@dataclass
class AgentCost:
    agent_id: str
    version: str
    requires: list[str]
    status: str
    ms_median: float
    ms_p90: float
    ms_max: float
    kib_peak: float
    cheap: bool


@dataclass
class FrameCost:
    timeframe: str
    symbol: str
    store: str
    candles: int
    asof: int
    agents: list[AgentCost]
    cycle_parallel_ms: float
    cycle_serial_ms: float
    cheap_ms_threshold: float = CHEAP_MS

    @property
    def cheap_ms(self) -> float:
        """Suma de los agentes portables por dato (solo `candles`)."""
        return sum(c.ms_median for c in self.agents if c.cheap)

    @property
    def fast(self) -> list[AgentCost]:
        """Barato POR COSTO: lo que el embudo puede permitirse sobre todo el universo."""
        return [c for c in self.agents if c.ms_median <= self.cheap_ms_threshold]

    @property
    def fast_ms(self) -> float:
        return sum(c.ms_median for c in self.fast)


def build_agents() -> list:
    """Última versión de cada agente registrado, con `context` sin LLM (banco sin red)."""
    agents = default_registry().latest()
    return [ContextAgent(unavailable="banco de medición T87: sin analizador LLM")
            if a.id == "context" else a for a in agents]


def snapshot_for(data_dir: Path, timeframe: str, symbol: str, bars: int
                 ) -> tuple[MarketSnapshot, str]:
    """(snapshot, raíz usada). 1 d vive en el almacén del universo de perpetuos (T181).

    `build_snapshot` NO admite 1 d: `_neighbor_candles` (`eim/data/snapshot.py:146`) busca el
    marco en la escalera `TF_MS` (15 m, 1 h, 4 h) y levanta `ValueError` con cualquier otro.
    Es uno de los acoplamientos que anota la matriz de T87 y que T90 tiene que resolver; aquí
    se evita armando el snapshot de 1 d a mano, SOLO con la serie de velas y sin tocar `eim/`.
    """
    if timeframe not in TF_MS:
        root = data_dir / UNIVERSE_SUBDIR
        store = Store(root)
        candles = store.read_candles(symbol, timeframe, last=bars)
        if not candles:
            raise SystemExit(f"sin velas de {symbol} {timeframe} en {root}")
        src = store.source("candles", symbol, timeframe) or "desconocida"
        snap = MarketSnapshot(
            symbol=symbol, timeframe=timeframe, candles=candles, asof=candles[-1].t,
            sources={"candles": src}, coverage={"candles": (candles[0].t, candles[-1].t)})
        return snap, root.as_posix()
    snap = build_snapshot(Store(data_dir), symbol, timeframe, bars)
    if not snap.candles:
        raise SystemExit(f"sin velas de {symbol} {timeframe} en {data_dir}")
    return snap, data_dir.as_posix()


def time_agent(agent, snap: MarketSnapshot, repeat: int) -> AgentCost:
    """Mediana/p90/máximo de `repeat` corridas (tras una de calentamiento) y pico de memoria."""
    rep = agent.run(snap)                       # calentamiento: cachés y primeras asignaciones
    samples: list[float] = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        agent.run(snap)
        samples.append((time.perf_counter() - t0) * 1000)
    tracemalloc.start()
    agent.run(snap)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    samples.sort()
    p90 = samples[min(len(samples) - 1, int(0.9 * len(samples)))]
    return AgentCost(
        agent_id=agent.id, version=agent.version, requires=sorted(agent.requires),
        status=rep.status, ms_median=statistics.median(samples), ms_p90=p90,
        ms_max=samples[-1], kib_peak=peak / 1024,
        cheap=set(agent.requires) <= CHEAP_REQUIRES,
    )


def measure_frame(data_dir: Path, timeframe: str, symbol: str, bars: int, repeat: int,
                  cheap_ms: float = CHEAP_MS) -> FrameCost:
    snap, root = snapshot_for(data_dir, timeframe, symbol, bars)
    agents = build_agents()
    costs = [time_agent(a, snap, repeat) for a in agents]
    run_agents(agents, snap)                    # calentamiento del ciclo
    t0 = time.perf_counter()
    run_agents(agents, snap)
    parallel = (time.perf_counter() - t0) * 1000
    return FrameCost(timeframe=timeframe, symbol=symbol, store=root, candles=len(snap.candles),
                     asof=snap.asof, agents=costs, cycle_parallel_ms=parallel,
                     cycle_serial_ms=sum(c.ms_median for c in costs),
                     cheap_ms_threshold=cheap_ms)


def _hours(n_instruments: int, ms_per_instrument: float, procs: int) -> float:
    return n_instruments * ms_per_instrument / 1000 / procs / 3600


def _ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d %H:%M UTC")


def _frame_section(f: FrameCost) -> list[str]:
    cheap = [c for c in f.agents if c.cheap]
    rows = [
        f"## Marco {f.timeframe} · {f.symbol}", "",
        f"Almacén `{f.store}` · {f.candles} velas cerradas · asof {_ts(f.asof)} · "
        f"{len(f.agents)} agentes ({len(cheap)} solo `candles`).", "",
        "| Agente | versión | requiere | estado | mediana (ms) | p90 (ms) | máx (ms) | "
        "pico mem (KiB) |", "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for c in sorted(f.agents, key=lambda x: -x.ms_median):
        mark = " ·" if c.cheap else ""
        rows.append(
            f"| `{c.agent_id}`{mark} | {c.version} | {', '.join(c.requires)} | {c.status} | "
            f"{c.ms_median:.2f} | {c.ms_p90:.2f} | {c.ms_max:.2f} | {c.kib_peak:,.0f} |")
    top = max(f.agents, key=lambda c: c.ms_median)
    rows += [
        "", "`·` = portable por dato (solo pide `candles`).", "",
        f"- **Ciclo completo, suma en serie**: {f.cycle_serial_ms:.1f} ms por instrumento.",
        f"- **Ciclo completo, `run_agents` en paralelo** (hilos, con el GIL): "
        f"{f.cycle_parallel_ms:.1f} ms.",
        f"- **Portables por dato** ({len(cheap)} agentes de `candles`): {f.cheap_ms:.1f} ms "
        f"({f.cheap_ms / f.cycle_serial_ms:.0%} del ciclo) — **no** es la etapa barata: "
        f"`{top.agent_id}` solo pide `candles` y se lleva "
        f"{top.ms_median / f.cycle_serial_ms:.0%} del ciclo.",
        f"- **Baratos por costo** (≤ {f.cheap_ms_threshold:g} ms: "
        f"{', '.join(f'`{c.agent_id}`' for c in sorted(f.fast, key=lambda c: c.ms_median))}): "
        f"{f.fast_ms:.1f} ms ({f.fast_ms / f.cycle_serial_ms:.1%} del ciclo).", "",
    ]
    return rows


def render(frames: list[FrameCost], repeat: int) -> str:
    out: list[str] = [
        "# T87 — Costo por agente y del ciclo (medido)", "",
        f"Generado: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} · reproducible con "
        f"`python scripts/agents_cost.py` · {repeat} repeticiones por agente tras una de "
        "calentamiento (mediana, p90 y máximo).", "",
        "`context` se mide **sin analizador LLM** (el banco no llama a ninguna API): su costo "
        "real es la llamada al modelo. Los agentes que salen `no_data` cuestan lo que cuesta "
        "comprobar que les falta el dato — ese es justo el costo que paga el escáner cuando el "
        "instrumento no tiene funding, libro o líderes.", "",
    ]
    for f in frames:
        out += _frame_section(f)
    out += ["## Extrapolación al universo", "",
            "Un marco por instrumento y una pasada; el tiempo de OBTENER los datos no está "
            "incluido (lo mide T90). `proc` = procesos del equipo (4 núcleos; este proyecto no "
            "pasa de 2 por la cola, ver `CLAUDE.md`).", "",
            "| Marco | etapa | ms/instr. | 1 000 (1 proc) | 1 000 (4 proc) | 10 000 (1 proc) | "
            "10 000 (4 proc) |", "|---|---|---:|---:|---:|---:|---:|"]
    for f in frames:
        for label, ms in (("ciclo completo", f.cycle_serial_ms),
                          ("portables por dato", f.cheap_ms),
                          (f"baratos por costo (≤ {f.cheap_ms_threshold:g} ms)", f.fast_ms)):
            cells = " | ".join(f"{_hours(n, ms, p):.2f} h"
                               for n in (1_000, 10_000) for p in (1, 4))
            out.append(f"| {f.timeframe} | {label} | {ms:.1f} | {cells} |")
    out += ["", "Lectura para T93: **el embudo no puede definirse por `requires`**, porque los "
            "agentes más caros son justo los portables (solo `candles`). Hay que definirlo por "
            "costo medido: con los baratos por costo el universo entero cabe en minutos; con el "
            "ciclo completo, no cabe. Y la caché por `(instrumento, marco, hash de datos, "
            "versión del agente)` evita repetir incluso esa etapa cuando no hay vela nueva.", ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Costo por agente y del ciclo (T87)")
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--frames", default=",".join(DEFAULT_FRAMES))
    p.add_argument("--bars", type=int, default=500, help="velas del snapshot (como el ciclo)")
    p.add_argument("--repeat", type=int, default=5)
    p.add_argument("--cheap-ms", type=float, default=CHEAP_MS,
                   help="umbral de «barato por costo» de la etapa del embudo")
    p.add_argument("--out", type=Path, default=Path("reports/t87_agents_cost.md"))
    p.add_argument("--json", type=Path, default=None, help="volcado crudo de las mediciones")
    a = p.parse_args(argv)

    frames = [measure_frame(a.data_dir, tf.strip(), a.symbol, a.bars, a.repeat, a.cheap_ms)
              for tf in a.frames.split(",") if tf.strip()]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(render(frames, a.repeat), encoding="utf-8")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps([asdict(f) for f in frames], indent=1), encoding="utf-8")
    print(f"escrito {a.out}")
    for f in frames:
        print(f"  {f.timeframe}: ciclo {f.cycle_serial_ms:.0f} ms en serie, "
              f"{f.cycle_parallel_ms:.0f} ms en paralelo ({len(f.agents)} agentes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
