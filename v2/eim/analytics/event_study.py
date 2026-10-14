"""Estudio de eventos del calendario (T37): cuánto mueven BTC/ETH las publicaciones macro.

Para cada evento se mide, en velas de 15 m, la ventana [−60 min, +4 h] alrededor de la hora
de publicación `t0`:
- rango realizado (máx − mín) / apertura antes (−60…0) y después (0…+4 h, y sub-ventanas);
- retorno logarítmico (con signo) y su valor absoluto;
- rango de cada vela (−4…+15) para localizar dónde empieza y termina el efecto.

"Normal" = la MISMA hora UTC en días hábiles cercanos (hasta `max_lookback_days` hacia atrás)
sin eventos medio/alto en la ventana: así se descuenta la estacionalidad intradía (la apertura
de Wall Street a las 13:30/14:30 UTC ya es volátil por sí sola). La medida de cada evento es el
log-cociente frente a la mediana de sus controles; se reporta la distribución completa, el
tamaño de muestra y un p-valor bootstrap (media del log-cociente = 0) corregido por Holm.
Funciones puras sobre arrays: el I/O vive en `event_report.py`.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from eim.backtest.edge import holm
from eim.core import Candle

MIN_MS = 60_000
DAY_MS = 1440 * MIN_MS
# Nombre exacto de la publicación → tipo corto del estudio.
EVENT_TYPES: dict[str, str] = {
    "Decisión de tipos FOMC": "FOMC",
    "Consumer Price Index": "CPI",
    "Employment Situation": "NFP",
    "Personal Income and Outlays": "PCE",
    "Gross Domestic Product": "GDP",
    "Producer Price Index": "PPI",
    "Job Openings and Labor Turnover Survey": "JOLTS",
    "Employment Cost Index": "ECI",
    "U.S. International Trade in Goods and Services": "Comercio",
    "Vencimiento futuros trimestrales Binance (BTC/ETH)": "Vencimiento",
}
# Ventanas medidas (minutos relativos a t0, [a, b)).
WINDOWS: dict[str, tuple[int, int]] = {
    "pre_60": (-60, 0), "post_15": (0, 15), "post_60": (0, 60), "post_240": (0, 240)}


@dataclass(frozen=True)
class StudyParams:
    bar_min: int = 15
    pre_bars: int = 4              # −60 min
    post_bars: int = 16            # +4 h
    n_controls: int = 20           # días de control por evento
    max_lookback_days: int = 60
    guard_min: int = 240           # un control no puede tener eventos medio/alto a ±4 h
    n_boot: int = 4000
    seed: int = 37
    alpha: float = 0.05
    min_ratio: float = 1.25        # efecto mínimo relevante (rango ×1.25 frente a lo normal)
    min_n: int = 12                # por debajo: muestra insuficiente para fijar ventana


@dataclass
class Bars:
    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    lo: np.ndarray
    c: np.ndarray
    index: dict[int, int] = field(default_factory=dict)

    @classmethod
    def from_candles(cls, candles: Sequence[Candle]) -> Bars:
        t = np.array([c.t for c in candles], dtype=np.int64)
        b = cls(t, *(np.array([getattr(c, k) for c in candles], dtype=float)
                     for k in ("o", "h", "l", "c")))
        b.index = {int(x): i for i, x in enumerate(t)}
        return b


def _segment(bars: Bars, t0: int, p: StudyParams) -> np.ndarray | None:
    """Índices de las velas −pre…+post alrededor de t0 (None si falta alguna)."""
    step = p.bar_min * MIN_MS
    i0 = bars.index.get(t0 - t0 % step)
    if i0 is None or i0 - p.pre_bars < 0 or i0 + p.post_bars > len(bars.t):
        return None
    idx = np.arange(i0 - p.pre_bars, i0 + p.post_bars)
    if bars.t[idx[-1]] - bars.t[idx[0]] != (len(idx) - 1) * step:
        return None  # hueco dentro de la ventana
    return idx


def window_metrics(bars: Bars, t0: int, p: StudyParams) -> dict | None:
    """Rango, retorno y rango por vela de la ventana alrededor de t0."""
    idx = _segment(bars, t0, p)
    if idx is None:
        return None
    o, h, lo, c = bars.o[idx], bars.h[idx], bars.lo[idx], bars.c[idx]
    out: dict = {"bar_range": (h - lo) / o}
    for name, (a, b) in WINDOWS.items():
        s, e = p.pre_bars + a // p.bar_min, p.pre_bars + b // p.bar_min
        base = o[s]
        out[f"range_{name}"] = float((h[s:e].max() - lo[s:e].min()) / base)
        out[f"ret_{name}"] = float(math.log(c[e - 1] / base))
    return out


def control_times(t0: int, blocked: np.ndarray, p: StudyParams) -> list[int]:
    """Misma hora UTC en días hábiles previos sin eventos medio/alto a ±guard_min."""
    out: list[int] = []
    guard = p.guard_min * MIN_MS
    for k in range(1, p.max_lookback_days + 1):
        tc = t0 - k * DAY_MS
        if datetime.fromtimestamp(tc / 1000, tz=UTC).weekday() >= 5:
            continue
        j = np.searchsorted(blocked, tc - guard)
        if j < len(blocked) and blocked[j] <= tc + guard:
            continue
        out.append(tc)
        if len(out) == p.n_controls:
            break
    return out


def measure_event(bars: Bars, t0: int, blocked: np.ndarray, p: StudyParams) -> dict | None:
    """Log-cocientes evento / mediana de controles (rango por ventana y por vela)."""
    ev = window_metrics(bars, t0, p)
    if ev is None:
        return None
    ctl = [m for tc in control_times(t0, blocked, p) if (m := window_metrics(bars, tc, p))]
    if len(ctl) < max(5, p.n_controls // 2):
        return None
    row: dict = {"t0": t0, "n_controls": len(ctl)}
    for name in WINDOWS:
        base = float(np.median([m[f"range_{name}"] for m in ctl]))
        row[f"lr_{name}"] = math.log(ev[f"range_{name}"] / base) if base > 0 else math.nan
        row[f"ret_{name}"] = ev[f"ret_{name}"]
    base_bar = np.median(np.array([m["bar_range"] for m in ctl]), axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        row["lr_bars"] = np.log(ev["bar_range"] / base_bar)
    return row


# --- estadística ------------------------------------------------------------
def bootstrap_mean(x: Iterable[float], n_boot: int, seed: int) -> dict:
    """Media, IC 95 % y p bilateral (bootstrap centrado: H0 media = 0)."""
    a = np.array([v for v in x if math.isfinite(v)], dtype=float)
    n = len(a)
    if n < 3:
        return {"n": n, "mean": math.nan, "ci": (math.nan, math.nan), "p": math.nan}
    rng = np.random.default_rng(seed)
    boot = a[rng.integers(0, n, size=(n_boot, n))].mean(axis=1)
    m = float(a.mean())
    extreme = int(np.sum(np.abs(boot - m) >= abs(m)))
    return {"n": n, "mean": m, "ci": (float(np.quantile(boot, 0.025)),
                                      float(np.quantile(boot, 0.975))),
            "p": (extreme + 1) / (n_boot + 1)}


def distribution(x: Iterable[float]) -> dict:
    a = np.array([v for v in x if math.isfinite(v)], dtype=float)
    if not len(a):
        return {"n": 0}
    q = np.quantile(a, [0.1, 0.25, 0.5, 0.75, 0.9])
    return {"n": len(a), "mean": float(a.mean()), "sd": float(a.std(ddof=1)) if len(a) > 1
            else math.nan, "p10": q[0], "p25": q[1], "p50": q[2], "p75": q[3], "p90": q[4],
            "frac_pos": float((a > 0).mean())}


def by_surprise(rows: list[dict], surprise: dict[int, float], key: str = "lr_post_60") -> dict:
    """Dispersión según |sorpresa| por terciles (solo eventos con sorpresa conocida)."""
    pts = [(abs(surprise[r["t0"]]), r[key]) for r in rows
           if r["t0"] in surprise and math.isfinite(r[key])]
    if len(pts) < 6:
        return {"n": len(pts), "available": False}
    pts.sort()
    thirds = np.array_split(np.array(pts), 3)
    return {"n": len(pts), "available": True,
            "terciles": [{"abs_surprise_max": float(t[:, 0].max()), "n": len(t),
                          "mean_lr": float(t[:, 1].mean()), "sd_lr": float(t[:, 1].std())}
                         for t in thirds]}


# --- estudio completo ---------------------------------------------------------
def study_type(bars: Bars, times: Sequence[int], blocked: np.ndarray, p: StudyParams) -> dict:
    """Todas las medidas de un tipo de evento sobre un activo (sin corrección múltiple)."""
    rows = [r for t in sorted(set(times)) if (r := measure_event(bars, t, blocked, p))]
    out: dict = {"n_events": len(times), "n": len(rows), "rows": rows, "windows": {}}
    for i, name in enumerate(WINDOWS):
        lr = [r[f"lr_{name}"] for r in rows]
        out["windows"][name] = {
            "range": distribution(lr) | {"ratio_p50": math.exp(np.median(lr)) if lr else math.nan},
            "boot": bootstrap_mean(lr, p.n_boot, p.seed + i),
            "ret": distribution(r[f"ret_{name}"] for r in rows),
            "ret_boot": bootstrap_mean((r[f"ret_{name}"] for r in rows), p.n_boot, p.seed + 50 + i),
        }
    bars_lr = np.array([r["lr_bars"] for r in rows]) if rows else np.empty((0, 0))
    out["bars"] = [bootstrap_mean(bars_lr[:, k], p.n_boot, p.seed + 100 + k) | {
        "offset_min": (k - p.pre_bars) * p.bar_min} for k in range(bars_lr.shape[1])]
    return out


def adjust_all(results: dict[str, dict[str, dict]], alpha: float) -> None:
    """Holm sobre todas las pruebas de ventana (tipo × activo × ventana), sobre las de dirección
    (retorno 0…+4 h, tipo × activo) y sobre las velas de cada tipo × activo. In situ."""
    flat = {f"{a}|{ty}|{w}": res["windows"][w]["boot"]["p"]
            for a, by in results.items() for ty, res in by.items() for w in WINDOWS
            if math.isfinite(res["windows"][w]["boot"]["p"])}
    adj = holm(flat)
    rflat = {f"{a}|{ty}": res["windows"]["post_240"]["ret_boot"]["p"]
             for a, by in results.items() for ty, res in by.items()
             if math.isfinite(res["windows"]["post_240"]["ret_boot"]["p"])}
    radj = holm(rflat)
    for a, by in results.items():
        for ty, res in by.items():
            for w in WINDOWS:
                b = res["windows"][w]["boot"]
                b["p_holm"] = adj.get(f"{a}|{ty}|{w}", math.nan)
                b["significant"] = bool(b["p_holm"] <= alpha)
            rb = res["windows"]["post_240"]["ret_boot"]
            rb["p_holm"] = radj.get(f"{a}|{ty}", math.nan)
            rb["significant"] = bool(rb["p_holm"] <= alpha)
            bp = {str(k): b["p"] for k, b in enumerate(res["bars"]) if math.isfinite(b["p"])}
            badj = holm(bp)
            for k, b in enumerate(res["bars"]):
                b["p_holm"] = badj.get(str(k), math.nan)
                b["significant"] = bool(b["p_holm"] <= alpha)


def recommend(res: dict, p: StudyParams) -> dict:
    """Ventana de pausa mínima que cubre (a) las velas contiguas a t0 (hacia atrás y hacia
    delante) con rango significativamente elevado y (b) la ventana agregada −60…0 si es
    significativa (efecto previo difuso, sin vela aislada). Ambas con Holm y cociente ≥
    min_ratio. Las ventanas agregadas posteriores NO alargan el post: su rango incluye el pico
    de la primera vela y no prueban que el efecto dure."""
    if res["n"] < p.min_n:
        return {"status": "insuficiente", "pre": None, "post": None, "n": res["n"]}

    def hot(b: dict) -> bool:
        return b["significant"] and b["mean"] > 0 and math.exp(b["mean"]) >= p.min_ratio

    bars = res["bars"]
    pre = 0
    while pre < p.pre_bars and hot(bars[p.pre_bars - 1 - pre]):
        pre += 1
    post = 0
    while p.pre_bars + post < len(bars) and hot(bars[p.pre_bars + post]):
        post += 1
    pre_m, post_m = pre * p.bar_min, post * p.bar_min
    if hot(res["windows"]["pre_60"]["boot"]):
        pre_m = max(pre_m, -WINDOWS["pre_60"][0])
    return {"status": "efecto" if pre_m or post_m else "sin_efecto", "n": res["n"],
            "pre": pre_m, "post": post_m}


def run_study(bars_by_asset: dict[str, Bars], events: Sequence[tuple[int, str, str]],
              p: StudyParams | None = None) -> dict:
    """`events` = (t_utc, nombre, impacto). Devuelve resultados por activo y tipo + ventanas."""
    p = p or StudyParams()
    blocked = np.array(sorted({t for t, _n, imp in events if imp in ("medio", "alto")}),
                       dtype=np.int64)
    by_type: dict[str, list[int]] = {}
    for t, name, _imp in events:
        if (ty := EVENT_TYPES.get(name)) is not None:
            by_type.setdefault(ty, []).append(t)
    results = {a: {ty: study_type(b, ts, blocked, p) for ty, ts in by_type.items()}
               for a, b in bars_by_asset.items()}
    adjust_all(results, p.alpha)
    rec: dict[str, dict] = {}
    for ty in by_type:
        per = {a: recommend(results[a][ty], p) for a in results}
        ok = [r for r in per.values() if r["status"] != "insuficiente"]
        rec[ty] = {"per_asset": per,
                   "pre": max((r["pre"] for r in ok), default=None),
                   "post": max((r["post"] for r in ok), default=None),
                   "status": ("insuficiente" if not ok else
                              "efecto" if any(r["status"] == "efecto" for r in ok)
                              else "sin_efecto")}
    return {"params": p, "results": results, "recommended": rec}
