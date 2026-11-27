"""Rasgos de la superficie de volatilidad implícita de una toma de opciones (T214). Puro.

Recibe las filas de una toma de Deribit tal como las guarda T213 (`eim/data/options_parse.py`) y
devuelve, sin rellenar nada que falte (lo que no se puede medir queda `None`):

- **σ ATM a 7 y 30 días**: en cada vencimiento, la sonrisa de la IV de la marca con la opción
  fuera del dinero (puts K ≤ F, calls K > F), interpolada en `ln(K/F)` en el forward (`F` =
  subyacente del vencimiento); entre vencimientos, lineal en la varianza total σ²·T. Nunca se
  extrapola. **Pendiente** `ln(σ7²/σ30²)` (> 0: el plazo corto paga más).
- **Sesgo 25Δ** a 30 días, σ(put −25Δ) − σ(call +25Δ) con la delta forward de Black-76 a la IV de
  cada opción (> 0: las puts cuestan más), y **sesgo 90/110**, σ(0,9F) − σ(1,1F); entre
  vencimientos, lineal en el plazo.
- **Prima de varianza por plazo** `ln(σ_T²/σ_real_T²)` si quien llama da la realizada.
- **Calidad**: cada vencimiento usado pasa un contraste (≥ 6 opciones fuera del dinero; cerca del
  dinero, dos lados sin cruzar y con horquilla razonable; σ ATM de la marca a ≤ 2 puntos de la del
  precio medio; varianza total creciente). `ok` si todos pasan, `degradado` si alguno no,
  `no_data` si falta un plazo.

La marca y no el medio para los rasgos: la marca es la superficie completa y suave de cada fila;
el medio solo existe con dos lados y en las alas salta de a un tick (T213: casi todos los
vencimientos tienen alguna mariposa negativa de un tick). El medio **comprueba** la marca cerca
del dinero, donde se miden los rasgos.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from statistics import median

from eim.options.black_scholes import CALL, PUT
from eim.options.implied_vol import NoImpliedVol, implied_vol

SURFACE_VERSION = "1.0.0"
YEAR_MS = 365 * 86_400_000


@dataclass(frozen=True)
class SurfaceParams:
    """Umbrales de la superficie (los mismos que fija el pre-registro de T214)."""

    tenors_days: tuple[int, int] = (7, 30)   # plazo corto y largo de la estructura temporal
    skew_tenor_days: int = 30                # plazo del sesgo 25Δ y 90/110
    min_expiry_days: float = 2.0             # vencimientos más cortos no entran
    min_otm: int = 6                         # opciones fuera del dinero mínimas por vencimiento
    atm_near: int = 2                        # opciones a cada lado del forward para el contraste
    max_mark_gap: float = 0.02               # |σ ATM marca − σ ATM medio| tolerado, en σ
    max_rel_spread: float = 0.25             # horquilla/medio por encima de esto: no cotiza
    delta: float = 0.25                      # delta del sesgo
    moneyness: tuple[float, float] = (0.9, 1.1)


@dataclass
class ExpirySmile:
    """Lo que se lee de un vencimiento."""

    expiry: int
    t_years: float
    forward: float
    n_otm: int
    atm: float | None = None
    rr: float | None = None                  # σ(put −25Δ) − σ(call +25Δ)
    skew_mny: float | None = None            # σ(0,9F) − σ(1,1F)
    mid_atm: float | None = None
    mark_gap: float | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def days(self) -> float:
        return self.t_years * 365.0


@dataclass
class SurfaceFeatures:
    """Rasgos de una toma. `None` = no se pudo medir (nunca se rellena)."""

    status: str                              # "ok" | "degradado" | "no_data"
    taken_ms: int
    n_rows: int
    n_expiries: int
    atm: dict[int, float | None]
    term_slope: float | None
    rr25: float | None
    skew_90_110: float | None
    vrp: dict[int, float | None]
    used: list[ExpirySmile]
    warnings: list[str] = field(default_factory=list)

    def metrics(self) -> dict:
        """Cifras planas y redondeadas para `AgentReport.metrics` y para el informe."""
        short, long_ = sorted(self.atm)
        return {
            "surface_version": SURFACE_VERSION, "surface_status": self.status,
            "taken_ms": self.taken_ms, "n_rows": self.n_rows, "n_expiries": self.n_expiries,
            f"atm_{short}d": _r(self.atm[short]), f"atm_{long_}d": _r(self.atm[long_]),
            "term_slope": _r(self.term_slope), "rr25": _r(self.rr25),
            "skew_90_110": _r(self.skew_90_110),
            **{f"vrp_{k}d": _r(v) for k, v in sorted(self.vrp.items())},
            "expiries_used": [{"expiry_ms": s.expiry, "days": round(s.days, 3),
                               "atm": _r(s.atm), "mid_atm": _r(s.mid_atm),
                               "mark_gap": _r(s.mark_gap), "n_otm": s.n_otm,
                               "issues": list(s.issues)} for s in self.used],
        }


# --- piezas -----------------------------------------------------------------------------------

def _cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _interp(pts: Sequence[tuple[float, float]], x: float) -> float | None:
    """Interpolación lineal en `x` sobre puntos ordenados; `None` fuera del rango."""
    if not pts or x < pts[0][0] or x > pts[-1][0]:
        return None
    for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False):
        if x0 <= x <= x1:
            return y0 if x1 == x0 else y0 + (x - x0) / (x1 - x0) * (y1 - y0)
    return pts[-1][1]


def forward_delta(k: float, sigma: float, t: float, kind: str) -> float:
    """Delta forward de Black-76 con log-moneyness `k = ln(K/F)` (sin descuento: Deribit r = 0)."""
    d1 = (-k + 0.5 * sigma * sigma * t) / (sigma * math.sqrt(t))
    return _cdf(d1) if kind == CALL else _cdf(d1) - 1.0


def _otm(rows: Sequence[Mapping], fwd: float) -> list[tuple[float, float, str]]:
    """(ln K/F, σ marca, tipo) de la opción fuera del dinero en cada precio de ejercicio."""
    seen: dict[float, tuple[float, float, str]] = {}
    for r in rows:
        k_abs, kind, iv = float(r["strike"]), str(r["kind"]), float(r["mark_iv"]) / 100.0
        if iv <= 0 or not ((kind == PUT and k_abs <= fwd) or (kind == CALL and k_abs > fwd)):
            continue
        seen.setdefault(k_abs, (math.log(k_abs / fwd), iv, kind))
    return sorted(seen.values())


def _delta_vol(otm: list[tuple[float, float, str]], t: float, kind: str,
               target: float) -> float | None:
    pts = sorted((forward_delta(k, s, t, kind), s) for k, s, kd in otm if kd == kind)
    return _interp(pts, target)


def _mid_atm(rows: Sequence[Mapping], fwd: float, t: float, p: SurfaceParams,
             issues: list[str]) -> float | None:
    """σ ATM del precio medio con las `atm_near` opciones fuera del dinero a cada lado."""
    below = sorted((r for r in rows if r["kind"] == PUT and float(r["strike"]) <= fwd),
                   key=lambda r: -float(r["strike"]))[:p.atm_near]
    above = sorted((r for r in rows if r["kind"] == CALL and float(r["strike"]) > fwd),
                   key=lambda r: float(r["strike"]))[:p.atm_near]
    pts: list[tuple[float, float]] = []
    crossed = wide = 0
    for r in [*below, *above]:
        bid, ask = r.get("bid"), r.get("ask")
        if bid is None or ask is None:
            continue
        if bid > ask:
            crossed += 1
            continue
        mid = 0.5 * (bid + ask)
        if mid <= 0 or (ask - bid) / mid > p.max_rel_spread:
            wide += 1
            continue
        k_abs, und = float(r["strike"]), float(r["underlying"])
        try:
            iv = implied_vol(mid * und, fwd, k_abs, t, float(r.get("rate") or 0.0),
                             str(r["kind"]), b=0.0)
        except NoImpliedVol:
            continue
        pts.append((math.log(k_abs / fwd), iv))
    if crossed:
        issues.append(f"{crossed} cotización(es) cruzada(s) cerca del dinero")
    if wide:
        issues.append(f"{wide} horquilla(s) > {p.max_rel_spread:.0%} cerca del dinero")
    pts.sort()
    if not pts or pts[0][0] > 0 or pts[-1][0] < 0:
        issues.append("sin precio medio a los dos lados del forward")
        return None
    return _interp(pts, 0.0)


def expiry_smile(rows: Sequence[Mapping], taken_ms: int,
                 p: SurfaceParams | None = None) -> ExpirySmile:
    """Sonrisa de un vencimiento (todas las filas del mismo `expiry`)."""
    p = p or SurfaceParams()
    expiry = int(rows[0]["expiry"])
    t = (expiry - taken_ms) / YEAR_MS
    fwd = median(float(r["underlying"]) for r in rows)
    if t <= 0:
        return ExpirySmile(expiry, t, fwd, 0, issues=["vencimiento ya pasado"])
    otm = _otm(rows, fwd)
    sm = ExpirySmile(expiry, t, fwd, len(otm))
    pts = [(k, s) for k, s, _ in otm]
    sm.atm = _interp(pts, 0.0)
    lo, hi = (_interp(pts, math.log(m)) for m in p.moneyness)
    sm.skew_mny = None if lo is None or hi is None else lo - hi
    put, call = _delta_vol(otm, t, PUT, -p.delta), _delta_vol(otm, t, CALL, p.delta)
    sm.rr = None if put is None or call is None else put - call
    if len(otm) < p.min_otm:
        sm.issues.append(f"solo {len(otm)} opciones fuera del dinero (< {p.min_otm})")
    sm.mid_atm = _mid_atm(rows, fwd, t, p, sm.issues)
    if sm.atm is not None and sm.mid_atm is not None:
        sm.mark_gap = abs(sm.atm - sm.mid_atm)
        if sm.mark_gap > p.max_mark_gap:
            sm.issues.append(f"la marca se aparta {sm.mark_gap * 100:.1f} puntos del medio")
    return sm


def _bracket(smiles: list[ExpirySmile], t: float) -> tuple[ExpirySmile, ExpirySmile] | None:
    for a, b in zip(smiles, smiles[1:], strict=False):
        if a.t_years <= t <= b.t_years:
            return a, b
    return None


def _total_var(a: ExpirySmile, b: ExpirySmile, t: float) -> float:
    wa, wb = a.atm * a.atm * a.t_years, b.atm * b.atm * b.t_years    # type: ignore[operator]
    w = wa if b.t_years == a.t_years else wa + (t - a.t_years) / (b.t_years - a.t_years) * (wb - wa)
    return math.sqrt(w / t) if w > 0 else math.nan


def _lin(a: float | None, b: float | None, ta: float, tb: float, t: float) -> float | None:
    if a is None or b is None:
        return None
    return a if tb == ta else a + (t - ta) / (tb - ta) * (b - a)


def surface_features(rows: Sequence[Mapping], taken_ms: int,
                     realized: Mapping[int, float | None] | None = None,
                     p: SurfaceParams | None = None) -> SurfaceFeatures:
    """Rasgos de una toma completa. `realized` = σ realizada anualizada por plazo (días)."""
    p = p or SurfaceParams()
    groups: dict[int, list[Mapping]] = {}
    for r in rows:
        groups.setdefault(int(r["expiry"]), []).append(r)
    smiles = [expiry_smile(g, taken_ms, p) for _, g in sorted(groups.items())]
    usable = [s for s in smiles if s.days >= p.min_expiry_days and s.atm is not None]
    warn: list[str] = []
    atm: dict[int, float | None] = {}
    used: dict[int, ExpirySmile] = {}
    for days in p.tenors_days:
        t = days / 365.0
        br = _bracket(usable, t)
        if br is None:
            atm[days] = None
            warn.append(f"sin vencimientos que rodeen {days} días: σ ATM {days} d sin medir")
            continue
        a, b = br
        used |= {a.expiry: a, b.expiry: b}
        if b.atm * b.atm * b.t_years < a.atm * a.atm * a.t_years:          # type: ignore[operator]
            a.issues.append("varianza total decreciente con el plazo (arbitraje de calendario)")
        v = _total_var(a, b, t)
        atm[days] = None if math.isnan(v) else v
    t_sk = p.skew_tenor_days / 365.0
    br = _bracket(usable, t_sk)
    rr = mny = None
    if br is not None:
        a, b = br
        used |= {a.expiry: a, b.expiry: b}
        rr = _lin(a.rr, b.rr, a.t_years, b.t_years, t_sk)
        mny = _lin(a.skew_mny, b.skew_mny, a.t_years, b.t_years, t_sk)
    if rr is None:
        warn.append(f"sesgo 25Δ a {p.skew_tenor_days} d sin medir (la sonrisa no llega a ±25Δ)")
    short, long_ = p.tenors_days
    slope = (2.0 * math.log(atm[short] / atm[long_])
             if atm.get(short) and atm.get(long_) else None)
    vrp: dict[int, float | None] = {}
    for days in p.tenors_days:
        rv = (realized or {}).get(days)
        vrp[days] = (2.0 * math.log(atm[days] / rv) if atm.get(days) and rv and rv > 0
                     else None)
    used_l = [used[k] for k in sorted(used)]
    if any(v is None for v in atm.values()):
        status = "no_data"
    elif any(s.issues for s in used_l):
        status = "degradado"
        warn += [f"vencimiento {s.days:.1f} d: {'; '.join(s.issues)}" for s in used_l if s.issues]
    else:
        status = "ok"
    return SurfaceFeatures(status, taken_ms, len(rows), len(smiles), atm, slope, rr, mny, vrp,
                           used_l, warn)


def _r(x: float | None, nd: int = 6) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), nd)
