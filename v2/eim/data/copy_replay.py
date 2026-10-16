"""Reproducción de la copia sobre el historial capturado (T40/T41). Modo SIMULADO.

Por líder, desde su primera foto (inicio del seguimiento), en orden de tiempo, lo que el
seguidor habría visto y hecho, con el MISMO motor que corre en vivo:
- señales = ejecuciones del líder agrupadas por instante en que las vimos (`observed_at`),
  ejecutadas `exec_delay_ms` después. Las anteriores a la primera foto ya están en ella.
- precio del seguidor: cotización grabada (`leader_follow`: bid/ask del WS `bbo`, o
  `allMids` + medio diferencial supuesto); sin ella, cierre de la última vela de 1 min
  cerrada + deslizamiento de T25 (`slippage_frac`); sin vela, precio del líder (supuesto).
- fotos de posiciones → reconciliación; reconciliaciones T40 → frescura del flujo; huecos
  del WS → flujo caído; funding de cualquier líder capturado → tasa por moneda y hora.
- velas de 1 min de Hyperliquid → marcas, capital y stops (al cierre de cada minuto con su
  mínimo/máximo: si abrimos dentro de ese minuto, un extremo anterior puede disparar el stop;
  sesgo en contra del seguidor, raro con stops al 5 %).
"""

from __future__ import annotations

import bisect
import json
from collections import Counter
from dataclasses import dataclass, field

from eim.backtest.perp import slippage_frac
from eim.copytrading.copy_engine import CopyEngine
from eim.copytrading.copy_models import ExecQuote, Signal, group_fills
from eim.copytrading.copy_params import CopyParams, ExchangeSpec
from eim.copytrading.portfolio import account_values, value_at
from eim.copytrading.trades import Trip, build_trips
from eim.core import Candle
from eim.core.leaders import FollowQuote, Leader, LeaderPosition
from eim.data.hl_market import MIN_MS, Bar
from eim.risk import RiskConfig

HOUR_MS = 3_600_000


@dataclass
class ReplayResult:
    leader: Leader
    engine: CopyEngine
    start: int
    end: int
    trips: list[Trip]  # viajes del líder abiertos tras el inicio (T41)
    price_src: dict[str, int] = field(default_factory=dict)
    funding_missing: int = 0  # horas con posición propia sin tasa conocida
    bars: int = 0
    av_points: int = 0
    warnings: list[str] = field(default_factory=list)


def funding_rates(store, start: int, end: int) -> dict[tuple[str, int], tuple[float, float]]:
    """(moneda, hora en punto) → (tasa, precio) desde los pagos de todos los líderes capturados:
    precio = usdc / (−tamaño × tasa) (la tasa es la del exchange, igual para todos)."""
    out = {}
    for coin, t, usdc, rate, size in store.query(
            "SELECT symbol, t, usdc, rate, size FROM leader_funding WHERE t >= ? AND t <= ?",
            [start, end]):
        h = t - t % HOUR_MS  # el pago es horario; la clave es la hora
        if rate and size and (coin, h) not in out:
            px = usdc / (-size * rate)
            if px > 0:
                out[(coin, h)] = (rate, px)
    return out


def _photos(store, lid: str) -> list[tuple[int, int, list[LeaderPosition]]]:
    rows = store.query("SELECT t, observed_at, positions FROM leader_positions WHERE "
                       "leader_id = ? ORDER BY observed_at", [lid])
    return [(t, obs, [LeaderPosition.model_validate(x) for x in json.loads(raw)])
            for t, obs, raw in rows]


def _signed(ps: list[LeaderPosition]) -> dict[str, float]:
    return {x.symbol: x.size if x.side == "long" else -x.size for x in ps}


class _Prices:
    def __init__(self, bars: dict[str, list[Bar]], p: CopyParams) -> None:
        self.bars, self.p = bars, p
        self.t = {c: [b[0] for b in bs] for c, bs in bars.items()}

    def last_closed(self, coin: str, at: int) -> Bar | None:
        ts = self.t.get(coin)
        if not ts:
            return None
        i = bisect.bisect_right(ts, at - MIN_MS) - 1  # vela cerrada antes de `at`
        return self.bars[coin][i] if i >= 0 and at - ts[i] <= 10 * MIN_MS else None

    def quote(self, sig: Signal, q: FollowQuote | None) -> ExecQuote:
        p, at = self.p, sig.observed_at + self.p.exec_delay_ms
        if q is not None and q.follow_at - q.quote_t <= p.quote_timeout_ms:
            return ExecQuote(t=q.quote_t, at=q.follow_at, mid=q.mid, bid=q.bid, ask=q.ask,
                             src=q.src)
        b = self.last_closed(sig.coin, at)
        if b is not None:
            c = Candle(t=b[0], o=b[1], h=b[2], l=b[3], c=b[4], v=b[5])
            slip = slippage_frac(c, 0.0, p.costs)
            return ExecQuote(t=b[0] + MIN_MS, at=at, mid=b[4], bid=b[4] * (1 - slip),
                             ask=b[4] * (1 + slip), src="vela_1m")
        slip = p.costs.slip_base_bps / 1e4
        return ExecQuote(t=sig.t, at=at, mid=sig.vwap, bid=sig.vwap * (1 - slip),
                         ask=sig.vwap * (1 + slip), src="lider")


def _signal_events(sigs: list[Signal], photos: list, delay: int, end: int) -> list[tuple]:
    """Señales (vistas en `observed_at`, ejecutadas `delay` después) y fotos. Cada foto se
    compara cuando ya se ejecutó todo lo que ella refleja (ejecuciones con hora ≤ la de su
    estado): en vivo la foto se guarda tras el relleno de T40, pero su `observed_at` es el de
    la consulta, anterior a ese relleno."""
    ev: list[tuple] = []  # (t, prioridad, orden, tipo, dato)
    for k, s in enumerate(sigs):
        ev.append((s.observed_at, 1, k, "seen", s.coin))
        ev.append((s.observed_at + delay, 3, k, "signal", s))
    order = sorted(sigs, key=lambda s: s.t)
    ts, ready, run = [s.t for s in order], [], 0
    for s in order:
        run = max(run, s.observed_at + delay)
        ready.append(run)
    for t_state, obs, ps in photos:
        i = bisect.bisect_right(ts, t_state) - 1
        at = max(obs, ready[i] + 1) if i >= 0 else obs
        if at <= end:
            ev.append((at, 4, 0, "photo", (_signed(ps), t_state)))
    return ev


def replay(store, leader: Leader, p: CopyParams, spec: ExchangeSpec, risk_cfg: RiskConfig,
           bars: dict[str, list[Bar]], rates: dict[tuple[str, int], tuple[float, float]],
           end: int, start: int | None = None) -> ReplayResult | None:
    """None si el líder no tiene ninguna foto (nunca empezamos a seguirlo)."""
    lid = leader.id
    photos = [x for x in _photos(store, lid) if start is None or x[1] >= start]
    if not photos:
        return None
    t_state, t0, first = photos[0]
    eng = CopyEngine(lid, p, spec, risk_cfg, t0=t0, label=leader.label,
                     measure=leader.status != "approved")
    portfolio = store.portfolio(lid)
    avs = account_values(portfolio[1] if portfolio else None)
    eng.leader_av = value_at(avs, t0) or (avs[0][1] if avs else None)
    eng.confirm_feed(t0)
    eng.start(t0, first, state_t=t_state)
    fills = [f for f in store.fills_fast(lid) if f.t > t_state and f.observed_at <= end]
    quotes = store.follow_quotes(lid)
    prices = _Prices(bars, p)
    sigs = group_fills(fills)
    ev = _signal_events(sigs, photos[1:], p.exec_delay_ms, end)
    for (obs,) in store.query("SELECT observed_at FROM leader_recon WHERE leader_id = ? AND "
                              "observed_at > ? AND observed_at <= ?", [lid, t0, end]):
        ev.append((obs, 0, 0, "feed", obs))
    for a, b in store.query("SELECT t_from, t_to FROM leader_gaps WHERE leader_id = ? AND "
                            "cause = 'ws' AND t_to > ? AND t_from <= ?", [lid, t0, end]):
        ev += [(max(a, t0), 0, 1, "down", a), (b, 0, 2, "up", b)]
    coins = {f.symbol for f in fills} | {x.symbol for _, _, ps in photos for x in ps}
    n_bars = 0
    for coin in coins:
        for b in bars.get(coin, []):
            if t0 <= b[0] + MIN_MS <= end:
                ev.append((b[0] + MIN_MS, 1, 0, "bar", (coin, b)))
                n_bars += 1
    for (coin, t), (rate, px) in rates.items():
        if coin in coins and t0 < t <= end:
            ev.append((t, 2, 0, "funding", (coin, t, rate, px)))
    h = t0 - t0 % HOUR_MS + HOUR_MS
    while h <= end:
        ev.append((h, 2, 1, "hour", h))
        h += HOUR_MS
    ev.sort(key=lambda e: (e[0], e[1], e[2]))
    res = ReplayResult(leader=leader, engine=eng, start=t0, end=end, trips=[], bars=n_bars,
                       av_points=len(avs))
    flying: Counter[str] = Counter()  # señales vistas y aún no ejecutadas, por moneda
    for t, _, _, kind, d in ev:
        if kind == "seen":
            flying[d] += 1
        elif kind == "signal":
            s: Signal = d
            flying[s.coin] -= 1
            q = prices.quote(s, quotes.get(s.last_key))
            res.price_src[q.src] = res.price_src.get(q.src, 0) + 1
            eng.leader_av = value_at(avs, t) or eng.leader_av
            eng.on_signal(s, q, t)
        elif kind == "bar":
            coin, b = d
            eng.on_mark(coin, t, b[4], low=b[3], high=b[2], open_=b[1])
        elif kind == "funding":
            eng.on_funding(*d)
        elif kind == "hour":
            res.funding_missing += sum(1 for c in eng.account.positions
                                       if (c, d) not in rates and eng.account.size_at(c, d))
        elif kind == "photo":
            photo, state_t = d
            eng.reconcile(t, photo, {c for c, n in flying.items() if n > 0}, state_t=state_t)
        elif kind == "feed":
            eng.confirm_feed(d)
        elif kind == "down":
            eng.set_feed_down(d)
        elif kind == "up":
            eng.set_feed_down(None)
    funding = store.funding_rows(lid)
    res.trips = [tr for tr in build_trips(store.fills_fast(lid), funding)
                 if tr.t_open > t_state and tr.complete and tr.t_open <= end]
    if not avs:
        res.warnings.append("sin historial de cuenta (`portfolio`): no se pudo fijar la "
                            "proporción")
    missing = sorted(c for c in coins if not bars.get(c))
    if missing:
        res.warnings.append(f"sin velas de 1 min para {', '.join(missing)}: sin marcas ni "
                            "stops en esas monedas")
    return res
