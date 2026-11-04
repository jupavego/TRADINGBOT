"""`ExitFeatures` v1 (§4.1 de `T129_sl_dinamico.md`): lo que las políticas de T132 miran del camino.

Versionado y con **procedencia y cobertura por campo**, como exige la regla del proyecto de que
ninguna cifra se presente como real sin decir de dónde sale. Todo se calcula con velas **≤ j**, así
que una política puede leer el valor de la vela `j` sin anticipación, y donde falta ventana va
`nan`: la falta de datos **no aprieta** (un σ de 0 pondría el stop encima del precio).

Campos:

- `sigma_abs`: σ en **precio** por vela del camino, del estimador que se pida (`sigma.py` o el
  HAR-RV de 1 min de `harrv.py`). Es σ relativo × el cierre de la vela.
- `swing_low` / `swing_high`: último swing **confirmado** (fractal de `n` velas) al cerrar `j`. Un
  fractal de 5 no existe hasta que han cerrado las dos velas posteriores: eso es lo que hace que
  M3 no mire al futuro.
- `htf_dir`: signo de la tendencia del marco mayor por vela (+1, −1, 0), de dos EMAs calculadas
  sobre el propio camino. Lo usa M7.
- `bar_range`: rango relativo mediano reciente, la unidad de «ruido» con la que T129 comparaba la
  distancia del stop.

Puro: numpy, sin dependencias nuevas (◆5 de T129).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from eim.paper.engine import Path
from eim.paper.exits import harrv, sigma

VERSION = "v1"
SWING_BARS = (3, 5)
EMA_FAST, EMA_SLOW = 21, 55
RANGE_WINDOW = 96            # ≈ un día de velas de 15 m
SIGMA_WINDOW = 96
HARRV = "harrv_1m"
BARS_PER_DAY = 96.0


def ema(x: np.ndarray, n: int) -> np.ndarray:
    """EMA causal con arranque en la primera media simple; `nan` antes de tener `n` velas."""
    out = np.full(len(x), np.nan)
    if n < 1 or len(x) < n:
        return out
    a = 2.0 / (n + 1.0)
    out[n - 1] = float(np.mean(x[:n]))
    for j in range(n, len(x)):
        out[j] = a * x[j] + (1 - a) * out[j - 1]
    return out


def swings(h: np.ndarray, lo: np.ndarray, bars: int) -> tuple[np.ndarray, np.ndarray]:
    """(último mínimo, último máximo) de swing CONFIRMADO al cerrar cada vela.

    Un swing de `bars` velas necesita `k = bars // 2` velas a cada lado: el pivote en `i` solo se
    conoce al cerrar `i + k`, y es entonces cuando entra en la serie. Así M3 nunca ancla el stop en
    un swing que el mercado todavía no había confirmado.
    """
    n = len(h)
    out_lo, out_hi = np.full(n, np.nan), np.full(n, np.nan)
    k = max(1, bars // 2)
    if n < bars:
        return out_lo, out_hi
    last_lo = last_hi = np.nan
    for j in range(n):
        i = j - k                                   # pivote que se confirma al cerrar j
        if i - k >= 0 and i + k <= j:
            w_lo, w_hi = lo[i - k:i + k + 1], h[i - k:i + k + 1]
            if np.isfinite(w_lo).all() and lo[i] == w_lo.min():
                last_lo = float(lo[i])
            if np.isfinite(w_hi).all() and h[i] == w_hi.max():
                last_hi = float(h[i])
        out_lo[j], out_hi[j] = last_lo, last_hi
    return out_lo, out_hi


def htf_direction(c: np.ndarray, fast: int = EMA_FAST, slow: int = EMA_SLOW) -> np.ndarray:
    """Signo de la tendencia: +1 si la EMA rápida va por encima de la lenta, −1 si por debajo."""
    f, s = ema(c, fast), ema(c, slow)
    out = np.zeros(len(c), dtype=np.int8)
    ok = np.isfinite(f) & np.isfinite(s)
    out[ok & (f > s)] = 1
    out[ok & (f < s)] = -1
    return out


def median_range(h: np.ndarray, lo: np.ndarray, c: np.ndarray,
                 window: int = RANGE_WINDOW) -> np.ndarray:
    """Rango relativo mediano de las últimas `window` velas (la unidad de ruido de T129)."""
    n = len(c)
    out = np.full(n, np.nan)
    rel = np.where((c > 0) & np.isfinite(c), (h - lo) / np.where(c > 0, c, 1.0), np.nan)
    for j in range(window - 1, n):
        w = rel[j - window + 1:j + 1]
        if np.isfinite(w).all():
            out[j] = float(np.median(w))
    return out


@dataclass(frozen=True)
class ExitFeatures:
    """Rasgos del camino, con su procedencia y su cobertura real por campo."""

    version: str
    sigma_name: str
    sigma_abs: np.ndarray
    swing_low: np.ndarray
    swing_high: np.ndarray
    htf_dir: np.ndarray
    bar_range: np.ndarray
    source: dict[str, str]
    coverage: dict[str, float]

    def to_json(self) -> dict:
        return {"version": self.version, "sigma": self.sigma_name, "source": self.source,
                "coverage": {k: round(v, 6) for k, v in self.coverage.items()}}


def _cover(x: np.ndarray) -> float:
    return float(np.isfinite(np.asarray(x, dtype=float)).mean()) if len(x) else 0.0


def build(path: Path, sigma_name: str, *, swing_bars: int = 5, fine: Path | None = None,
          sigma_window: int = SIGMA_WINDOW) -> ExitFeatures:
    """Rasgos de todo el camino con el estimador `sigma_name`.

    `fine` solo hace falta para `harrv_1m`; sin velas finas ese estimador queda todo en `nan` y las
    políticas que lo pidan usarán su valor base, que es lo correcto: no se inventa una σ.
    """
    o, h, lo, c = path.o, path.h, path.l, path.c
    if sigma_name == HARRV:
        rel = (harrv.sigma_by_bar(path.t, fine.t, fine.c, BARS_PER_DAY) if fine is not None
               else np.full(len(c), np.nan))
        src = ("HAR-RV de las velas de 1 min, ajustado solo con dias anteriores"
               if fine is not None else "sin velas de 1 min en la copia")
    else:
        rel = sigma.of(sigma_name, o, h, lo, c, sigma_window)
        src = f"{sigma_name} sobre las velas del camino, ventana {sigma_window}"
    with np.errstate(invalid="ignore"):
        sig_abs = rel * np.where((c > 0) & np.isfinite(c), c, np.nan)
    s_lo, s_hi = swings(h, lo, swing_bars)
    hd = htf_direction(c)
    rng = median_range(h, lo, c)
    return ExitFeatures(
        version=VERSION, sigma_name=sigma_name, sigma_abs=sig_abs, swing_low=s_lo,
        swing_high=s_hi, htf_dir=hd, bar_range=rng,
        source={"sigma_abs": src,
                "swing_low": f"fractal de {swing_bars} velas del camino, confirmado",
                "swing_high": f"fractal de {swing_bars} velas del camino, confirmado",
                "htf_dir": f"EMA {EMA_FAST}/{EMA_SLOW} del propio camino",
                "bar_range": f"rango relativo mediano de {RANGE_WINDOW} velas"},
        coverage={"sigma_abs": _cover(sig_abs), "swing_low": _cover(s_lo),
                  "swing_high": _cover(s_hi), "htf_dir": float((hd != 0).mean()) if len(hd) else 0,
                  "bar_range": _cover(rng)})
