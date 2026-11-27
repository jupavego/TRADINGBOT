"""Control placebo del escáner (T95, entregable 4): ¿cuántos «hallazgos» salen solo por azar?

El mismo escáner —etapa 3, lista corta, agentes elegibles, síntesis, proyección y ranking— corre
sobre el universo real y sobre **réplicas sin estructura temporal** del mismo universo:

- `permuted` (por defecto): se permutan **las mismas fechas para todos los instrumentos a la vez**
  (cada vela con su forma relativa al cierre anterior, su volumen y su flujo comprador). Conserva
  la volatilidad, la distribución y la correlación contemporánea de cada par; destruye tendencia,
  momentum y dependencia temporal, que es justo lo que el escáner dice detectar.
- `gaussian`: rendimientos normales con la misma σ por instrumento y la misma matriz de
  correlación (estimada por pares), sin deriva; volumen permutado dentro de cada instrumento.

En una réplica todo hallazgo es falso por construcción. El **umbral de prioridad** del panel es el
cuantil (1 − α) del **máximo** de prioridad por réplica: con él, en el (1 − α) de los universos
sin estructura el panel no mostraría nada. Con ese umbral se cuentan los hallazgos reales, los
falsos esperados por pasada (estimación de la tasa de falsos descubrimientos) y un p global de
«el mejor hallazgo real supera al mejor del azar» (`placebo_eval.py`). Puro.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace

import numpy as np

from eim.core import Candle
from eim.instruments.models import Instrument
from eim.scanner import rank, screen
from eim.scanner.panel import Panel, row_hash

FIELDS = ("o", "h", "l", "c", "v", "tb")
MIN_OVERLAP = 30


@dataclass(frozen=True)
class Stack:
    """Velas del universo alineadas a la derecha (última columna = última vela cerrada)."""

    ids: tuple[str, ...]
    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray  # noqa: E741
    c: np.ndarray
    v: np.ndarray
    tb: np.ndarray            # flujo comprador (NaN si la fuente no lo trae)
    n: np.ndarray

    @property
    def width(self) -> int:
        return int(self.c.shape[1])


def stack(series: Mapping[str, Sequence[Candle]], width: int) -> Stack:
    ids = tuple(sorted(series))
    S = len(ids)
    t = np.zeros((S, width), np.int64)
    m = {f: np.full((S, width), np.nan) for f in FIELDS}
    n = np.zeros(S, np.int64)
    for i, iid in enumerate(ids):
        cs = list(series[iid])[-width:]
        k = len(cs)
        n[i] = k
        if not k:
            continue
        t[i, width - k:] = [x.t for x in cs]
        for f, attr in zip(FIELDS, ("o", "h", "l", "c", "v", "taker_buy_v"), strict=True):
            m[f][i, width - k:] = [np.nan if getattr(x, attr) is None else getattr(x, attr)
                                   for x in cs]
    return Stack(ids, t, m["o"], m["h"], m["l"], m["c"], m["v"], m["tb"], n)


def candles_of(s: Stack, i: int) -> list[Candle]:
    a = s.width - int(s.n[i])
    out = []
    for j in range(a, s.width):
        tb = s.tb[i, j]
        out.append(Candle(t=int(s.t[i, j]), o=float(s.o[i, j]), h=float(s.h[i, j]),
                          l=float(s.l[i, j]), c=float(s.c[i, j]), v=float(s.v[i, j]),
                          taker_buy_v=None if not np.isfinite(tb) else float(tb)))
    return out


def to_panel(s: Stack, k: int) -> Panel:
    """Las últimas `k` velas en el formato de la etapa 3 (`panel.py`)."""
    sl = slice(s.width - k, s.width)
    n = np.minimum(s.n, k)
    cols = {f: getattr(s, f)[:, sl] for f in ("o", "h", "l", "c", "v")}
    hashes = tuple(row_hash(s.t[i, sl][k - n[i]:], *(cols[f][i, k - n[i]:]
                                                      for f in ("o", "h", "l", "c", "v")))
                   for i in range(len(s.ids)))
    return Panel(ids=s.ids, symbols=tuple(x.rsplit(".", 1)[-1] for x in s.ids), t=s.t[:, sl],
                 n=n, hashes=hashes, **cols)


def _prev(c: np.ndarray) -> np.ndarray:
    return np.c_[np.full((c.shape[0], 1), np.nan), c[:, :-1]]


def _rebuild(s: Stack, i: int, rel: dict[str, np.ndarray], v: np.ndarray, tb: np.ndarray,
             out: dict[str, np.ndarray]) -> None:
    """Fila `i` desde formas relativas al cierre anterior (la primera vela válida se conserva)."""
    a = s.width - int(s.n[i])
    if s.n[i] < 2:
        return
    c = np.empty(s.width - a)
    c[0] = s.c[i, a]
    c[1:] = c[0] * np.cumprod(rel["c"][a + 1:])
    prev = c[:-1]
    out["c"][i, a:] = c
    for f in ("o", "h", "l"):
        out[f][i, a + 1:] = prev * rel[f][a + 1:]
    out["v"][i, a + 1:] = v[a + 1:]
    out["tb"][i, a + 1:] = tb[a + 1:]
    # el redondeo puede dejar h una milésima bajo c cuando en la vela original eran iguales:
    # se restablece la coherencia OHLC (h el máximo, l el mínimo) que exige `Candle`
    sl = slice(a, s.width)
    body_hi = np.maximum(out["o"][i, sl], out["c"][i, sl])
    body_lo = np.minimum(out["o"][i, sl], out["c"][i, sl])
    out["h"][i, sl] = np.maximum(out["h"][i, sl], body_hi)
    out["l"][i, sl] = np.minimum(out["l"][i, sl], body_lo)


def permuted(s: Stack, rng: np.random.Generator) -> Stack:
    """Misma permutación de fechas para todo el universo (ver el docstring del módulo)."""
    prev = _prev(s.c)
    rel = {f: getattr(s, f) / prev for f in ("o", "h", "l", "c")}
    valid = np.isfinite(rel["c"]) & np.isfinite(rel["o"]) & np.isfinite(rel["h"]) & \
        np.isfinite(rel["l"])
    perm = np.r_[0, 1 + rng.permutation(s.width - 1)]   # la columna 0 no tiene anterior
    out = {f: getattr(s, f).copy() for f in FIELDS}
    for i in range(len(s.ids)):
        src = perm.copy()
        need = valid[i] & ~valid[i, src]
        if need.any():                       # historia corta: de su propia fila, al azar
            src[need] = rng.choice(np.flatnonzero(valid[i]), int(need.sum()))
        _rebuild(s, i, {f: rel[f][i, src] for f in rel}, s.v[i, src], s.tb[i, src], out)
    return replace(s, **out)


_CORR_CACHE: dict[bytes, np.ndarray] = {}


def _corr_matrix(r: np.ndarray) -> np.ndarray:
    """Correlación por pares (≥ `MIN_OVERLAP` comunes), recortada a matriz válida. Es la misma en
    todas las réplicas gaussianas de un universo: se calcula una vez (con ~560 instrumentos son
    ~160 000 pares)."""
    key = np.nan_to_num(r, nan=-9.0).tobytes()
    if key not in _CORR_CACHE:
        _CORR_CACHE.clear()
        _CORR_CACHE[key] = _corr_uncached(r)
    return _CORR_CACHE[key]


def _corr_uncached(r: np.ndarray) -> np.ndarray:
    S = r.shape[0]
    c = np.eye(S)
    for i in range(S):
        for j in range(i + 1, S):
            m = np.isfinite(r[i]) & np.isfinite(r[j])
            if m.sum() >= MIN_OVERLAP and np.std(r[i, m]) > 0 and np.std(r[j, m]) > 0:
                c[i, j] = c[j, i] = float(np.corrcoef(r[i, m], r[j, m])[0, 1])
    w, q = np.linalg.eigh(c)
    c = (q * np.clip(w, 1e-6, None)) @ q.T            # matriz válida más cercana (recorte)
    d = np.sqrt(np.diag(c))
    return c / np.outer(d, d)


def gaussian(s: Stack, rng: np.random.Generator) -> Stack:
    """Normales con la σ y la correlación de cada par, sin deriva."""
    prev = _prev(s.c)
    r = np.log(s.c / prev)
    sig = np.nanstd(r, axis=1)
    w, q = np.linalg.eigh(_corr_matrix(r))
    z = rng.standard_normal((s.width, len(s.ids))) @ (q * np.sqrt(np.clip(w, 0, None))).T
    ret = (z * np.nan_to_num(sig)).T
    body = np.maximum(s.o, s.c)
    with np.errstate(invalid="ignore", divide="ignore"):
        k_hi = np.nanmedian(np.log(s.h / body), axis=1)
        k_lo = np.nanmedian(np.log(np.minimum(s.o, s.c) / s.l), axis=1)
    out = {f: getattr(s, f).copy() for f in FIELDS}
    for i in range(len(s.ids)):
        e = np.abs(rng.standard_normal((2, s.width)))
        rc = np.exp(ret[i])
        rel = {"c": rc, "o": np.ones(s.width),
               "h": np.maximum(1.0, rc) * np.exp(e[0] * np.nan_to_num(k_hi[i])),
               "l": np.minimum(1.0, rc) * np.exp(-e[1] * np.nan_to_num(k_lo[i]))}
        src = rng.permutation(s.width)
        a = s.width - int(s.n[i])
        valid = np.arange(s.width) >= a + 1
        src = np.where(valid[src], src, np.arange(s.width))
        _rebuild(s, i, rel, s.v[i, src], s.tb[i, src], out)
    return replace(s, **out)


KINDS: dict[str, Callable[[Stack, np.random.Generator], Stack]] = {
    "permuted": permuted, "gaussian": gaussian}


# --- un escaneo completo ---------------------------------------------------------------------
def scan(s: Stack, insts: Mapping[str, Instrument], *, n_bars: int, shortlist_size: int,
         run_many: Callable[[list[dict]], list[dict]], timeframe: str, cut: int, asof: int,
         weights: rank.Weights = rank.DEFAULT_WEIGHTS, min_score: float = 0.0) -> dict:
    """Etapa 3 → lista corta → agentes (por `run_many`) → oportunidades → prioridades."""
    res = screen.screen(to_panel(s, n_bars), [insts[i].asset_class.value for i in s.ids])
    short = res.shortlist(shortlist_size, min_score)
    pos = {iid: k for k, iid in enumerate(s.ids)}
    q = {res.ids[k]: float(res.quality[k]) for k in range(len(res.ids))}
    payloads = [{"instrument": insts[iid].model_dump(mode="json"),
                 "candles": [c.model_dump() for c in candles_of(s, pos[iid])],
                 "timeframe": timeframe, "cut": cut, "asof": asof,
                 "screen": {"quality": q.get(iid)}} for iid in short]
    results = run_many(payloads) if payloads else []
    opps = [r["opportunity"] for r in results if r.get("opportunity")]
    closes = {iid: s.c[pos[iid], s.width - int(s.n[pos[iid]]):] for iid in short}
    ranked = rank.rank(opps, closes, weights)
    pr = [r["priority"] for r in ranked if r["priority"] is not None]
    return {"shortlist": short, "n_candidates": len(opps), "priorities": pr,
            "max": max(pr) if pr else None, "ranked": ranked,
            "reasons": sorted({r.get("reason", "").split(" (")[0] for r in results
                               if r.get("reason")})}


def analyze_payload(payload: dict) -> dict:
    """Trabajo de un proceso: la misma activación de agentes del escáner (`deep.analyze`)."""
    from eim.scanner import deep

    inst = Instrument.model_validate(payload["instrument"])
    cs = [Candle(**c) for c in payload["candles"]]
    return deep.analyze(inst, cs, deep.default_agents(), asof=payload["asof"],
                        timeframe=payload["timeframe"], cut=payload["cut"], run_id="placebo",
                        source="placebo", screen=payload["screen"], spread_bps=None).as_json()


def safe_analyze(payload: dict) -> dict:
    """`analyze_payload` sin tumbar la réplica: un fallo cuenta como «sin candidata» y se dice."""
    try:
        return analyze_payload(payload)
    except Exception as exc:  # noqa: BLE001 - el informe lo cuenta
        return {"instrument_id": payload["instrument"]["id"], "opportunity": None,
                "reason": f"error: {type(exc).__name__}: {exc}"}
