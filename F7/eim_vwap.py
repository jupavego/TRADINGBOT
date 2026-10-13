"""
EIM-F7 | Módulo 6: VWAP (Volume Weighted Average Price)
==========================================================
VWAP diario (ancla en 00:00 UTC), semanal (ancla lunes 00:00 UTC), quincenal
(ancla los días 1 y 16 de cada mes — la "quincena" de nómina en español/
LatAm, NO un bloque rodante de 14 días) y mensual (ancla el día 1), cada uno
con bandas de desviación estándar (±1σ/±2σ). Más un VWAP anclado al inicio
de la ventana cargada. Complementa al FRM (basado en EMAs) con una
referencia de "precio justo" ponderada por volumen — muy usada en mesas
institucionales para ubicar sobreextensión.

No requiere datos adicionales: el volumen ya viene en el feed OHLCV de Binance.

Nota de cobertura: cada período reinicia su acumulación en la primera vela
disponible de ese período dentro de la ventana cargada — si la ventana no
alcanza a cubrir un período completo (ej. pides VWAP mensual con solo 3 días
de velas), el primer período de la serie queda parcial, no es una lectura
de mes completo. Igual que con las bandas de EMA-200, cárguese suficiente
contexto histórico para el período más largo que se necesite.
"""

import math

import numpy as np
import pandas as pd


class EIMVWAP:
    """Calcula VWAP diario + bandas y VWAP anclado a la ventana completa."""

    # Notas interpretativas por posición — lectura estándar de mesa institucional.
    POSITION_NOTES = {
        "SOBRE_VWAP":     "Cotiza ligeramente por encima del precio promedio ponderado del día — "
                          "sesgo comprador de corto plazo, dentro de rango normal.",
        "ESTIRADO_SOBRE": "Se está alejando del VWAP (1-2σ) — el movimiento podría continuar, "
                          "pero crece la probabilidad de un retroceso hacia el VWAP.",
        "EXTREMO_SOBRE":  "Muy alejado del VWAP (>2σ) — estadísticamente sobreextendido; "
                          "el precio tiende a revertir hacia el VWAP desde este nivel.",
        "BAJO_VWAP":      "Cotiza ligeramente por debajo del precio promedio ponderado del día — "
                          "sesgo vendedor de corto plazo, dentro de rango normal.",
        "ESTIRADO_BAJO":  "Se está alejando del VWAP hacia abajo (1-2σ) — el movimiento podría "
                          "continuar, pero crece la probabilidad de un rebote hacia el VWAP.",
        "EXTREMO_BAJO":   "Muy alejado del VWAP hacia abajo (>2σ) — estadísticamente sobrevendido; "
                          "el precio tiende a revertir hacia el VWAP desde este nivel.",
        "SIN_DATOS":      "Inicio de sesión — todavía no hay suficiente volumen acumulado "
                          "para una lectura confiable.",
    }

    # Sesgo direccional heurístico por posición (puntos sobre una base neutra de 50).
    _POSITION_BIAS = {
        "SOBRE_VWAP": 15, "ESTIRADO_SOBRE": 6, "EXTREMO_SOBRE": -8,
        "BAJO_VWAP": -15, "ESTIRADO_BAJO": -6, "EXTREMO_BAJO": 8,
        "SIN_DATOS": 0,
    }

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy().reset_index(drop=True)

    def _typical_price(self) -> pd.Series:
        return (self.df["high"] + self.df["low"] + self.df["close"]) / 3

    # ── Motor genérico: VWAP acumulado dentro de un período + bandas ──
    def _compute_period_vwap(self, period_key: pd.Series, prefix: str) -> pd.DataFrame:
        tp  = self._typical_price()
        vol = self.df["volume"]

        cum_pv  = (tp * vol).groupby(period_key).cumsum()
        cum_vol = vol.groupby(period_key).cumsum()
        vwap    = cum_pv / cum_vol

        sq_dev = vol * (tp - vwap) ** 2
        std    = np.sqrt(sq_dev.groupby(period_key).cumsum() / cum_vol)

        self.df[prefix]              = vwap
        self.df[f"{prefix}_STD"]     = std
        self.df[f"{prefix}_UPPER_1"] = vwap + std
        self.df[f"{prefix}_LOWER_1"] = vwap - std
        self.df[f"{prefix}_UPPER_2"] = vwap + 2 * std
        self.df[f"{prefix}_LOWER_2"] = vwap - 2 * std
        return self.df

    # ── VWAP diario (reinicia cada día UTC) ────────────────────────
    def compute_daily(self) -> pd.DataFrame:
        day = self.df["timestamp"].dt.floor("D")
        self.df["VWAP_DAY_PERIOD"] = day
        return self._compute_period_vwap(day, "VWAP_DAY")

    # ── VWAP semanal (reinicia lunes 00:00 UTC) ─────────────────────
    def compute_weekly(self) -> pd.DataFrame:
        day = self.df["timestamp"].dt.floor("D")
        week_start = day - pd.to_timedelta(self.df["timestamp"].dt.dayofweek, unit="D")
        self.df["VWAP_WEEK_PERIOD"] = week_start
        return self._compute_period_vwap(week_start, "VWAP_WEEK")

    @staticmethod
    def _month_start(ts: pd.Series) -> pd.Series:
        """Día 1 del mes a las 00:00, preservando timezone (sin pasar por Period, que la descarta)."""
        return ts.dt.normalize() - pd.to_timedelta(ts.dt.day - 1, unit="D")

    # ── VWAP quincenal (reinicia días 1 y 16 de cada mes) ───────────
    def compute_quincenal(self) -> pd.DataFrame:
        ts = self.df["timestamp"]
        month_start = self._month_start(ts)
        second_half_start = month_start + pd.to_timedelta(15, unit="D")
        period_start = month_start.where(ts.dt.day <= 15, second_half_start)
        self.df["VWAP_QUINCENA_PERIOD"] = period_start
        return self._compute_period_vwap(period_start, "VWAP_QUINCENA")

    # ── VWAP mensual (reinicia el día 1 de cada mes) ────────────────
    def compute_monthly(self) -> pd.DataFrame:
        month_start = self._month_start(self.df["timestamp"])
        self.df["VWAP_MONTH_PERIOD"] = month_start
        return self._compute_period_vwap(month_start, "VWAP_MONTH")

    # ── VWAP anclado al inicio de la ventana cargada ───────────────
    def compute_anchored(self) -> pd.DataFrame:
        tp  = self._typical_price()
        vol = self.df["volume"]

        cum_pv  = (tp * vol).cumsum()
        cum_vol = vol.cumsum()
        vwap    = cum_pv / cum_vol
        std     = np.sqrt((vol * (tp - vwap) ** 2).cumsum() / cum_vol)

        self.df["VWAP_ANCHOR"]         = vwap
        self.df["VWAP_ANCHOR_STD"]     = std
        self.df["VWAP_ANCHOR_UPPER_1"] = vwap + std
        self.df["VWAP_ANCHOR_LOWER_1"] = vwap - std
        return self.df

    # ── Posición del cierre respecto a un VWAP (con bandas) y sus bandas ──
    def compute_position_for(self, prefix: str) -> pd.Series:
        vwap_col, std_col, out_col = prefix, f"{prefix}_STD", f"{prefix}_POSITION"

        def classify(row):
            close, vwap, std = row["close"], row[vwap_col], row[std_col]
            if pd.isna(vwap) or pd.isna(std) or std == 0:
                return "SIN_DATOS"
            dev = (close - vwap) / std
            if dev > 2:  return "EXTREMO_SOBRE"
            if dev > 1:  return "ESTIRADO_SOBRE"
            if dev > 0:  return "SOBRE_VWAP"
            if dev > -1: return "BAJO_VWAP"
            if dev > -2: return "ESTIRADO_BAJO"
            return "EXTREMO_BAJO"

        self.df[out_col] = self.df.apply(classify, axis=1)
        return self.df[out_col]

    # Alias retrocompatible — equivalente a compute_position_for("VWAP_DAY").
    def compute_position(self) -> pd.Series:
        return self.compute_position_for("VWAP_DAY")

    # ── Pendiente de un VWAP (tendencia del "precio justo" de ese período) ──
    def compute_slope_for(self, prefix: str) -> pd.Series:
        out_col = f"{prefix}_SLOPE"
        self.df[out_col] = (
            (self.df[prefix] - self.df[prefix].shift(1)) / self.df[prefix].shift(1)
        ) * 100
        return self.df[out_col]

    # Alias retrocompatible — equivalente a compute_slope_for("VWAP_DAY").
    def compute_slope(self) -> pd.Series:
        return self.compute_slope_for("VWAP_DAY")

    PERIOD_COMPUTE = {
        "daily":     ("compute_daily",     "VWAP_DAY"),
        "weekly":    ("compute_weekly",    "VWAP_WEEK"),
        "quincenal": ("compute_quincenal", "VWAP_QUINCENA"),
        "monthly":   ("compute_monthly",   "VWAP_MONTH"),
    }

    def run_all(self, periods: tuple = ("daily",)) -> pd.DataFrame:
        """
        periods: subconjunto de {"daily","weekly","quincenal","monthly"}.
        Por defecto solo calcula "daily" (+ anclado) — mismo comportamiento
        que antes de añadir los períodos nuevos, para no romper a quien ya
        llama run_all() sin argumentos (ej. /api/vwap).
        """
        self.compute_anchored()
        for period in periods:
            if period not in self.PERIOD_COMPUTE:
                raise ValueError(
                    f"Período '{period}' no reconocido — usar uno de: "
                    f"{', '.join(self.PERIOD_COMPUTE)}"
                )
            method_name, prefix = self.PERIOD_COMPUTE[period]
            getattr(self, method_name)()
            self.compute_position_for(prefix)
            self.compute_slope_for(prefix)
        return self.df

    # ── Lectura direccional heurística (posición + pendiente del VWAP) ─────
    @classmethod
    def interpret(cls, position: str, slope) -> dict:
        """
        Combina la posición vs VWAP con la pendiente del VWAP en una lectura
        direccional explícita: 0-1σ a favor de la pendiente = sesgo de
        continuación; >1σ empieza a pesar la reversión hacia el VWAP.
        NO es una probabilidad estadística validada — es una heurística
        documentada, igual que los umbrales θ del BRM.
        """
        position_bias = cls._POSITION_BIAS.get(position, 0)

        slope_val = 0.0 if slope is None or (isinstance(slope, float) and math.isnan(slope)) else float(slope)
        slope_bias = max(-20.0, min(20.0, slope_val * 40))

        prob_up = max(5.0, min(95.0, 50 + position_bias + slope_bias))
        return {
            "note":          cls.POSITION_NOTES.get(position, ""),
            "prob_up_pct":   round(prob_up, 1),
            "prob_down_pct": round(100 - prob_up, 1),
        }
