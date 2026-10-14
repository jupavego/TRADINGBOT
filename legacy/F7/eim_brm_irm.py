"""
EIM-F7 | Módulo 3: BRM + IRM
==============================
Implementa EIM-BRM-001 v1.0.1 — Reglas R-001, R-002, R-003 + matriz de transiciones
Implementa EIM-IRM-001 v1.0.1 — DIAG-001 (4 etapas, 7 modificadores de confianza)
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone


# ─── Umbrales BRM (provisionales — calibrar en VRM Fase VI) ──────
@dataclass
class BRMThresholds:
    """
    Umbrales θ-001 a θ-007 definidos en EIM-BRM-001.
    Todos los valores son provisionales hasta calibración.
    """
    theta_001_compress:     float = 0.50   # CI umbral compresión
    theta_002_expand:       float = 2.00   # CI umbral expansión
    theta_003_elastic:      float = 5.00   # Elasticidad significativa
    theta_004_velocity:     float = 0.05   # Velocidad estable
    theta_005_curvature:    float = 0.02   # Curvatura plana
    theta_006_duration:     int   = 5      # Duración mín. compresión (velas)
    theta_007_persistence:  int   = 3      # Persistencia mín. tendencia (velas)


# ─── Output del diagnóstico ───────────────────────────────────────
@dataclass
class StructuralDiagnosis:
    """
    DIAG-001: Output del motor de inferencia EIM.
    Ref: EIM-IRM-001 § Parte V.
    """
    # Metadatos
    timestamp:          str = ""
    timeframe:          str = ""
    symbol:             str = ""

    # Inputs L3 (para trazabilidad)
    structural_state:   str   = ""
    momentum_state:     str   = ""
    energy_state:       str   = ""
    coherence_score:    float = 0.0
    friction_index:     float = 0.0

    # Outputs del IRM
    conviction_score:   float = 0.0
    probable_scenario:  str   = ""
    confidence_score:   float = 0.0
    explanation:        str   = ""

    # Moduladores
    mtf_sync:           Optional[float] = None
    bounce_count_200:   int   = 0
    combination_status: str   = "NORMAL"
    transition_status:  str   = "N/A"

    # Versiones (trazabilidad documental)
    frm_version:        str = "EIM-FRM-001 v1.0.0"
    brm_version:        str = "EIM-BRM-001 v1.0.1"
    irm_version:        str = "EIM-IRM-001 v1.0.1"

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════
# BRM — MOTOR DE CLASIFICACIÓN DE ESTADOS
# ═══════════════════════════════════════════════════════════════════

class EIMBRM:
    """
    Implementación de EIM-BRM-001.
    Clasifica variables L2 en estados L3 categóricos.
    """

    def __init__(self, thresholds: BRMThresholds = None):
        self.θ = thresholds or BRMThresholds()

    # ── R-001: Estado Estructural ─────────────────────────────────
    def classify_structural_state(self, row: pd.Series) -> str:
        """
        R-001: Clasifica STRUCTURAL_STATE en E-01 a E-07.
        Jerarquía de evaluación: Compresión → Expansión → Fuerte → Ordenado
                                 → Agotado → Débil → Divergente.
        """
        θ = self.θ
        ci       = row.get("COMPRESSION_INDEX",    np.nan)
        cd       = row.get("COMPRESSION_DURATION", 0)
        cd_prev  = row.get("COMPRESSION_DURATION_PREV", 0)
        ci_prev  = row.get("COMPRESSION_INDEX_PREV", np.nan)
        sv       = row.get("SPREAD_VELOCITY",      np.nan)
        so       = row.get("STACK_ORDER",          "NEUTRAL")
        ss       = row.get("STACK_SCORE",          5.0)
        pvs      = row.get("PRICE_VS_STACK",       2)
        sd       = row.get("SLOPE_DIRECTION",      "NEUTRAL")

        # [1] Compresión activa
        if not pd.isna(ci) and ci <= θ.theta_001_compress and cd >= θ.theta_006_duration:
            return "E-05_COMPRESSED"

        # [2] Expansión activa (salida de compresión)
        if (not pd.isna(sv) and sv > θ.theta_004_velocity
                and (cd_prev >= 3 or (not pd.isna(ci_prev)
                     and ci_prev <= θ.theta_001_compress * 1.5))):
            return "E-06_EXPANDING"

        # [3] Tendencia fuerte alcista
        if (so == "BULL_PERFECT" and ss >= 7.5 and pvs >= 4 and sd == "UP"):
            return "E-01_TREND_STRONG"

        # [3] Tendencia fuerte bajista
        if (so == "BEAR_PERFECT" and ss <= 2.5 and pvs <= 1 and sd == "DOWN"):
            return "E-01_TREND_STRONG"

        # [4] Ordenado
        if ss >= 5.0 and sd != "NEUTRAL":
            return "E-03_ORDERED"

        # [5] Agotado
        if (so in ["BULL_PARTIAL", "BEAR_PARTIAL"]
                and not pd.isna(sv) and sv < -θ.theta_004_velocity):
            return "E-04_EXHAUSTED"

        # [6] Tendencia débil
        if ss >= 2.5 and sd != "NEUTRAL":
            return "E-02_TREND_WEAK"

        # [7] Default: divergente
        return "E-07_DIVERGENT"

    # ── R-002: Estado de Momentum ─────────────────────────────────
    def classify_momentum_state(self, row: pd.Series) -> str:
        """
        R-002: Clasifica MOMENTUM_STATE.
        REVERSING → ACCELERATING → DECELERATING → STABLE.

        Ref: EIM-BRM-001 § R-002, C-008 — direction_changed compara contra
        SLOPE_DIRECTION[t-3] (no t-1); el pseudocódigo del BRM lo declara
        explícitamente como input (SLOPE_DIRECTION_T3). Comparar contra t-1
        dispara REVERSING con cualquier flip de una sola vela.
        """
        θ  = self.θ
        sd = row.get("SLOPE_DIRECTION", "NEUTRAL")
        sv = row.get("SPREAD_VELOCITY", np.nan)
        sa = row.get("SPREAD_ACCELERATION", np.nan)
        c9 = row.get("CURVATURE_9", np.nan)
        c55= row.get("CURVATURE_55", np.nan)

        cross_any = (
            row.get("CROSS_9_21_occurred",  False) or
            row.get("CROSS_21_55_occurred", False) or
            row.get("CROSS_55_200_occurred", False)
        )

        dir_sign = 1 if sd == "UP" else (-1 if sd == "DOWN" else 0)

        # Curvatura de EMA-55 opuesta a dirección con magnitud alta
        curve55_opposing = (
            dir_sign != 0 and not pd.isna(c55)
            and np.sign(c55) != dir_sign
            and abs(c55) > θ.theta_005_curvature * 3
        )

        sd_t3 = row.get("SLOPE_DIRECTION_T3", "NEUTRAL")
        direction_changed = (sd != sd_t3 and sd_t3 != "NEUTRAL")

        # [1] Reversión
        if cross_any or curve55_opposing or direction_changed:
            return "REVERSING"

        # [2] Aceleración
        if (not pd.isna(sv) and sv > θ.theta_004_velocity
                and not pd.isna(sa) and sa > 0
                and dir_sign != 0
                and not pd.isna(c9)  and np.sign(c9)  == dir_sign
                and not pd.isna(c55) and np.sign(c55) == dir_sign):
            return "ACCELERATING"

        # [3] Deceleración
        if (not pd.isna(sv) and sv < -θ.theta_004_velocity):
            return "DECELERATING"
        if (not pd.isna(sa) and sa < 0 and not pd.isna(sv) and sv > 0):
            return "DECELERATING"
        if (dir_sign != 0 and not pd.isna(c9)
                and np.sign(c9) != dir_sign and abs(c9) > θ.theta_005_curvature):
            return "DECELERATING"

        # [4] Estable
        return "STABLE"

    # ── R-003: Estado de Energía ──────────────────────────────────
    def classify_energy_state(self, row: pd.Series) -> str:
        """
        R-003: Clasifica ENERGY_STATE.
        COMPRESSED → HIGH_ENERGY → LOW_ENERGY → MODERATE_ENERGY.
        """
        θ  = self.θ
        ci = row.get("COMPRESSION_INDEX",    np.nan)
        cd = row.get("COMPRESSION_DURATION", 0)
        el = row.get("ELASTICITY",           np.nan)
        sv = row.get("SPREAD_VELOCITY",      np.nan)
        ar = row.get("ATR_RELATIVE",         np.nan)

        # [1] Compresión — energía potencial acumulada
        if not pd.isna(ci) and ci <= θ.theta_001_compress and cd >= θ.theta_006_duration:
            return "COMPRESSED"

        # [2] Alta energía cinética
        if (not pd.isna(ci) and ci > θ.theta_002_expand
                and not pd.isna(el) and abs(el) > θ.theta_003_elastic
                and not pd.isna(sv) and sv > θ.theta_004_velocity
                and not pd.isna(ar) and ar > 0.5):
            return "HIGH_ENERGY"

        # [3] Baja energía
        if (not pd.isna(ci) and ci <= θ.theta_002_expand
                and cd < θ.theta_006_duration
                and not pd.isna(el) and abs(el) <= θ.theta_003_elastic / 2
                and not pd.isna(ar) and ar < 0.3):
            return "LOW_ENERGY"

        # [4] Moderada — default
        return "MODERATE_ENERGY"

    def classify_row(self, row: pd.Series) -> dict:
        """Clasifica los tres estados L3 para una fila del DataFrame."""
        return {
            "STRUCTURAL_STATE": self.classify_structural_state(row),
            "MOMENTUM_STATE":   self.classify_momentum_state(row),
            "ENERGY_STATE":     self.classify_energy_state(row),
        }

    def run_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """Aplica R-001, R-002, R-003 sobre todo el DataFrame."""
        print("[EIM BRM] Clasificando estados L3...")

        # Añadir columnas de contexto previo necesarias para las reglas
        df = df.copy()
        df["COMPRESSION_DURATION_PREV"] = df["COMPRESSION_DURATION"].shift(1).fillna(0)
        df["COMPRESSION_INDEX_PREV"]    = df["COMPRESSION_INDEX"].shift(1)
        # R-002 C-008: direction_changed compara contra t-3, no t-1 (BRM-001 § R-002).
        df["SLOPE_DIRECTION_T3"]        = df["SLOPE_DIRECTION"].shift(3).fillna("NEUTRAL")

        states = [self.classify_row(row) for _, row in df.iterrows()]

        states_df = pd.DataFrame(states, index=df.index)
        df = pd.concat([df, states_df], axis=1)

        # Verificar combinaciones válidas
        df["COMBINATION_STATUS"] = df.apply(self._check_combination, axis=1)

        # Verificar transición desde el estado anterior contra la matriz de
        # transiciones válidas (BRM-001 § Parte III — antes no implementado).
        df["TRANSITION_STATUS"] = self._check_transitions(df["STRUCTURAL_STATE"])

        print(f"[EIM BRM] Completado.")
        print(f"  STRUCTURAL: {df['STRUCTURAL_STATE'].value_counts().to_dict()}")
        print(f"  MOMENTUM:   {df['MOMENTUM_STATE'].value_counts().to_dict()}")
        print(f"  ENERGY:     {df['ENERGY_STATE'].value_counts().to_dict()}")
        invalid = (df["TRANSITION_STATUS"] == "INVALID").sum()
        if invalid:
            print(f"  TRANSICIONES INVÁLIDAS detectadas: {invalid} (ver TRANSITION_STATUS)")
        return df

    # ── Matriz de Transiciones Válidas (BRM-001 § Parte III) ────────
    # Transiciones ✗: "no son físicamente posibles en un mercado real sin
    # pasar por un estado intermedio". No bloquean el diagnóstico, pero
    # deben registrarse como anomalía y reducir el confidence_score — nota
    # de implementación explícita en BRM-001 que no tenía código asociado
    # hasta ahora. Ver modificador M-007 en IRM-001 § Etapa 3 (añadido).
    VALID_TRANSITIONS = {
        "E-01_TREND_STRONG": {"E-01_TREND_STRONG", "E-02_TREND_WEAK", "E-03_ORDERED",
                               "E-04_EXHAUSTED", "E-07_DIVERGENT"},
        "E-02_TREND_WEAK":   {"E-01_TREND_STRONG", "E-02_TREND_WEAK", "E-03_ORDERED",
                               "E-04_EXHAUSTED", "E-05_COMPRESSED", "E-06_EXPANDING",
                               "E-07_DIVERGENT"},
        "E-03_ORDERED":      {"E-01_TREND_STRONG", "E-02_TREND_WEAK", "E-03_ORDERED",
                               "E-04_EXHAUSTED", "E-05_COMPRESSED", "E-06_EXPANDING",
                               "E-07_DIVERGENT"},
        "E-04_EXHAUSTED":    {"E-02_TREND_WEAK", "E-03_ORDERED", "E-04_EXHAUSTED",
                               "E-05_COMPRESSED", "E-07_DIVERGENT"},
        "E-05_COMPRESSED":   {"E-05_COMPRESSED", "E-06_EXPANDING", "E-07_DIVERGENT"},
        "E-06_EXPANDING":    {"E-01_TREND_STRONG", "E-02_TREND_WEAK", "E-03_ORDERED",
                               "E-06_EXPANDING", "E-07_DIVERGENT"},
        "E-07_DIVERGENT":    {"E-01_TREND_STRONG", "E-02_TREND_WEAK", "E-03_ORDERED",
                               "E-04_EXHAUSTED", "E-05_COMPRESSED", "E-06_EXPANDING",
                               "E-07_DIVERGENT"},
    }

    def _check_transitions(self, structural_state: pd.Series) -> pd.Series:
        """
        Verifica cada transición STRUCTURAL_STATE[t-1] → STRUCTURAL_STATE[t]
        contra VALID_TRANSITIONS. Primera vela (sin t-1) queda "N/A".
        """
        prev = structural_state.shift(1)

        def check(cur, prv):
            if pd.isna(prv):
                return "N/A"
            allowed = self.VALID_TRANSITIONS.get(prv, set())
            return "VALID" if cur in allowed else "INVALID"

        return pd.Series(
            [check(c, p) for c, p in zip(structural_state, prev)],
            index=structural_state.index,
        )

    def _check_combination(self, row: pd.Series) -> str:
        """Verifica la combinación de estados contra la matriz del BRM."""
        ss = row.get("STRUCTURAL_STATE", "")
        es = row.get("ENERGY_STATE",     "")

        # Combinaciones imposibles (BRM § Matriz de Combinaciones)
        impossibles = [
            ("E-05_COMPRESSED", "HIGH_ENERGY"),
            ("E-06_EXPANDING",  "COMPRESSED"),
        ]
        for s, e in impossibles:
            if ss == s and es == e:
                return "IMPOSIBLE"

        # Combinaciones inusuales
        unusual = [
            ("E-01_TREND_STRONG", "COMPRESSED"),
            ("E-04_EXHAUSTED",    "HIGH_ENERGY"),
        ]
        for s, e in unusual:
            if ss == s and es == e:
                return "INUSUAL"

        return "NORMAL"


# ═══════════════════════════════════════════════════════════════════
# IRM — MOTOR DE INFERENCIA Y DIAGNÓSTICO
# ═══════════════════════════════════════════════════════════════════

class EIMIRM:
    """
    Implementación de EIM-IRM-001.
    Produce STRUCTURAL_DIAGNOSIS a partir de los estados L3.
    """

    # ── Etapa 1: Conviction Score ─────────────────────────────────
    def compute_conviction_score(self, row: pd.Series) -> float:
        """
        IRM Etapa 1: Score de convicción [0–100].
        Ref: EIM-IRM-001 § Parte I.
        """
        ss = row.get("STRUCTURAL_STATE", "E-07_DIVERGENT")
        ms = row.get("MOMENTUM_STATE",   "STABLE")
        es = row.get("ENERGY_STATE",     "MODERATE_ENERGY")
        fi = row.get("FRICTION_INDEX",   5.0)
        sd = row.get("SLOPE_DIRECTION",  "NEUTRAL")
        so = row.get("STACK_ORDER",      "NEUTRAL")

        # Determinar dirección
        if sd == "UP":
            dir_sign = 1
        elif sd == "DOWN":
            dir_sign = -1
        else:
            dir_sign = 1 if so in ["BULL_PERFECT", "BULL_PARTIAL"] else -1

        # Tabla CS-001: Score base estructural
        base_map = {
            "E-01_TREND_STRONG": 95 if dir_sign == 1 else 5,
            "E-03_ORDERED":      75 if dir_sign == 1 else 25,
            "E-02_TREND_WEAK":   62 if dir_sign == 1 else 38,
            "E-06_EXPANDING":    70 if dir_sign == 1 else 30,
            "E-04_EXHAUSTED":    50,
            "E-05_COMPRESSED":   50,
            "E-07_DIVERGENT":    50,
        }
        S1 = base_map.get(ss, 50)

        # Tabla CS-002: Modificador momentum
        mult_map = {"ACCELERATING": 1.20, "STABLE": 1.00,
                    "DECELERATING": 0.80, "REVERSING": 0.60}
        S2 = 50 + (S1 - 50) * mult_map.get(ms, 1.0)

        # Tabla CS-003: Modificador energía
        energy_delta = {"HIGH_ENERGY": 8, "MODERATE_ENERGY": 0,
                        "LOW_ENERGY": -5, "COMPRESSED": 3}
        delta_e = energy_delta.get(es, 0) * np.sign(S2 - 50)
        S3 = S2 + delta_e

        # Tabla CS-004: Modificador fricción
        if fi >= 8.0:   fd = -8
        elif fi >= 5.0: fd = -3
        elif fi >= 2.0: fd = 0
        else:           fd = 4
        S4 = S3 + fd * np.sign(S3 - 50 + 1e-9)

        return float(np.clip(S4, 0, 100))

    # ── Etapa 2: Scenario Mapping ─────────────────────────────────
    def compute_scenario(self, row: pd.Series,
                          conviction: float,
                          mtf_sync:   Optional[float] = None) -> str:
        """
        IRM Etapa 2: Mapeo al escenario más probable.
        Aplica tabla de mapeo + 4 reglas de refinamiento SR-001 a SR-004.
        Ref: EIM-IRM-001 § Parte II.
        """
        ss = row.get("STRUCTURAL_STATE", "E-07_DIVERGENT")
        ms = row.get("MOMENTUM_STATE",   "STABLE")
        es = row.get("ENERGY_STATE",     "MODERATE_ENERGY")
        fi = row.get("FRICTION_INDEX",   5.0)
        cs = row.get("COHERENCE_SCORE",  5.0)
        bc200 = int(row.get("BOUNCE_COUNT_200", 0))

        # Tabla de mapeo primario
        scenario = self._primary_scenario(ss, ms, es)

        # SR-001: Alta fricción bloquea BREAKOUT
        if scenario == "SC-02_BREAKOUT" and fi >= 7.0:
            scenario = "SC-05_CONSOLIDATION"

        # SR-002: Baja convicción + baja coherencia → CONSOLIDATION
        if scenario == "SC-01_CONTINUATION" and 40 <= conviction <= 60 and cs < 5.0:
            scenario = "SC-05_CONSOLIDATION"

        # SR-003: BREAKOUT sin confirmación multi-TF
        if scenario == "SC-02_BREAKOUT" and mtf_sync is not None and mtf_sync < 50:
            scenario = "SC-01_CONTINUATION"

        # SR-004: PULLBACK sin historia en EMA-200 + EXHAUSTED
        if (scenario == "SC-03_PULLBACK" and bc200 == 0
                and ss == "E-04_EXHAUSTED"):
            scenario = "SC-04_STRUCTURAL_CHANGE"

        return scenario

    def _primary_scenario(self, ss: str, ms: str, es: str) -> str:
        """Tabla de mapeo primario (28 combinaciones)."""
        table = {
            ("E-01_TREND_STRONG", "ACCELERATING", "HIGH_ENERGY"):      "SC-01_CONTINUATION",
            ("E-01_TREND_STRONG", "ACCELERATING", "COMPRESSED"):       "SC-02_BREAKOUT",
            ("E-01_TREND_STRONG", "STABLE",       "HIGH_ENERGY"):      "SC-01_CONTINUATION",
            ("E-01_TREND_STRONG", "STABLE",       "MODERATE_ENERGY"):  "SC-01_CONTINUATION",
            ("E-01_TREND_STRONG", "DECELERATING", None):               "SC-03_PULLBACK",
            ("E-01_TREND_STRONG", "REVERSING",    None):               "SC-04_STRUCTURAL_CHANGE",
            ("E-03_ORDERED",      "ACCELERATING", None):               "SC-01_CONTINUATION",
            ("E-03_ORDERED",      "STABLE",       "MODERATE_ENERGY"):  "SC-01_CONTINUATION",
            ("E-03_ORDERED",      "STABLE",       "LOW_ENERGY"):       "SC-05_CONSOLIDATION",
            ("E-03_ORDERED",      "DECELERATING", None):               "SC-03_PULLBACK",
            ("E-03_ORDERED",      "REVERSING",    None):               "SC-04_STRUCTURAL_CHANGE",
            ("E-02_TREND_WEAK",   "ACCELERATING", None):               "SC-01_CONTINUATION",
            ("E-02_TREND_WEAK",   "STABLE",       None):               "SC-05_CONSOLIDATION",
            ("E-02_TREND_WEAK",   "DECELERATING", None):               "SC-03_PULLBACK",
            ("E-02_TREND_WEAK",   "REVERSING",    None):               "SC-04_STRUCTURAL_CHANGE",
            ("E-04_EXHAUSTED",    "ACCELERATING", None):               "SC-03_PULLBACK",
            ("E-04_EXHAUSTED",    "STABLE",       None):               "SC-03_PULLBACK",
            ("E-04_EXHAUSTED",    "DECELERATING", None):               "SC-04_STRUCTURAL_CHANGE",
            ("E-04_EXHAUSTED",    "REVERSING",    None):               "SC-04_STRUCTURAL_CHANGE",
            ("E-05_COMPRESSED",   "STABLE",       "COMPRESSED"):       "SC-02_BREAKOUT",
            ("E-05_COMPRESSED",   "ACCELERATING", None):               "SC-02_BREAKOUT",
            ("E-05_COMPRESSED",   "DECELERATING", None):               "SC-05_CONSOLIDATION",
            ("E-05_COMPRESSED",   "REVERSING",    None):               "SC-04_STRUCTURAL_CHANGE",
            ("E-06_EXPANDING",    "ACCELERATING", "HIGH_ENERGY"):      "SC-02_BREAKOUT",
            ("E-06_EXPANDING",    "ACCELERATING", "MODERATE_ENERGY"):  "SC-01_CONTINUATION",
            ("E-06_EXPANDING",    "STABLE",       None):               "SC-01_CONTINUATION",
            ("E-06_EXPANDING",    "DECELERATING", None):               "SC-03_PULLBACK",
            ("E-06_EXPANDING",    "REVERSING",    None):               "SC-04_STRUCTURAL_CHANGE",
        }

        # Buscar coincidencia exacta primero
        key_exact = (ss, ms, es)
        if key_exact in table:
            return table[key_exact]

        # Buscar con energy=None (wildcard)
        key_wild = (ss, ms, None)
        if key_wild in table:
            return table[key_wild]

        # Default para DIVERGENT o no encontrado
        return "SC-05_CONSOLIDATION"

    # ── Etapa 3: Confidence Score ─────────────────────────────────
    def compute_confidence_score(self, row: pd.Series,
                                  scenario:         str,
                                  conviction:       float,
                                  mtf_sync:         Optional[float],
                                  comb_status:      str,
                                  transition_status: str = "N/A") -> float:
        """
        IRM Etapa 3: Score de confianza [0–95].
        Base en COHERENCE_SCORE + 7 modificadores (M-001 a M-007).
        Ref: EIM-IRM-001 § Parte III.
        """
        cs   = row.get("COHERENCE_SCORE", 5.0)
        fi   = row.get("FRICTION_INDEX",  5.0)
        es   = row.get("ENERGY_STATE",    "MODERATE_ENERGY")
        bc200= int(row.get("BOUNCE_COUNT_200", 0))

        score = cs * 10   # Base [0–100]

        # M-001: MTF_SYNC
        if mtf_sync is not None:
            if   mtf_sync >= 75: score += 10
            elif mtf_sync >= 50: score += 5
            elif mtf_sync >= 25: score += 0
            else:                score -= 15

        # M-002: BOUNCE_COUNT_200
        if   bc200 >= 5: score += 8
        elif bc200 >= 3: score += 5
        elif bc200 >= 1: score += 2
        else:            score -= 5

        # M-003: Combinación
        if   comb_status == "IMPOSIBLE": score -= 50
        elif comb_status == "INUSUAL":   score -= 10

        # M-004: Fricción vs Escenario
        if scenario == "SC-02_BREAKOUT"      and fi >= 6.0: score -= 10
        if scenario == "SC-01_CONTINUATION"  and fi <  3.0: score += 5

        # M-005: Conviction extremo
        if conviction >= 85 or conviction <= 15: score += 8
        if 45 <= conviction <= 55:               score -= 8

        # M-006: Energía vs Escenario
        if scenario == "SC-02_BREAKOUT"     and es == "COMPRESSED":    score += 10
        if scenario == "SC-01_CONTINUATION" and es == "LOW_ENERGY":    score -= 8

        # M-007: Transición inválida de STRUCTURAL_STATE (BRM-001 § Parte III
        # — matriz de transiciones. Penalidad análoga a INUSUAL de M-003, ya
        # que ambas son "no bloquea el diagnóstico, reduce confianza". Valor
        # provisional, no fijado numéricamente en el documento original —
        # sujeto a calibración en Fase VI como el resto de modificadores.)
        if transition_status == "INVALID": score -= 10

        return float(np.clip(score, 0, 95))

    # ── Etapa 4: Explanation ──────────────────────────────────────
    def generate_explanation(self, row: pd.Series,
                              scenario:   str,
                              conviction: float,
                              confidence: float,
                              mtf_sync:   Optional[float],
                              transition_status: str = "N/A") -> str:
        """
        IRM Etapa 4: Narrativa explicativa del diagnóstico.
        Ref: EIM-IRM-001 § Parte IV.
        """
        ss  = row.get("STRUCTURAL_STATE", "")
        ms  = row.get("MOMENTUM_STATE",   "")
        es  = row.get("ENERGY_STATE",     "")
        cs  = row.get("COHERENCE_SCORE",  0.0)
        fi  = row.get("FRICTION_INDEX",   0.0)
        sd  = row.get("SLOPE_DIRECTION",  "NEUTRAL")
        bc200 = int(row.get("BOUNCE_COUNT_200", 0))

        state_labels = {
            "E-01_TREND_STRONG": "tendencia fuerte",
            "E-02_TREND_WEAK":   "tendencia débil",
            "E-03_ORDERED":      "estructura ordenada",
            "E-04_EXHAUSTED":    "estructura agotada",
            "E-05_COMPRESSED":   "compresión estructural",
            "E-06_EXPANDING":    "expansión estructural",
            "E-07_DIVERGENT":    "estructura divergente",
        }
        energy_suffix = {
            "COMPRESSED":       " — alta energía potencial acumulada",
            "HIGH_ENERGY":      " — expansión activa en progreso",
            "LOW_ENERGY":       " — capacidad de movimiento reducida",
            "MODERATE_ENERGY":  "",
        }
        scenario_labels = {
            "SC-01_CONTINUATION":      "continuación",
            "SC-02_BREAKOUT":          "ruptura",
            "SC-03_PULLBACK":          "pullback",
            "SC-04_STRUCTURAL_CHANGE": "cambio estructural",
            "SC-05_CONSOLIDATION":     "consolidación",
        }
        scenario_desc = {
            "SC-01_CONTINUATION":      "persistencia del estado actual sin señales de reversión",
            "SC-02_BREAKOUT":          "salida de estructura con cambio significativo en propiedades",
            "SC-03_PULLBACK":          "corrección temporal hacia referencia estructural",
            "SC-04_STRUCTURAL_CHANGE": "reconfiguración sostenida de la organización interna",
            "SC-05_CONSOLIDATION":     "ausencia de tendencia definida — propiedades oscilan sin dirección",
        }

        conv_label = "alta" if conviction > 60 else ("moderada" if conviction >= 40 else "baja")
        coh_label  = ("alta — diagnóstico confiable" if cs >= 8
                      else "moderada — diagnóstico válido con reservas" if cs >= 5
                      else "baja — señales contradictorias")

        parts = [
            f"El mercado presenta {state_labels.get(ss, ss)}.",
            f"El momentum es {ms.lower()} con dirección {sd} y {conv_label} convicción.",
            f"La energía estructural es {es.replace('_', ' ').lower()}"
            f"{energy_suffix.get(es, '')}.",
            f"La coherencia estructural es {cs:.1f}/10 ({coh_label}).",
            f"El escenario más probable es {scenario_labels.get(scenario, scenario)}: "
            f"{scenario_desc.get(scenario, '')}. "
            f"Confianza del diagnóstico: {confidence:.1f}%.",
        ]

        if mtf_sync is not None:
            mtf_label = ("alta confirmación" if mtf_sync >= 75
                         else "confirmación parcial" if mtf_sync >= 50
                         else "sin confirmación")
            parts.append(f"Confirmación multi-timeframe: {mtf_sync:.0f}% ({mtf_label}).")

        if fi >= 6.0:
            parts.append(f"Alta fricción estructural ({fi:.1f}/10) "
                         f"limita la velocidad del movimiento esperado.")

        if bc200 >= 3:
            parts.append(f"El precio ha respetado la EMA-200 {bc200} veces "
                         f"en la ventana actual, confirmando el régimen macro.")

        if transition_status == "INVALID":
            parts.append(
                "Anomalía: la transición desde el estado estructural anterior no figura "
                "en la matriz de transiciones válidas de EIM-BRM-001 — no bloquea el "
                "diagnóstico, pero reduce la confianza y debería revisarse."
            )

        return " ".join(parts)

    # ── DIAG-001: Diagnóstico completo ───────────────────────────
    def diagnose_row(self, row: pd.Series,
                      comb_status: str = "NORMAL",
                      mtf_sync:    Optional[float] = None,
                      transition_status: str = "N/A") -> StructuralDiagnosis:
        """
        Produce DIAG-001 para una observación.
        Ejecuta las 4 etapas del IRM secuencialmente.
        """
        conviction = self.compute_conviction_score(row)
        scenario   = self.compute_scenario(row, conviction, mtf_sync)
        confidence = self.compute_confidence_score(
            row, scenario, conviction, mtf_sync, comb_status, transition_status
        )
        explanation = self.generate_explanation(
            row, scenario, conviction, confidence, mtf_sync, transition_status
        )

        ts = row.get("timestamp", "")
        if hasattr(ts, "strftime"):
            ts = ts.strftime("%Y-%m-%dT%H:%M:%SZ")

        return StructuralDiagnosis(
            timestamp         = str(ts),
            timeframe         = str(row.get("timeframe", "")),
            symbol            = str(row.get("symbol", "")),
            structural_state  = str(row.get("STRUCTURAL_STATE", "")),
            momentum_state    = str(row.get("MOMENTUM_STATE", "")),
            energy_state      = str(row.get("ENERGY_STATE", "")),
            coherence_score   = float(row.get("COHERENCE_SCORE", 0)),
            friction_index    = float(row.get("FRICTION_INDEX", 0)),
            conviction_score  = round(conviction, 2),
            probable_scenario = scenario,
            confidence_score  = round(confidence, 2),
            explanation       = explanation,
            mtf_sync          = mtf_sync,
            bounce_count_200  = int(row.get("BOUNCE_COUNT_200", 0)),
            combination_status= comb_status,
            transition_status = transition_status,
        )

    def run_all(self, df: pd.DataFrame,
                 mtf_sync: Optional[float] = None) -> pd.DataFrame:
        """Aplica el motor de inferencia sobre todo el DataFrame."""
        print("[EIM IRM] Generando diagnósticos...")

        records = []
        for _, row in df.iterrows():
            comb  = row.get("COMBINATION_STATUS", "NORMAL")
            trans = row.get("TRANSITION_STATUS", "N/A")
            diag = self.diagnose_row(row, comb_status=comb, mtf_sync=mtf_sync,
                                      transition_status=trans)
            records.append({
                "CONVICTION_SCORE":   diag.conviction_score,
                "PROBABLE_SCENARIO":  diag.probable_scenario,
                "CONFIDENCE_SCORE":   diag.confidence_score,
                # NO reincluir COMBINATION_STATUS/TRANSITION_STATUS aquí: ya
                # existen en df (los agregó EIMBRM.run_all) — duplicarlos
                # produce dos columnas con el mismo nombre tras el concat de
                # abajo, y cualquier .get() posterior sobre una fila deja de
                # devolver un escalar (rompe con "truth value of a Series is
                # ambiguous"). Bug real encontrado al probar el pipeline
                # completo con datos sintéticos.
            })

        diag_df = pd.DataFrame(records, index=df.index)
        df = pd.concat([df, diag_df], axis=1)

        print(f"[EIM IRM] Completado.")
        print(f"  Escenarios: {df['PROBABLE_SCENARIO'].value_counts().to_dict()}")
        return df
