"""Seguimiento y calibración de escenarios (T19): ¿son fiables las probabilidades y bandas?

`evaluate_forecast` compara un `ForecastSet` con lo ocurrido pasado el horizonte (escenario que se
cumplió, bandas, dirección). `summarize` agrega: cobertura 50/80/90 vs nominal, Brier y curva de
calibración, acierto direccional y comparación con una caminata aleatoria (sin deriva) cuya
volatilidad es la del propio pronóstico (σ = RIC/1.349 de su distribución terminal). Todo es
estadística sobre pronósticos ya cerrados; no re-entrena nada.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import NormalDist

from eim.core import ForecastSet

IDS = ("bull", "neutral", "bear")
BANDS = {"50": ("25", "75"), "80": ("10", "90"), "90": ("5", "95")}
QLEVELS = (5, 10, 25, 50, 75, 90, 95)
MIN_EVAL = 100  # por debajo no se emite veredicto
_ND = NormalDist()


@dataclass(frozen=True)
class Outcome:
    made_at: int
    realized: str  # bull | neutral | bear
    ret: float  # retorno log terminal
    probs: dict[str, float]
    top: str
    brier: float
    brier_rw: float
    pinball: float | None
    pinball_rw: float | None
    dir_pred: int  # signo de p_bull − p_bear
    dir_real: int
    in_band_terminal: dict[str, bool] = field(default_factory=dict)
    in_band_pooled: dict[str, float] = field(default_factory=dict)  # fracción de pasos dentro


def _pin(y: float, q: float, tau: float) -> float:
    d = y - q
    return max(tau * d, (tau - 1) * d)


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def evaluate_forecast(fs: ForecastSet, closes: dict[int, float]) -> Outcome | None:
    """None si el horizonte aún no ocurrió (faltan cierres) o el pronóstico no es evaluable."""
    sc = {s.id: s for s in fs.scenarios}
    times = [t for t, _ in sc["neutral"].path]
    if not times or any(t not in closes for t in times):
        return None
    inv = sc["neutral"].invalidation
    lo, hi = inv["level_low"], inv["level"]
    last, half = (lo + hi) / 2, (hi - lo) / 2
    final = closes[times[-1]]
    delta = final - last
    realized = "neutral" if abs(delta) < half else ("bull" if delta > 0 else "bear")
    probs = {i: sc[i].probability for i in IDS}
    brier = sum((probs[i] - (i == realized)) ** 2 for i in IDS)
    ret = math.log(final / last)
    q = fs.quantiles
    pin = pin_rw = None
    brier_rw = brier
    in_t: dict[str, bool] = {}
    pooled: dict[str, float] = {}
    if q and all(str(k) in q for k in QLEVELS):
        term = {k: dict(q[str(k)])[times[-1]] for k in QLEVELS}
        sigma = (math.log(term[75]) - math.log(term[25])) / (2 * _ND.inv_cdf(0.75))
        if sigma > 0:
            pin = sum(_pin(ret, math.log(term[k] / last), k / 100) for k in QLEVELS) / len(QLEVELS)
            pin_rw = sum(_pin(ret, sigma * _ND.inv_cdf(k / 100), k / 100)
                         for k in QLEVELS) / len(QLEVELS)
            cdf = lambda p: _ND.cdf(math.log(p / last) / sigma)  # noqa: E731
            rw = {"bear": cdf(last - half), "bull": 1 - cdf(last + half)}
            rw["neutral"] = 1 - rw["bear"] - rw["bull"]
            brier_rw = sum((rw[i] - (i == realized)) ** 2 for i in IDS)
        series = {k: dict(v) for k, v in q.items()}
        for name, (a, b) in BANDS.items():
            in_t[name] = series[a][times[-1]] <= final <= series[b][times[-1]]
            inside = sum(series[a][t] <= closes[t] <= series[b][t] for t in times)
            pooled[name] = inside / len(times)
    return Outcome(
        made_at=fs.made_at, realized=realized, ret=ret, probs=probs,
        top=max(IDS, key=lambda i: probs[i]), brier=brier, brier_rw=brier_rw, pinball=pin,
        pinball_rw=pin_rw, dir_pred=_sign(probs["bull"] - probs["bear"]), dir_real=_sign(delta),
        in_band_terminal=in_t, in_band_pooled=pooled)


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def calibration_curve(outs: list[Outcome], bins: int = 10) -> list[dict]:
    """Probabilidad predicha vs frecuencia observada (3 clases juntas, `bins` intervalos)."""
    acc = [[0, 0.0, 0] for _ in range(bins)]  # n, suma p, aciertos
    for o in outs:
        for i in IDS:
            b = min(int(o.probs[i] * bins), bins - 1)
            acc[b][0] += 1
            acc[b][1] += o.probs[i]
            acc[b][2] += o.realized == i
    return [{"p_pred": s / n, "p_obs": h / n, "n": n} for n, s, h in acc if n]


def summarize(outs: list[Outcome], horizon: int, pending: int = 0) -> dict:
    """Métricas agregadas + veredicto textual honesto."""
    n = len(outs)
    rep: dict = {"n_evaluated": n, "n_pending": pending, "horizon": horizon,
                 "n_effective": round(n / horizon, 1) if n else 0}
    if not n:
        rep["verdict"] = ["Sin pronósticos evaluados todavía: no hay base para opinar."]
        return rep
    withq = [o for o in outs if o.in_band_terminal]
    rep["coverage"] = {
        k: {"nominal": int(k) / 100,
            "terminal": _mean([o.in_band_terminal[k] for o in withq]),
            "pooled": _mean([o.in_band_pooled[k] for o in withq])} for k in BANDS}
    rep["n_with_bands"] = len(withq)
    rep["brier"] = _mean([o.brier for o in outs])
    rep["brier_rw"] = _mean([o.brier_rw for o in outs])
    rep["brier_skill"] = 1 - rep["brier"] / rep["brier_rw"] if rep["brier_rw"] else None
    pin = [o for o in outs if o.pinball is not None and o.pinball_rw is not None]
    rep["pinball"] = _mean([o.pinball for o in pin])
    rep["pinball_rw"] = _mean([o.pinball_rw for o in pin])
    rep["pinball_skill"] = (1 - rep["pinball"] / rep["pinball_rw"]) if pin and rep["pinball_rw"] \
        else None
    rep["curve"] = calibration_curve(outs)
    rep["ece"] = sum(abs(c["p_pred"] - c["p_obs"]) * c["n"] for c in rep["curve"]) / (3 * n)
    dd = [o for o in outs if o.dir_real != 0 and o.dir_pred != 0]
    rep["directional"] = {"n": len(dd), "accuracy": _mean([o.dir_pred == o.dir_real for o in dd])}
    rep["top_hit"] = _mean([o.top == o.realized for o in outs])
    rep["realized_freq"] = {i: sum(o.realized == i for o in outs) / n for i in IDS}
    rep["mean_prob"] = {i: sum(o.probs[i] for o in outs) / n for i in IDS}
    rep["verdict"] = verdict(rep)
    return rep


def verdict(rep: dict) -> list[str]:
    """Frases honestas derivadas de las métricas (sin adornos)."""
    n, ne = rep["n_evaluated"], rep["n_effective"]
    out: list[str] = []
    if n < MIN_EVAL:
        return [f"Muestra insuficiente ({n} pronósticos; mínimo {MIN_EVAL}): sin veredicto."]
    out.append(f"{n} pronósticos evaluados; por solape entre horizontes la muestra efectiva es "
               f"≈{ne:.0f} independientes: las diferencias pequeñas no son concluyentes.")
    cov = rep.get("coverage") or {}
    bad = [f"{k} %: {c['terminal']:.0%} observado" for k, c in cov.items()
           if c["terminal"] is not None and abs(c["terminal"] - c["nominal"]) > 0.05]
    if cov:
        out.append("Bandas fuera de la cobertura nominal (±5 pp) en " + "; ".join(bad) + "."
                   if bad else "Las bandas 50/80/90 cubren cerca de lo nominal (±5 pp).")
    bs = rep.get("brier_skill")
    if bs is not None:
        out.append("Las probabilidades de escenario NO superan a la caminata aleatoria "
                   f"(Brier skill {bs:+.1%})." if bs <= 0.02 else
                   f"Las probabilidades mejoran a la caminata aleatoria (Brier skill {bs:+.1%}).")
    ps = rep.get("pinball_skill")
    if ps is not None:
        out.append("La distribución terminal NO supera a la caminata aleatoria "
                   f"(pinball skill {ps:+.1%})." if ps <= 0.02 else
                   f"La distribución terminal mejora a la caminata aleatoria (pinball {ps:+.1%}).")
    d = rep["directional"]
    if d["accuracy"] is not None and d["n"] >= 30:
        z = (d["accuracy"] - 0.5) / math.sqrt(0.25 / max(ne, 1))
        out.append(f"Acierto direccional {d['accuracy']:.1%} (n={d['n']}): "
                   + ("no distinguible del azar." if abs(z) < 2 else
                      "distinto del azar." if z > 0 else "peor que el azar."))
    if rep["ece"] > 0.05:
        out.append(f"Calibración imperfecta (error esperado {rep['ece']:.1%}).")
    if (bs is not None and bs <= 0.02) and (ps is None or ps <= 0.02):
        out.append("Conclusión: no supera la línea base; usar la proyección solo como rango de "
                   "incertidumbre, no como señal.")
    return out
