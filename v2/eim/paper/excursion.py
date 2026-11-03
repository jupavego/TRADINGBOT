"""MFE y MAE desde el llenado (T130): una sola definición en la sombra y en la escalera.

Antes se medían sobre la vela del llenado completa: en una entrada límite contaban precios
anteriores al llenado (MFE inflado; p. ej. 0,49 R con un neto máximo de −51 USDT) y la sombra
recortaba al TP/SL mientras la escalera no. Ahora solo cuenta lo que la posición recorrió viva,
con el mismo supuesto de orden que usa cada motor:
- La ventana empieza en el llenado: la vela del llenado cuenta si se entró a mercado (a su
  apertura); en una entrada límite empieza en la vela siguiente (el orden dentro de la vela del
  llenado no se conoce).
- En la vela de salida por stop no cuenta el extremo favorable (el motor supone que el stop llegó
  primero); en la de salida por TP, el favorable es el propio TP; una salida por tiempo se ejecuta
  a la apertura de su vela, que no cuenta.
- El precio de salida siempre cuenta: una salida en la vela del llenado tiene MAE hasta su stop.

Puro: sin I/O.
"""

from __future__ import annotations


class Extremes:
    """Extremo favorable y adverso que la posición recorrió viva (precios)."""

    __slots__ = ("adv", "fav", "s")

    def __init__(self, s: int) -> None:
        self.s, self.fav, self.adv = s, None, None

    def see(self, fav: float, adv: float) -> None:
        s = self.s
        if self.fav is None or (fav - self.fav) * s > 0:
            self.fav = fav
        if self.adv is None or (self.adv - adv) * s > 0:
            self.adv = adv

    def see_bars(self, path, a: int, b: int) -> None:
        """Velas completas [a, b) del camino."""
        if b > a:
            hi, lo = float(path.h[a:b].max()), float(path.l[a:b].min())
            self.see(hi if self.s > 0 else lo, lo if self.s > 0 else hi)

    def r(self, fill: float, risk: float, exit_px: float | None = None) -> tuple[float, float]:
        """(MFE, MAE) en R con el precio de salida incluido; `risk` en precio."""
        if exit_px is not None:
            self.see(exit_px, exit_px)
        s = self.s
        mfe = 0.0 if self.fav is None else max(0.0, (self.fav - fill) * s) / risk
        mae = 0.0 if self.adv is None else max(0.0, (fill - self.adv) * s) / risk
        return mfe, mae


def shadow_excursion(path, s: int, kind: str, k: int, start: int, jx: int | None, reason: str,
                     fill: float, risk: float, ex: float | None) -> tuple[float, float]:
    """(MFE, MAE) de `engine.simulate`: llenado en la vela `k`, salida `reason` en la vela `jx`
    (None = abierta hasta el final del camino)."""
    e = Extremes(s)
    w0 = k if kind == "market" else start
    if jx is None:
        e.see_bars(path, w0, len(path.t))
    elif reason == "TP":                       # la vela del TP: su adverso y el propio TP
        e.see_bars(path, w0, jx)
        e.see(ex, float(path.l[jx] if s > 0 else path.h[jx]))
    else:                                      # SL/BE (stop primero) y TIEMPO (a la apertura)
        e.see_bars(path, w0, jx)
    return e.r(fill, risk, ex)
