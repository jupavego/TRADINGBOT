"""
EIM-F7 | Módulo 2: Formula Repository
=======================================
Implementa EIM-FRM-001 v1.0.0 — F-001 a F-022
Orden de cálculo: Apéndice A del FRM
"""

import numpy as np
import pandas as pd
from typing import Optional


class EIMFRM:
    """
    Implementación computacional de EIM-FRM-001.
    Recibe un DataFrame OHLCV y produce todas las variables L1 y L2.
    """

    def __init__(self, df: pd.DataFrame):
        """
        Args:
            df: DataFrame con columnas [timestamp, open, high, low, close, volume]
                Mínimo 400 velas para warmup EMA-200.
        """
        self.df = df.copy().reset_index(drop=True)
        self._validate_input()

    def _validate_input(self):
        required = ["timestamp", "open", "high", "low", "close", "volume"]
        missing  = [c for c in required if c not in self.df.columns]
        if missing:
            raise ValueError(f"Columnas faltantes en DataFrame: {missing}")
        if len(self.df) < 400:
            print(f"[EIM FRM] ADVERTENCIA: Solo {len(self.df)} velas. "
                  f"Se recomiendan >= 400 para warmup EMA-200.")

    # ═══════════════════════════════════════════════════════════════
    # BLOQUE 1 — INSTRUMENTOS (L1)
    # ═══════════════════════════════════════════════════════════════

    def compute_emas(self) -> pd.DataFrame:
        """
        F-001: Calcula EMA_9, EMA_21, EMA_55, EMA_100, EMA_200.
        Usa EWM de pandas (inicialización por media simple = adjust=False).
        """
        close = self.df["close"]
        for n in [9, 21, 55, 100, 200]:
            self.df[f"EMA_{n}"] = close.ewm(span=n, adjust=False).mean()
        return self.df

    # ═══════════════════════════════════════════════════════════════
    # BLOQUE 2 — POSICIÓN RELATIVA Y ESTRUCTURA (L2 Grupo A)
    # ═══════════════════════════════════════════════════════════════

    def compute_stack_order(self) -> pd.Series:
        """
        F-002: Orden del stack — clasificación categórica del alineamiento.
        """
        emas = [self.df[f"EMA_{n}"] for n in [9, 21, 55, 100, 200]]

        def classify(row):
            vals      = [row[f"EMA_{n}"] for n in [9, 21, 55, 100, 200]]
            bull_pairs = sum(vals[i] > vals[i+1] for i in range(4))
            map_ = {4: "BULL_PERFECT", 3: "BULL_PARTIAL",
                    2: "NEUTRAL",      1: "BEAR_PARTIAL", 0: "BEAR_PERFECT"}
            return map_[bull_pairs]

        self.df["STACK_ORDER"] = self.df.apply(classify, axis=1)
        return self.df["STACK_ORDER"]

    def compute_stack_score(self) -> pd.Series:
        """F-003: Puntaje numérico del stack [0–10]. bull_pairs × 2.5."""
        def score(row):
            vals       = [row[f"EMA_{n}"] for n in [9, 21, 55, 100, 200]]
            bull_pairs = sum(vals[i] > vals[i+1] for i in range(4))
            return bull_pairs * 2.5

        self.df["STACK_SCORE"] = self.df.apply(score, axis=1)
        return self.df["STACK_SCORE"]

    def compute_price_vs_stack(self) -> pd.Series:
        """F-004: Número de EMAs por debajo del precio [0–5]."""
        cols = [f"EMA_{n}" for n in [9, 21, 55, 100, 200]]
        self.df["PRICE_VS_STACK"] = self.df.apply(
            lambda r: sum(r["close"] > r[c] for c in cols), axis=1
        ).astype(int)
        return self.df["PRICE_VS_STACK"]

    def compute_slopes(self) -> pd.DataFrame:
        """F-005: Pendiente porcentual de EMA_9 y EMA_55 (y auxiliares para SLOPE_SYNC)."""
        for n in [9, 21, 55, 100, 200]:
            col = f"EMA_{n}"
            self.df[f"SLOPE_{n}"] = (
                (self.df[col] - self.df[col].shift(1)) / self.df[col].shift(1)
            ) * 100
        return self.df

    def compute_spreads(self) -> pd.DataFrame:
        """F-006: Separación relativa porcentual entre pares de EMAs."""
        pairs = [(9, 21), (21, 55), (55, 100), (100, 200)]
        for fast, slow in pairs:
            self.df[f"SPREAD_{fast}_{slow}"] = (
                (self.df[f"EMA_{fast}"] - self.df[f"EMA_{slow}"])
                / self.df[f"EMA_{slow}"]
            ) * 100
        return self.df

    def compute_elasticity(self) -> pd.Series:
        """F-007: Distancia relativa precio vs EMA_200 (equilibrio macro)."""
        self.df["ELASTICITY"] = (
            (self.df["close"] - self.df["EMA_200"]) / self.df["EMA_200"]
        ) * 100
        return self.df["ELASTICITY"]

    def compute_volume_ratio(self, window: int = 20) -> pd.Series:
        """F-008: Ratio volumen actual / promedio N velas anteriores."""
        avg = self.df["volume"].shift(1).rolling(window).mean()
        self.df["VOLUME_RATIO"] = self.df["volume"] / avg
        return self.df["VOLUME_RATIO"]

    def compute_slope_direction(self) -> pd.Series:
        """
        F-009: Dirección predominante — requiere acuerdo entre SLOPE_9 y SLOPE_55.
        UP | DOWN | NEUTRAL
        """
        def direction(row):
            s9, s55 = row["SLOPE_9"], row["SLOPE_55"]
            if pd.isna(s9) or pd.isna(s55):
                return "NEUTRAL"
            if s9 > 0 and s55 > 0:
                return "UP"
            if s9 < 0 and s55 < 0:
                return "DOWN"
            return "NEUTRAL"

        self.df["SLOPE_DIRECTION"] = self.df.apply(direction, axis=1)
        return self.df["SLOPE_DIRECTION"]

    # ═══════════════════════════════════════════════════════════════
    # BLOQUE 2 — COMPRESIÓN Y DERIVADAS (L2 Grupo B)
    # ═══════════════════════════════════════════════════════════════

    def compute_compression_index(self) -> pd.Series:
        """F-010: Promedio de spreads absolutos entre pares contiguos."""
        self.df["COMPRESSION_INDEX"] = (
            self.df["SPREAD_9_21"].abs()   +
            self.df["SPREAD_21_55"].abs()  +
            self.df["SPREAD_55_100"].abs() +
            self.df["SPREAD_100_200"].abs()
        ) / 4
        return self.df["COMPRESSION_INDEX"]

    def compute_curvatures(self) -> pd.DataFrame:
        """F-015: Curvatura = derivada de pendiente (SLOPE_t - SLOPE_t-1)."""
        for n in [9, 55]:
            self.df[f"CURVATURE_{n}"] = (
                self.df[f"SLOPE_{n}"] - self.df[f"SLOPE_{n}"].shift(1)
            )
        return self.df

    def compute_persistence_above_21(self) -> pd.Series:
        """
        F-016: Contador con signo de velas consecutivas sobre/bajo EMA-21.
        Positivo = sobre EMA-21, negativo = bajo EMA-21.
        """
        above = (self.df["close"] > self.df["EMA_21"]).astype(int)
        result = [0] * len(self.df)

        for i in range(1, len(self.df)):
            prev = result[i-1]
            if above.iloc[i] == 1:   # precio sobre EMA-21
                result[i] = max(prev, 0) + 1
            else:                     # precio bajo EMA-21
                result[i] = min(prev, 0) - 1

        self.df["PERSISTENCE_ABOVE_21"] = result
        return self.df["PERSISTENCE_ABOVE_21"]

    def compute_bounce_counts(self, window: int = 50) -> pd.DataFrame:
        """
        F-020: Conteo de rebotes en EMA-n en ventana de N velas.
        Un rebote = EMA tocada + precio cierra mismo lado que 2 velas atrás.
        """
        for n in [9, 21, 55, 200]:
            ema_col = f"EMA_{n}"
            counts  = [0] * len(self.df)

            for i in range(2, len(self.df)):
                start   = max(1, i - window + 1)
                bounces = 0

                for k in range(start, i + 1):
                    if k < 2:
                        continue
                    lo   = min(self.df["close"].iloc[k], self.df["close"].iloc[k-1])
                    hi   = max(self.df["close"].iloc[k], self.df["close"].iloc[k-1])
                    ema  = self.df[ema_col].iloc[k]

                    if lo <= ema <= hi:   # EMA tocada en esa vela
                        side_now  = np.sign(self.df["close"].iloc[k]   - ema)
                        side_prev = np.sign(self.df["close"].iloc[k-2] - self.df[ema_col].iloc[k-2])
                        if side_now == side_prev and side_now != 0:
                            bounces += 1

                counts[i] = bounces

            self.df[f"BOUNCE_COUNT_{n}"] = counts

        return self.df

    def compute_cross_events(self) -> pd.DataFrame:
        """
        F-021: Eventos de cruce entre pares de EMAs.
        Produce columnas: CROSS_{fast}_{slow}_occurred, _direction, _magnitude.
        """
        pairs = [(9, 21), (21, 55), (55, 200)]

        for fast, slow in pairs:
            f_col = f"EMA_{fast}"
            s_col = f"EMA_{slow}"
            prefix = f"CROSS_{fast}_{slow}"

            f_now  = self.df[f_col]
            s_now  = self.df[s_col]
            f_prev = self.df[f_col].shift(1)
            s_prev = self.df[s_col].shift(1)

            bull = (f_prev <= s_prev) & (f_now > s_now)
            bear = (f_prev >= s_prev) & (f_now < s_now)

            occurred  = bull | bear
            direction = pd.Series("NONE", index=self.df.index)

            # Para el par 55/200 usar Golden/Death
            if fast == 55 and slow == 200:
                direction[bull] = "GOLDEN_CROSS"
                direction[bear] = "DEATH_CROSS"
            else:
                direction[bull] = "BULLISH"
                direction[bear] = "BEARISH"

            magnitude = ((f_now - s_now).abs() / s_now * 100).where(occurred, 0.0)

            self.df[f"{prefix}_occurred"]  = occurred
            self.df[f"{prefix}_direction"] = direction
            self.df[f"{prefix}_magnitude"] = magnitude

        return self.df

    def compute_atr_relative(self, period: int = 14) -> pd.Series:
        """F-022: ATR de 14 períodos normalizado por precio."""
        prev_close = self.df["close"].shift(1)
        tr = pd.concat([
            self.df["high"] - self.df["low"],
            (self.df["high"] - prev_close).abs(),
            (self.df["low"]  - prev_close).abs(),
        ], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()
        self.df["ATR_RELATIVE"] = (atr / self.df["close"]) * 100
        return self.df["ATR_RELATIVE"]

    # ═══════════════════════════════════════════════════════════════
    # BLOQUE 2 — SEGUNDA DERIVADA Y TEMPORAL (L2 Grupo C)
    # ═══════════════════════════════════════════════════════════════

    def compute_spread_velocity(self) -> pd.Series:
        """F-013: Derivada primera del COMPRESSION_INDEX (puntos/vela)."""
        self.df["SPREAD_VELOCITY"] = (
            self.df["COMPRESSION_INDEX"] - self.df["COMPRESSION_INDEX"].shift(1)
        )
        return self.df["SPREAD_VELOCITY"]

    def compute_compression_duration(self, theta: float = 0.5) -> pd.Series:
        """
        F-017: Velas consecutivas con COMPRESSION_INDEX <= theta.
        theta = 0.5 por defecto (provisional, calibrar en VRM).
        """
        below   = (self.df["COMPRESSION_INDEX"] <= theta).astype(int)
        counts  = [0] * len(self.df)

        for i in range(1, len(self.df)):
            counts[i] = (counts[i-1] + 1) if below.iloc[i] else 0

        self.df["COMPRESSION_DURATION"] = counts
        return self.df["COMPRESSION_DURATION"]

    def compute_slope_sync(self) -> pd.Series:
        """
        F-018: % de EMAs cuya pendiente concuerda con SLOPE_DIRECTION.
        100% = todas apuntan igual.
        """
        def sync(row):
            direction = row["SLOPE_DIRECTION"]
            if direction == "NEUTRAL":
                return 0.0
            sign = 1 if direction == "UP" else -1
            count = sum(
                1 for n in [9, 21, 55, 100, 200]
                if not pd.isna(row[f"SLOPE_{n}"]) and np.sign(row[f"SLOPE_{n}"]) == sign
            )
            return (count / 5) * 100

        self.df["SLOPE_SYNC"] = self.df.apply(sync, axis=1)
        return self.df["SLOPE_SYNC"]

    # ═══════════════════════════════════════════════════════════════
    # BLOQUE 3 — TERCERA DERIVADA
    # ═══════════════════════════════════════════════════════════════

    def compute_spread_acceleration(self) -> pd.Series:
        """F-014: Derivada segunda del CI = diferencia de velocidades."""
        self.df["SPREAD_ACCELERATION"] = (
            self.df["SPREAD_VELOCITY"] - self.df["SPREAD_VELOCITY"].shift(1)
        )
        return self.df["SPREAD_ACCELERATION"]

    # ═══════════════════════════════════════════════════════════════
    # VARIABLES COMPUESTAS (L3 via fórmula — sin BRM)
    # ═══════════════════════════════════════════════════════════════

    def compute_coherence_score(self) -> pd.Series:
        """
        F-011: Score de coherencia estructural [0–10].
        Composición ponderada: Stack 30% + Precio 30% + Sync 20% + Vol 10% + Bounce 10%.
        """
        C1 = self.df["STACK_SCORE"]
        C2 = self.df["PRICE_VS_STACK"] * 2
        C3 = self.df["SLOPE_SYNC"] / 10
        C4 = self.df["VOLUME_RATIO"].clip(0, 3) * (10 / 3)
        C5 = self.df["BOUNCE_COUNT_55"].clip(0, 10)

        self.df["COHERENCE_SCORE"] = (
            0.30 * C1 + 0.30 * C2 + 0.20 * C3 + 0.10 * C4 + 0.10 * C5
        ).clip(0, 10)
        return self.df["COHERENCE_SCORE"]

    def compute_friction_index(self) -> pd.Series:
        """
        F-012: Índice de fricción estructural [0–10].
        Alta fricción = compresión + baja elasticidad + bajo volumen.
        """
        F1 = (10 - (self.df["COMPRESSION_INDEX"] * 10).clip(0, 10))
        F2 = (10 - self.df["ELASTICITY"].abs().clip(0, 10))
        F3 = (10 - self.df["VOLUME_RATIO"].clip(0, 3) * (10 / 3))
        F4 = (self.df["COMPRESSION_DURATION"] / 5).clip(0, 10)
        F5 = (10 - (self.df["ATR_RELATIVE"] * 10).clip(0, 10))

        self.df["FRICTION_INDEX"] = (
            0.35 * F1 + 0.25 * F2 + 0.20 * F3 + 0.10 * F4 + 0.10 * F5
        ).clip(0, 10)
        return self.df["FRICTION_INDEX"]

    # ═══════════════════════════════════════════════════════════════
    # PIPELINE COMPLETO — Ejecuta todas las fórmulas en orden (FRM Apéndice A)
    # ═══════════════════════════════════════════════════════════════

    def run_all(self, theta_compress: float = 0.5) -> pd.DataFrame:
        """
        Ejecuta el pipeline FRM completo en el orden definido en
        EIM-FRM-001 Apéndice A (Pasos 1–6).

        Args:
            theta_compress: Umbral θ-001 de compresión (provisional 0.5).

        Returns:
            DataFrame con todas las variables L0-L2 calculadas.
        """
        print("[EIM FRM] Iniciando pipeline de fórmulas...")

        # Paso 2: L1 — Instrumentos
        self.compute_emas()

        # Paso 3: L2 Grupo A — Posición y pendientes
        self.compute_stack_order()
        self.compute_stack_score()
        self.compute_price_vs_stack()
        self.compute_slopes()
        self.compute_spreads()
        self.compute_elasticity()
        self.compute_volume_ratio()
        self.compute_slope_direction()

        # Paso 4: L2 Grupo B — Derivadas y temporales
        self.compute_compression_index()
        self.compute_curvatures()
        self.compute_persistence_above_21()
        self.compute_bounce_counts()
        self.compute_cross_events()
        self.compute_atr_relative()

        # Paso 5: L2 Grupo C — Segunda derivada y sync
        self.compute_spread_velocity()
        self.compute_compression_duration(theta=theta_compress)
        self.compute_slope_sync()

        # Paso 6: Tercera derivada
        self.compute_spread_acceleration()

        # Paso 7: Variables compuestas L3 (vía fórmula)
        self.compute_coherence_score()
        self.compute_friction_index()

        l2_cols = [c for c in self.df.columns if c not in
                   ["timestamp","symbol","timeframe","open","high","low","close","volume"]]
        print(f"[EIM FRM] Completado — {len(l2_cols)} variables calculadas.")
        return self.df
