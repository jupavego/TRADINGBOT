"""Control, sustitutas, regresión contra T137 y línea base de T139. Puro.

**El nulo** es el de T134 y T137: los retornos reales de 1 min barajados, que conservan su
distribución y destruyen la dependencia. Sobre esas series se sortean entradas al azar con la
geometría relativa de cada clave y su mismo n: el bruto de cada serie dice cuánto da el azar con esa
muestra, y por eso una clave no se compara con una cifra fija.

**La regresión** reproduce con este camino lo que T137 publicó de `control_aleatorio@1h`. Si no
coincide, lo que aquí se mide no es lo que se midió allí.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import numpy as np

from eim.core import Candle
from eim.data.timeframes import tf_ms
from eim.paper.catalog import CATALOG, generate_ideas
from eim.paper.engine import Path, run_shadow, simulate
from eim.paper.exits import surrogate
from eim.paper.ideas import Idea
from eim.paper.params import ExecParams
from eim.paper.trend import HtfTrend
from eim.validation.entry_control import control_geometry, random_ideas
from eim.validation.evidence import cost_r
from eim.validation.hypotheses.pipeline import truncate_path
from eim.validation.hypotheses.prereg import Prereg
from eim.validation.hypotheses.rules import Series, minimal_ctxs
from eim.validation.lineage import iso_ms
from eim.validation.stats import rng_for


def surrogate_paths(fine_c: np.ndarray, pr: Prereg, px0: float, t0: int,
                    log: Callable[[str], None] | None = None) -> list[Path]:
    """Las series sustitutas, una vez: todas las claves se miden sobre las mismas."""
    c = pr.control
    out = []
    for s in range(c.surrogates):
        rng = rng_for(pr.seed, f"{pr.version}|sur|{s}")
        coarse, _ = surrogate.surrogate_of(fine_c, rng, bars=c.bars, px0=px0, t0=t0,
                                           block=c.block_minutes)
        if len(coarse.t):
            out.append(coarse)
        if log and (s + 1) % 5 == 0:
            log(f"  sustitutas {s + 1}/{c.surrogates}")
    return out


def _gross(o) -> float | None:
    return float(o.r) + cost_r(o) if o.status == "CERRADA" and o.r is not None else None


def null_gross(paths: Sequence[Path], ideas: Sequence[Idea], n: int, ep: ExecParams, pr: Prereg,
               sid: str) -> list[float]:
    """Bruto medio de `n` entradas al azar con la geometría de `ideas`, en cada sustituta."""
    g = control_geometry(ideas)
    if g is None or n <= 0:
        return []
    strategy, tf = sid.split("@")
    size = min(n, pr.control.max_ideas)
    out = []
    for s, path in enumerate(paths):
        got = [x for x in (_gross(simulate(i, path, ep))
                           for i in random_ideas(path, s, size, g, strategy, tf))
               if x is not None]
        if got:
            out.append(float(np.mean(got)))
    return out


def null_summary(null: Sequence[float], q: float) -> dict:
    a = np.asarray(null, dtype=float)
    if not len(a):
        return {"surrogates": 0, "mean": None, "sd": None, "p95": None}
    return {"surrogates": int(len(a)), "mean": float(a.mean()),
            "sd": float(a.std(ddof=1)) if len(a) > 1 else None, "p95": float(np.quantile(a, q))}


def control_verdict(gross: float | None, n: int, null: Sequence[float], alpha: float) -> dict:
    """El control en verde: entradas al azar que no destacan sobre sus sustitutas."""
    if gross is None or n == 0 or not len(null):
        return {"ok": None, "gross": gross, "n": n, "p": None, "reason": "sin muestra"}
    res = surrogate.verdict(gross, list(null), alpha)
    return {"ok": bool(res["ok"]), "gross": gross, "n": n, "p": res["p_one_sided"],
            "null_mean": res["null_mean"], "null_sd": res["null_sd"]}


def catalog_subset(ids: Sequence[str] | None = None, families: Sequence[str] | None = None) -> dict:
    """Parte del catálogo vigente: el control y las estrategias que solo piden velas."""
    return {k: v for k, v in CATALOG.items()
            if (ids is not None and k in ids) or (families is not None and v.family in families)}


def catalog_ideas(s: Series, candles_htf: Sequence[Candle] | None, ep: ExecParams, symbol: str,
                  catalog: Mapping, ctxs: Sequence[dict] | None = None) -> list[Idea]:
    """Ideas de parte del catálogo con contextos mínimos y la tendencia del marco mayor."""
    spec = ep.htf.get(s.tf)
    htf = None
    if spec and candles_htf is not None:
        htf = HtfTrend(candles_htf, tf_ms(spec[0]), spec[1], spec[2]).at
    return generate_ideas(minimal_ctxs(s) if ctxs is None else ctxs, s.candles, symbol, s.bar_ms,
                          origin_of=lambda _c: "backtest", catalog=dict(catalog), timeframe=s.tf,
                          htf=htf, exec_params=ep)


def gross_of(ideas: Sequence[Idea], path: Path, ep: ExecParams, keep: Callable[[Idea], bool]
             ) -> tuple[float | None, int]:
    """Bruto medio y n de la sombra de unas ideas, en las decisiones que `keep` acepta."""
    got = [x for x in (_gross(o) for o in run_shadow(ideas, path, ep) if keep(o.idea))
           if x is not None]
    return (float(np.mean(got)) if got else None, len(got))


def regression(stored: Sequence[dict], s: Series, path: Path, ep: ExecParams, pr: Prereg) -> dict:
    """`control_aleatorio@1h` frente a lo publicado por T137, con dos caminos.

    Con los contextos guardados prueba el camino y el motor. Con los mínimos, en los mismos
    instantes, prueba además que el ATR de T139 es el de los contextos: es lo que pide el
    pre-registro, y lo que permite usar la regla antes de 2023, donde no hay contextos.
    """
    rg = pr.regression
    cut = truncate_path(path, iso_ms(rg.asof))
    start = iso_ms(rg.from_)
    cat = catalog_subset(ids=(rg.strategy.split("@")[0],))

    def keep(i: Idea) -> bool:
        return i.t >= start

    mine = {c["t"]: c for c in minimal_ctxs(s)}
    ats = [c["t"] for c in stored]
    missing = [t for t in ats if t not in mine]
    minimal = [mine[t] for t in ats if t in mine]
    raw = [{"t": c["t"], "close": c["close"], "atr": c["atr"], "regime": None} for c in stored]
    a_gross, a_n = gross_of(catalog_ideas(s, None, ep, pr.symbol, cat, raw), cut, ep, keep)
    b_gross, b_n = gross_of(catalog_ideas(s, None, ep, pr.symbol, cat, minimal), cut, ep, keep)
    diffs = np.array([abs(mine[c["t"]]["atr"] - c["atr"]) / c["atr"] for c in stored
                      if c["t"] in mine and mine[c["t"]]["atr"] and c.get("atr")], dtype=float)
    tol = rg.tolerance_r

    def ok(g: float | None, n: int) -> bool:
        return g is not None and n == rg.n and abs(g - rg.gross_r) <= tol
    return {"want": {"n": rg.n, "gross_r": rg.gross_r},
            "stored": {"n": a_n, "gross_r": a_gross, "ok": ok(a_gross, a_n)},
            "minimal": {"n": b_n, "gross_r": b_gross, "ok": ok(b_gross, b_n)},
            "contexts": len(stored), "missing_bars": len(missing),
            "atr_rel_diff_median": float(np.median(diffs)) if len(diffs) else None,
            "atr_rel_diff_max": float(diffs.max()) if len(diffs) else None}
