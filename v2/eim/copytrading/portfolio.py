"""Historial de cartera de Hyperliquid (`portfolio`) → métricas largas (puro). Solo preselecciona.

`pnlHistory` es el PnL acumulado de la cuenta (marcado a mercado, neto de comisiones y
funding, sin depósitos ni retiros) y `accountValueHistory` el valor de la cuenta, en puntos
espaciados (≈ 6 días en `perpAllTime`, ≈ 16 h en `perpMonth`). El retorno por tramo es
Modified Dietz (ΔPnL / capital medio del tramo): los depósitos no cuentan como ganancia.
"""

from __future__ import annotations

import bisect

from eim.copytrading.params import ScoreParams
from eim.core.market import Frozen

DAY_MS = 86_400_000


class PortfolioStats(Frozen):
    period: str  # serie usada: perpAllTime
    first_t: int
    last_t: int
    days: float
    account_value: float | None
    pnl: float  # PnL acumulado del periodo (USD)
    twr: float | None  # retorno compuesto por tramos
    max_dd: float | None  # caída máxima del retorno compuesto
    windows: int  # tramos con cuenta suficiente
    windows_pos: int
    worst_window: float | None
    best_window: float | None = None  # mayor ΔPnL de un tramo (USD): racha de cartera
    month_pnl: float | None = None
    month_twr: float | None = None
    volume: float | None = None
    source: str = "hyperliquid:info.portfolio"


def _series(raw: list, name: str) -> tuple[list[tuple[int, float]], list[tuple[int, float]],
                                           float | None] | None:
    for item in raw or []:
        if isinstance(item, list) and len(item) == 2 and item[0] == name:
            d = item[1] or {}
            av = [(int(t), float(v)) for t, v in d.get("accountValueHistory") or []]
            pnl = [(int(t), float(v)) for t, v in d.get("pnlHistory") or []]
            vlm = d.get("vlm")
            return av, pnl, float(vlm) if vlm is not None else None
    return None


def _returns(av: list[tuple[int, float]], pnl: list[tuple[int, float]], min_av: float
             ) -> list[float]:
    """Modified Dietz por tramo: ΔPnL / (cuenta inicial + mitad del depósito neto). Sin esto
    un retiro grande deja una base mínima y el retorno explota. Pérdida acotada a −100 %."""
    if len(av) != len(pnl):
        return []
    out = []
    for i in range(1, len(pnl)):
        d_pnl = pnl[i][1] - pnl[i - 1][1]
        flow = (av[i][1] - av[i - 1][1]) - d_pnl  # depósitos − retiros del tramo
        base = av[i - 1][1] + 0.5 * flow
        if av[i - 1][1] >= min_av and base >= min_av:
            out.append(max(-1.0, d_pnl / base))
    return out


def _compound(rs: list[float]) -> tuple[float, float]:
    eq = peak = 1.0
    dd = 0.0
    for r in rs:
        eq *= 1 + r
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
    return eq - 1, dd


def portfolio_stats(raw: list, p: ScoreParams) -> PortfolioStats | None:
    """None si la respuesta no trae la serie o está vacía."""
    full = _series(raw, "perpAllTime")
    if not full or len(full[1]) < 2:
        return None
    av, pnl, vlm = full
    alive = [i for i, (_, v) in enumerate(av) if v >= p.min_account_usd]
    first = av[alive[0]][0] if alive else pnl[0][0]
    rs = _returns(av, pnl, p.min_account_usd)
    twr, dd = _compound(rs) if rs else (None, None)
    month = _series(raw, "perpMonth")
    m_pnl = m_twr = None
    if month and len(month[1]) >= 2:
        m_pnl = month[1][-1][1] - month[1][0][1]
        mr = _returns(month[0], month[1], p.min_account_usd)
        m_twr = _compound(mr)[0] if mr else None
    last = pnl[-1][0]
    steps = [b[1] - a[1] for a, b in zip(pnl, pnl[1:], strict=False)]
    return PortfolioStats(
        period="perpAllTime", first_t=first, last_t=last, days=(last - first) / DAY_MS,
        account_value=av[-1][1] if av else None, pnl=pnl[-1][1] - pnl[0][1], twr=twr,
        max_dd=dd, windows=len(rs), windows_pos=sum(r > 0 for r in rs),
        worst_window=min(rs) if rs else None, best_window=max(steps) if steps else None,
        month_pnl=m_pnl, month_twr=m_twr, volume=vlm)


def account_values(raw: list | None) -> list[tuple[int, float]]:
    """Valor de la cuenta en el tiempo (T42): puntos de todas las series perp (`perpDay` es
    la más fina) unidos y ordenados. Sirve para fijar la proporción de la copia."""
    pts: dict[int, float] = {}
    for name in ("perpAllTime", "perpMonth", "perpWeek", "perpDay"):  # la más fina manda
        s = _series(raw or [], name)
        if s:
            pts.update(dict(s[0]))
    return sorted(pts.items())


def value_at(series: list[tuple[int, float]], t: int) -> float | None:
    """Último valor conocido en `t` (nunca uno posterior); None si la serie empieza después."""
    i = bisect.bisect_right([x for x, _ in series], t) - 1
    return series[i][1] if i >= 0 else None
