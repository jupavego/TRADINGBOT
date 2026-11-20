"""Validación determinista de lo leído (T66): ninguna cifra se acepta solo por la imagen.

- **Precio** (nivel, cifra en USD o etiqueta del eje): se acepta si coinciden OCR y visión
  (≤ `agree_rel`) **o** si cae en el rango real del activo (velas T03 de la ventana anterior a
  `ref_ms`, ± `range_tol`). Ambas → `confirmada`; una → `plausible`; fuera de rango o capas en
  desacuerdo → `inconsistente`; sin velas ni acuerdo → `no_verificable`.
- **Indicador** calculable (RSI, EMA, SMA/MA, VWAP): se **recalcula** con `eim.indicators` sobre
  las velas del activo y el marco leídos y se compara (RSI ± `rsi_tol_abs`; medias y VWAP ±
  `ma_tol_rel`): `confirmada` o `inconsistente`; si no se puede recalcular, `no_verificable`.
- Titulares, dibujos y cifras sin unidad de precio: `no_verificable` (se guardan como dato).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from eim.core import Candle
from eim.core.video import Validation
from eim.indicators import ema, momentum, sma
from eim.indicators.registry import candle_arrays, compute
from eim.video.visual.params import DEFAULT, VisualParams
from eim.video.visual.readings import Reading, rel_diff

CandleSource = Callable[[str, str, int, int], list[Candle]]
"""`(símbolo, marco, desde_ms, hasta_ms) -> velas cerradas con desde ≤ t < hasta`."""

_UNIT_MS = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}
PRICE_UNITS = ("USD", "precio")


def tf_ms(tf: str | None) -> int | None:
    if not tf or tf[-1] not in _UNIT_MS or not tf[:-1].isdigit():
        return None
    return int(tf[:-1]) * _UNIT_MS[tf[-1]]


@dataclass(frozen=True)
class Verdict:
    state: Validation
    note: str


class Validator:
    """Valida lecturas de un fotograma con el activo/marco leídos y la fecha del video."""

    def __init__(self, candles: CandleSource | None, symbol: str | None, timeframe: str | None,
                 ref_ms: int | None, p: VisualParams = DEFAULT) -> None:
        self.src, self.symbol, self.tf, self.ref, self.p = candles, symbol, timeframe, ref_ms, p
        self._range: tuple[float, float] | None | bool = False   # False = sin calcular
        self._cache: dict[str, list[Candle]] = {}

    def _candles(self, tf: str, start: int) -> list[Candle]:
        key = f"{tf}:{start}"
        if key not in self._cache:
            try:
                self._cache[key] = list(self.src(self.symbol, tf, start, self.ref)) if (
                    self.src and self.symbol and self.ref) else []
            except Exception:      # proveedor caído: no verificable, nunca inventado
                self._cache[key] = []
        return self._cache[key]

    def price_range(self) -> tuple[float, float] | None:
        if self._range is False:
            self._range = None
            if self.symbol and self.ref:
                step = tf_ms(self.tf)
                span = (step * self.p.range_bars if step
                        else int(self.p.range_default_days * 86_400_000))
                cs = self._candles("1h" if not step or step < 3_600_000 else self.tf,
                                   self.ref - span)
                if cs:
                    self._range = (min(c.l for c in cs), max(c.h for c in cs))
        return self._range or None

    def check(self, r: Reading) -> Verdict:
        if r.kind in ("titular", "dibujo"):
            return Verdict("no_verificable", "texto o dibujo: se guarda como dato")
        if r.kind == "indicador":
            return self._indicator(r)
        if r.kind == "cifra" and r.unit not in PRICE_UNITS:
            return Verdict("no_verificable", "cifra sin unidad de precio: no se sabe qué mide")
        return self._price(r)

    def _price(self, r: Reading) -> Verdict:
        v = float(r.value)
        both = r.source == "ambos" and r.other is not None
        agree = both and rel_diff(v, r.other) <= self.p.agree_rel
        if both and not agree:
            return Verdict("inconsistente", f"OCR y visión no coinciden ({v:g} frente a "
                                            f"{r.other:g})")
        rng = self.price_range()
        if rng is None:
            return (Verdict("plausible", "OCR y visión coinciden; sin velas para el rango")
                    if agree else Verdict("no_verificable", "una sola capa y sin velas del "
                                                            "activo en esa fecha"))
        lo, hi = rng[0] * (1 - self.p.range_tol), rng[1] * (1 + self.p.range_tol)
        where = f"rango real {rng[0]:g}–{rng[1]:g} ± {self.p.range_tol:.0%}"
        if not lo <= v <= hi:
            return Verdict("inconsistente", f"{v:g} fuera del {where}")
        if agree:
            return Verdict("confirmada", f"OCR y visión coinciden y dentro del {where}")
        return Verdict("plausible", f"una sola capa, dentro del {where}")

    def _indicator(self, r: Reading) -> Verdict:
        name, _, per = r.unit.partition(":")
        period = int(per) if per.isdigit() else (14 if name == "rsi" else None)
        step = tf_ms(self.tf)
        if not self.symbol or not step or not self.ref:
            return Verdict("no_verificable", "sin activo, marco o fecha para recalcular")
        if name not in ("rsi", "ema", "sma", "vwap") or (name != "vwap" and not period):
            return Verdict("no_verificable", f"«{r.unit}» no se puede recalcular")
        need = (period or 0) * 6 + 50 if name != "vwap" else max(2, 86_400_000 // step + 2)
        cs = self._candles(self.tf, self.ref - need * step)
        if len(cs) < (period or 2) + 1:
            return Verdict("no_verificable", "velas insuficientes para recalcular")
        a = candle_arrays(cs)
        if name == "rsi":
            series = momentum.rsi(a["close"], period)
        elif name == "ema":
            series = ema(a["close"], period)
        elif name == "sma":
            series = sma(a["close"], period)
        else:
            series = compute("VWAP", a)["vwap"]
        calc = float(series[-1]) if len(series) else float("nan")
        if not np.isfinite(calc):
            return Verdict("no_verificable", "el recálculo no dio valor")
        v = float(r.value)
        ok = (abs(v - calc) <= self.p.rsi_tol_abs if name == "rsi"
              else rel_diff(v, calc) <= self.p.ma_tol_rel)
        note = f"recalculado {calc:.4g} con {len(cs)} velas {self.tf} de {self.symbol}"
        return Verdict("confirmada" if ok else "inconsistente", note)
