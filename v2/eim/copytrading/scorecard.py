"""Scorecard de un líder (puro): métricas robustas, reglas duras y veredicto explicado.

Orden de decisión (cada paso deja su motivo en `reasons`):
1. **Reglas duras** sobre todo lo capturado (historial + adelante) y su cartera: muestra < N,
   racha (sin su mejor operación/día no gana), un solo activo (gana en uno y pierde en el
   resto), martingala, promediado a la baja, pérdidas latentes ocultas, liquidaciones,
   apalancamiento, caída máxima y cartera perdedora → **descartado**.
2. **Adelante**: sin muestra propia suficiente → **vigilancia**; con muestra, Sharpe
   deflactado por N billeteras < mínimo → descartado.
3. **Copiabilidad**: sin precios del seguidor → vigilancia; seguidor con neto ≤ 0 →
   descartado. Si todo pasa → **aprobado**, calidad = DSR × retención del seguidor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from eim.copytrading.copyability import CopyStats, copy_stats
from eim.copytrading.forward import DAY_MS, Verdict, forward_trips
from eim.copytrading.metrics import TradeStats, trade_stats
from eim.copytrading.params import ScoreParams
from eim.copytrading.portfolio import PortfolioStats, portfolio_stats
from eim.copytrading.trades import Trip, build_trips
from eim.core.leaders import FollowQuote, Leader, LeaderFill, LeaderFunding, LeaderPosition
from eim.core.market import Frozen

Kind = Literal["descarte", "vigilancia", "aprobado", "aviso"]


class Reason(Frozen):
    code: str
    kind: Kind
    text: str


class Scorecard(Frozen):
    leader_id: str
    address: str
    label: str = ""
    origin: str
    verdict: Verdict
    quality: float = 0.0  # 0..1; solo > 0 si está aprobado
    reasons: list[Reason]
    all: TradeStats  # todo lo capturado (reglas duras)
    hist: TradeStats  # antes de empezar a seguirlo (solo preselecciona)
    fwd: TradeStats  # observado por nosotros (lo único que aprueba)
    portfolio: PortfolioStats | None = None
    copyability: CopyStats | None = None
    forward_start: int | None = None
    forward_days: float = 0.0
    account_value: float | None = None
    unrealized: float | None = None  # PnL latente de las posiciones abiertas
    n_positions: int = 0
    n_trials: int
    scored_at: int
    rank: int = 0


@dataclass
class LeaderData:
    """Todo lo capturado de un líder (lo reúne `eim/data/leader_eval.py`)."""

    leader: Leader
    fills: list[LeaderFill]
    funding: list[LeaderFunding] = field(default_factory=list)
    positions: list[LeaderPosition] = field(default_factory=list)
    portfolio: list | None = None  # respuesta cruda de `portfolio`
    quotes: dict[tuple[int, int], FollowQuote] = field(default_factory=dict)
    forward_start: int | None = None
    observed_ms: int = 0  # tiempo cubierto por nuestra captura desde `forward_start`


def _usd(x: float) -> str:
    return f"{x:+,.0f} USD".replace(",", " ")


def _n(x: float, d: int = 2) -> str:
    """Decimal con coma, como el resto de la interfaz."""
    return f"{x:.{d}f}".replace(".", ",")


def _pct(x: float) -> str:
    return f"{_n(x * 100, 1)} %"


def _hard(a: TradeStats, pf: PortfolioStats | None, unreal: float | None,
          av: float | None, p: ScoreParams) -> list[Reason]:
    out: list[Reason] = []

    def bad(code: str, text: str) -> None:
        out.append(Reason(code=code, kind="descarte", text=text))

    days = pf.days if pf else 0.0
    if a.n < p.min_hist_trades and days < p.min_portfolio_days:
        bad("muestra", f"muestra insuficiente: {a.n} operaciones cerradas < {p.min_hist_trades}"
            f" y {days:.0f} d de cartera < {p.min_portfolio_days:.0f} d")
    if a.liquidations > p.max_liquidations:
        bad("liquidacion", f"liquidado {a.liquidations} vez/veces en lo capturado")
    # Las reglas por proporción solo se juzgan con muestra: con 5 operaciones o 2 días, una
    # sola buena «explica» todo por construcción (eso ya lo descarta la regla de muestra).
    sample = a.n >= p.min_hist_trades
    if sample and a.best_trade_share is not None and a.best_trade_share >= 1:
        bad("racha", f"sin su mejor operación no gana: una sola explica "
            f"{_pct(a.best_trade_share)} del neto {_usd(a.net)}")
    elif (a.best_day_share is not None and a.best_day_share >= 1
          and a.windows >= p.min_racha_windows):
        bad("racha", f"sin su mejor día no gana: explica {_pct(a.best_day_share)} del neto "
            f"de {a.windows} días")
    elif (pf is not None and pf.pnl > 0 and pf.best_window is not None
          and pf.windows >= p.min_racha_windows and pf.best_window >= pf.pnl):
        bad("racha", f"sin su mejor tramo de cartera no gana: {_usd(pf.best_window)} de "
            f"{_usd(pf.pnl)} en {pf.days:.0f} d")
    if sample and a.best_asset_share is not None and a.best_asset_share >= 1:
        bad("un_activo", f"gana solo en {a.best_asset or 'un activo'} y pierde en el resto "
            f"({_pct(a.best_asset_share)} del neto en esa moneda)")
    if sample and a.avg_down_share is not None and a.avg_down_share > p.max_avg_down_share:
        bad("promediado", f"promedia a la baja en {_pct(a.avg_down_share)} de sus operaciones "
            f"(máx. {_pct(p.max_avg_down_share)})")
    if a.martingale is not None and a.martingale >= p.martingale_ratio:
        bad("martingala", f"tras perder opera ×{_n(a.martingale, 1)} más grande que tras ganar "
            f"(máx. ×{_n(p.martingale_ratio, 1)})")
    if a.lev_median is not None and a.lev_median > p.max_leverage:
        bad("apalancamiento", f"apalancamiento mediano {a.lev_median:.0f}× > "
            f"{p.max_leverage:.0f}×")
    if unreal is not None and unreal < 0:
        gain = max(a.net, 0.0)
        if (gain > 0 and -unreal >= p.latent_loss_share * gain) or (
                av and -unreal >= p.latent_loss_equity * av):
            bad("latentes", f"pérdidas latentes ocultas: {_usd(unreal)} sin cerrar frente a "
                f"{_usd(a.net)} realizados" + (f" ({_pct(-unreal / av)} de la cuenta)"
                                                if av else ""))
    dd = max((x for x in (pf.max_dd if pf else None, a.max_dd) if x is not None), default=None)
    if dd is not None and dd > p.max_drawdown:
        bad("drawdown", f"caída máxima {_pct(dd)} > {_pct(p.max_drawdown)}")
    if pf is not None and pf.pnl <= 0:
        bad("perdedor", f"pierde en su historial de cartera: {_usd(pf.pnl)} en {pf.days:.0f} d")
    return out


def _forward(f: TradeStats, cp: CopyStats, days: float, n_trials: int,
             p: ScoreParams) -> tuple[Verdict, float, list[Reason]]:
    if f.n < p.min_fwd_trades or days < p.min_fwd_days:
        return "watch", 0.0, [Reason(code="adelante", kind="vigilancia", text=(
            f"seguimiento adelante: {f.n}/{p.min_fwd_trades} operaciones y "
            f"{_n(days, 1)}/{p.min_fwd_days:.0f} d observados por nosotros"))]
    if f.dsr is None or f.dsr < p.dsr_min:
        sr = _n(f.sharpe, 2) if f.sharpe is not None else "—"
        sr0 = f" frente a {_n(f.sr0, 2)} esperado por azar" if f.sr0 is not None else ""
        dsr = _n(f.dsr, 2) if f.dsr is not None else "sin calcular"
        return "rejected", 0.0, [Reason(code="sin_ventaja", kind="descarte", text=(
            f"sin ventaja tras deflactar por {n_trials} billeteras: DSR {dsr} < "
            f"{_n(p.dsr_min, 2)} (Sharpe por operación {sr}{sr0}, n = {f.n})"))]
    if cp.trades < p.min_quoted_trades:
        return "watch", 0.0, [Reason(code="copiabilidad", kind="vigilancia", text=(
            f"copiabilidad sin medir: {cp.trades}/{p.min_quoted_trades} operaciones con "
            "precio del seguidor"))]
    lat, slip = cp.latency_ms.get("p50"), cp.slip_bps.get("p50")
    how = (f"latencia p50 {lat:.0f} ms + {cp.delay_ms} ms de orden, deslizamiento p50 "
           f"{_n(slip, 1)} pb" if lat is not None and slip is not None else "")
    if cp.follower_net <= 0:
        return "rejected", 0.0, [Reason(code="no_copiable", kind="descarte", text=(
            f"no copiable: un seguidor habría obtenido {_usd(cp.follower_net)} (el líder "
            f"{_usd(cp.leader_net)}) en {cp.trades} operaciones; {how}"))]
    ret = min(1.0, max(0.0, cp.retention or 0.0))
    q = round(f.dsr * ret, 4)
    return "approved", q, [Reason(code="aprobado", kind="aprobado", text=(
        f"DSR {_n(f.dsr, 2)} con {f.n} operaciones en {_n(days, 1)} d; el seguidor retiene "
        f"{_pct(ret)} del neto del líder ({how})"))]


def _notes(a: TradeStats, cp: CopyStats) -> list[Reason]:
    out = []
    if cp.taker_share is not None and cp.taker_share < 0.1:
        out.append(Reason(code="creador", kind="aviso", text=(
            f"opera como creador de mercado ({_pct(1 - cp.taker_share)} pasivo): copiarlo "
            "como tomador paga el diferencial que él cobra")))
    if a.top_asset_share is not None and a.top_asset_share >= 0.9 and a.n_assets == 1:
        out.append(Reason(code="especialista", kind="aviso", text=(
            f"opera solo {a.top_asset}: su señal vale para esa moneda")))
    if a.n_partial:
        out.append(Reason(code="parciales", kind="aviso", text=(
            f"{a.n_partial} operaciones sin apertura vista (anteriores al historial o "
            "cortadas por un hueco): fuera de las métricas")))
    return out


def score(d: LeaderData, n_trials: int, now: int, p: ScoreParams | None = None
          ) -> tuple[Scorecard, list[Trip]]:
    """Scorecard y las operaciones adelante (para las cohortes del filtro)."""
    p = p or ScoreParams()
    trips = build_trips(d.fills, d.funding, p.avg_down_tol)
    fwd = forward_trips(trips, d.forward_start)
    return assemble(d, trips, fwd, copy_stats(fwd, d.fills, d.quotes, p), n_trials, now, p), fwd


def assemble(d: LeaderData, trips: list[Trip], fwd: list[Trip], cp: CopyStats, n_trials: int,
             now: int, p: ScoreParams) -> Scorecard:
    """Scorecard con los viajes y la copiabilidad ya calculados (de `d` no usa `fills` ni
    `quotes`: la evaluación incremental los arma sin guardar el historial)."""
    pf = portfolio_stats(d.portfolio, p) if d.portfolio else None
    av = pf.account_value if pf and pf.account_value else None
    fwd_ids = {id(t) for t in fwd}
    hist = [t for t in trips if id(t) not in fwd_ids]
    a = trade_stats(trips, av, n_trials, p)
    f = trade_stats(fwd, av, n_trials, p)
    h = trade_stats(hist, av, n_trials, p)
    days = d.observed_ms / DAY_MS
    ups = [x.unrealized_pnl for x in d.positions if x.unrealized_pnl is not None]
    unreal = sum(ups) if ups else None
    hard = _hard(a, pf, unreal, av, p)
    if hard:
        verdict, quality, reasons = "rejected", 0.0, hard
    else:
        verdict, quality, reasons = _forward(f, cp, days, n_trials, p)
    ld = d.leader
    return Scorecard(
        leader_id=ld.id, address=ld.address, label=ld.label, origin=ld.origin,
        verdict=verdict, quality=quality, reasons=reasons + _notes(a, cp), all=a, hist=h,
        fwd=f, portfolio=pf, copyability=cp, forward_start=d.forward_start, forward_days=days,
        account_value=av, unrealized=unreal, n_positions=len(d.positions),
        n_trials=n_trials, scored_at=now)
