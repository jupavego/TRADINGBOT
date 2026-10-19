"""Ajuste bibliográfico de las probabilidades de escenario (T54): experimento APAGADO por defecto.

p'ᵢ = pᵢ · exp(k · netoᵢ) / Σⱼ pⱼ · exp(k · netoⱼ), con `netoᵢ` = `scenario_support[i].net` del
agente `literature` (−1..+1) y `k` fijado en el preregistro. Con `neto = 0` las probabilidades no
cambian; siempre suman 1. La definición (`k`, criterios, muestra) es inmutable en
`versions/lit_tilt_v1.json`; solo se aplica en vivo si `lit_tilt_state.json` dice `enabled: true`
para esa versión (commit tras cumplir los criterios del informe de T54).
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from eim.core import ForecastSet

CONFIG_FILE = Path(__file__).parent / "versions" / "lit_tilt_v1.json"
STATE_FILE = Path(__file__).parent / "lit_tilt_state.json"
IDS = ("bull", "neutral", "bear")
LABEL = "incluye ajuste bibliográfico (experimento T54)"


class TiltCriteria(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_forecasts: int
    min_active: int
    boot_reps: int
    level: float
    seed: int


class TiltSample(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: str
    horizon: int
    stride: int
    n_paths: int
    context: int
    agent_bars: int


class TiltConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str
    enabled: bool
    description: str
    k: float
    criteria: TiltCriteria
    sample: TiltSample


def load_config(path: Path = CONFIG_FILE, state: Path = STATE_FILE) -> TiltConfig:
    """Definición inmutable + estado de activación (apagado si falta o no es de esta versión)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    st = json.loads(state.read_text(encoding="utf-8")) if state.exists() else {}
    on = bool(st.get("enabled")) and st.get("version") == raw["version"]
    return TiltConfig.model_validate({**raw, "enabled": on})


def tilt_probs(probs: Mapping[str, float], net: Mapping[str, float], k: float
               ) -> dict[str, float]:
    """Probabilidades ajustadas (suman 1). `net` ausente = 0; sin ajuste si `k = 0`."""
    w = {i: probs[i] * math.exp(k * float(net.get(i) or 0.0)) for i in IDS}
    z = sum(w.values())
    if z <= 0:
        return {i: float(probs[i]) for i in IDS}
    return {i: w[i] / z for i in IDS}


def apply_tilt(fs: ForecastSet, net: Mapping[str, float], cfg: TiltConfig) -> ForecastSet:
    """`ForecastSet` con las probabilidades ajustadas y `adjustments` que lo declara. Si el
    experimento está apagado, o el neto es 0 en todos los escenarios, devuelve `fs` intacto."""
    if not cfg.enabled or not any(net.get(i) for i in IDS):
        return fs
    base = {s.id: s.probability for s in fs.scenarios}
    new = tilt_probs(base, net, cfg.k)
    scen = [s.model_copy(update={
        "probability": new[s.id],
        "narrative": f"{s.narrative} Probabilidad con ajuste bibliográfico: "
                     f"{base[s.id]:.0%} del motor → {new[s.id]:.0%} ({cfg.version})."})
        for s in fs.scenarios]
    adj = {"id": cfg.version, "k": cfg.k, "label": LABEL, "net": {i: float(net.get(i) or 0.0)
                                                                   for i in IDS},
           "base_probability": base}
    return fs.model_copy(update={"scenarios": scen, "adjustments": [*fs.adjustments, adj]})
