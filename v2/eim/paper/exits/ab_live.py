"""A/B prospectivo de M8 frente a la escalera (T135, criterio 7 de §5.4 y E9 de §8).

Mide en datos nuevos lo mismo que T134 midió en el banco: todas las ideas de 1 h y 4 h, con tamaño
fijo y sin la memoria de los perfiles, emparejadas por idea. Por eso no es un perfil más: un libro
con topes y cupos mediría otra población, y comparar su intervalo con la estimación de T134 no
querría decir nada. Tampoco toca el vivo: corre sobre una copia y no cambia los perfiles de T31.

**Medir no es adoptar.** M8 falló los criterios 2, 4 y 5 en T134. Un buen resultado aquí dice que el
efecto se mantiene en datos nuevos, no que M8 se pueda encender: eso sería otra decisión del
usuario.

Lo que queda congelado antes de la primera idea que cuenta, en un archivo con huella:
- la tabla del cuantil del MAE por estrategia@marco, ajustada solo con datos anteriores al inicio;
- las unidades de T134 tal cual: cuantil en σ de Parkinson aplicado sobre σ ATR(14), porque es la
  geometría que dio la señal (BACKLOG T137 (1));
- el inicio, los mínimos y la regla del veredicto. **Hasta cumplir los mínimos no hay veredicto,**
  para que no se pueda parar en una semana que salga bien.

Puro salvo `load_frozen` y `save_frozen`, que solo leen y escriben el archivo que se les pide.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np

from eim.paper.exits import bench, grid, power, stats, winners_mae
from eim.paper.exits import walkforward as wf
from eim.paper.exits.prereg import Prereg
from eim.paper.ideas import Idea
from eim.validation.stats import rng_for

CANDIDATE = "M8 q=0.95"
BASE = "M0 first_r=0.1"
QUANTILE = 0.95
RATIO_SIGMA = "parkinson"        # en qué σ se mide el MAE de las ganadoras (como T134)
STOP_SIGMA = "atr14"             # sobre qué σ se aplica el cuantil (como T134)
SIGMAS = (STOP_SIGMA, RATIO_SIGMA)     # el orden importa: `grid` toma el primero para M8
DAY_MS = 86_400_000
WEEK_MS = 7 * DAY_MS
RUNNING, PASS, FAIL = "EN CURSO", "PASA", "NO PASA"


def fit_table(ref_trades: Sequence[bench.BenchTrade], ratio_of: Callable, cutoff: int,
              embargo_ms: int, pr: Prereg) -> winners_mae.WinnersMae:
    """Cuantil del MAE de las ganadoras con los últimos meses de ajuste antes de `cutoff`.

    Son las mismas reglas de un pliegue de T134: salida de referencia fija, purga y embargo, y
    muestra mínima por estrategia@marco. El tramo de prueba es todo lo que venga después.
    """
    fold = wf.Fold(0, wf.add_months(cutoff, -pr.design.fit_months), cutoff, cutoff,
                   cutoff + 1, embargo_ms)
    return winners_mae.fit_fold(ref_trades, fold, ratio_of,
                                reference=pr.winners_mae.reference, quantile=QUANTILE,
                                min_trades=pr.winners_mae.min_trades)


def freeze(table: winners_mae.WinnersMae, *, start: int, cutoff: int, plan: dict, sd_daily: float,
           t134: dict, pr: Prereg, commit: str, data_note: str) -> dict:
    """El pre-registro del A/B. Exige que el ajuste termine antes de la primera idea que cuenta."""
    if cutoff > start:
        raise ValueError("la tabla no puede usar datos posteriores al inicio del A/B")
    effect = plan["effect_r"]
    days = power.required_n(sd_daily, effect)
    body = {"version": "t135_ab_m8_v1", "candidate": CANDIDATE, "base": BASE, "symbol": pr.symbol,
            "prereg": pr.version, "commit": commit, "mode": "SIMULADO", "data": data_note,
            "start": start, "start_iso": wf.iso(start), "fit_cutoff_iso": wf.iso(cutoff),
            "decision_timeframes": list(pr.design.decision_timeframes),
            "sigma_stop": STOP_SIGMA, "sigma_ratio": RATIO_SIGMA,
            "table": table.to_json(), "t134": t134, "plan": plan,
            "sd_daily_r": sd_daily, "required_days": days,
            "min_detectable_r_at_min_weeks_by_day": power.min_detectable(
                sd_daily, power.MIN_WEEKS * 7),
            "min_weeks": power.MIN_WEEKS, "required_n": plan["required_n"],
            "rule": ("Sin veredicto hasta cumplir a la vez las semanas, las operaciones y los "
                     "días mínimos. Entonces PASA si ΔE[R] > 0 y su IC 95 % por bloques de día "
                     "contiene la estimación de T134; si no, NO PASA. Pasar no adopta nada: M8 "
                     "falló los criterios 2, 4 y 5 en T134."),
            "seed": pr.seed, "reps": pr.bootstrap.reps, "level": pr.bootstrap.level}
    return {**body, "fingerprint": power.fingerprint(body)}


def save_frozen(frozen: dict, path: str | Path) -> Path:
    """Guarda el pre-registro. Se niega a cambiarlo: un cambio es una versión nueva."""
    return power.write_plan(frozen, path)


def load_frozen(path: str | Path) -> dict:
    """Lee el pre-registro y comprueba su huella: uno editado a mano no vale."""
    frozen = json.loads(Path(path).read_text(encoding="utf-8"))
    if frozen.get("fingerprint") != power.fingerprint(frozen):
        raise ValueError(f"{path} no cuadra con su huella: se editó después de congelarse")
    return frozen


def quantile_of(frozen: dict) -> Callable[[str, int], float | None]:
    """Cuantil congelado por estrategia@marco. Sin muestra, None: M8 no toca el SL de esa idea."""
    table = {k: float(v["mae_sigma"]) for k, v in frozen["table"]["sids"].items()}

    def of(sid: str, t: int) -> float | None:
        return table.get(sid)
    return of


def counted_ideas(ideas: Sequence[Idea], frozen: dict) -> list[Idea]:
    """Las ideas del A/B: posteriores al inicio, de los marcos de T134 y sin el control."""
    tfs = set(frozen["decision_timeframes"])
    return sorted((i for i in ideas if i.t >= frozen["start"] and i.timeframe in tfs
                   and i.strategy != bench.CONTROL_STRATEGY), key=lambda x: (x.t, x.id))


def pick(variants: Sequence[grid.Variant]) -> tuple[grid.Variant, grid.Variant]:
    """La base y la candidata, con los nombres de T134: si cambian, falla en vez de medir otra."""
    by_id = {v.id: v for v in variants}
    return by_id[BASE], by_id[CANDIDATE]


def _mean(xs: Sequence[float]) -> float | None:
    return float(np.mean(xs)) if len(xs) else None


def evaluate(b: bench.Bench, frozen: dict, last_t: int) -> dict:
    """Lo medido hasta `last_t`, la última vela de la copia. Solo cuenta lo que cerraron las dos."""
    rows = b.paired()
    base, cand = [r.by_policy[BASE] for r in rows], [r.by_policy[CANDIDATE] for r in rows]
    diffs = b.diffs(CANDIDATE, BASE) if rows else []
    days = {d for d, _ in diffs}
    rng = rng_for(frozen["seed"], f"{frozen['version']}|ci")
    lo, hi = stats.paired_ci(diffs, frozen["reps"], frozen["level"], rng)
    moved = sum(1 for a, c in zip(base, cand, strict=True)
                if c.risk_usd > a.risk_usd * (1 + 1e-9))
    return {"n": len(rows), "days": len(days), "ideas": len(b.rows),
            "weeks": max(0.0, (last_t - frozen["start"]) / WEEK_MS), "last_t": last_t,
            "last_iso": wf.iso(last_t), "dropped": b.dropped, "skipped_qty": b.skipped_qty,
            "delta": _mean([d for _, d in diffs]), "ci": [lo, hi],
            "e_r_base": _mean([t.r for t in base]), "e_r_candidate": _mean([t.r for t in cand]),
            "gross_r_base": _mean([t.gross_r for t in base]),
            "gross_r_candidate": _mean([t.gross_r for t in cand]),
            "cost_r_base": _mean([t.cost_r for t in base]),
            "cost_r_candidate": _mean([t.cost_r for t in cand]),
            "moved_sl": moved}


def verdict(ev: dict, frozen: dict) -> dict:
    """La regla congelada. Mientras falte un mínimo, EN CURSO: si faltan datos, se alarga."""
    missing = []
    if ev["weeks"] < frozen["min_weeks"]:
        missing.append(f"{ev['weeks']:.1f} de {frozen['min_weeks']} semanas")
    if ev["n"] < frozen["required_n"]:
        missing.append(f"{ev['n']} de {frozen['required_n']} operaciones")
    if ev["days"] < frozen["required_days"]:
        missing.append(f"{ev['days']} de {frozen['required_days']} días")
    if missing:
        return {"state": RUNNING, "why": "faltan " + ", ".join(missing)}
    d, (lo, hi), ref = ev["delta"], ev["ci"], frozen["t134"]["delta"]
    if d is None or not (math.isfinite(lo) and math.isfinite(hi)):
        return {"state": RUNNING, "why": "sin intervalo calculable"}
    if d <= 0:
        return {"state": FAIL, "why": f"ΔE[R] {d:+.4f} no es positivo"}
    if not lo <= ref <= hi:
        return {"state": FAIL, "why": (f"el IC [{lo:+.4f}, {hi:+.4f}] no contiene la estimación "
                                       f"de T134 ({ref:+.4f}): el efecto se degradó")}
    # El criterio 7 no pide que el IC excluya el 0. Con 4 semanas, una salida sin efecto pasaría
    # alrededor del 17 % de las veces, así que el informe lo dice en vez de esconderlo.
    weak = ("; **el IC incluye el 0: también es compatible con que no haya efecto**"
            if lo <= 0 else "")
    return {"state": PASS, "why": (f"ΔE[R] {d:+.4f} > 0 y el IC [{lo:+.4f}, {hi:+.4f}] contiene "
                                   f"la estimación de T134 ({ref:+.4f}){weak}")}


def _r(x: float | None) -> str:
    return "sin dato" if x is None or not math.isfinite(x) else f"{x:+.4f} R"


def render(ev: dict, frozen: dict, coverage: str = "") -> str:
    """Informe semanal. Mientras no haya veredicto, las cifras son provisionales y se dice."""
    v = verdict(ev, frozen)
    lo, hi = ev["ci"]
    out = [f"# T135 — A/B de {frozen['candidate']} frente a {frozen['base']}", "",
           f"**Modo: {frozen['mode']}.** Copia con velas hasta {ev['last_iso']}. Pre-registro "
           f"`{frozen['version']}`, huella `{frozen['fingerprint'][:12]}`, inicio "
           f"{frozen['start_iso']}.", "",
           f"**Estado: {v['state']}** ({v['why']}).", ""]
    if v["state"] == RUNNING:
        out += ["Las cifras son provisionales. **No se decide con ellas:** parar en una semana que "
                "salga bien es ajustar el resultado.", ""]
    out += ["| Medida | Valor |", "|---|---|",
            f"| Operaciones emparejadas (mínimo {frozen['required_n']}) | {ev['n']} |",
            f"| Días con operaciones (mínimo {frozen['required_days']}) | {ev['days']} |",
            f"| Semanas (mínimo {frozen['min_weeks']}) | {ev['weeks']:.1f} |",
            f"| ΔE[R] | {_r(ev['delta'])} |",
            f"| IC 95 % por bloques de día | {_r(lo)} a {_r(hi)} |",
            f"| Estimación de T134 | {_r(frozen['t134']['delta'])} |",
            f"| E[R] neto, {frozen['base']} | {_r(ev['e_r_base'])} |",
            f"| E[R] neto, {frozen['candidate']} | {_r(ev['e_r_candidate'])} |",
            f"| E[R] bruto, base y candidata | {_r(ev['gross_r_base'])} y "
            f"{_r(ev['gross_r_candidate'])} |",
            f"| Costo, base y candidata | {_r(ev['cost_r_base'])} y "
            f"{_r(ev['cost_r_candidate'])} |",
            f"| Operaciones en las que M8 apartó el SL | {ev['moved_sl']} de {ev['n']} |",
            f"| Ideas vistas | {ev['ideas']} |",
            f"| Sin cerrar, por salida | {ev['dropped']} |", ""]
    if coverage:
        out += [f"**Fuente y cobertura:** {coverage}", ""]
    out += ["**Medir no es adoptar.** M8 falló los criterios 2, 4 y 5 de §5.4 en T134. Aunque "
            "pase, encenderla sería otra decisión, y una mejor salida no crea ventaja de entrada: "
            "mira el E[R] neto de la candidata.", ""]
    return "\n".join(out)
