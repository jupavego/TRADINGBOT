"""IRM (EIM-IRM-001 v1.0.1): DIAG-001 en 4 etapas. Puro, sin I/O.

Migrado de F7/eim_brm_irm.py. Cada etapa devuelve además la traza de reglas disparadas
(para la evidencia del agente) sin alterar los valores.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from eim.agents.structure.params import IRMParams

# Tabla de mapeo primario (estado, momentum, energía|None=comodín) → escenario
PRIMARY = {
    ("E-01_TREND_STRONG", "ACCELERATING", "HIGH_ENERGY"): "SC-01_CONTINUATION",
    ("E-01_TREND_STRONG", "ACCELERATING", "COMPRESSED"): "SC-02_BREAKOUT",
    ("E-01_TREND_STRONG", "STABLE", "HIGH_ENERGY"): "SC-01_CONTINUATION",
    ("E-01_TREND_STRONG", "STABLE", "MODERATE_ENERGY"): "SC-01_CONTINUATION",
    ("E-01_TREND_STRONG", "DECELERATING", None): "SC-03_PULLBACK",
    ("E-01_TREND_STRONG", "REVERSING", None): "SC-04_STRUCTURAL_CHANGE",
    ("E-03_ORDERED", "ACCELERATING", None): "SC-01_CONTINUATION",
    ("E-03_ORDERED", "STABLE", "MODERATE_ENERGY"): "SC-01_CONTINUATION",
    ("E-03_ORDERED", "STABLE", "LOW_ENERGY"): "SC-05_CONSOLIDATION",
    ("E-03_ORDERED", "DECELERATING", None): "SC-03_PULLBACK",
    ("E-03_ORDERED", "REVERSING", None): "SC-04_STRUCTURAL_CHANGE",
    ("E-02_TREND_WEAK", "ACCELERATING", None): "SC-01_CONTINUATION",
    ("E-02_TREND_WEAK", "STABLE", None): "SC-05_CONSOLIDATION",
    ("E-02_TREND_WEAK", "DECELERATING", None): "SC-03_PULLBACK",
    ("E-02_TREND_WEAK", "REVERSING", None): "SC-04_STRUCTURAL_CHANGE",
    ("E-04_EXHAUSTED", "ACCELERATING", None): "SC-03_PULLBACK",
    ("E-04_EXHAUSTED", "STABLE", None): "SC-03_PULLBACK",
    ("E-04_EXHAUSTED", "DECELERATING", None): "SC-04_STRUCTURAL_CHANGE",
    ("E-04_EXHAUSTED", "REVERSING", None): "SC-04_STRUCTURAL_CHANGE",
    ("E-05_COMPRESSED", "STABLE", "COMPRESSED"): "SC-02_BREAKOUT",
    ("E-05_COMPRESSED", "ACCELERATING", None): "SC-02_BREAKOUT",
    ("E-05_COMPRESSED", "DECELERATING", None): "SC-05_CONSOLIDATION",
    ("E-05_COMPRESSED", "REVERSING", None): "SC-04_STRUCTURAL_CHANGE",
    ("E-06_EXPANDING", "ACCELERATING", "HIGH_ENERGY"): "SC-02_BREAKOUT",
    ("E-06_EXPANDING", "ACCELERATING", "MODERATE_ENERGY"): "SC-01_CONTINUATION",
    ("E-06_EXPANDING", "STABLE", None): "SC-01_CONTINUATION",
    ("E-06_EXPANDING", "DECELERATING", None): "SC-03_PULLBACK",
    ("E-06_EXPANDING", "REVERSING", None): "SC-04_STRUCTURAL_CHANGE",
}

STATE_LABELS = {
    "E-01_TREND_STRONG": "tendencia fuerte", "E-02_TREND_WEAK": "tendencia débil",
    "E-03_ORDERED": "estructura ordenada", "E-04_EXHAUSTED": "estructura agotada",
    "E-05_COMPRESSED": "compresión estructural", "E-06_EXPANDING": "expansión estructural",
    "E-07_DIVERGENT": "estructura divergente",
}
ENERGY_SUFFIX = {
    "COMPRESSED": " — alta energía potencial acumulada",
    "HIGH_ENERGY": " — expansión activa en progreso",
    "LOW_ENERGY": " — capacidad de movimiento reducida",
    "MODERATE_ENERGY": "",
}
SCENARIO_LABELS = {
    "SC-01_CONTINUATION": "continuación", "SC-02_BREAKOUT": "ruptura",
    "SC-03_PULLBACK": "pullback", "SC-04_STRUCTURAL_CHANGE": "cambio estructural",
    "SC-05_CONSOLIDATION": "consolidación",
}
SCENARIO_DESC = {
    "SC-01_CONTINUATION": "persistencia del estado actual sin señales de reversión",
    "SC-02_BREAKOUT": "salida de estructura con cambio significativo en propiedades",
    "SC-03_PULLBACK": "corrección temporal hacia referencia estructural",
    "SC-04_STRUCTURAL_CHANGE": "reconfiguración sostenida de la organización interna",
    "SC-05_CONSOLIDATION": "ausencia de tendencia definida — propiedades oscilan sin dirección",
}


def direction_sign(row: dict) -> int:
    sd, so = row.get("SLOPE_DIRECTION", "NEUTRAL"), row.get("STACK_ORDER", "NEUTRAL")
    if sd == "UP":
        return 1
    if sd == "DOWN":
        return -1
    return 1 if so in ("BULL_PERFECT", "BULL_PARTIAL") else -1


def conviction(row: dict, p: IRMParams) -> float:
    """Etapa 1 (CS-001…CS-004): score [0–100]; >50 alcista, <50 bajista."""
    ss = row.get("STRUCTURAL_STATE", "E-07_DIVERGENT")
    ms = row.get("MOMENTUM_STATE", "STABLE")
    es = row.get("ENERGY_STATE", "MODERATE_ENERGY")
    fi = row.get("FRICTION_INDEX", 5.0)
    up, down = p.base_scores.get(ss, (50, 50))
    s1 = up if direction_sign(row) == 1 else down
    s2 = 50 + (s1 - 50) * p.momentum_mult.get(ms, 1.0)
    s3 = s2 + p.energy_delta.get(es, 0) * np.sign(s2 - 50)
    fd = next((d for lo, d in p.friction_bands if fi >= lo), p.friction_default)
    s4 = s3 + fd * np.sign(s3 - 50 + 1e-9)
    return float(np.clip(s4, 0, 100))


def scenario(
    row: dict, conv: float, p: IRMParams, mtf_sync: float | None = None
) -> tuple[str, list[str]]:
    """Etapa 2: mapeo primario + SR-001…SR-004. Devuelve (escenario, reglas disparadas)."""
    ss = row.get("STRUCTURAL_STATE", "E-07_DIVERGENT")
    ms = row.get("MOMENTUM_STATE", "STABLE")
    es = row.get("ENERGY_STATE", "MODERATE_ENERGY")
    fi = row.get("FRICTION_INDEX", 5.0)
    cs = row.get("COHERENCE_SCORE", 5.0)
    bc200 = int(row.get("BOUNCE_COUNT_200", 0))

    sc = PRIMARY.get((ss, ms, es)) or PRIMARY.get((ss, ms, None)) or "SC-05_CONSOLIDATION"
    fired: list[str] = []
    if sc == "SC-02_BREAKOUT" and fi >= p.sr1_friction:
        sc = "SC-05_CONSOLIDATION"
        fired.append(f"SR-001: fricción {fi:.1f} ≥ {p.sr1_friction}: ruptura → consolidación")
    lo, hi = p.sr2_conviction_band
    if sc == "SC-01_CONTINUATION" and lo <= conv <= hi and cs < p.sr2_coherence:
        sc = "SC-05_CONSOLIDATION"
        fired.append("SR-002: convicción media y coherencia baja → consolidación")
    if sc == "SC-02_BREAKOUT" and mtf_sync is not None and mtf_sync < p.sr3_mtf_min:
        sc = "SC-01_CONTINUATION"
        fired.append("SR-003: ruptura sin confirmación multi-timeframe → continuación")
    if sc == "SC-03_PULLBACK" and bc200 == 0 and ss == "E-04_EXHAUSTED":
        sc = "SC-04_STRUCTURAL_CHANGE"
        fired.append("SR-004: pullback sin historia en EMA-200 y estructura agotada → cambio")
    return sc, fired


def confidence(
    row: dict, sc: str, conv: float, mtf_sync: float | None, comb: str, trans: str,
    p: IRMParams,
) -> tuple[float, list[str]]:
    """Etapa 3: base coherencia×10 + M-001…M-007, tope 95. Devuelve (score, modificadores)."""
    cs = row.get("COHERENCE_SCORE", 5.0)
    fi = row.get("FRICTION_INDEX", 5.0)
    es = row.get("ENERGY_STATE", "MODERATE_ENERGY")
    bc = int(row.get("BOUNCE_COUNT_200", 0))
    score, mods = cs * 10, []

    def add(delta: float, label: str) -> None:
        nonlocal score
        score += delta
        mods.append(f"{label} ({delta:+g})")

    if mtf_sync is not None:
        add(10 if mtf_sync >= 75 else 5 if mtf_sync >= 50 else 0 if mtf_sync >= 25 else -15,
            f"M-001 MTF_SYNC {mtf_sync:.0f}%")
    add(8 if bc >= 5 else 5 if bc >= 3 else 2 if bc >= 1 else -5, f"M-002 rebotes EMA-200={bc}")
    if comb == "IMPOSIBLE":
        add(-50, "M-003 combinación imposible")
    elif comb == "INUSUAL":
        add(-10, "M-003 combinación inusual")
    if sc == "SC-02_BREAKOUT" and fi >= 6.0:
        add(-10, "M-004 fricción alta vs ruptura")
    if sc == "SC-01_CONTINUATION" and fi < 3.0:
        add(5, "M-004 fricción baja vs continuación")
    if conv >= 85 or conv <= 15:
        add(8, "M-005 convicción extrema")
    if 45 <= conv <= 55:
        add(-8, "M-005 convicción indefinida")
    if sc == "SC-02_BREAKOUT" and es == "COMPRESSED":
        add(10, "M-006 energía comprimida vs ruptura")
    if sc == "SC-01_CONTINUATION" and es == "LOW_ENERGY":
        add(-8, "M-006 baja energía vs continuación")
    if trans == "INVALID":
        add(-10, "M-007 transición inválida")
    return float(np.clip(score, 0, p.confidence_cap)), mods


def explanation(
    row: dict, sc: str, conv: float, conf: float, mtf_sync: float | None, trans: str
) -> str:
    """Etapa 4: narrativa del diagnóstico."""
    ss, ms, es = (row.get(k, "") for k in ("STRUCTURAL_STATE", "MOMENTUM_STATE", "ENERGY_STATE"))
    cs, fi = row.get("COHERENCE_SCORE", 0.0), row.get("FRICTION_INDEX", 0.0)
    sd, bc = row.get("SLOPE_DIRECTION", "NEUTRAL"), int(row.get("BOUNCE_COUNT_200", 0))
    conv_l = "alta" if conv > 60 else ("moderada" if conv >= 40 else "baja")
    coh_l = ("alta — diagnóstico confiable" if cs >= 8
             else "moderada — diagnóstico válido con reservas" if cs >= 5
             else "baja — señales contradictorias")
    parts = [
        f"El mercado presenta {STATE_LABELS.get(ss, ss)}.",
        f"El momentum es {ms.lower()} con dirección {sd} y {conv_l} convicción.",
        f"La energía estructural es {es.replace('_', ' ').lower()}{ENERGY_SUFFIX.get(es, '')}.",
        f"La coherencia estructural es {cs:.1f}/10 ({coh_l}).",
        f"El escenario más probable es {SCENARIO_LABELS.get(sc, sc)}: "
        f"{SCENARIO_DESC.get(sc, '')}. Confianza del diagnóstico: {conf:.1f}%.",
    ]
    if mtf_sync is not None:
        lbl = ("alta confirmación" if mtf_sync >= 75
               else "confirmación parcial" if mtf_sync >= 50 else "sin confirmación")
        parts.append(f"Confirmación multi-timeframe: {mtf_sync:.0f}% ({lbl}).")
    if fi >= 6.0:
        parts.append(
            f"Alta fricción estructural ({fi:.1f}/10) limita la velocidad del movimiento esperado."
        )
    if bc >= 3:
        parts.append(f"El precio ha respetado la EMA-200 {bc} veces en la ventana actual, "
                     "confirmando el régimen macro.")
    if trans == "INVALID":
        parts.append("Anomalía: la transición desde el estado estructural anterior no figura en la "
                     "matriz de transiciones válidas de EIM-BRM-001 — no bloquea el diagnóstico, "
                     "pero reduce la confianza y debería revisarse.")
    return " ".join(parts)


def diagnose(row: dict, p: IRMParams, mtf_sync: float | None = None) -> dict:
    """DIAG-001 de una fila ya clasificada por el BRM."""
    conv = conviction(row, p)
    sc, sr = scenario(row, conv, p, mtf_sync)
    comb, trans = row.get("COMBINATION_STATUS", "NORMAL"), row.get("TRANSITION_STATUS", "N/A")
    conf, mods = confidence(row, sc, conv, mtf_sync, comb, trans, p)
    return {
        "conviction": round(conv, 2), "scenario": sc, "confidence": round(conf, 2),
        "explanation": explanation(row, sc, conv, conf, mtf_sync, trans),
        "rules": sr, "modifiers": mods,
    }


def compute_irm(
    df: pd.DataFrame, p: IRMParams | None = None, mtf_sync: float | None = None
) -> pd.DataFrame:
    """Añade CONVICTION_SCORE, PROBABLE_SCENARIO y CONFIDENCE_SCORE a todo el frame."""
    p = p or IRMParams()
    diags = [diagnose(r, p, mtf_sync) for r in df.to_dict("records")]
    df = df.copy()
    df["CONVICTION_SCORE"] = [d["conviction"] for d in diags]
    df["PROBABLE_SCENARIO"] = [d["scenario"] for d in diags]
    df["CONFIDENCE_SCORE"] = [d["confidence"] for d in diags]
    return df
