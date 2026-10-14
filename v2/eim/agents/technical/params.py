"""Parámetros del agente `technical` (todos calibrables en T26; nada mágico en las reglas)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

FAMILIES: tuple[str, ...] = ("tendencia", "momentum", "volatilidad", "volumen", "flujo")
REGIMES: tuple[str, ...] = ("tendencia", "rango", "mixto")


class RuleParams(BaseModel):
    """Umbrales de las reglas de voto (ver `rules.py`)."""

    model_config = ConfigDict(frozen=True)

    rsi_ob: float = 70.0
    rsi_os: float = 30.0
    stoch_ob: float = 80.0  # KDJ-K, StochRSI-K, MFI
    stoch_os: float = 20.0
    wr_ob: float = -20.0
    wr_os: float = -80.0
    cci_ext: float = 100.0
    divergence_lookback: int = 20  # velas para buscar divergencias precio/oscilador
    divergence_weight: float = 0.5
    adx_full: float = 25.0  # ADX al que el voto DMI alcanza su magnitud plena
    atr_scale: float = 1.0  # distancia en ATR a la que VWAP vota ±1
    vol_lookback: int = 5  # cambio de precio que VOL confirma
    flow_window: int = 20  # velas del desequilibrio agresor (BS.Vol, TakerRatio, CVD)
    delta_window: int = 5
    flow_gain: float = 3.0  # desequilibrio de 1/3 → voto ±1


class TechnicalParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    rules: RuleParams = RuleParams()
    min_bars: int = 120  # por marco: calentamiento de MA99/TRIX/StochRSI
    warmup_bars: int = 300  # por debajo: estado degradado
    horizon_bars: int = 12
    # Anti-redundancia: dentro de una familia, votos con correlación ≥ umbral (en la ventana)
    # forman un grupo que pesa como uno solo; los duplicados exactos se colapsan antes.
    cluster_corr: float = 0.85
    cluster_window: int = 300
    cluster_min_obs: int = 30
    # Peso base de cada indicador dentro de su familia (1.0 si no figura).
    indicator_weights: dict[str, float] = {}
    # Régimen simple: ADX (DMI) y ancho de Bollinger en percentil de la ventana.
    adx_trend: float = 25.0
    adx_range: float = 20.0
    squeeze_pct: float = 0.2  # ancho ≤ percentil → compresión = rango (si ADX es intermedio)
    width_window: int = 200
    # Peso de cada familia por régimen: en rango pesan más osciladores y bandas.
    family_weights: dict[str, dict[str, float]] = {
        "tendencia": {"tendencia": 1.6, "momentum": 0.7, "volatilidad": 0.5,
                      "volumen": 1.0, "flujo": 1.0},
        "rango": {"tendencia": 0.5, "momentum": 1.5, "volatilidad": 1.4,
                  "volumen": 1.0, "flujo": 1.0},
        "mixto": {f: 1.0 for f in FAMILIES},
    }
    # Multi-marco: escalera de marcos (minutos) y factor de agregación hacia el superior.
    tf_minutes: dict[str, int] = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    mtf_neutral: float = 0.1  # |sesgo| menor = neutral al medir acuerdo entre marcos
    mtf_min_factor: float = 0.5  # confianza × (min + (1 − min)·acuerdo)
    conf_floor: float = 0.3  # confianza con sesgo 0 y familias de acuerdo
    conf_full_bias: float = 0.5  # |sesgo| a partir del cual la magnitud no limita la confianza
    max_confidence: float = 0.8  # sin edge demostrado (reports/technical_ic.md) no se satura
    evidence_per_family: int = 3
