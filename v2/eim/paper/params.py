"""Parámetros del bróker simulado: ejecución, retroalimentación y los 3 perfiles (sin números
mágicos en la lógica)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from eim.backtest.params import CostParams
from eim.paper.caps import CapParams

FAMILIES: dict[str, str] = {
    "consenso": "Consenso de agentes",
    "sugerencias": "Operaciones sugeridas",
    "escenarios": "Escenarios proyectados",
    "agentes": "Agentes individuales",
    "indicadores": "Indicadores técnicos",
    "literatura": "Literatura (reglas de los libros, T54)",
    "contrarias": "Contrarias",
    "base": "Posición base (mínimo de abiertas)",
    "ppp": "Entradas propias de la escalera (PPP)",
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


class LadderParams(BaseModel):
    """Protección progresiva de ganancias (perfil `ppp_btcusdt`): SL dinámico por escalones.

    Los escalones se miden en beneficio NETO estimado (tras comisiones, deslizamiento y funding),
    no en precio. Los tres «prohibidos» son configuración visible pero no se pueden activar: la
    estrategia no tiene TP final, ni cierre por tiempo, ni dinero real (`ladder.py` los respeta).
    """

    model_config = ConfigDict(frozen=True)

    first_usdt: float = 10.0         # beneficio neto que activa la protección (primer escalón)
    step_usdt: float = 5.0           # cada +5 USDT de beneficio máximo eleva un escalón
    tick: float = 0.1                # precisión del precio (BTCUSDT perpetuo)
    qty_step: float = 0.001          # precisión de la cantidad (BTC)
    min_target_vs_first: float = 1.0  # el objetivo de la idea (solo estimación) debe cubrir ≥ ×
    # Reservas del SL para que el neto realizado se parezca al nominal: deslizamiento de salida =
    # el MAYOR de las últimas `slip_lookback` velas (ya conocidas) y funding de `funding_reserve`
    # liquidaciones futuras a la tasa supuesta. Un hueco real puede seguir superándolas.
    slip_lookback: int = 4
    fine_tf: str = "1m"     # velas que resuelven el orden dentro de una vela ambigua de 15 m
    funding_reserve: int = 1
    # Freno de riesgo (solo frena ENTRADAS NUEVAS, jamás cierra posiciones): tras
    # `max_consec_losses` pérdidas seguidas, o si el capital cae `max_drawdown` desde su máximo,
    # no abre durante `pause_hours`; luego reanuda (el máximo se reinicia al capital actual).
    max_consec_losses: int = 4
    max_drawdown: float = 0.08
    pause_hours: float = 24.0
    fixed_take_profit: bool = False
    time_exit: bool = False
    real_money: bool = False

    @model_validator(mode="after")
    def _forbidden(self) -> LadderParams:
        if self.fixed_take_profit or self.time_exit or self.real_money:
            raise ValueError("PPP no admite TP fijo, cierre por tiempo ni dinero real")
        if self.first_usdt <= 0 or self.step_usdt <= 0 or self.tick <= 0 or self.qty_step <= 0:
            raise ValueError("first_usdt, step_usdt, tick y qty_step deben ser positivos")
        if self.slip_lookback < 1 or self.funding_reserve < 0 or self.pause_hours < 0:
            raise ValueError("slip_lookback ≥ 1, funding_reserve ≥ 0 y pause_hours ≥ 0")
        if self.max_consec_losses < 1 or not 0 < self.max_drawdown < 1:
            raise ValueError("max_consec_losses ≥ 1 y 0 < max_drawdown < 1")
        return self


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
    # Mínimo de operaciones abiertas: si hay menos de `min_open` posiciones, la primera señal a
    # mercado que solo incumpla filtros BLANDOS (confianza, R:B ≥ `floor_min_rr`, síntesis,
    # «solo lo probado», costo ≤ `floor_max_cost_r`) entra con riesgo × `floor_weight`. Pausas,
    # tendencia mayor, cupo, cobertura y margen siguen siendo vetos duros. Queda marcada
    # «mínimo» en el libro. 0 lo desactiva.
    min_open: int = 0
    # Lo mismo para las órdenes de entrada pendientes (límites sin llenar): con menos de
    # `min_pending`, la primera idea LÍMITE que solo incumpla filtros blandos se coloca.
    min_pending: int = 0
    floor_weight: float = 0.5
    floor_min_rr: float = 1.0
    floor_max_cost_r: float = 0.3    # costo ida y vuelta máximo (en R) que tolera el mínimo
    # Salida: "tp" (SL/TP/BE/tiempo de la sombra) o "ladder" (SL dinámico por escalones, sin TP
    # ni tiempo; se simula en el libro porque los escalones dependen de la cantidad en USDT).
    exit_mode: Literal["tp", "ladder"] = "tp"
    ladder: LadderParams | None = None
    symbols: tuple[str, ...] | None = None   # None = todos los símbolos de la mesa
    feedback: FeedbackParams = FeedbackParams()
    caps: CapParams = CapParams()    # topes de riesgo (apagados por defecto)


PROFILES: tuple[ProfileParams, ...] = (
    ProfileParams(
        id="conservador", name="Conservador",
        description="Solo lo ya probado (≥ 10 operaciones con expectativa positiva), a favor "
                    "de la síntesis y de la tendencia mayor, costo ≤ 0,12 R; 0,5 % de riesgo, "
                    "hasta 3x. Mantiene al menos 1 posición abierta y 1 orden pendiente (riesgo "
                    "reducido).",
        risk_pct=0.005, max_leverage=3, max_open=3, min_conf=0.3, min_rr=1.5,
        min_open=1, min_pending=1,
        families=frozenset({"consenso", "sugerencias", "escenarios", "agentes", "indicadores",
                            "base"}),
        allow_hedge=False, follow_synthesis=True, max_cost_r=0.12, require_htf=True,
        # solo lo ya probado: sin peso en observación y pausa ante expectativa negativa
        feedback=FeedbackParams(gain=1.0, w_min=0.25, w_max=1.5, n_min=10, z_pause=0.0,
                                observe_w=0.0)),
    ProfileParams(
        id="moderado", name="Moderado",
        description="Todas las familias direccionales salvo las contrarias, a favor de la "
                    "tendencia mayor, costo ≤ 0,15 R; 1 % de riesgo, hasta 5x. Mantiene al menos 2 "
                    "posiciones abiertas y 1 orden pendiente.",
        risk_pct=0.01, max_leverage=5, max_open=6, min_conf=0.15, min_rr=1.3,
        min_open=2, min_pending=1,
        families=frozenset({"consenso", "sugerencias", "escenarios", "agentes", "indicadores",
                            "base"}),
        allow_hedge=True, follow_synthesis=False, max_cost_r=0.15, require_htf=True,
        feedback=FeedbackParams(z_pause=0.0, observe_w=0.25)),
    ProfileParams(
        id="agresivo", name="Agresivo",
        description="Todo el abanico (incluidas las contrarias) a favor de la tendencia mayor; "
                    "2 % de riesgo, hasta 10x, explora más y refuerza rápido lo que gana. Mantiene "
                    "al menos 3 posiciones abiertas y 2 órdenes pendientes.",
        risk_pct=0.02, max_leverage=10, max_open=10, min_conf=0.0, min_rr=1.1,
        min_open=3, min_pending=2,
        families=frozenset({"consenso", "sugerencias", "escenarios", "agentes", "indicadores",
                            "base", "contrarias"}),
        allow_hedge=True, follow_synthesis=False, max_cost_r=0.2, require_htf=True,
        feedback=FeedbackParams(gain=2.5, w_min=0.25, w_max=3.0, half_life=20, n_min=6,
                                z_pause=0.0, observe_w=0.5)),
)


PPP_ID = "ppp_btcusdt"
PROFILES = PROFILES + (
    ProfileParams(
        id=PPP_ID, name="Progressive Profit Protection — BTCUSDT",
        description="BTCUSDT, simulado. SL inicial por riesgo (0,5 % del capital) y, al llegar a "
                    "+10 USDT netos, SL dinámico por escalones de +5 USDT que nunca retrocede. "
                    "Sin TP final ni cierre por tiempo: cierra solo al tocar el SL vigente. "
                    "A favor de la síntesis y de la tendencia mayor; hasta 2 posiciones, 5x.",
        risk_pct=0.005, max_leverage=5, max_open=2, min_conf=0.3, min_rr=1.3,
        families=frozenset({"consenso", "sugerencias", "escenarios", "agentes", "indicadores",
                            "ppp"}),
        allow_hedge=False, follow_synthesis=True, max_cost_r=0.15, require_htf=True,
        exit_mode="ladder", ladder=LadderParams(), symbols=("BTCUSDT",),
        # aprende de SUS PROPIOS cierres (`ladder_book.LadderRisk`), no de la sombra con TP:
        # peso fijo 1 (jamás sube el tamaño tras una pérdida) y pausa si una estrategia o
        # contexto rinde con expectativa claramente negativa en la escalera
        feedback=FeedbackParams(gain=0.0, w_min=1.0, w_max=1.0, n_min=8, z_pause=0.0,
                                observe_w=1.0)),
)
