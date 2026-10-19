"""Puerta de validación (T49), pura: evidencia de una versión → veredicto con motivo.

`measure` calcula los números de una `estrategia@marco@vN` en `asof` con solo sus operaciones
sombra cerradas en `exit_t ≤ asof`, fuera de muestra y netas de costos; `validate_all` ajusta los
p de V3 por Holm sobre TODOS los intentos registrados (también retirados) y aplica los criterios.
Sin I/O: el servicio (`service.py`) le pasa las operaciones, las ventanas y los p previos.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from eim.backtest.edge import holm
from eim.validation import stats as st
from eim.validation.criteria import Criteria
from eim.validation.evidence import Trade, select
from eim.validation.lineage import Version, Window

VALIDADA, OBSERVACION, RECHAZADA = "VALIDADA", "EN OBSERVACIÓN", "RECHAZADA"
NAMES = {"V1": "Suficiencia de datos", "V2": "Expectativa neta", "V3": "Contra el azar",
         "V4": "Drawdown", "V5": "Estabilidad", "V6": "Costos"}


@dataclass(frozen=True)
class Check:
    id: str
    name: str
    value: Any
    threshold: str
    ok: bool | None            # None = pendiente (aún sin datos para juzgarlo)
    reason: str

    def to_json(self) -> dict:
        return {"id": self.id, "name": self.name, "value": self.value,
                "threshold": self.threshold, "ok": self.ok, "reason": self.reason}


@dataclass(frozen=True)
class Measure:
    label: str
    asof: int
    n: int
    excluded: int
    future: int
    mean_r: float | None
    se: float | None
    regimes: dict[str, int]
    ci: tuple[float, float]
    p_raw: float | None
    reps: int
    dd: float
    ret: float
    windows: list[tuple[int, int, float]]
    n_live: int
    mean_live: float | None
    cost_r: float | None
    span: tuple[int | None, int | None]
    extras: dict = field(default_factory=dict)


def _r(x: float | None, k: int = 4) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), k)


def measure(label: str, trades: Sequence[Trade], windows: Sequence[Window], symbol: str,
            asof: int, crit: Criteria, attempts: int,
            prices: tuple[np.ndarray, np.ndarray] | None = None) -> Measure:
    s = select(trades, windows, symbol, asof)
    x = s.oos
    r = np.array([o.r for o in x], dtype=float)
    t = np.array([o.t for o in x], dtype=np.int64)
    rng = st.rng_for(crit.seed, f"{label}|{symbol}")
    n = len(r)
    mean = float(r.mean()) if n else None
    se = float(r.std(ddof=1) / math.sqrt(n)) if n >= 2 else None
    reps = crit.null_reps(attempts)
    ci = st.day_block_ci(r, t, crit.v2_expectancy.boot_reps, crit.v2_expectancy.level, rng)
    p = st.random_side_pvalue(r, np.array([o.r_flip for o in x], dtype=float), reps, rng)
    dd, ret = st.compounded_dd(r, crit.v4_drawdown.risk_per_trade)
    v5 = crit.v5_stability
    live = np.array([o.r for o in x if o.origin == "vivo"], dtype=float)
    span = (int(t.min()) if n else None, int(max(o.exit_t for o in x)) if n else None)
    extras = {
        "win_rate": _r(float((r > 0).mean())) if n else None,
        "pf": _r(st.profit_factor(r), 3) if n else None,
        "mfe_r": _r(float(np.mean([o.mfe_r for o in x])), 3) if n else None,
        "mae_r": _r(float(np.mean([o.mae_r for o in x])), 3) if n else None,
        "dsr": _r(st.dsr(list(r), attempts)) if n else None,
        "ret_1pct": _r(ret),
        "buy_hold": _r(st.buy_hold(prices, span[0], span[1])) if n else None,
    }
    return Measure(
        label=label, asof=asof, n=n, excluded=s.excluded, future=s.future, mean_r=mean, se=se,
        regimes=dict(Counter(o.regime for o in x)), ci=ci, p_raw=p, reps=reps, dd=dd, ret=ret,
        windows=st.window_means(r, t, v5.window_days, v5.window_min_trades), n_live=len(live),
        mean_live=float(live.mean()) if len(live) else None,
        cost_r=float(np.mean([o.cost_r for o in x])) if n else None, span=span, extras=extras)


def _checks(m: Measure, p_holm: float | None, crit: Criteria) -> list[Check]:
    c1, c2, c3 = crit.v1_data, crit.v2_expectancy, crit.v3_random
    c4, c5, c6 = crit.v4_drawdown, crit.v5_stability, crit.v6_costs
    big = {k: v for k, v in m.regimes.items() if v >= c1.min_per_regime}
    ok1 = m.n >= c1.min_trades and len(big) >= c1.min_regimes
    lo, hi = m.ci
    ok2 = None if m.n < 2 else bool(m.mean_r > 0 and lo > 0)
    ok3 = None if p_holm is None else bool(p_holm < c3.alpha)
    ok4 = None if m.n == 0 else bool(m.dd <= c4.max_dd)
    pos = sum(1 for _, _, mu in m.windows if mu > 0)
    frac = pos / len(m.windows) if m.windows else None
    win_ok = None if len(m.windows) < c5.min_windows else bool(frac >= c5.min_positive_frac)
    live_ok = (None if m.n_live < c5.live_min_trades else bool(m.mean_live > 0))
    ok5 = False if False in (win_ok, live_ok) else (None if None in (win_ok, live_ok) else True)
    ok6 = None if m.cost_r is None else bool(m.cost_r <= c6.max_cost_r)
    reg = ", ".join(f"{k} {v}" for k, v in sorted(m.regimes.items(), key=lambda kv: -kv[1]))
    return [
        Check("V1", NAMES["V1"], {"n": m.n, "regimes": m.regimes}, f"≥ {c1.min_trades} op. y "
              f"≥ {c1.min_regimes} regímenes con ≥ {c1.min_per_regime}", ok1,
              f"{m.n} operaciones fuera de muestra; regímenes: {reg or 'ninguno'}"),
        Check("V2", NAMES["V2"], {"mean_r": _r(m.mean_r), "ci": [_r(lo), _r(hi)]},
              f"R medio > 0 e IC{c2.level:.0%} (bloques de día, {c2.boot_reps} remuestreos) "
              "sin el 0", ok2,
              "muestra insuficiente" if ok2 is None else
              f"R medio {m.mean_r:+.3f}, IC [{lo:+.3f}, {hi:+.3f}]"),
        Check("V3", NAMES["V3"], {"p": _r(m.p_raw), "p_holm": _r(p_holm), "reps": m.reps},
              f"p (Holm sobre todos los intentos) < {c3.alpha}", ok3,
              "sin operaciones" if ok3 is None else
              f"p bruto {m.p_raw:.4f} → Holm {p_holm:.4f} ({m.reps} réplicas de lado al azar)"),
        Check("V4", NAMES["V4"], {"max_dd": _r(m.dd)},
              f"DD ≤ {c4.max_dd:.0%} con {c4.risk_per_trade:.0%} de riesgo por operación", ok4,
              "sin operaciones" if ok4 is None else f"DD máximo {m.dd:.1%}"),
        Check("V5", NAMES["V5"], {"windows": len(m.windows), "positive": pos,
                                  "frac": _r(frac), "n_live": m.n_live,
                                  "mean_live": _r(m.mean_live)},
              f"≥ {c5.min_positive_frac:.0%} de ventanas de {c5.window_days} d con R > 0 "
              f"(≥ {c5.min_windows}) y en vivo ≥ {c5.live_min_trades} op. con R > 0", ok5,
              f"{pos}/{len(m.windows)} ventanas positivas"
              + ("" if win_ok is not None else f" (pendiente: < {c5.min_windows} ventanas)")
              + f"; en vivo {m.n_live} op."
              + ("" if m.mean_live is None else f", R medio {m.mean_live:+.3f}")
              + ("" if live_ok is not None else f" (pendiente: < {c5.live_min_trades})")),
        Check("V6", NAMES["V6"], {"cost_r": _r(m.cost_r)}, f"costo medio ≤ {c6.max_cost_r} R",
              ok6, "sin operaciones" if ok6 is None else f"costo medio {m.cost_r:.3f} R"),
    ]


@dataclass(frozen=True)
class Verdict:
    version: Version
    measure: Measure
    verdict: str
    reason: str
    checks: tuple[Check, ...]
    p_holm: float | None
    criteria: str
    windows: tuple[Window, ...]

    def to_json(self) -> dict:
        m, v = self.measure, self.version
        return {
            "id": v.label, "sid": v.sid, "n": v.n, "strategy": v.strategy,
            "timeframe": v.timeframe, "fingerprint": v.fingerprint, "origin": v.origin,
            "retired": v.retired_ms, "verdict": self.verdict, "reason": self.reason,
            "criteria": self.criteria, "asof": m.asof, "n_oos": m.n, "n_live": m.n_live,
            "p_raw": _r(m.p_raw, 6), "p_holm": _r(self.p_holm, 6),
            "checks": [c.to_json() for c in self.checks],
            "oos": {"from": m.span[0], "to": m.span[1], "excluded_in_windows": m.excluded,
                    "after_asof": m.future, "windows": [w.to_json() for w in self.windows]},
            "mean_r": _r(m.mean_r), "extras": m.extras,
        }


def validate(version: Version, m: Measure, p_holm: float | None, crit: Criteria,
             windows: Sequence[Window] = ()) -> Verdict:
    checks = _checks(m, p_holm, crit)
    neg = crit.clear_negative
    bad = [c.id for c in checks[1:] if c.ok is False]
    pend = [c.id for c in checks[1:] if c.ok is None]
    if m.n >= neg.min_trades and m.mean_r + neg.z * (m.se or 0.0) < 0:
        out = (RECHAZADA, f"claramente negativa: R medio {m.mean_r:+.3f} + {neg.z:g}·EE "
                          f"{m.se:.3f} < 0 → ciclo de mejora")
    elif checks[0].ok is False:
        out = (OBSERVACION, f"V1: {checks[0].reason}")
    elif bad:
        out = (RECHAZADA, "falla " + ", ".join(f"{b} ({NAMES[b]})" for b in bad)
               + " → ciclo de mejora")
    elif pend:
        out = (OBSERVACION, "pendiente: " + ", ".join(f"{b} ({NAMES[b]})" for b in pend))
    else:
        out = (VALIDADA, "cumple V1–V6")
    return Verdict(version, m, out[0], out[1], tuple(checks), p_holm, crit.version,
                   tuple(windows))


def holm_family(current: Mapping[str, float | None],
                prior: Mapping[str, float | None]) -> dict[str, float]:
    """p ajustados por Holm sobre la familia completa de intentos (sin p → 1)."""
    fam = {k: (1.0 if p is None else p) for k, p in prior.items()}
    fam.update({k: (1.0 if p is None else p) for k, p in current.items()})
    return holm(fam) if fam else {}


def validate_all(items: Sequence[tuple[Version, Measure, Sequence[Window]]],
                 prior: Mapping[str, float | None], crit: Criteria) -> list[Verdict]:
    """`items`: (versión, medida, ventanas usadas); `prior`: último p bruto de cada intento
    registrado (clave = la misma que `Measure.label`), también los retirados."""
    adj = holm_family({m.label: m.p_raw for _, m, _ in items}, prior)
    return [validate(v, m, None if m.p_raw is None else adj[m.label], crit, w)
            for v, m, w in items]
