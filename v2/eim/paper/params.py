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
    timeframes: tuple[str, ...] = ("15m", "1h", "4h")   # marcos de decisión (T48)
    path_tf: str = "15m"             # camino del precio para llenar y salir
    min_risk_frac: float = 0.001     # SL a menos de 0,1 % del precio = geometría inválida
    funding_8h_assumed: float = 0.0001   # solo donde falta el funding real
    cooldown_bars: int = 1           # velas de espera tras cerrar antes de reentrar
    # Break-even+ (T48b): tras avanzar `be_trigger_r` R, desde la vela siguiente el SL pasa a
    # entrada + costo estimado + `be_lock_r` R (la salida queda en ganancia neta). 0 lo desactiva.
    # Evidencia (simulación exacta, 4.034 ops): acierto 1 h 37 → 44 %, 4 h 38 → 48 %, con R medio
    # igual o mejor; en 15 m empeora la expectativa → solo en `be_timeframes`.
    be_trigger_r: float = 1.0
    be_lock_r: float = 0.1
    be_cover_costs: bool = True
    be_timeframes: tuple[str, ...] = ("1h", "4h")
    est_cost_frac: float = 0.0016    # costo ida y vuelta estimado (fracción del precio)
    # Tendencia del marco mayor por marco de decisión: (marco, EMA rápida, EMA lenta). En 4 h se
    # usa el propio 4 h con EMAs largas (≈ tendencia diaria). Evidencia: a favor rinde mejor en 3/3.
    htf: dict[str, tuple[str, int, int]] = {"15m": ("1h", 21, 55), "1h": ("4h", 21, 55),
                                            "4h": ("4h", 50, 200)}


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
    # T48b: costo estimado ida y vuelta (taker 0,05 % ×2 + deslizamiento típico ≈ 0,03 % ×2) y
    # máximo que se acepta pagar en R. Evidencia (4.034 ops): costo < 0,1 R → −0,10 R/op;
    # > 0,3 R → −0,63 R/op. En 15 m el costo medio era 0,48 R por operación.
    est_cost_frac: float = 0.0016
    max_cost_r: float = 0.2
    require_htf: bool = False        # exige ir a favor de la tendencia del marco mayor
    min_risk_fill: float = 0.25      # si el margen no alcanza para ≥ 25 % del riesgo: rechazo
    # Recarga (decisión del usuario, 2026-10-18: ningún perfil se queda sin dinero y el simulador
    # sigue operando): si el saldo cae bajo `refill_below` × capital inicial se inyecta lo que
    # falta hasta el inicial. Queda en la bitácora («recarga») y la rentabilidad se mide sobre
    # todo el capital aportado. 0 = sin recarga.
    refill_below: float = 0.5
    # Opera también las estrategias y contextos en pausa (decisión del usuario, 2026-10-18: que
    # el Agresivo tome todas las operaciones) con el peso mínimo `feedback.w_min`.
    trade_paused: bool = False
    feedback: FeedbackParams = FeedbackParams()


PROFILES: tuple[ProfileParams, ...] = (
    ProfileParams(
        id="conservador", name="Conservador",
        description="Solo lo ya probado (≥ 10 operaciones con expectativa positiva), a favor "
                    "de la síntesis y de la tendencia mayor, costo ≤ 0,12 R; 0,5 % de riesgo, "
                    "hasta 3x.",
        risk_pct=0.005, max_leverage=3, max_open=3, min_conf=0.3, min_rr=1.5,
        families=frozenset({"consenso", "sugerencias", "escenarios", "agentes", "indicadores"}),
        allow_hedge=False, follow_synthesis=True, max_cost_r=0.12, require_htf=True,
        # solo lo ya probado: sin peso en observación y pausa ante expectativa negativa
        feedback=FeedbackParams(gain=1.0, w_min=0.25, w_max=1.5, n_min=10, z_pause=0.0,
                                observe_w=0.0)),
    ProfileParams(
        id="moderado", name="Moderado",
        description="Todas las familias direccionales salvo las contrarias, a favor de la "
                    "tendencia mayor, costo ≤ 0,15 R; 1 % de riesgo, hasta 5x.",
        risk_pct=0.01, max_leverage=5, max_open=6, min_conf=0.15, min_rr=1.3,
        families=frozenset({"consenso", "sugerencias", "escenarios", "agentes", "indicadores"}),
        allow_hedge=True, follow_synthesis=False, max_cost_r=0.15, require_htf=True,
        feedback=FeedbackParams(z_pause=0.0, observe_w=0.25)),
    ProfileParams(
        id="agresivo", name="Agresivo",
        description="Todo el abanico (incluidas las contrarias) a favor de la tendencia mayor; "
                    "2 % de riesgo, hasta 10x, explora más y refuerza rápido lo que gana; opera "
                    "también lo que está en pausa, con el peso mínimo.",
        risk_pct=0.02, max_leverage=10, max_open=10, min_conf=0.0, min_rr=1.1,
        families=frozenset({"consenso", "sugerencias", "escenarios", "agentes", "indicadores",
                            "contrarias"}),
        allow_hedge=True, follow_synthesis=False, max_cost_r=0.2, require_htf=True,
        trade_paused=True,
        feedback=FeedbackParams(gain=2.5, w_min=0.25, w_max=3.0, half_life=20, n_min=6,
                                z_pause=0.0, observe_w=0.5)),
)
