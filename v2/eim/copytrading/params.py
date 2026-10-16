"""Umbrales del scorecard de líderes (T41). Nada mágico en la lógica: todo se ajusta aquí."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ScoreParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    # --- Muestra ------------------------------------------------------------------------------
    # Preselección (histórico): operaciones cerradas en el historial capturado O historial de
    # cartera (`portfolio`) suficientemente largo. Lo histórico nunca aprueba por sí solo.
    min_hist_trades: int = 20
    min_portfolio_days: float = 30.0
    # Aprobación: solo con lo observado por nosotros hacia adelante.
    min_fwd_trades: int = 30
    min_fwd_days: float = 7.0

    # --- Estadística --------------------------------------------------------------------------
    dsr_min: float = 0.95  # probabilidad de que el Sharpe real supere al mejor de N al azar
    ci_level: float = 0.95  # intervalo; se corrige por Bonferroni con el nº de billeteras
    # Billeteras «probadas»: el descubrimiento (T40) muestrea cientos de direcciones y se queda
    # con las mejores. Si no consta el tamaño del universo se asume este mínimo (conservador).
    min_trials: int = 100

    # --- Reglas duras de descarte -------------------------------------------------------------
    max_drawdown: float = 0.5  # caída máxima de la cartera (fracción)
    max_leverage: float = 20.0  # apalancamiento mediano
    max_liquidations: int = 0
    min_racha_windows: int = 5  # días (o tramos de cartera) para juzgar una racha
    max_avg_down_share: float = 0.25  # fracción de operaciones con promediado a la baja
    avg_down_tol: float = 0.002  # aumento a precio peor que la entrada media en > 0,2 %
    martingale_ratio: float = 1.8  # tamaño tras pérdida / tamaño tras ganancia
    martingale_min_n: int = 10  # pérdidas y ganancias mínimas para medirlo (con menos es ruido)
    latent_loss_share: float = 0.5  # PnL latente negativo / ganancia realizada
    latent_loss_equity: float = 0.1  # o / valor de la cuenta
    min_account_usd: float = 1_000.0  # cuentas más chicas no sirven de base para retornos

    # --- Copiabilidad -------------------------------------------------------------------------
    exec_delay_ms: int = 300  # lo que tarda nuestra orden tras ver la ejecución del líder
    follower_taker_fee: float = 0.00045  # Hyperliquid, nivel base tomador (2026-10)
    allmids_half_spread: float = 0.0002  # con `allMids` no hay libro: medio diferencial supuesto
    quote_timeout_ms: int = 15_000  # cotización más vieja que esto no vale
    live_max_latency_ms: int = 120_000  # ejecución vista más tarde no es «en vivo»
    min_quoted_trades: int = 10  # operaciones adelante con precio del seguidor

    # --- Ventanas y cambios -------------------------------------------------------------------
    window_ms: int = 86_400_000  # consistencia por ventanas diarias
    change_windows_h: tuple[float, ...] = (1.0, 4.0, 24.0)

    def summary(self) -> dict[str, float | int]:
        """Umbrales que la UI muestra junto al ranking."""
        keys = ("min_hist_trades", "min_portfolio_days", "min_fwd_trades", "min_fwd_days",
                "dsr_min", "ci_level", "min_trials", "max_drawdown", "max_leverage",
                "max_avg_down_share", "martingale_ratio", "latent_loss_share",
                "latent_loss_equity", "exec_delay_ms", "follower_taker_fee", "min_quoted_trades")
        return {k: getattr(self, k) for k in keys}
