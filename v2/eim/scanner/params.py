"""Parámetros del escáner global (T93): embudo, presupuesto, cola y ritmos.

Todo lo que decide quién pasa el embudo vive aquí, con su valor por defecto y el porqué. Los
parámetros viajan con cada corrida (`runs.params_json` de `scanner.duckdb`), así que una
puntuación siempre se puede reconstruir con los mismos umbrales.

**Presupuesto (T87, `PLAN/notas/T87_matriz.md` §2.2).** La etapa barata del embudo se definió
por costo medido: los 13 agentes ≤ 20 ms suman 18,7 ms por instrumento. El escáner se fija el
mismo techo, `budget_ms_per_instrument = 20`, para las etapas 1–3 completas (lectura del
almacén incluida); con él, 10 000 instrumentos caben en ≈ 3,3 min de un proceso.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from eim.core.market import Frozen

#: Versión de la etapa 3 (fórmulas y pesos de `screen.py`). Cambiarla invalida la caché y deja
#: escrito en cada corrida con qué fórmula salió cada puntuación.
SCREEN_VERSION = "1.0.0"

DAY_MS = 86_400_000

#: Perpetuos sin mercado subyacente que los ancle (T88, BACKLOG T88 (5) y T89 (1)): fuera del
#: universo por decisión escrita, no por una heurística sobre el nombre.
PRE_IPO: frozenset[str] = frozenset({"OPENAIUSDT", "OURAUSDT", "MOONSHOTUSDT"})


class ScannerParams(Frozen):
    """Umbrales del embudo y del servicio (los valores por defecto están razonados abajo)."""

    # --- universo (etapa 1) ------------------------------------------------------------------
    venue: str = "binance"
    #: Primer universo de T93: los perpetuos USDⓈ-M liquidados en USDT (los 659 de T181).
    quote_currencies: tuple[str, ...] = ("USDT",)
    perpetual_only: bool = True
    #: Nivel de permiso mínimo (T89 `TradableLevel`): 1 = investigación, que es el alcance
    #: aprobado (análisis simulado). Subirlo a 2 deja fuera los perpetuos TradFi.
    min_level: int = 1
    #: Ventana para contar altas, bajas y vencimientos recientes en el informe de la corrida.
    lifecycle_days: int = 7

    # --- datos (etapa 2) ---------------------------------------------------------------------
    timeframe: str = "1d"
    #: Velas que se leen por instrumento; la etapa 3 usa como mucho 61 (volatilidad de 60).
    n_bars: int = 90
    min_bars: int = 61
    #: Velas de margen antes de llamar «viejo» a un dato (por clase; el resto, 1): las mismas
    #: de `eim/data/quality.py` (`STALE_GRACE_BARS`).
    stale_grace_bars: dict[str, int] = Field(default_factory=lambda: {"crypto": 2})
    #: Liquidez mínima: mediana del volumen en moneda de cotización por día (v · c) en las
    #: últimas `liquidity_bars` velas, reescalada al marco.
    min_quote_volume_per_day: float = 1_000_000.0
    liquidity_bars: int = 20
    #: Diferencial máximo (pb) cuando hay cotización; sin cotización no se excluye salvo que
    #: `require_spread` lo pida (se cuenta como «spread sin medir», nunca se inventa).
    max_spread_bps: float = 20.0
    require_spread: bool = False

    # --- etapa 3 -----------------------------------------------------------------------------
    budget_ms_per_instrument: float = 20.0
    #: Velas que recibe la preparación profunda de la lista corta (las de la medición de T87;
    #: `plan`, `regime` y `technical` piden 120 como mínimo).
    deep_bars: int = 500
    shortlist_size: int = 25
    min_score: float = 0.0

    # --- ritmo rápido ------------------------------------------------------------------------
    #: Alerta de precio: movimiento desde el cierre puntuado, en desviaciones de la volatilidad
    #: de 20 velas.
    alert_sigma: float = 2.0
    quote_max_age_ms: int = 120_000
    fast_every_s: float = 60.0
    deep_every_s: float = 3_600.0

    # --- cola --------------------------------------------------------------------------------
    max_procs: int = 2              # CLAUDE.md / T87: como mucho 2 procesos en estos equipos
    max_attempts: int = 3
    backoff_s: float = 2.0
    max_backoff_s: float = 60.0
    #: Llamadas por segundo por proveedor. Binance: una cada 1,5 s (velas con `limit=1000`, peso
    #: 5: ≈ 200 de peso/min, el 8 % del límite por IP que comparte con la corrida de T31).
    rate_limits: dict[str, float] = Field(default_factory=lambda: {"binance": 1 / 1.5})
    sync_days: int = 520            # una llamada por símbolo (≤ 1500 velas) y cubre `deep_bars`
    sync_per_cycle: int = 40

    # --- observatorio ------------------------------------------------------------------------
    obs_min_interval_s: float = 300.0
    obs_max_alerts: int = 5

    @model_validator(mode="after")
    def _coherent(self) -> ScannerParams:
        if self.min_bars > self.n_bars:
            raise ValueError("min_bars no puede superar n_bars")
        if self.min_bars < 61:
            raise ValueError("la etapa 3 necesita al menos 61 velas (volatilidad de 60)")
        if self.max_procs < 1 or self.max_attempts < 1:
            raise ValueError("max_procs y max_attempts ≥ 1")
        return self

    def grace(self, asset_class: str) -> int:
        return int(self.stale_grace_bars.get(asset_class, 1))


DEFAULT_PARAMS = ScannerParams()
