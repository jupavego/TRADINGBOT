"""
EIM-F7 | Módulo 4: Engine Principal
=====================================
Orquesta el pipeline completo:
    EIMDataFeed → EIMFRM → EIMBRM → EIMIRM → DIAG-001

Modos:
    - histórico: analiza series históricas
    - tiempo real: diagnostica la vela actual
    - backtesting: protocolo EIM-VRM-001

Uso:
    python eim_engine.py
    python eim_engine.py --symbol ETHUSDT --timeframe 1h --mode realtime
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

from eim_data    import EIMDataFeed
from eim_frm     import EIMFRM
from eim_brm_irm import EIMBRM, EIMIRM, BRMThresholds, StructuralDiagnosis

# El motor imprime caracteres unicode (→, ═, θ...); en Windows el codepage
# de consola por defecto (cp1252) no los soporta y revienta el print. Mismo
# fix ya aplicado en eim_web.py — aquí faltaba, y el CLI directo
# (`python eim_engine.py`) crasheaba en la primera línea con caja Unicode.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ─── Rutas del proyecto ────────────────────────────────────────────
BASE_PATH = Path(
    r"E:\REGIONAL ANTIOQUIA\GESTION SUPERVISION REGIONAL"
    r"\VIDEOCONFERENCIAS\7. 2026\6. JUNIO\27-06-2026 EIM"
)
F7_OUTPUT = BASE_PATH / "F7"

# ─── Umbrales de aceptación EIM-VRM-001 § Capítulo 6 ──────────────
# (threshold, criticidad) — criticidad BLOQUEANTE detiene el paso a Fase VII
# si falla; ADVERTENCIA solo se documenta. Los umbrales son los del propio
# documento VRM, no inventados aquí.
CA_THRESHOLDS = {
    "CA-001": (0.60, "BLOQUEANTE"),   # MET-001 Accuracy Global >= 60%
    "CA-002": (0.55, "BLOQUEANTE"),   # MET-002 Accuracy por escenario >= 55% c/u
    "CA-003": (0.50, "BLOQUEANTE"),   # MET-003 F1 en E-01/E-03/E-05 >= 0.50
    "CA-004": (0.10, "BLOQUEANTE"),   # MET-004 Calibration Error <= 0.10
    "CA-005": (0.85, "BLOQUEANTE"),   # MET-005 Stability >= 0.85
    "CA-006": (1.00, "BLOQUEANTE"),   # MET-006 Coverage = 100%
    "CA-007": (0.65, "ADVERTENCIA"),  # MET-007 Cross-TF Consistency >= 65%
    "CA-008": (3,    "ADVERTENCIA"),  # MET-008 Detection Latency <= 3 velas (4h)
    "CA-009": (0.80, "BLOQUEANTE"),   # AO-002 Accuracy adverso >= global*0.80
    "CA-010": (0.55, "ADVERTENCIA"),  # AO-003 Cross-instrument >= 55%
}
CRITICAL_STATES = ["E-01_TREND_STRONG", "E-03_ORDERED", "E-05_COMPRESSED"]


# ═══════════════════════════════════════════════════════════════════
# ENGINE PRINCIPAL
# ═══════════════════════════════════════════════════════════════════

class EIMEngine:
    """
    Motor principal del EIM.
    Orquesta todos los módulos del pipeline.
    """

    def __init__(
        self,
        symbol:    str = "BTCUSDT",
        timeframe: str = "4h",
        api_key:   str = "",
        api_secret:str = "",
        thresholds: BRMThresholds = None,
    ):
        self.symbol    = symbol.upper()
        self.timeframe = timeframe
        self.thresholds = thresholds or BRMThresholds()

        # Módulos
        self.feed = EIMDataFeed(api_key, api_secret)
        self.brm  = EIMBRM(self.thresholds)
        self.irm  = EIMIRM()

        print(f"\n{'='*60}")
        print(f"  EMA Intelligence Model — EIM v1.0")
        print(f"  Instrumento: {self.symbol} | Timeframe: {self.timeframe}")
        print(f"{'='*60}\n")

    # ── Modo histórico ────────────────────────────────────────────
    def run_historical(
        self,
        candles: int = 1000,
        save:    bool = True,
    ) -> pd.DataFrame:
        """
        Corre el pipeline completo sobre N velas históricas.

        Args:
            candles: Número de velas a analizar (mín 400).
            save:    Si True, guarda resultados en F7/.

        Returns:
            DataFrame con todas las variables y diagnósticos.
        """
        print("[EIM Engine] Modo: HISTÓRICO")

        # 1. Datos
        df = self.feed.get_historical(self.symbol, self.timeframe, candles)

        # 2. FRM
        frm = EIMFRM(df)
        df  = frm.run_all()

        # 3. BRM
        df = self.brm.run_all(df)

        # 4. IRM
        df = self.irm.run_all(df)

        # 5. Resumen
        self._print_summary(df)

        # 6. Guardar
        if save:
            self._save_results(df, mode="historical")

        return df

    # ── Modo tiempo real ─────────────────────────────────────────
    def run_realtime(
        self,
        context: int = 500,
    ) -> StructuralDiagnosis:
        """
        Diagnostica la vela actual con contexto histórico suficiente.

        Args:
            context: Velas de contexto para warmup (mín 400).

        Returns:
            StructuralDiagnosis de la vela actual.
        """
        print("[EIM Engine] Modo: TIEMPO REAL")

        # 1. Datos con contexto
        df = self.feed.get_realtime_with_context(self.symbol, self.timeframe, context)

        # 2. FRM
        frm = EIMFRM(df)
        df  = frm.run_all()

        # 3. BRM
        df = self.brm.run_all(df)

        # 4. IRM — diagnóstico de la última vela
        last_row  = df.iloc[-1]
        comb      = last_row.get("COMBINATION_STATUS", "NORMAL")
        trans     = last_row.get("TRANSITION_STATUS", "N/A")
        diagnosis = self.irm.diagnose_row(last_row, comb_status=comb, transition_status=trans)

        # 5. Imprimir diagnóstico actual
        self._print_diagnosis(diagnosis)

        return diagnosis

    # ── Modo backtesting (VRM) ────────────────────────────────────
    def run_backtest(
        self,
        candles:  int = 2000,
        horizon:  int = 6,
        save:     bool = True,
    ) -> dict:
        """
        Protocolo de backtesting EIM-VRM-001.
        Evalúa la calidad del diagnóstico sobre datos históricos.

        Args:
            candles: Total de velas para el backtest.
            horizon: Velas hacia adelante para evaluar cada diagnóstico.
            save:    Si True, guarda reporte en F7/.

        Returns:
            Diccionario con MET-001 a MET-006 y MET-008 (MET-007 no
            evaluado — requiere correr el pipeline en varios timeframes
            simultáneamente, ver notas en el reporte) y el veredicto
            CA-001 a CA-010 de EIM-VRM-001 § Capítulo 6.
        """
        print(f"[EIM Engine] Modo: BACKTESTING | Horizon: {horizon} velas")

        # 1. Pipeline completo
        df = self.run_historical(candles, save=False)

        # 2. Evaluar diagnósticos (excluir warmup y últimas 'horizon' velas)
        start = 400
        end   = len(df) - horizon
        eval_df = df.iloc[start:end].copy()

        correct       = []
        state_true    = []
        state_pred    = []
        scenario_list = []
        confidence_list = []

        for i in range(len(eval_df)):
            idx      = start + i
            diag_row = df.iloc[idx]
            future   = df.iloc[idx+1 : idx+horizon+1]

            scenario  = diag_row.get("PROBABLE_SCENARIO", "SC-05_CONSOLIDATION")
            ss_now    = diag_row.get("STRUCTURAL_STATE",  "E-07_DIVERGENT")
            ss_future = future["STRUCTURAL_STATE"].mode()
            ss_future = ss_future.iloc[0] if len(ss_future) else "E-07_DIVERGENT"

            is_correct = self._evaluate_diagnosis(scenario, ss_now, ss_future, future)
            correct.append(is_correct)
            state_true.append(ss_future)
            state_pred.append(ss_now)
            scenario_list.append(scenario)
            confidence_list.append(float(diag_row.get("CONFIDENCE_SCORE", 0.0)))

        met001 = self._met001_accuracy_global(correct)
        met002 = self._met002_accuracy_by_scenario(correct, scenario_list)
        met003 = self._met003_f1_by_state(state_true, state_pred)
        met004 = self._met004_calibration_error(correct, confidence_list)
        met005 = self._compute_stability(eval_df)
        met006 = self._met006_coverage(eval_df)
        met008 = self._met008_detection_latency(eval_df)

        acceptance = self._evaluate_acceptance_criteria(met001, met002, met003, met004, met005, met006, met008)

        metrics = {
            "MET-001_accuracy_global":     round(met001 * 100, 2),
            "MET-002_accuracy_by_scenario": {k: round(v * 100, 2) for k, v in met002.items()},
            "MET-003_f1_by_state":          {k: round(v["f1"], 3) for k, v in met003.items()},
            "MET-004_calibration_error":   round(met004, 4) if met004 is not None else None,
            "MET-005_stability":           round(met005, 4),
            "MET-006_coverage_pct":        round(met006 * 100, 2),
            "MET-007_cross_tf_consistency": None,
            "MET-008_detection_latency_p50": met008,
            "not_evaluated": {
                "MET-007": "Requiere correr FRM→BRM→IRM en 1h/4h/1d simultáneamente y alinear timestamps — no implementado en run_backtest().",
                "AO-002 (CA-009)": "Requiere partición explícita en régimen alcista/bajista sostenido — no disponible en una sola corrida.",
                "AO-003 (CA-010)": "Requiere correr los mismos parámetros calibrados sobre un segundo instrumento (ej. ETH si se calibró en BTC).",
            },
            "acceptance_criteria": acceptance,
            "scenario_distribution": eval_df["PROBABLE_SCENARIO"].value_counts().to_dict(),
            "avg_confidence_score":  round(eval_df["CONFIDENCE_SCORE"].mean(), 2),
            "avg_conviction_score":  round(eval_df["CONVICTION_SCORE"].mean(), 2),
            "total_evaluated":       len(correct),
            "correct_diagnoses":     sum(correct),
        }

        print(f"\n{'─'*50}")
        print(f"  BACKTEST RESULTS — {self.symbol} {self.timeframe}")
        print(f"{'─'*50}")
        print(f"  MET-001 Accuracy global:    {metrics['MET-001_accuracy_global']}%")
        print(f"  MET-002 Accuracy/escenario: {metrics['MET-002_accuracy_by_scenario']}")
        print(f"  MET-003 F1/estado crítico:  {metrics['MET-003_f1_by_state']}")
        print(f"  MET-004 Calibration error:  {metrics['MET-004_calibration_error']}")
        print(f"  MET-005 Stability:          {metrics['MET-005_stability']}")
        print(f"  MET-006 Coverage:           {metrics['MET-006_coverage_pct']}%")
        print(f"  MET-008 Detection latency:  {metrics['MET-008_detection_latency_p50']}")
        print(f"  Veredicto (CA-001..010):    {acceptance['overall_status']}")
        if acceptance["blocking_failures"]:
            print(f"  Fallos bloqueantes:         {acceptance['blocking_failures']}")
        print(f"{'─'*50}\n")

        if save:
            self._save_backtest(metrics)

        return metrics

    # ── Evaluación de diagnóstico ─────────────────────────────────
    def _evaluate_diagnosis(self, scenario: str, ss_now: str,
                             ss_future: str, future: pd.DataFrame) -> bool:
        """Evalúa si el diagnóstico fue correcto según VRM § 3.2."""
        if scenario == "SC-01_CONTINUATION":
            # Estado se mantiene igual o adyacente
            adjacent = {
                "E-01_TREND_STRONG": ["E-01_TREND_STRONG", "E-03_ORDERED"],
                "E-03_ORDERED":      ["E-03_ORDERED", "E-01_TREND_STRONG", "E-02_TREND_WEAK"],
                "E-02_TREND_WEAK":   ["E-02_TREND_WEAK", "E-03_ORDERED", "E-04_EXHAUSTED"],
                "E-06_EXPANDING":    ["E-06_EXPANDING", "E-01_TREND_STRONG", "E-03_ORDERED"],
            }
            return ss_future in adjacent.get(ss_now, [ss_now])

        elif scenario == "SC-02_BREAKOUT":
            # CI aumenta > θ-002 en las primeras horizon/2 velas (VRM § 3.2).
            # Antes hardcodeado a 0.5, que no correspondía a θ-002 (2.00 por
            # defecto) — el propio umbral configurado del BRM, no un valor
            # arbitrario distinto.
            h2 = len(future) // 2
            if h2 == 0:
                return False
            ci_start = future["COMPRESSION_INDEX"].iloc[0]
            ci_end   = future["COMPRESSION_INDEX"].iloc[min(h2, len(future)-1)]
            return (ci_end - ci_start) > self.thresholds.theta_002_expand

        elif scenario == "SC-03_PULLBACK":
            # Precio toca EMA-21 o EMA-55 en el horizonte
            touched = (
                (future["close"] <= future["EMA_21"] * 1.005).any() or
                (future["close"] <= future["EMA_55"] * 1.005).any()
            )
            return bool(touched)

        elif scenario == "SC-04_STRUCTURAL_CHANGE":
            # Estado cambia a algo no adyacente
            return ss_future != ss_now

        elif scenario == "SC-05_CONSOLIDATION":
            # Permanece en estados de baja convicción
            low_conv = ["E-07_DIVERGENT", "E-04_EXHAUSTED", "E-02_TREND_WEAK"]
            return ss_future in low_conv

        return False

    # ── MET-001 ──────────────────────────────────────────────────
    def _met001_accuracy_global(self, correct: list) -> float:
        """Fracción [0,1] de diagnósticos correctos."""
        return sum(correct) / len(correct) if correct else 0.0

    # ── MET-002 ──────────────────────────────────────────────────
    def _met002_accuracy_by_scenario(self, correct: list, scenarios: list) -> dict:
        """Accuracy [0,1] por cada uno de los 5 escenarios SC-01..SC-05."""
        by_scenario = {}
        for sc in ["SC-01_CONTINUATION", "SC-02_BREAKOUT", "SC-03_PULLBACK",
                   "SC-04_STRUCTURAL_CHANGE", "SC-05_CONSOLIDATION"]:
            idx = [i for i, s in enumerate(scenarios) if s == sc]
            by_scenario[sc] = (sum(correct[i] for i in idx) / len(idx)) if idx else None
        return by_scenario

    # ── MET-003 ──────────────────────────────────────────────────
    def _met003_f1_by_state(self, state_true: list, state_pred: list) -> dict:
        """
        Precision/Recall/F1 por STRUCTURAL_STATE (E-01 a E-07), comparando
        el estado diagnosticado (state_pred) contra el estado dominante
        observado en las H velas siguientes (state_true) — VRM § MET-003.
        """
        states = ["E-01_TREND_STRONG", "E-02_TREND_WEAK", "E-03_ORDERED",
                  "E-04_EXHAUSTED", "E-05_COMPRESSED", "E-06_EXPANDING", "E-07_DIVERGENT"]
        out = {}
        for st in states:
            tp = sum(1 for t, p in zip(state_true, state_pred) if p == st and t == st)
            fp = sum(1 for t, p in zip(state_true, state_pred) if p == st and t != st)
            fn = sum(1 for t, p in zip(state_true, state_pred) if p != st and t == st)
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall    = tp / (tp + fn) if (tp + fn) else 0.0
            f1        = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
            out[st] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
        return out

    # ── MET-004 ──────────────────────────────────────────────────
    def _met004_calibration_error(self, correct: list, confidence: list) -> Optional[float]:
        """
        Error de calibración: |accuracy(bin) - confianza_media(bin)| promediado
        sobre 10 bins de 10 puntos porcentuales cada uno (VRM § MET-004).
        Ambos términos se expresan como fracción [0,1] — el umbral CA-004
        (<=0.10) está en esa misma escala ("10% de desviación promedio").
        """
        if not correct:
            return None
        bins = [[] for _ in range(10)]
        for c, conf in zip(correct, confidence):
            b = min(int(conf // 10), 9)
            bins[b].append((c, conf))

        errors = []
        for b in bins:
            if not b:
                continue
            acc_b  = sum(1 for c, _ in b if c) / len(b)
            conf_b = (sum(conf for _, conf in b) / len(b)) / 100.0
            errors.append(abs(acc_b - conf_b))

        return (sum(errors) / len(errors)) if errors else None

    # ── MET-005 ──────────────────────────────────────────────────
    def _compute_stability(self, df: pd.DataFrame) -> float:
        """
        MET-005: Fracción [0,1] de velas sin cambio ESPURIO de diagnóstico
        (VRM § MET-005 pide excluir cambios con un cambio estructural real
        detrás; la versión anterior contaba cualquier cambio como espurio,
        penalizando también transiciones de régimen genuinas).

        Definición operacional (VRM no fija un algoritmo — provisional,
        sujeta a calibración en Fase VI como el resto de umbrales):
        un cambio de STRUCTURAL_STATE cuenta como espurio si (a) la matriz
        de transiciones de BRM-001 lo marca INVALID, o (b) el estado
        revierte al anterior en la vela inmediatamente siguiente (flicker
        de una vela) — mismo espíritu que la técnica de matriz de
        transición usada en la investigación de referencia (market-regime).
        """
        states = df["STRUCTURAL_STATE"].reset_index(drop=True)
        trans  = df["TRANSITION_STATUS"].reset_index(drop=True) if "TRANSITION_STATUS" in df.columns else None
        n = len(states)
        if n < 2:
            return 1.0

        total = n - 1
        spurious = 0
        for i in range(1, n):
            if states[i] == states[i - 1]:
                continue
            is_invalid = trans is not None and trans[i] == "INVALID"
            reverts    = (i + 1 < n) and (states[i + 1] == states[i - 1])
            if is_invalid or reverts:
                spurious += 1

        return max(0.0, 1 - spurious / total)

    # ── MET-006 ──────────────────────────────────────────────────
    def _met006_coverage(self, df: pd.DataFrame) -> float:
        """MET-006: fracción [0,1] de los 7 estados diagnosticados al menos una vez."""
        return df["STRUCTURAL_STATE"].nunique() / 7

    # ── MET-008 ──────────────────────────────────────────────────
    def _met008_detection_latency(self, df: pd.DataFrame, max_lookahead: int = 10) -> Optional[float]:
        """
        MET-008: mediana de velas entre un cambio estructural real (no
        espurio, ver _compute_stability) y el primer diagnóstico que lo
        reconoce como BREAKOUT o STRUCTURAL_CHANGE.
        """
        states    = df["STRUCTURAL_STATE"].reset_index(drop=True)
        scenarios = df["PROBABLE_SCENARIO"].reset_index(drop=True) if "PROBABLE_SCENARIO" in df.columns else None
        trans     = df["TRANSITION_STATUS"].reset_index(drop=True) if "TRANSITION_STATUS" in df.columns else None
        if scenarios is None:
            return None

        n = len(states)
        latencies = []
        for i in range(1, n):
            if states[i] == states[i - 1]:
                continue
            if trans is not None and trans[i] == "INVALID":
                continue
            for j in range(i, min(i + max_lookahead, n)):
                if scenarios[j] in ("SC-02_BREAKOUT", "SC-04_STRUCTURAL_CHANGE"):
                    latencies.append(j - i)
                    break

        if not latencies:
            return None
        latencies.sort()
        mid = len(latencies) // 2
        if len(latencies) % 2:
            return float(latencies[mid])
        return float((latencies[mid - 1] + latencies[mid]) / 2)

    # ── Criterios de aceptación CA-001 a CA-010 ─────────────────────
    def _evaluate_acceptance_criteria(self, met001, met002, met003, met004,
                                       met005, met006, met008) -> dict:
        """Evalúa CA-001 a CA-010 contra CA_THRESHOLDS (VRM § Capítulo 6)."""
        results = {}

        def add(ca_id, value, passed):
            threshold, crit = CA_THRESHOLDS[ca_id]
            results[ca_id] = {
                "threshold": threshold, "criticidad": crit,
                "result": value, "status": "PASS" if passed else "FAIL",
            }

        add("CA-001", round(met001, 4), met001 >= CA_THRESHOLDS["CA-001"][0])

        sc_values = [v for v in met002.values() if v is not None]
        sc_pass = all(v >= CA_THRESHOLDS["CA-002"][0] for v in sc_values) if sc_values else False
        add("CA-002", {k: (round(v, 4) if v is not None else None) for k, v in met002.items()}, sc_pass)

        crit_f1 = {k: met003[k]["f1"] for k in CRITICAL_STATES}
        crit_pass = all(v >= CA_THRESHOLDS["CA-003"][0] for v in crit_f1.values())
        add("CA-003", {k: round(v, 4) for k, v in crit_f1.items()}, crit_pass)

        if met004 is None:
            results["CA-004"] = {"threshold": CA_THRESHOLDS["CA-004"][0], "criticidad": "BLOQUEANTE",
                                  "result": None, "status": "NO_EVALUADO"}
        else:
            add("CA-004", round(met004, 4), met004 <= CA_THRESHOLDS["CA-004"][0])

        add("CA-005", round(met005, 4), met005 >= CA_THRESHOLDS["CA-005"][0])
        add("CA-006", round(met006, 4), met006 >= CA_THRESHOLDS["CA-006"][0])

        results["CA-007"] = {"threshold": CA_THRESHOLDS["CA-007"][0], "criticidad": "ADVERTENCIA",
                              "result": None, "status": "NO_EVALUADO"}

        if met008 is None:
            results["CA-008"] = {"threshold": CA_THRESHOLDS["CA-008"][0], "criticidad": "ADVERTENCIA",
                                  "result": None, "status": "NO_EVALUADO"}
        else:
            add("CA-008", met008, met008 <= CA_THRESHOLDS["CA-008"][0])

        results["CA-009"] = {"threshold": CA_THRESHOLDS["CA-009"][0], "criticidad": "BLOQUEANTE",
                              "result": None, "status": "NO_EVALUADO"}
        results["CA-010"] = {"threshold": CA_THRESHOLDS["CA-010"][0], "criticidad": "ADVERTENCIA",
                              "result": None, "status": "NO_EVALUADO"}

        blocking_ids = [k for k, (_, crit) in CA_THRESHOLDS.items() if crit == "BLOQUEANTE"]
        blocking_failures  = [k for k in blocking_ids if results[k]["status"] == "FAIL"]
        blocking_pending   = [k for k in blocking_ids if results[k]["status"] == "NO_EVALUADO"]
        warnings = [k for k in results if results[k]["criticidad"] == "ADVERTENCIA"
                    and results[k]["status"] in ("FAIL", "NO_EVALUADO")]

        if blocking_failures:
            overall = "FAIL"
        elif blocking_pending:
            overall = "INCOMPLETO — requiere corridas adicionales para CA bloqueantes: " + ", ".join(blocking_pending)
        else:
            overall = "PASS"

        return {
            "criteria": results,
            "overall_status": overall,
            "blocking_failures": blocking_failures,
            "warnings": warnings,
        }

    # ── Output y guardado ─────────────────────────────────────────
    def _print_summary(self, df: pd.DataFrame):
        """Imprime resumen del análisis histórico."""
        last = df.iloc[-1]
        print(f"\n{'─'*60}")
        print(f"  RESUMEN — Últimas 5 velas")
        print(f"{'─'*60}")
        cols = ["timestamp", "close", "STRUCTURAL_STATE",
                "MOMENTUM_STATE", "ENERGY_STATE",
                "PROBABLE_SCENARIO", "CONFIDENCE_SCORE"]
        cols_present = [c for c in cols if c in df.columns]
        print(df[cols_present].tail(5).to_string(index=False))
        print(f"{'─'*60}\n")

    def _print_diagnosis(self, diag: StructuralDiagnosis):
        """Imprime el diagnóstico de tiempo real."""
        print(f"\n{'═'*60}")
        print(f"  DIAGNÓSTICO ESTRUCTURAL — TIEMPO REAL")
        print(f"{'═'*60}")
        print(f"  Símbolo:    {diag.symbol} | Timeframe: {diag.timeframe}")
        print(f"  Timestamp:  {diag.timestamp}")
        print(f"{'─'*60}")
        print(f"  Estado:     {diag.structural_state}")
        print(f"  Momentum:   {diag.momentum_state}")
        print(f"  Energía:    {diag.energy_state}")
        print(f"{'─'*60}")
        print(f"  Convicción: {diag.conviction_score:.1f}/100")
        print(f"  Escenario:  {diag.probable_scenario}")
        print(f"  Confianza:  {diag.confidence_score:.1f}%")
        print(f"  Coherencia: {diag.coherence_score:.2f}/10")
        print(f"  Fricción:   {diag.friction_index:.2f}/10")
        print(f"{'─'*60}")
        print(f"  {diag.explanation}")
        print(f"{'═'*60}\n")

    def _save_results(self, df: pd.DataFrame, mode: str):
        """Guarda resultados en F7/ como CSV."""
        try:
            out_dir = F7_OUTPUT
            out_dir.mkdir(parents=True, exist_ok=True)
            ts  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out = out_dir / f"EIM_{self.symbol}_{self.timeframe}_{mode}_{ts}.csv"
            df.to_csv(out, index=False)
            print(f"[EIM Engine] Resultados guardados: {out}")
        except Exception as e:
            print(f"[EIM Engine] No se pudo guardar en ruta de proyecto: {e}")
            # Guardar en directorio local como fallback
            local = Path(f"EIM_{self.symbol}_{self.timeframe}_{mode}.csv")
            df.to_csv(local, index=False)
            print(f"[EIM Engine] Guardado localmente: {local}")

    def _save_backtest(self, metrics: dict):
        """Guarda el reporte de backtesting."""
        try:
            out_dir = F7_OUTPUT
            out_dir.mkdir(parents=True, exist_ok=True)
            ts  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            out = out_dir / f"EIM_BACKTEST_{self.symbol}_{self.timeframe}_{ts}.json"
            with open(out, "w") as f:
                json.dump(metrics, f, indent=2)
            print(f"[EIM Engine] Reporte guardado: {out}")
        except Exception as e:
            print(f"[EIM Engine] Guardado localmente (fallback): {e}")
            with open("EIM_BACKTEST.json", "w") as f:
                json.dump(metrics, f, indent=2)


# ═══════════════════════════════════════════════════════════════════
# CLI — Ejecución desde línea de comandos
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="EMA Intelligence Model (EIM) v1.0 — Motor de Diagnóstico Estructural"
    )
    parser.add_argument("--symbol",    default="BTCUSDT",
                        help="Par de futuros (ej. BTCUSDT, ETHUSDT)")
    parser.add_argument("--timeframe", default="4h",
                        choices=["1h", "4h", "1d"],
                        help="Timeframe de análisis")
    parser.add_argument("--mode",      default="realtime",
                        choices=["historical", "realtime", "backtest"],
                        help="Modo de operación")
    parser.add_argument("--candles",   default=1000, type=int,
                        help="Número de velas (modo historical/backtest)")
    parser.add_argument("--horizon",   default=6, type=int,
                        help="Velas de evaluación hacia adelante (backtest)")
    parser.add_argument("--api-key",   default="",
                        help="Binance API Key (opcional — datos públicos no la requieren)")
    parser.add_argument("--api-secret",default="",
                        help="Binance API Secret")

    args = parser.parse_args()

    engine = EIMEngine(
        symbol     = args.symbol,
        timeframe  = args.timeframe,
        api_key    = args.api_key,
        api_secret = args.api_secret,
    )

    if args.mode == "historical":
        engine.run_historical(candles=args.candles)

    elif args.mode == "realtime":
        engine.run_realtime()

    elif args.mode == "backtest":
        engine.run_backtest(candles=args.candles, horizon=args.horizon)


if __name__ == "__main__":
    main()
