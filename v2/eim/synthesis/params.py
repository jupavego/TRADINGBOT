"""Parámetros de la síntesis (pesos ajustables en T26; sin números mágicos en la lógica)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Agentes NO direccionales (T44): jamás suman al sesgo, aunque se vacíe `excluded` o se les dé
# peso. `calendar` solo modula la confianza (ventana de evento) y el tamaño (motor de riesgo);
# `arbitrage` vive en su carril propio (pestaña y satélite del río).
NON_DIRECTIONAL: frozenset[str] = frozenset({"calendar", "arbitrage"})

# Núcleo con el que se mide la correlación de un agente nuevo (T44) o de un bot (T59/T60).
PEERS: tuple[str, ...] = ("ema", "structure", "technical")

Role = Literal["direccional", "riesgo", "carril", "derivado", "contexto"]
# Papel de cada agente que no vota como uno más (el resto es «direccional").
ROLES: dict[str, Role] = {"calendar": "riesgo", "regime": "riesgo", "arbitrage": "carril",
                          "plan": "derivado"}
# Papel mientras el agente siga en `excluded`: al sacarlo (T60, tras la puerta de edge de T59)
# `role_of` lo devuelve como «direccional» sin tocar nada más.
EXCLUDED_ROLES: dict[str, Role] = {"bots": "contexto"}

# T44 — agentes nuevos que entran como votos direccionales. Peso candidato «moderado» = 0.5
# (la mitad de un agente existente); el vigente sale de la prueba de contribución marginal
# fuera de muestra (`python -m eim.analytics.agents_marginal_report`, reports/agents_marginal.md):
# si no aporta, su peso inicial es 0 (sigue a la vista, no mueve la síntesis).
MODERATE_WEIGHT = 0.5
T44_WEIGHTS: dict[str, float] = {
    # BTCUSDT 1h, prueba 2024-12 → 2026-10: ΔSharpe −0,00, ΔE[R] +0,000, ΔIC24 +0,0004 (IC95
    # −0,002…+0,003), mejora en 2 de 7 ventanas → no aporta (como reports/technical_ic.md).
    "technical": 0.0,
    # Sin historia: tablero desde 2026-10-16 y ningún líder aprobado (100 % `no_data`) → no medible.
    "smart_money": 0.0,
    # T53: reglas de los libros; sin medición (T54) aporta contexto, no voto.
    "literature": 0.0,
    # T57: escuadrón de bots; ninguno está en estado `vota` hasta T59/T60.
    "bots": 0.0,
}
# Correlación (Pearson del sesgo, velas en que ambos tienen datos) de cada agente nuevo con los
# existentes que miden lo mismo, medida en la mitad de descubrimiento (BTCUSDT 1h 2023-01 →
# 2024-12, n = 4093). Solo se penaliza el agente nuevo, y solo si el correlacionado vota.
T44_CORRELATION: dict[str, dict[str, float]] = {"technical": {"ema": 0.684, "structure": 0.584}}


class SynthesisParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Peso base por agente (1.0 si no figura). Calibrable en T26; los de T44 vienen medidos.
    weights: dict[str, float] = Field(default_factory=lambda: dict(T44_WEIGHTS))
    # Agentes que no votan: `plan` deriva de structure/levels (doble conteo), `regime` modula
    # pesos y los no direccionales (`NON_DIRECTIONAL`, siempre fuera) emiten bias=0.
    excluded: frozenset[str] = frozenset({"plan", "calendar", "arbitrage", "regime", "bots"})
    # Multiplicadores de peso por régimen y agente (cuando exista el agente de régimen, T22).
    regime_weights: dict[str, dict[str, float]] = Field(default_factory=dict)
    # ρ medida entre agentes (nuevo → {existente: ρ}); peso × (1 − k·máx ρ⁺ de los que votan).
    correlation: dict[str, dict[str, float]] = Field(
        default_factory=lambda: {k: dict(v) for k, v in T44_CORRELATION.items()})
    corr_penalty: float = 1.0
    degraded_factor: float = 0.5      # un agente degradado pesa y confía la mitad
    conflict_bias: float = 0.2        # |sesgo| mínimo para considerar que un agente toma partido
    disagree_penalty: float = 0.5     # factor de confianza si hay agentes fuertes opuestos
    # Calendario (T44): confianza × esto dentro de una ventana de evento; × `blackout_conf` si la
    # ventana abre `blackout` (el motor de riesgo además veta entradas nuevas, T29).
    event_conf: float = 0.75
    blackout_conf: float = 0.5
    # Escuadrón (T60), canal (a): desacuerdo entre los bots que T59 midió útiles → confianza ×
    # `squad_conf` (solo baja, nunca sube). Apagado salvo que la política lo active.
    squad_confidence: bool = False
    squad_split: float = 0.8          # desviación (pstdev) de posturas ±1 que cuenta como «extremo»
    squad_conf: float = 0.85
    neutral_band: float = 0.1         # |sesgo| bajo esta banda se describe como neutral
    drift_scale: float = 0.1          # deriva = sesgo·confianza·scale·σ (σ = desv. del log-retorno)


def role_of(agent_id: str, p: SynthesisParams | None = None) -> Role:
    """Papel del agente en la síntesis: vota (`direccional`) o no (riesgo, carril, derivado)."""
    if agent_id in ROLES:
        return ROLES[agent_id]
    p = p or SynthesisParams()
    if agent_id in p.excluded and agent_id in EXCLUDED_ROLES:
        return EXCLUDED_ROLES[agent_id]
    return "riesgo" if agent_id in p.excluded | NON_DIRECTIONAL else "direccional"
