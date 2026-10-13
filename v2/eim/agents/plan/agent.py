"""Agente `plan`: propone entrada/SL/TP/R:R desde `structure` y `levels`. Siempre ANALISIS."""

from __future__ import annotations

import numpy as np

from eim.agents.base import no_data_report
from eim.agents.levels import LevelsAgent
from eim.agents.levels.pivots import atr
from eim.agents.plan.params import PlanParams
from eim.agents.plan.plan import Plan, advance, combine, improve, propose
from eim.agents.structure import StructureAgent
from eim.core import AgentReport, MarketSnapshot, Mode, Overlay


def _px(x: float) -> str:
    return f"{x:,.2f}"


def _line_at(geom: list, t: int) -> float:
    (t0, p0), (t1, p1) = geom
    return p0 + (p1 - p0) * (t - t0) / (t1 - t0) if t1 != t0 else p0


class PlanAgent:
    id = "plan"
    version = "1.0.0"
    requires = {"candles"}

    def __init__(self, params: PlanParams | None = None) -> None:
        self.params = params or PlanParams()
        self._structure = StructureAgent()
        self._levels = LevelsAgent()

    # --- insumos de un instante ----------------------------------------
    def _inputs(self, snap: MarketSnapshot, close: float, t: int):
        """(sesgo, confianza, soportes, resistencias) o None si `levels` no tiene datos."""
        st = self._structure.run(snap)
        lv = self._levels.run(snap)
        if lv.status == "no_data":
            return None
        sup: list[float] = []
        res: list[float] = []
        for z in lv.metrics["zones"]:
            if (z["p_low"] + z["p_high"]) / 2 >= close:
                res.append(z["p_low"])
            else:
                sup.append(z["p_high"])
        for o in lv.overlays:
            if o.kind in {"channel", "range"} and o.geometry["state"] == "INSIDE":
                up, lo = (_line_at(o.geometry[k], t) for k in ("upper", "lower"))
                if up > close:
                    res.append(up)
                if lo < close:
                    sup.append(lo)
        bias, conf = combine([st, lv], self.params)
        return bias, conf, sup, res

    # --- run ------------------------------------------------------------
    def run(self, snapshot: MarketSnapshot) -> AgentReport:
        p = self.params
        cs = snapshot.candles
        n = len(cs)
        if n < p.min_bars:
            return no_data_report(self.id, self.version, snapshot.asof,
                                  f"velas insuficientes: {n} < {p.min_bars}")
        src = snapshot.sources.get("candles", "desconocida")
        t = np.array([x.t for x in cs], dtype=np.int64)
        bar_ms = int(np.median(np.diff(t)))
        h = np.array([x.h for x in cs])
        lo = np.array([x.l for x in cs])
        c = np.array([x.c for x in cs])

        plan: Plan | None = None
        last: Plan | None = None       # último plan resuelto
        reason = "sin evaluar"
        cool_until = -1
        start = max(p.min_bars - 1, n - p.replay_bars)
        for j in range(start, n):
            if plan is not None:
                plan = advance(plan, j, float(h[j]), float(lo[j]), float(c[j]), p)
                if plan.status != "VIGENTE":
                    last, plan, cool_until = plan, None, j + p.cooldown_bars
                    reason = f"plan {last.status.lower()}"
            if (n - 1 - j) % p.replay_step or (plan is None and j < cool_until):
                continue
            sub = snapshot.model_copy(update={"candles": cs[: j + 1], "forming": None,
                                              "asof": int(t[j]) + bar_ms})
            inp = self._inputs(sub, float(c[j]), int(t[j]))
            if inp is None:
                reason = "niveles sin datos"
                continue
            bias, conf, sup, res = inp
            a = atr(h[: j + 1], lo[: j + 1], c[: j + 1], p.atr_period)
            if a <= 0:
                reason = "ATR nulo"
                continue
            if plan is not None:
                if bias * plan.side > 0:
                    new = propose(plan.side, float(c[j]), a, sup, res, conf, j, int(t[j]), p)
                    if isinstance(new, Plan):
                        plan = improve(plan, new, a, p)
                continue
            if abs(bias) < p.min_abs_bias:
                reason = f"sesgo combinado débil ({bias:+.2f})"
            elif conf < p.min_confidence:
                reason = f"confianza {conf:.2f} < {p.min_confidence:.2f}"
            else:
                new = propose(1 if bias > 0 else -1, float(c[j]), a, sup, res, conf, j,
                              int(t[j]), p)
                if isinstance(new, Plan):
                    plan = new
                else:
                    reason = new
        return self._report(snapshot, plan, last, reason, t, bar_ms, src)

    # --- salida ---------------------------------------------------------
    def _report(self, snap: MarketSnapshot, plan: Plan | None, last: Plan | None,
                reason: str, t: np.ndarray, bar_ms: int, src: str) -> AgentReport:
        p = self.params
        n = len(t)
        shown = plan
        if (shown is None and last is not None
                and n - 1 - (last.resolved_i or 0) < p.show_resolved_bars):
            shown = last
        metrics: dict = {"mode": Mode.ANALISIS.value, "plan": None, "source": src,
                         "coverage": snap.coverage.get("candles")}
        warnings = ["Propuesta analítica, no es una orden; el tamaño lo decide el motor de riesgo"]
        if shown is None:
            return AgentReport(
                agent_id=self.id, version=self.version, asof=snap.asof, bias=0, confidence=0,
                horizon_bars=p.horizon_bars, evidence=[f"sin plan: {reason}"],
                metrics=metrics, warnings=warnings, status="ok")
        tp = [shown.tp1] + ([shown.tp2] if shown.tp2 is not None else [])
        geom = {"side": "long" if shown.side > 0 else "short", "entry": shown.entry,
                "sl": shown.sl, "tp": tp, "rr": shown.rr, "mode": Mode.ANALISIS.value,
                "status": shown.status}
        metrics["plan"] = {**geom, "created_t": shown.created_t, "revisions": shown.revisions,
                           "tp_hit": shown.tp_hit}
        ev = [f"Plan {shown.name} {shown.status.lower()}: entrada {_px(shown.entry)}, "
              f"SL {_px(shown.sl)}, TP1 {_px(shown.tp1)}"
              + (f", TP2 {_px(shown.tp2)}" if shown.tp2 is not None else "")
              + f", R:R {shown.rr:.2f}",
              "SL tras el nivel de invalidación estructural con colchón de ATR"]
        if shown.revisions:
            ev.append(f"SL acercado {shown.revisions} vez/veces por nuevo nivel estructural")
        live = shown.status == "VIGENTE"
        end_t = None if live else int(t[shown.resolved_i or n - 1])
        ov = Overlay(
            id=f"plan:{shown.created_t}", agent_id=self.id, kind="trade_plan",
            t_from=shown.created_t, t_to=end_t, geometry=geom,
            label=f"Plan {shown.name} (ANALISIS) · {shown.status.lower()}",
            confidence=shown.confidence, evidence=ev,
            valid_until=shown.created_t + p.expiry_bars * bar_ms,
        )
        return AgentReport(
            agent_id=self.id, version=self.version, asof=snap.asof,
            bias=shown.side * shown.confidence if live else 0.0,
            confidence=shown.confidence if live else 0.0, horizon_bars=p.horizon_bars,
            evidence=ev, metrics=metrics, warnings=warnings, overlays=[ov], status="ok")
