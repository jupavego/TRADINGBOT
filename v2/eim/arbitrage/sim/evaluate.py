"""Evaluación completa del arbitraje (T43): caso base, horizontes del carry, sensibilidad
(comisiones VIP/BNB, nocional, profundidad, latencia y probabilidad de pata incompleta),
calibración del selector y veredicto por estrategia. Puro: recibe `ArbHistory`.

Veredicto (caso base = la cuenta real, VIP 0 verificado):
- No viable: el selector no toma nada o el neto medio por operación es ≤ 0.
- Viable: neto medio > 0 con IC95 % > 0, rentabilidad anual sobre el período Y en los
  últimos 12 meses ≥ umbral de referencia (`hurdle_apr`, supuesto), sin liquidaciones y
  ≥ 10 operaciones.
- Marginal: el resto (positivo pero no significativo, bajo el umbral, o con liquidaciones).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from eim.arbitrage.params import ArbParams
from eim.arbitrage.sim.calibrate import measured, pick_threshold, recommend, threshold_sweep
from eim.arbitrage.sim.depth import DepthModel
from eim.arbitrage.sim.frame import H_MS, ArbHistory
from eim.arbitrage.sim.panel import Panel, PanelRow, build_panel, decision_times, policy
from eim.arbitrage.sim.params import SimParams
from eim.arbitrage.sim.replay import spot_key
from eim.arbitrage.sim.stats import legging_table, mc_nets, trade_stats
from eim.arbitrage.sim.trade import SimTrade
from eim.arbitrage.sim.triangular import scan_captures, scan_ticker
from eim.arbitrage.sim.verdict import capital_min, verdict, verdicts
from eim.core import CostModel

STRATS = ("funding_carry", "basis", "related_perps")
HORIZONS = (24.0, 72.0, 168.0, 720.0, 2160.0)
LATENCIES = (50.0, 250.0, 1_000.0, 5_000.0, 30_000.0)
P_FAILS = (0.0, 0.01, 0.05)
FEE_CASES: dict[str, dict] = {
    "VIP 0": {}, "VIP 0 + BNB": {"bnb_discount": True},
    "VIP 3 + BNB": {"spot_vip": 3, "futures_vip": 3, "bnb_discount": True},
    "VIP 9 + BNB": {"spot_vip": 9, "futures_vip": 9, "bnb_discount": True}}
NOTIONALS = (1_000.0, 10_000.0, 100_000.0, 1_000_000.0)
DEPTH_SCALES = (1.0, 0.5, 0.1)
LEVERAGES = (1.0, 2.0, 3.0)
Log = Callable[[str], None]


class Evaluator:
    def __init__(self, hist: ArbHistory, cm: CostModel, p: ArbParams, sp: SimParams,
                 log: Log = lambda _m: None) -> None:
        self.hist, self.cm, self.p, self.sp, self.log = hist, cm, p, sp, log
        self.rets = {a: h.returns_15m for a, h in hist.assets.items()}
        self.n_assets = len([a for a in p.assets if a in hist.assets])
        self.disabled: tuple[str, ...] = ()  # variantes No viable (se excluyen al comparar)

    def panel(self, *, p: ArbParams | None = None, sp: SimParams | None = None,
              cm: CostModel | None = None, strategies: tuple[str, ...] = STRATS,
              label: str = "") -> Panel:
        p, sp, cm = p or self.p, sp or self.sp, cm or self.cm
        times = decision_times(self.hist, p, sp)
        self.log(f"panel {label or 'base'}: {len(times)} decisiones × {strategies}")
        return build_panel(self.hist, cm, p, sp, strategies=strategies, times=times)

    def stats(self, trades: list[SimTrade], panel: Panel, sp: SimParams | None = None) -> dict:
        span = (panel.times[-1] - panel.times[0]) if len(panel.times) > 1 else H_MS
        return trade_stats(trades, period_ms=span, n_assets=self.n_assets, sp=sp or self.sp,
                           rets=self.rets)

    def strategy_block(self, panel: Panel, s: str) -> dict:
        rows = panel.of(s)
        trades = policy(rows)
        sel = [r for r in rows if r.selected and r.trade is not None]
        out = {"stats": self.stats(trades, panel), "counts": _counts(rows, panel),
               "sweep": threshold_sweep(rows, self.sp.decision_every_h, self.sp.seed,
                                        lambda th: self.stats(policy(rows, min_est_bps=th),
                                                              panel)),
               "est_vs_real": _gap(sel), "trades": [t.summary() for t in trades]}
        out["pick_theta"] = pick_threshold(out["sweep"], self.p.min_net_bps)
        if s == "basis":
            groups = ("spot/trimestral", "perpetuo/trimestral")
            out["variants"] = {g: self.stats(policy([r for r in rows if _group(r) == g]), panel)
                               for g in groups}
            out["gap_by_variant"] = {g: _gap([r for r in sel if _group(r) == g]) for g in groups}
            off = {g for g, st in out["variants"].items()
                   if verdict(st, self.sp.hurdle_apr)[0] == "No viable"}
            out["disabled_variants"] = sorted({r.variant for r in rows if _group(r) in off})
            if off:  # la estrategia se juzga con lo que queda activo
                self.disabled = tuple(out["disabled_variants"])
                trades = policy([r for r in rows if r.variant not in self.disabled])
                out["stats_all"], out["stats"] = out["stats"], self.stats(trades, panel)
                out["trades"] = [t.summary() for t in trades]
        out["p_fail"] = _p_fail_table(trades, self.sp)
        out["latency_mc"] = _latency_mc(trades, self.rets, self.sp)
        return out

    def run(self, *, sensitivities: bool = True) -> dict:
        base = self.panel()
        res: dict = {"strategies": {s: self.strategy_block(base, s) for s in STRATS},
                     "decisions": len(base.times),
                     "period": [base.times[0], base.times[-1]] if base.times else None,
                     "missing": _top(base.missing), "skips": _top(base.skips)}
        res["carry_horizons"] = self.horizons()
        best_h = max(res["carry_horizons"], key=lambda r: r["stats"].get("apr_period") or -1e9,
                     default={"horizon_h": self.p.carry_horizon_h})["horizon_h"]
        res["best_carry_h"] = best_h
        if sensitivities:
            res["sensitivity"] = self.sensitivities(best_h)
        res["legging"] = self.legging()
        res["calibration"] = measured(self.hist, best_h, self.p.funding_realized_n)
        cms = {k: self.cm.model_copy(update=v) for k, v in FEE_CASES.items()
               if k in ("VIP 0", "VIP 9 + BNB")}
        res["triangular"] = scan_ticker(self.hist, cms, self.p.notional_usd)
        res["triangular"]["captured"] = scan_captures(self.hist, cms, self.p)
        res["verdicts"] = verdicts(res, self.sp)
        res["capital_min"] = capital_min(self.hist, self.p)
        res["carry_h_live"] = self.p.carry_horizon_h
        res["recommend"] = recommend(res, self.p)
        return res

    def horizons(self) -> list[dict]:
        out = []
        for h in HORIZONS:
            p = self.p.model_copy(update={"carry_horizon_h": h})
            panel = self.panel(p=p, strategies=("funding_carry",), label=f"carry {h:g} h")
            out.append({"horizon_h": h, **self.strategy_block(panel, "funding_carry")})
        return out

    def sensitivities(self, carry_h: float) -> dict:
        """Con decisión cada 24 h (más liviano) y el carry en su mejor tenencia; cada tabla
        trae su propio caso de referencia."""
        sp = self.sp.model_copy(update={"decision_every_h": 24})
        p = self.p.model_copy(update={"carry_horizon_h": carry_h})

        def row(panel: Panel) -> dict:
            return {s: _brief(self.stats(policy([r for r in panel.of(s)
                                                 if r.variant not in self.disabled]), panel, sp))
                    for s in STRATS}

        fees = {k: row(self.panel(p=p, sp=sp, cm=self.cm.model_copy(update=v), label=k))
                for k, v in FEE_CASES.items()}
        notional = {n: row(self.panel(p=p.model_copy(update={"notional_usd": n}), sp=sp,
                                      label=f"nocional {n:g}")) for n in NOTIONALS}
        depth = {d: row(self.panel(p=p, sp=sp.model_copy(update={"depth_scale": d}),
                                   label=f"libro ×{d:g}")) for d in DEPTH_SCALES}
        lev = {lv: row(self.panel(p=p.model_copy(update={"perp_leverage": lv}), sp=sp,
                                  label=f"apalancamiento ×{lv:g}")) for lv in LEVERAGES}
        return {"fees": fees, "notional": notional, "depth": depth, "leverage": lev,
                "every_h": 24}

    def legging(self) -> dict:
        """Incidente típico: deshacer la pata spot (la primera, menos líquida) de ida y
        vuelta: comisión + deslizamiento del perfil capturado al nocional base."""
        dm, n = DepthModel(self.hist.depth, self.p.notional_usd), self.p.notional_usd
        out = {}
        for a, r in self.rets.items():
            got = dm.cost(spot_key(f"{a}USDT"), n, "buy")
            slip = got[0] / n if got else 0.0
            undo = 2 * (self.cm.fee_rate("spot") + slip)
            out[a] = {"undo_bps": undo * 1e4, "rows": legging_table(
                r, LATENCIES, undo, self.sp.p_fail, seed=self.sp.seed)}
        return out


def _group(r: PanelRow) -> str:
    return "spot/trimestral" if r.variant.startswith("largo spot") else "perpetuo/trimestral"


def _counts(rows: list[PanelRow], panel: Panel) -> dict:
    sel = [r for r in rows if r.selected]
    sim = [r for r in sel if r.trade is not None]
    codes: dict[str, int] = {}
    for r in rows:
        if r.reject_code:
            codes[r.reject_code] = codes.get(r.reject_code, 0) + 1
    scores = np.array([r.est_score for r in sel]) if sel else np.array([])
    return {"decisions": len(panel.times), "valued": len(rows), "selected": len(sel),
            "selected_simulated": len(sim),
            "selected_positive": sum(1 for r in sim if r.trade and r.trade.net > 0),
            "rejected_by_code": codes,
            "score_pcts": {q: float(np.percentile(scores, q)) for q in (50, 90, 99)}
            if len(scores) else {}}


def _gap(sel: list[PanelRow]) -> dict:
    if not sel:
        return {"n": 0}
    est = np.array([r.est_net_bps for r in sel])
    real = np.array([r.trade.net_bps for r in sel if r.trade is not None])
    return {"n": len(sel), "est_mean_bps": float(est.mean()), "real_mean_bps": float(real.mean()),
            "real_minus_est_bps": float((real - est).mean())}


def _brief(st: dict) -> dict:
    keys = ("n", "apr_period", "apr_invested", "mean_bps", "worst_bps", "win_rate", "max_dd",
            "liquidations", "rebalances", "last_year_apr")
    return {k: st.get(k) for k in keys}


def _top(c, k: int = 12) -> list[list]:  # noqa: ANN001 — Counter
    return [[*key, n] for key, n in c.most_common(k)]


def _p_fail_table(trades: list[SimTrade], sp: SimParams) -> list[dict]:
    out = []
    for pf in P_FAILS:
        net = [t.net + t.legging - pf * sum(u for _, u in t.events) for t in trades]
        cap = [t.capital for t in trades]
        out.append({"p_fail": pf, "mean_bps": float(np.mean(np.array(net) / cap) * 1e4)
                     if trades else None, "net_usd": float(sum(net))})
    return out


def _latency_mc(trades: list[SimTrade], rets: dict, sp: SimParams) -> list[dict]:
    if not trades:
        return []
    cap = np.array([t.capital for t in trades])[:, None]
    out = []
    for lat in LATENCIES:
        mc = mc_nets(trades, rets, sp, latency_ms=lat) / cap * 1e4
        out.append({"latency_ms": lat, "p1_bps": float(np.percentile(mc, 1)),
                    "p5_bps": float(np.percentile(mc, 5)), "worst_bps": float(mc.min()),
                    "mean_bps": float(mc.mean())})
    return out
