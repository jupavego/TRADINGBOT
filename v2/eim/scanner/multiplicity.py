"""Registro de intentos y control de multiplicidad del escáner (T95, 3/3). Puro.

Escanear cientos de instrumentos con una veintena de agentes es una máquina de generar hipótesis.
Cada **intento** es una hipótesis direccional concreta: *instrumento × agente × marco × versión ×
horizonte* (la síntesis cuenta como un agente más, `sintesis`). Se registra **cada vez que se
evalúa**, tenga lado o no, y no se borra nunca: la familia solo crece.

- **Resultado hacia adelante.** Cuando pasan las `horizon_bars` velas, la observación madura: el
  rendimiento logarítmico del instrumento en el lado que dijo, en σ de su horizonte y **neto del
  costo de ida y vuelta de su clase**; y el del lado contrario con el mismo costo (la réplica de
  lado al azar de V3, T49). No se reconstruye historia: solo cuenta lo dicho antes de saberlo.
- **p bruto** por intento con ≥ `MIN_OBS` observaciones maduras: lado al azar (p = ½ por
  observación), réplicas `max(min_reps, reps_per_attempt × familia)` de `validation_v1` (como T49).
- **Corrección sobre la familia completa**: los `PRIOR_FAMILY` intentos ya registrados en la puerta
  de T49 (sin p = 1, lo conservador) **más** todos los del escáner. Holm (vinculante) y
  Benjamini–Hochberg (tasa de falsos descubrimientos, informativa), y Sharpe deflactado por el
  tamaño de la familia. PBO no aplica todavía: T84, que lo traía, se archivó sin construirse.
- **Nunca «validada»** salvo que la puerta v1 de T49 lo diga para ese mismo intento
  (`validation_status`): superar Holm aquí no basta, falta V1–V6.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

import numpy as np

from eim.backtest.edge import bh, holm
from eim.validation import stats as st
from eim.validation.criteria import Criteria, load_criteria

MULTIPLICITY_VERSION = "1.0.0"
#: Intentos de la puerta T49 al abrir T95 (T139 «familia de 841»; T145 y T164 la citan igual).
PRIOR_FAMILY = 841
PRIOR_SOURCE = ("familia de la puerta T49 (841 intentos, citada en T139/T145/T164): se amplía "
                "con el universo, no se reinicia (T87, punto 7)")
MIN_OBS = 10
MAX_REPS = 250_000
SYNTHESIS_AGENT = "sintesis"
VALIDATED = "VALIDADA"
NOT_VALIDATED = "no validada"


@dataclass(frozen=True)
class Attempt:
    key: str
    instrument_id: str
    symbol: str
    agent_id: str
    version: str
    timeframe: str
    horizon_bars: int
    side: int                       # +1 largo, −1 corto, 0 sin lado (cuenta en la familia)
    close0: float
    sigma_h: float | None
    cost: float | None
    scores: dict | None = None      # solo la síntesis: las 4 puntuaciones (para calibrar)

    def as_json(self) -> dict:
        return asdict(self)


def attempt_key(instrument_id: str, agent_id: str, timeframe: str, version: str,
                horizon_bars: int) -> str:
    return f"{instrument_id}|{agent_id}@{version}|{timeframe}|h{int(horizon_bars)}"


def _sign(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def attempts_of(result: Mapping, *, horizon_bars: int, close0: float, sigma_h: float | None,
                cost: float | None, synthesis_version: str,
                scores: Mapping | None = None) -> list[Attempt]:
    """Los intentos de un análisis profundo (`DeepResult.as_json()`): uno por agente que corrió y
    uno de la síntesis si la hubo (con lado solo si salió oportunidad)."""
    iid, sym, tf = result["instrument_id"], result.get("symbol", ""), result["timeframe"]
    out = []
    for r in result.get("ran") or []:
        side = 0 if r.get("status") == "no_data" else _sign(float(r.get("bias") or 0.0))
        out.append(Attempt(attempt_key(iid, r["agent_id"], tf, r["version"], horizon_bars), iid,
                           sym, r["agent_id"], r["version"], tf, horizon_bars, side, close0,
                           sigma_h, cost))
    if result.get("synthesis"):
        opp = result.get("opportunity")
        side = 0 if not opp else (1 if opp["side"] == "largo" else -1)
        out.append(Attempt(attempt_key(iid, SYNTHESIS_AGENT, tf, synthesis_version, horizon_bars),
                           iid, sym, SYNTHESIS_AGENT, synthesis_version, tf, horizon_bars, side,
                           close0, sigma_h, cost, dict(scores) if scores else None))
    return out


def outcome(side: int, close0: float, close_end: float, sigma_h: float,
            cost: float) -> tuple[float, float]:
    """(resultado, resultado del lado contrario) en σ del horizonte, netos del costo."""
    r = math.log(close_end / close0)
    return (side * r - cost) / sigma_h, (-side * r - cost) / sigma_h


def pvalue(outcomes: Sequence[float], flips: Sequence[float], family: int, label: str,
           crit: Criteria | None = None) -> float | None:
    """p unilateral de «resultado medio > lado al azar» (None con < `MIN_OBS` maduras)."""
    if len(outcomes) < MIN_OBS:
        return None
    crit = crit or load_criteria()
    reps = min(MAX_REPS, crit.null_reps(family))
    return st.random_side_pvalue(np.asarray(outcomes, float), np.asarray(flips, float), reps,
                                 st.rng_for(crit.seed, f"escaner|{label}"))


def dsr(outcomes: Sequence[float], family: int) -> float | None:
    return st.dsr(list(outcomes), family) if len(outcomes) >= 3 else None


def adjust(pvals: Mapping[str, float | None], prior_family: int = PRIOR_FAMILY
           ) -> dict[str, tuple[float, float]]:
    """(p de Holm, q de BH) de cada intento del escáner sobre la familia completa: los previos de
    T49 sin p (= 1) más todos los del escáner (sin p = 1)."""
    fam = {f"previo:{i:05d}": 1.0 for i in range(prior_family)}
    fam.update({k: 1.0 if p is None else float(p) for k, p in pvals.items()})
    if not pvals:
        return {}
    h, q = holm(fam), bh(fam)
    return {k: (h[k], q[k]) for k in pvals}


def family_size(n_scanner: int, prior_family: int = PRIOR_FAMILY) -> int:
    return prior_family + n_scanner


def verdict(n_matured: int, p_holm: float | None, alpha: float) -> str:
    if n_matured < MIN_OBS:
        return f"sin resultados suficientes ({n_matured}/{MIN_OBS} maduros): p = 1"
    if p_holm is not None and p_holm < alpha:
        return "supera el azar con Holm — NO validada: falta la puerta v1 de T49 (V1–V6)"
    return "no supera el azar con Holm sobre la familia completa"


def present(key: str, stats: Mapping | None, adj: Mapping[str, tuple[float, float]],
            family: int, alpha: float) -> dict:
    """Lo que muestra la candidata: nº de hipótesis de su familia y su p ajustado."""
    s = stats or {}
    p_h, q = adj.get(key, (1.0, 1.0))
    n_m = int(s.get("n_matured") or 0)
    return {"attempt_key": key, "n_family": family, "n_obs": int(s.get("n_obs") or 0),
            "n_matured": n_m, "p_raw": s.get("p_raw"), "p_holm": round(p_h, 6),
            "q_bh": round(q, 6), "dsr": s.get("dsr"), "verdict": verdict(n_m, p_h, alpha),
            "validation": validation_status(key)}


def validation_status(key: str, t49_validated: frozenset[str] = frozenset()) -> str:
    """«VALIDADA» solo si la puerta v1 de T49 validó ese mismo intento; si no, «no validada»."""
    return VALIDATED if key in t49_validated else NOT_VALIDATED
