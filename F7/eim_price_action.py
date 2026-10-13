"""
EIM-F7 | Módulo 7: Price Action
=================================
Complementa al FRM (basado en EMAs) con lectura de acción del precio pura:
  - Swings (fractales de alta/baja) — pivotes confirmados n velas después.
  - Patrones de vela (envolvente, martillo, estrella fugaz, doji, inside/outside bar).
  - Estructura de mercado: HH/HL/LH/LL, rupturas de estructura (BOS) y
    cambios de carácter (CHOCH) — terminología estándar de "price action" moderno.
  - Zonas de soporte/resistencia por clustering de pivotes.

Nota: un swing solo se puede confirmar `n` velas después de ocurrir (necesita
ver hacia adelante) — es una limitación inherente al método, no un bug; por
eso las últimas `n` velas de cualquier serie nunca muestran swings todavía.
"""

import numpy as np
import pandas as pd


class EIMPriceAction:
    """Calcula swings, patrones de vela y estructura de mercado sobre un OHLCV."""

    def __init__(self, df: pd.DataFrame, fractal_n: int = 2):
        self.df = df.copy().reset_index(drop=True)
        self.n = fractal_n

    # ── Swings (fractales) ──────────────────────────────────────────
    def compute_swings(self) -> pd.DataFrame:
        n = self.n
        high, low = self.df["high"], self.df["low"]
        swing_high = [False] * len(self.df)
        swing_low  = [False] * len(self.df)

        for i in range(n, len(self.df) - n):
            hw = high.iloc[i - n:i + n + 1]
            lw = low.iloc[i - n:i + n + 1]
            if high.iloc[i] == hw.max() and (hw == high.iloc[i]).sum() == 1:
                swing_high[i] = True
            if low.iloc[i] == lw.min() and (lw == low.iloc[i]).sum() == 1:
                swing_low[i] = True

        self.df["SWING_HIGH"] = swing_high
        self.df["SWING_LOW"]  = swing_low
        return self.df

    # ── Patrones de vela ─────────────────────────────────────────────
    def compute_candle_patterns(self) -> pd.DataFrame:
        o, h, l, c = self.df["open"], self.df["high"], self.df["low"], self.df["close"]
        body  = (c - o).abs()
        rng   = (h - l).replace(0, np.nan)
        upper = h - pd.concat([c, o], axis=1).max(axis=1)
        lower = pd.concat([c, o], axis=1).min(axis=1) - l

        o_p, c_p = o.shift(1), c.shift(1)
        h_p, l_p = h.shift(1), l.shift(1)

        bull_now  = c > o
        bear_now  = c < o
        bull_prev = c_p < o_p
        bear_prev = c_p > o_p

        self.df["BULLISH_ENGULFING"] = (
            bull_now & bear_prev & (o <= c_p) & (c >= o_p)
        ).fillna(False)
        self.df["BEARISH_ENGULFING"] = (
            bear_now & bull_prev & (o >= c_p) & (c <= o_p)
        ).fillna(False)
        body_floor = body.where(body != 0, rng * 0.05)
        self.df["HAMMER"] = (
            (lower >= 2 * body) & (upper <= 0.3 * body_floor)
        ).fillna(False)
        self.df["SHOOTING_STAR"] = (
            (upper >= 2 * body) & (lower <= 0.3 * body_floor)
        ).fillna(False)
        self.df["DOJI"] = (body <= 0.1 * rng).fillna(False)
        self.df["INSIDE_BAR"]  = ((h <= h_p) & (l >= l_p)).fillna(False)
        self.df["OUTSIDE_BAR"] = ((h >= h_p) & (l <= l_p)).fillna(False)
        return self.df

    # ── Estructura de mercado: HH/HL/LH/LL + BOS/CHOCH ──────────────
    def compute_structure(self) -> pd.DataFrame:
        n = len(self.df)
        structure_event = ["NONE"] * n
        structure_state = ["UNDEFINED"] * n

        last_high_price = last_low_price = None
        last_high_label = last_low_label = None
        broken_high = broken_low = True   # nada que romper todavía
        state = "UNDEFINED"

        close = self.df["close"]
        high, low = self.df["high"], self.df["low"]
        is_sh, is_sl = self.df["SWING_HIGH"], self.df["SWING_LOW"]

        for i in range(n):
            # 1) ¿Rompe la vela actual el último swing confirmado?
            if last_high_price is not None and not broken_high and close.iloc[i] > last_high_price:
                structure_event[i] = "BOS_ALCISTA" if state == "BULLISH" else "CHOCH_ALCISTA"
                broken_high = True
                state = "BULLISH"
            if last_low_price is not None and not broken_low and close.iloc[i] < last_low_price:
                # Si ya se marcó un evento alcista en esta misma vela, igual registramos
                # el bajista solo si no había uno ya (caso muy raro, gana el primero calculado).
                if structure_event[i] == "NONE":
                    structure_event[i] = "BOS_BAJISTA" if state == "BEARISH" else "CHOCH_BAJISTA"
                broken_low = True
                state = "BEARISH"

            # 2) ¿Esta vela confirma un nuevo swing? (actualiza referencia y reabre el "no roto")
            if is_sh.iloc[i]:
                last_high_label = "HH" if (last_high_price is None or high.iloc[i] > last_high_price) else "LH"
                last_high_price = high.iloc[i]
                broken_high = False
            if is_sl.iloc[i]:
                last_low_label = "HL" if (last_low_price is None or low.iloc[i] > last_low_price) else "LL"
                last_low_price = low.iloc[i]
                broken_low = False

            structure_state[i] = state

        self.df["STRUCTURE_EVENT"] = structure_event
        self.df["STRUCTURE_STATE"] = structure_state
        self._last_high_label = last_high_label
        self._last_low_label  = last_low_label
        return self.df

    # ── Zonas de soporte/resistencia (clustering de pivotes) ────────
    def compute_sr_zones(self, tolerance_pct: float = 0.5) -> list:
        points = list(self.df.loc[self.df["SWING_HIGH"], "high"]) + \
                 list(self.df.loc[self.df["SWING_LOW"],  "low"])
        points.sort()

        zones = []
        for p in points:
            for z in zones:
                if z["price"] == 0:
                    continue
                if abs(p - z["price"]) / z["price"] * 100 <= tolerance_pct:
                    z["touches"] += 1
                    z["price"] += (p - z["price"]) / z["touches"]
                    break
            else:
                zones.append({"price": float(p), "touches": 1})

        zones.sort(key=lambda z: z["price"])
        return zones

    def run_all(self):
        self.compute_swings()
        self.compute_candle_patterns()
        self.compute_structure()
        sr_zones = self.compute_sr_zones()
        return self.df, sr_zones
