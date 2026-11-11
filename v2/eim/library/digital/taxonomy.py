"""Taxonomía de conceptos de la biblioteca digital (T151–T153), pura.

Cada concepto tiene un nombre en español, palabras clave (inglés y español, sin tildes) con las
que se reconoce en un resumen o texto, la categoría temática principal y el «lado» de una operación
al que se refiere. `strategy_concepts` traduce una estrategia del bróker simulado
(`eim/paper/strategies*.py`) a los conceptos que la describen: es el puente entre lo que hace el
sistema y lo que dice la literatura.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from eim.library.bm25 import fold


@dataclass(frozen=True)
class Concept:
    id: str
    name: str
    category: str
    keywords: tuple[str, ...]


_C = Concept
CONCEPTS: dict[str, Concept] = {c.id: c for c in (
    _C("technical_analysis", "Análisis técnico (en general)", "A",
       ("technical analysis", "technical trading", "trading rules", "analisis tecnico")),
    _C("support_resistance", "Soportes y resistencias", "A",
       ("support", "resistance", "soporte", "resistencia", "price level")),
    _C("chart_patterns", "Patrones gráficos", "A",
       ("head-and-shoulders", "head and shoulders", "chart pattern", "price pattern", "pattern")),
    _C("candlesticks", "Velas japonesas", "A", ("candlestick", "candle", "velas")),
    _C("volume", "Volumen", "A", ("volume", "trading volume", "volumen")),
    _C("order_flow", "Flujo de órdenes", "A",
       ("order flow", "order imbalance", "order book", "limit order", "toxicity")),
    _C("liquidity", "Liquidez", "A", ("liquidity", "illiquidity", "bid-ask", "spread", "liquidez")),
    _C("market_microstructure", "Microestructura", "A",
       ("microstructure", "price impact", "price formation", "price discovery", "informed")),
    _C("trend_following", "Seguimiento de tendencia", "E",
       ("trend following", "trend-following", "trend", "moving average", "tendencia")),
    _C("momentum", "Momentum", "E", ("momentum", "winners", "past returns", "continuation")),
    _C("intraday", "Intradía y alta frecuencia", "E",
       ("intraday", "high-frequency", "high frequency", "day trading", "day traders", "scalping")),
    _C("mean_reversion", "Reversión a la media", "E",
       ("mean reversion", "mean-reverting", "reversal", "overreaction", "reversion")),
    _C("breakout", "Rupturas", "E", ("breakout", "opening range", "channel", "ruptura")),
    _C("stat_arb", "Arbitraje estadístico y pares", "E",
       ("pairs trading", "statistical arbitrage", "relative-value", "cointegration")),
    _C("market_making", "Creación de mercado", "E",
       ("market making", "market maker", "market makers", "inventory", "quotes")),
    _C("backtest_overfitting", "Sobreajuste del backtest", "B",
       ("overfitting", "backtest", "out-of-sample", "data snooping", "data-snooping")),
    _C("multiple_testing", "Pruebas múltiples", "B",
       ("multiple testing", "reality check", "false discovery", "family-wise", "stepwise")),
    _C("performance_stats", "Estadística del rendimiento", "B",
       ("sharpe ratio", "sharpe", "deflated", "track record", "performance")),
    _C("return_distribution", "Distribución de rendimientos", "B",
       ("fat tails", "heavy tails", "stylized facts", "distribution", "kurtosis")),
    _C("volatility_model", "Modelos de volatilidad", "B",
       ("garch", "volatility", "realized volatility", "heteroskedasticity", "volatilidad")),
    _C("regime", "Regímenes y cambios estructurales", "B",
       ("regime", "switching", "changepoint", "change point", "structural break")),
    _C("forecast_eval", "Evaluación de pronósticos", "B",
       ("forecast", "predictive accuracy", "scoring rule", "calibration", "forecasting")),
    _C("time_series", "Series temporales", "B",
       ("time series", "autocorrelation", "random walk", "variance ratio", "arima")),
    _C("position_sizing", "Tamaño de la posición", "C",
       ("kelly", "position sizing", "growth", "bet sizing", "fraction")),
    _C("tail_risk", "Riesgo de cola", "C",
       ("value-at-risk", "value at risk", "expected shortfall", "coherent", "tail risk", "cvar")),
    _C("drawdown", "Caída máxima (drawdown)", "C", ("drawdown", "maximum drawdown")),
    _C("stop_loss", "Stop loss", "C", ("stop-loss", "stop loss", "stop")),
    _C("trailing_stop", "Stop dinámico (trailing)", "C",
       ("trailing stop", "trailing", "profit protection")),
    _C("vol_targeting", "Ajuste por volatilidad", "C",
       ("volatility targeting", "volatility-managed", "volatility scaling", "risk parity")),
    _C("execution_costs", "Costos de ejecución", "C",
       ("transaction costs", "execution", "market impact", "slippage", "costs")),
    _C("momentum_crash", "Caídas del momentum", "C", ("momentum crash", "crashes", "crash")),
    _C("behavioral_bias", "Sesgos cognitivos", "D",
       ("bias", "biases", "heuristics", "prospect theory", "loss aversion", "overconfidence")),
    _C("disposition", "Efecto disposición", "D",
       ("disposition", "realize their losses", "sell winners", "ride losers")),
    _C("overtrading", "Exceso de operaciones", "D",
       ("trade excessively", "overtrading", "turnover", "hazardous", "day trading")),
    _C("sentiment", "Sentimiento y psicología de masas", "D",
       ("sentiment", "noise trader", "fads", "cascades", "herding", "fear", "greed")),
    _C("market_efficiency", "Eficiencia de mercado", "D",
       ("efficient market", "efficient markets", "efficiency", "inefficiency", "adaptive markets")),
    _C("emotion", "Emoción y fisiología del operador", "D",
       ("emotional", "physiological", "psychophysiology", "stress", "emotion")),
    _C("crypto_returns", "Rendimiento y factores cripto", "F",
       ("cryptocurrency", "cryptocurrencies", "crypto", "bitcoin", "btc")),
    _C("perpetual_futures", "Futuros perpetuos", "F",
       ("perpetual", "perpetual futures", "perpetuals", "inverse futures")),
    _C("funding_rate", "Tasa de financiación (funding)", "F", ("funding rate", "funding")),
    _C("crypto_futures", "Futuros y derivados cripto", "F",
       ("bitcoin futures", "derivatives", "futures", "bitmex", "leverage")),
    _C("liquidation", "Liquidaciones y apalancamiento", "F",
       ("liquidation", "liquidations", "leverage", "margin")),
    _C("crypto_arbitrage", "Arbitraje entre plataformas cripto", "F",
       ("arbitrage", "exchanges", "price deviations", "kimchi")),
    _C("crypto_manipulation", "Manipulación y lavado de volumen", "F",
       ("manipulation", "wash trading", "tether", "pump")),
    _C("machine_learning", "Aprendizaje automático", "G",
       ("machine learning", "random forest", "gradient boosting", "neural network", "lasso")),
    _C("deep_learning", "Aprendizaje profundo", "G",
       ("deep learning", "lstm", "convolutional", "deep neural", "cnn")),
    _C("reinforcement_learning", "Aprendizaje por refuerzo", "G",
       ("reinforcement learning", "reinforcement", "q-learning", "policy gradient", "agent")),
    _C("monetary_policy", "Política monetaria y tipos", "H",
       ("monetary policy", "federal reserve", "fomc", "interest rate", "interest rates", "fed")),
    _C("macro_news", "Noticias macroeconómicas", "H",
       ("announcement", "announcements", "macroeconomic news", "news", "scheduled")),
    _C("global_liquidity", "Liquidez global y apalancamiento", "H",
       ("global financial cycle", "funding liquidity", "leverage", "dollar", "liquidity spiral")),
    _C("cross_asset", "Correlación entre activos y refugio", "H",
       ("safe haven", "hedge", "correlation", "spillover", "stocks", "gold", "diversifier")),
)}

# Conceptos de método (cómo evaluar, medir o modelar): validan una forma de trabajar, no que una
# operación vaya a ganar: el contraste los muestra como contexto, nunca como respaldo de la entrada.
METHOD_CONCEPTS = frozenset({"forecast_eval", "multiple_testing", "backtest_overfitting",
                             "performance_stats", "volatility_model", "regime", "time_series",
                             "return_distribution"})

# Estrategia del bróker (prefijo o nombre) → conceptos que describen su entrada.
STRATEGY_MAP: tuple[tuple[str, tuple[str, ...]], ...] = (
    (r"supertrend|cruce_ema|agente_ema|macd|adx|tendencia|ppp_|trend", ("trend_following",
                                                                         "momentum")),
    (r"donchian|bb_ruptura|ruptura|breakout", ("breakout", "trend_following")),
    (r"rsi|bb_reversion|retroceso|rango|reversion", ("mean_reversion", "support_resistance")),
    (r"levels|niveles", ("support_resistance",)),
    (r"structure|estructura", ("trend_following", "support_resistance")),
    (r"price_action", ("chart_patterns", "candlesticks")),
    (r"nison|vela|envolvente|hammer|star|soldier|crow|engulf", ("candlesticks", "chart_patterns")),
    (r"murphy|weekly", ("breakout", "trend_following")),
    (r"contra_", ("mean_reversion", "sentiment")),
    (r"funding|carry|basis", ("funding_rate", "perpetual_futures")),
    (r"micro|ofi|flow|liq", ("order_flow", "liquidation")),
    (r"control_aleatorio", ("market_efficiency",)),
)
FORECAST_FAMILIES = re.compile(r"consenso|sintesis|escenario|plan_|sugerencia|agente")


def strategy_concepts(strategy: str) -> list[str]:
    """Conceptos de una estrategia del bróker (`ind_donchian@1h` → rupturas, tendencia)."""
    s = fold(strategy.split("@")[0])
    out: list[str] = []
    for pat, cs in STRATEGY_MAP:
        if re.search(pat, s):
            out += [c for c in cs if c not in out]
    return out or ["technical_analysis"]


def strategy_context(strategy: str) -> list[str]:
    """Conceptos de método asociados a la estrategia (las que salen de pronósticos)."""
    return ["forecast_eval"] if FORECAST_FAMILIES.search(fold(strategy.split("@")[0])) else []


def detect(text: str, min_hits: int = 1) -> list[str]:
    """Conceptos mencionados en un texto (palabra clave completa, sin tildes)."""
    t = " " + re.sub(r"[^a-z0-9\- ]+", " ", fold(text)) + " "
    found = []
    for c in CONCEPTS.values():
        hits = sum(1 for k in c.keywords if f" {k} " in t or f" {k}s " in t)
        if hits >= min_hits:
            found.append(c.id)
    return found


def unknown(concepts: list[str]) -> list[str]:
    return [c for c in concepts if c not in CONCEPTS]
