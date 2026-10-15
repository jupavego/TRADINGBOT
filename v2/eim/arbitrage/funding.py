"""Funding: horario de liquidación, tasa prevista frente a realizada."""

from __future__ import annotations

from eim.core import PremiumInfo

H_MS = 3_600_000


def settlements(prem: PremiumInfo, asof: int, horizon_h: float) -> list[int]:
    """Liquidaciones de funding que cruza una posición abierta en `asof` y mantenida
    `horizon_h` horas (hay que estar posicionado a la hora exacta para cobrar o pagar)."""
    step = int(prem.interval_h * H_MS)
    end = asof + int(horizon_h * H_MS)
    t = prem.next_funding_t
    while t <= asof:  # premiumIndex desfasado: la próxima ya pasó
        t += step
    out: list[int] = []
    while t <= end:
        out.append(t)
        t += step
    return out


def realized(hist: list[tuple[int, float]] | None, asof: int, n: int) -> tuple[float | None, int]:
    """Media de las últimas `n` tasas liquidadas antes de `asof` y cuántas había."""
    rows = [r for t, r in (hist or []) if t <= asof][-n:]
    return (sum(rows) / len(rows), len(rows)) if rows else (None, 0)


def expected_path(prem: PremiumInfo, k: int, realized_mean: float | None) -> list[float]:
    """Tasa por liquidación: la prevista para la próxima y la media realizada para las
    siguientes (sin histórico: la prevista para todas)."""
    if k <= 0:
        return []
    rest = prem.funding_rate if realized_mean is None else realized_mean
    return [prem.funding_rate] + [rest] * (k - 1)


def comparison(prem: PremiumInfo, realized_mean: float | None, n: int) -> list[str]:
    """Advertencias cuando el previsto no se sostiene con lo realizado."""
    if realized_mean is None:
        return ["sin histórico de funding realizado: todas las liquidaciones usan la tasa "
                "prevista (menos fiable)"]
    out: list[str] = []
    f, r = prem.funding_rate, realized_mean
    if f * r < 0:
        out.append(f"funding previsto ({f:+.4%}) de signo contrario al realizado medio "
                   f"({r:+.4%}, n={n})")
    elif abs(f) > 2 * abs(r) and abs(f - r) > 1e-5:
        out.append(f"funding previsto ({f:+.4%}) > 2× el realizado medio ({r:+.4%}, n={n}): "
                   "el bruto puede estar inflado")
    return out
