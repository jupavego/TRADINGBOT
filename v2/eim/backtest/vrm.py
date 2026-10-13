"""Protocolo de backtesting EIM-VRM-001 (puro): métricas MET-001..006/008 y criterios CA-001..010.

Migrado de `F7/eim_engine.py` sin cambiar la lógica. Opera sobre el DataFrame de
`eim.agents.structure.agent.structure_frame`. MET-007, CA-009 y CA-010 no se pueden evaluar con
una sola corrida y se reportan como `NO_EVALUADO` (nunca se inventan).
"""

from __future__ import annotations

import pandas as pd

from eim.agents.structure.params import StructureParams

WARMUP = 400
CA_THRESHOLDS: dict[str, tuple[float, str]] = {
    "CA-001": (0.60, "BLOQUEANTE"), "CA-002": (0.55, "BLOQUEANTE"),
    "CA-003": (0.50, "BLOQUEANTE"), "CA-004": (0.10, "BLOQUEANTE"),
    "CA-005": (0.85, "BLOQUEANTE"), "CA-006": (1.00, "BLOQUEANTE"),
    "CA-007": (0.65, "ADVERTENCIA"), "CA-008": (3, "ADVERTENCIA"),
    "CA-009": (0.80, "BLOQUEANTE"), "CA-010": (0.55, "ADVERTENCIA"),
}
CRITICAL_STATES = ["E-01_TREND_STRONG", "E-03_ORDERED", "E-05_COMPRESSED"]
SCENARIOS = ["SC-01_CONTINUATION", "SC-02_BREAKOUT", "SC-03_PULLBACK",
             "SC-04_STRUCTURAL_CHANGE", "SC-05_CONSOLIDATION"]
STATES = ["E-01_TREND_STRONG", "E-02_TREND_WEAK", "E-03_ORDERED", "E-04_EXHAUSTED",
          "E-05_COMPRESSED", "E-06_EXPANDING", "E-07_DIVERGENT"]
_ADJACENT = {
    "E-01_TREND_STRONG": ["E-01_TREND_STRONG", "E-03_ORDERED"],
    "E-03_ORDERED": ["E-03_ORDERED", "E-01_TREND_STRONG", "E-02_TREND_WEAK"],
    "E-02_TREND_WEAK": ["E-02_TREND_WEAK", "E-03_ORDERED", "E-04_EXHAUSTED"],
    "E-06_EXPANDING": ["E-06_EXPANDING", "E-01_TREND_STRONG", "E-03_ORDERED"],
}
_NOT_EVALUATED = {
    "MET-007": "Requiere correr FRM→BRM→IRM en varios marcos y alinear marcas de tiempo.",
    "AO-002 (CA-009)": "Requiere partición explícita en régimen alcista/bajista sostenido.",
    "AO-003 (CA-010)": "Requiere correr los mismos parámetros sobre un segundo instrumento.",
}


def evaluate_diagnosis(scenario: str, ss_now: str, ss_future: str, future: pd.DataFrame,
                       theta_expand: float) -> bool:
    """¿Fue correcto el diagnóstico a `horizon` velas? (VRM § 3.2)."""
    if scenario == "SC-01_CONTINUATION":
        return ss_future in _ADJACENT.get(ss_now, [ss_now])
    if scenario == "SC-02_BREAKOUT":
        h2 = len(future) // 2
        if h2 == 0:
            return False
        ci = future["COMPRESSION_INDEX"]
        return bool((ci.iloc[min(h2, len(future) - 1)] - ci.iloc[0]) > theta_expand)
    if scenario == "SC-03_PULLBACK":
        return bool((future["close"] <= future["EMA_21"] * 1.005).any()
                    or (future["close"] <= future["EMA_55"] * 1.005).any())
    if scenario == "SC-04_STRUCTURAL_CHANGE":
        return ss_future != ss_now
    if scenario == "SC-05_CONSOLIDATION":
        return ss_future in ("E-07_DIVERGENT", "E-04_EXHAUSTED", "E-02_TREND_WEAK")
    return False


def f1_by_state(state_true: list, state_pred: list) -> dict:
    out = {}
    for st in STATES:
        tp = sum(1 for t, p in zip(state_true, state_pred, strict=True) if p == st and t == st)
        fp = sum(1 for t, p in zip(state_true, state_pred, strict=True) if p == st and t != st)
        fn = sum(1 for t, p in zip(state_true, state_pred, strict=True) if p != st and t == st)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        out[st] = {"precision": prec, "recall": rec, "support": tp + fn,
                   "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0}
    return out


def calibration_error(correct: list[bool], confidence: list[float]) -> float | None:
    """|accuracy − confianza media| por 10 bins de confianza (0..100), promediado."""
    bins: list[list[tuple[bool, float]]] = [[] for _ in range(10)]
    for c, conf in zip(correct, confidence, strict=True):
        bins[min(int(conf // 10), 9)].append((c, conf))
    errs = [abs(sum(1 for c, _ in b if c) / len(b) - sum(x for _, x in b) / len(b) / 100.0)
            for b in bins if b]
    return sum(errs) / len(errs) if errs else None


def stability(df: pd.DataFrame) -> float:
    """Fracción de velas sin cambio de estado ESPURIO (transición INVALID o flicker de 1 vela)."""
    states = df["STRUCTURAL_STATE"].reset_index(drop=True)
    trans = df["TRANSITION_STATUS"].reset_index(drop=True) if "TRANSITION_STATUS" in df else None
    n = len(states)
    if n < 2:
        return 1.0
    spurious = 0
    for i in range(1, n):
        if states[i] == states[i - 1]:
            continue
        reverts = i + 1 < n and states[i + 1] == states[i - 1]
        if (trans is not None and trans[i] == "INVALID") or reverts:
            spurious += 1
    return max(0.0, 1 - spurious / (n - 1))


def detection_latency(df: pd.DataFrame, max_lookahead: int = 10) -> float | None:
    """Mediana de velas entre un cambio estructural real y el primer BREAKOUT/STRUCTURAL_CHANGE."""
    states = df["STRUCTURAL_STATE"].reset_index(drop=True)
    sc = df["PROBABLE_SCENARIO"].reset_index(drop=True)
    trans = df["TRANSITION_STATUS"].reset_index(drop=True) if "TRANSITION_STATUS" in df else None
    lat: list[int] = []
    for i in range(1, len(states)):
        if states[i] == states[i - 1] or (trans is not None and trans[i] == "INVALID"):
            continue
        for j in range(i, min(i + max_lookahead, len(states))):
            if sc[j] in ("SC-02_BREAKOUT", "SC-04_STRUCTURAL_CHANGE"):
                lat.append(j - i)
                break
    if not lat:
        return None
    lat.sort()
    mid = len(lat) // 2
    return float(lat[mid]) if len(lat) % 2 else (lat[mid - 1] + lat[mid]) / 2


def acceptance(m1: float, m2: dict, m3: dict, m4: float | None, m5: float, m6: float,
               m8: float | None) -> dict:
    """Veredicto CA-001..010 (VRM § Cap. 6)."""
    res: dict[str, dict] = {}

    def put(ca: str, value, passed: bool | None) -> None:
        thr, crit = CA_THRESHOLDS[ca]
        res[ca] = {"threshold": thr, "criticidad": crit, "result": value,
                   "status": "NO_EVALUADO" if passed is None else "PASS" if passed else "FAIL"}

    put("CA-001", round(m1, 4), m1 >= CA_THRESHOLDS["CA-001"][0])
    vals = [v for v in m2.values() if v is not None]
    put("CA-002", {k: None if v is None else round(v, 4) for k, v in m2.items()},
        bool(vals) and all(v >= CA_THRESHOLDS["CA-002"][0] for v in vals))
    crit = {k: m3[k]["f1"] for k in CRITICAL_STATES}
    put("CA-003", {k: round(v, 4) for k, v in crit.items()},
        all(v >= CA_THRESHOLDS["CA-003"][0] for v in crit.values()))
    put("CA-004", None if m4 is None else round(m4, 4),
        None if m4 is None else m4 <= CA_THRESHOLDS["CA-004"][0])
    put("CA-005", round(m5, 4), m5 >= CA_THRESHOLDS["CA-005"][0])
    put("CA-006", round(m6, 4), m6 >= CA_THRESHOLDS["CA-006"][0])
    put("CA-007", None, None)
    put("CA-008", m8, None if m8 is None else m8 <= CA_THRESHOLDS["CA-008"][0])
    put("CA-009", None, None)
    put("CA-010", None, None)
    blocking = [k for k, (_, c) in CA_THRESHOLDS.items() if c == "BLOQUEANTE"]
    fails = [k for k in blocking if res[k]["status"] == "FAIL"]
    pending = [k for k in blocking if res[k]["status"] == "NO_EVALUADO"]
    pend = "INCOMPLETO — requiere corridas adicionales para CA bloqueantes: " + ", ".join(pending)
    overall = "FAIL" if fails else pend if pending else "PASS"
    warns = [k for k, v in res.items()
             if v["criticidad"] == "ADVERTENCIA" and v["status"] in ("FAIL", "NO_EVALUADO")]
    return {"criteria": res, "overall_status": overall, "blocking_failures": fails,
            "warnings": warns}


def run_backtest(df: pd.DataFrame, horizon: int = 6,
                 params: StructureParams | None = None) -> dict:
    """Evalúa cada diagnóstico de `df` (salida de `structure_frame`) contra las `horizon` velas
    siguientes, excluyendo el warmup (400) y las últimas `horizon` velas."""
    theta = (params or StructureParams()).brm.theta_002_expand
    end = len(df) - horizon
    if end <= WARMUP:
        raise ValueError(f"velas insuficientes: se necesitan > {WARMUP + horizon}, hay {len(df)}")
    ev = df.iloc[WARMUP:end]
    correct: list[bool] = []
    s_true: list[str] = []
    s_pred: list[str] = []
    scs: list[str] = []
    conf: list[float] = []
    for idx in range(WARMUP, end):
        row = df.iloc[idx]
        fut = df.iloc[idx + 1: idx + horizon + 1]
        mode = fut["STRUCTURAL_STATE"].mode()
        ss_f = mode.iloc[0] if len(mode) else "E-07_DIVERGENT"
        correct.append(evaluate_diagnosis(row["PROBABLE_SCENARIO"], row["STRUCTURAL_STATE"],
                                          ss_f, fut, theta))
        s_true.append(ss_f)
        s_pred.append(row["STRUCTURAL_STATE"])
        scs.append(row["PROBABLE_SCENARIO"])
        conf.append(float(row["CONFIDENCE_SCORE"]))
    m1 = sum(correct) / len(correct)
    m2 = {sc: (sum(c for c, s in zip(correct, scs, strict=True) if s == sc)
               / scs.count(sc)) if sc in scs else None for sc in SCENARIOS}
    m3, m4 = f1_by_state(s_true, s_pred), calibration_error(correct, conf)
    m5, m6, m8 = stability(ev), ev["STRUCTURAL_STATE"].nunique() / 7, detection_latency(ev)
    return {
        "MET-001_accuracy_global": round(m1 * 100, 2),
        "MET-002_accuracy_by_scenario": {k: None if v is None else round(v * 100, 2)
                                         for k, v in m2.items()},
        "MET-003_f1_by_state": {k: round(v["f1"], 3) for k, v in m3.items()},
        "MET-004_calibration_error": None if m4 is None else round(m4, 4),
        "MET-005_stability": round(m5, 4),
        "MET-006_coverage_pct": round(m6 * 100, 2),
        "MET-007_cross_tf_consistency": None,
        "MET-008_detection_latency_p50": m8,
        "not_evaluated": _NOT_EVALUATED,
        "acceptance_criteria": acceptance(m1, m2, m3, m4, m5, m6, m8),
        "scenario_distribution": {k: int(v) for k, v
                                  in ev["PROBABLE_SCENARIO"].value_counts().items()},
        "avg_confidence_score": round(float(ev["CONFIDENCE_SCORE"].mean()), 2),
        "avg_conviction_score": round(float(ev["CONVICTION_SCORE"].mean()), 2),
        "total_evaluated": len(correct), "correct_diagnoses": int(sum(correct)),
        "horizon": horizon, "bars": len(df),
    }
