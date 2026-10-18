"""Panel histórico de reportes de agentes (T44): sesgo, confianza y estado por vela, sin futuro.

Reproduce lo que `build_snapshot` daría a cada `asof` (velas, marcos vecinos, funding, OI,
long/short y base hasta `asof`), pero leyendo el almacén UNA vez y recortando en memoria
(`build_snapshot` relee Parquet en cada llamada: ≈1,2 s). Calendario, líderes, arbitraje y
microestructura no tienen historia point-in-time anterior a su captura (T36/T39/T41): en el
panel quedan en None, igual que los vería el sistema a esa fecha → sus agentes dan `no_data`.

Lo usa `agents_marginal` (correlación entre reportes y contribución marginal en la síntesis).
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from eim.agents.registry import default_registry
from eim.core import AgentReport, Candle, MarketSnapshot
from eim.data.store import Store
from eim.data.timeframes import TF_MS, tf_ms

# `plan` deriva de structure/levels (fuera de la síntesis) y es lo caro; `context` es un LLM
# sin titulares históricos; `arbitrage` no tiene historia de libros y no es direccional.
SKIP = frozenset({"plan", "context", "arbitrage"})
SNAP_BARS = 500                          # = Settings.snapshot_bars
SERIES = ("open_interest", "long_short_ratio", "basis")
COLS = ["asof", "agent", "bias", "conf", "status", "regime"]


class PanelData:
    """Almacén de un símbolo/marco en memoria; `snapshot(asof)` ≡ `build_snapshot` sin I/O."""

    def __init__(self, store: Store, symbol: str, timeframe: str, n: int = SNAP_BARS) -> None:
        self.symbol, self.tf, self.n, self.step = symbol, timeframe, n, tf_ms(timeframe)
        self.candles = store.read_candles(symbol, timeframe)
        self.t = [c.t for c in self.candles]
        self.src = store.source("candles", symbol, timeframe) or "desconocida"
        ladder = sorted(TF_MS, key=TF_MS.__getitem__)
        i = ladder.index(timeframe)
        self.nb: dict[str, tuple[list[Candle], list[int], str]] = {}
        for tf in ladder[max(0, i - 1):i] + ladder[i + 1:i + 2]:
            cs = store.read_candles(symbol, tf)
            if cs:
                self.nb[tf] = (cs, [c.t for c in cs],
                               store.source("candles", symbol, tf) or "desconocida")
        self.series: dict[str, tuple[list, list[int], str]] = {}
        for name, tf in (("funding", "-"), *((s, timeframe) for s in SERIES)):
            rows = (store.read_series(name, symbol) if tf == "-"
                    else store.read_series(name, symbol, timeframe))
            if rows:
                self.series[name] = (rows, [r[0] for r in rows],
                                     store.source(name, symbol, tf) or "desconocida")

    def snapshot(self, asof: int) -> MarketSnapshot:
        k = bisect_right(self.t, asof - self.step)          # velas con t ≤ asof − step
        cs = self.candles[max(0, k - self.n):k]
        sources: dict[str, str] = {}
        coverage: dict[str, tuple[int, int]] = {}
        extra: dict[str, list | None] = {"funding": None, **{s: None for s in SERIES}}
        tfs = None
        if cs:
            lo, hi = cs[0].t, cs[-1].t
            sources["candles"], coverage["candles"] = self.src, (lo, hi)
            end = min(asof, hi + self.step)
            for name, (rows, ts, src) in self.series.items():
                sel = rows[bisect_left(ts, lo):bisect_left(ts, end)]   # [lo, end) como el almacén
                if sel:
                    extra[name] = sel
                    sources[name], coverage[name] = src, (sel[0][0], sel[-1][0])
            tfs = {}
            for tf, (ncs, nts, src) in self.nb.items():
                j = bisect_right(nts, asof - TF_MS[tf])
                sel = ncs[max(0, j - self.n):j]
                if sel:
                    tfs[tf] = sel
                    sources[f"candles_{tf}"] = src
                    coverage[f"candles_{tf}"] = (sel[0].t, sel[-1].t)
        return MarketSnapshot(
            symbol=self.symbol, timeframe=self.tf, candles=cs, funding=extra["funding"],
            open_interest=extra["open_interest"], long_short_ratio=extra["long_short_ratio"],
            basis=extra["basis"], candles_tf=tfs or None, asof=asof, sources=sources,
            coverage=coverage)


def rows_of(asof: int, reports: list[AgentReport]) -> list[tuple]:
    reg = next((r.metrics.get("regime") for r in reports
                if r.agent_id == "regime" and r.status == "ok"), None)
    return [(asof, r.agent_id, float(r.bias), float(r.confidence), r.status, reg)
            for r in reports]


_W: tuple[PanelData, list] | None = None


def _init(root: str, symbol: str, timeframe: str) -> None:
    global _W
    agents = [a for a in default_registry().latest() if a.id not in SKIP]
    _W = (PanelData(Store(root), symbol, timeframe), agents)


def _chunk(asofs: list[int]) -> list[tuple]:
    assert _W is not None
    data, agents = _W
    out: list[tuple] = []
    for asof in asofs:
        snap = data.snapshot(asof)
        if len(snap.candles) < SNAP_BARS // 2 or snap.candles[-1].t + data.step != asof:
            continue                     # sin la vela que cierra en `asof` no hay decisión
        reps = []
        for a in agents:
            try:
                reps.append(a.run(snap))
            except Exception as exc:     # un agente que falla cuenta como sin datos
                reps.append(AgentReport(agent_id=a.id, version=a.version, asof=asof, bias=0,
                                        confidence=0, horizon_bars=1, status="no_data",
                                        warnings=[f"{type(exc).__name__}: {exc}"]))
        out.extend(rows_of(asof, reps))
    return out


def compute_panel(root: str | Path, symbol: str, timeframe: str, asofs: list[int],
                  workers: int = 1, chunk: int = 50) -> pd.DataFrame:
    """Reportes de los agentes (salvo `SKIP`) en cada `asof`; en paralelo si `workers > 1`."""
    parts = [asofs[i:i + chunk] for i in range(0, len(asofs), chunk)]
    rows: list[tuple] = []
    if workers <= 1:
        _init(str(root), symbol, timeframe)
        for p in parts:
            rows.extend(_chunk(p))
    else:
        with ProcessPoolExecutor(workers, initializer=_init,
                                 initargs=(str(root), symbol, timeframe)) as pool:
            for got in pool.map(_chunk, parts):
                rows.extend(got)
    return pd.DataFrame(rows, columns=COLS).sort_values(["asof", "agent"], ignore_index=True)


def panel_path(root: str | Path, symbol: str, timeframe: str, step: int) -> Path:
    return Path(root) / "cache" / "agent_panel" / f"{symbol}_{timeframe}_s{step}.parquet"


def load_or_compute(root: str | Path, symbol: str, timeframe: str, step: int, workers: int,
                    refresh: bool = False) -> pd.DataFrame:
    """Panel cada `step` velas sobre todo el histórico del almacén (caché en `data/cache`)."""
    path = panel_path(root, symbol, timeframe, step)
    if path.exists() and not refresh:
        return pd.read_parquet(path)
    data = PanelData(Store(root), symbol, timeframe)
    bar = data.step
    asofs = [t + bar for t in data.t[SNAP_BARS::step]]
    df = compute_panel(root, symbol, timeframe, asofs, workers)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df
