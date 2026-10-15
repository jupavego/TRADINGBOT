"""Parámetros del bróker simulado: ejecución, retroalimentación y los 3 perfiles (sin números
mágicos en la lógica)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from eim.backtest.params import CostParams

FAMILIES: dict[str, str] = {
    "consenso": "Consenso de agentes",
    "sugerencias": "Operaciones sugeridas",
    "escenarios": "Escenarios proyectados",
    "agentes": "Agentes individuales",
    "indicadores": "Indicadores técnicos",
    "contrarias": "Contrarias",
    "control": "Control aleatorio",
}


class ExecParams(BaseModel):
    """Mecánica de la simulación. Costos: tarifa regular de Binance (`CostParams`)."""

    model_config = ConfigDict(frozen=True)

    costs: CostParams = CostParams()
    timeframe: str = "1h"            # marco de decisión (contexto por vela cerrada)
    path_tf: str = "15m"             # camino del precio para llenar y salir
    min_risk_frac: float = 0.001     # SL a menos de 0,1 % del precio = geometría inválida
    funding_8h_assumed: float = 0.0001   # solo donde falta el funding real
    cooldown_bars: int = 1           # velas de espera tras cerrar antes de reentrar


class FeedbackParams(BaseModel):
    """Retroalimentación: expectativa en R contraída hacia 0 y con decaimiento.

    m = Σ wᵢ·rᵢ / (Σ wᵢ + prior_n), wᵢ = 0,5^(antigüedad/half_life). Peso = 1 + gain·m acotado.
    Pausa si m + z_pause·se < 0 con muestra ≥ n_min (claramente negativa); mientras la muestra es
    menor que n_min la estrategia está «en observación» con peso `observe_w`.
    """

    model_config = ConfigDict(frozen=True)

    prior_n: float = 10.0
    half_life: float = 40.0
    n_min: int = 8
    gain: float = 1.5
    w_min: float = 0.25
    w_max: float = 2.0
    z_pause: float = 1.0
    observe_w: float = 0.5


class ProfileParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    description: str
    initial_equity: float = 10_000.0
    risk_pct: float                  # fracción del capital arriesgada hasta el SL (× peso)
    max_leverage: int
    max_open: int                    # posiciones + órdenes abiertas a la vez
    min_conf: float
    min_rr: float
    families: frozenset[str]
    allow_hedge: bool                # largo y corto a la vez (subcuentas por estrategia)
    follow_synthesis: bool           # exige ir a favor del sesgo de la síntesis
    min_syn_bias: float = 0.1
    liq_buffer: float = 2.0          # distancia a liquidación ≥ liq_buffer × distancia al SL
    min_risk_fill: float = 0.25      # si el margen no alcanza para ≥ 25 % del riesgo: rechazo
    feedback: FeedbackParams = FeedbackParams()


PROFILES: tuple[ProfileParams, ...] = (
    ProfileParams(
        id="conservador", name="Conservador",
        description="Solo consenso, sugerencias y escenarios a favor de la síntesis; 0,5 % de "
                    "riesgo, hasta 3x; pausa toda estrategia cuya expectativa sea negativa.",
        risk_pct=0.005, max_leverage=3, max_open=3, min_conf=0.3, min_rr=1.5,
        families=frozenset({"consenso", "sugerencias", "escenarios"}),
        allow_hedge=False, follow_synthesis=True,
        # z_pause=0: con muestra suficiente, toda expectativa contraída negativa pausa
        feedback=FeedbackParams(gain=1.0, w_min=0.25, w_max=1.5, n_min=10, z_pause=0.0,
                                observe_w=0.5)),
    ProfileParams(
        id="moderado", name="Moderado",
        description="Todas las familias direccionales salvo las contrarias; 1 % de riesgo, "
                    "hasta 5x, aprendizaje estándar.",
        risk_pct=0.01, max_leverage=5, max_open=6, min_conf=0.15, min_rr=1.3,
        families=frozenset({"consenso", "sugerencias", "escenarios", "agentes", "indicadores"}),
        allow_hedge=True, follow_synthesis=False),
    ProfileParams(
        id="agresivo", name="Agresivo",
        description="Todo el abanico (incluidas las contrarias); 2 % de riesgo, hasta 10x, "
                    "refuerza rápido lo que gana y tolera más rachas.",
        risk_pct=0.02, max_leverage=10, max_open=10, min_conf=0.0, min_rr=1.1,
        families=frozenset({"consenso", "sugerencias", "escenarios", "agentes", "indicadores",
                            "contrarias"}),
        allow_hedge=True, follow_synthesis=False,
        feedback=FeedbackParams(gain=2.5, w_min=0.25, w_max=3.0, half_life=20, n_min=6,
                                z_pause=1.5, observe_w=1.0)),
)
