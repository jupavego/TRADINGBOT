"""Examen de la familia de la forja (T208): simular todas las recetas y medirlas con honradez.

Una sola pasada por la historia dentro de muestra: para cada (disparador, dirección, filtro) se
calcula la señal una vez y se prueban todas las salidas sobre ella. De cada receta no se guardan
las operaciones, sino lo que necesitan las pruebas: sumas de R **por día de sesión** (el bloque de
todos los remuestreos), sumas de potencias (para el Sharpe deflactado) y la reserva aparte, que no
se mira hasta el final.

No hay ajuste: la rejilla está congelada en el pre-registro, así que no se elige nada mirando
resultados. Los tramos sirven para el PBO y la estabilidad.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

import numpy as np

from eim.forge import features, fstats, space
from eim.forge.data import Series
from eim.forge.engine import Market, Rules, Trades, simulate
from eim.forge.session import Sessions
from eim.indicators import volatility


@dataclass
class Family:
    """Lo acumulado de todas las recetas: nada de operaciones sueltas, solo lo que se mide."""

    recipes: tuple[space.Recipe, ...]
    days: int
    s: np.ndarray = field(init=False)
    c: np.ndarray = field(init=False)
    cost: np.ndarray = field(init=False)
    pow_: np.ndarray = field(init=False)
    hold: np.ndarray = field(init=False)
    kinds: np.ndarray = field(init=False)
    capped: np.ndarray = field(init=False)
    distinct_signals: int = 0
    seconds: float = 0.0

    def __post_init__(self) -> None:
        m = len(self.recipes)
        self.s = np.zeros((m, self.days), dtype=np.float32)
        self.c = np.zeros((m, self.days), dtype=np.float32)
        self.cost = np.zeros((m, self.days), dtype=np.float32)
        self.pow_ = np.zeros((m, 4), dtype=np.float64)     # Σr, Σr², Σr³, Σr⁴
        self.hold = np.zeros((m, 2), dtype=np.float64)     # n y Σr de la reserva
        self.kinds = np.zeros((m, 4), dtype=np.int64)      # stop, objetivo, señal, cierre
        self.capped = np.zeros(m, dtype=np.int64)

    @property
    def n(self) -> np.ndarray:
        return self.c.sum(axis=1)

    @property
    def mean_r(self) -> np.ndarray:
        n = self.n
        return np.where(n > 0, self.s.sum(axis=1) / np.maximum(n, 1), np.nan)


def market(s: Series, ss: Sessions, f: dict[str, np.ndarray]) -> Market:
    return Market(s, ss, volatility.atr(s.h, s.l, s.c, 14), f["vwap_s"])


def _put(fam: Family, r: int, tr: Trades, hold_day: int) -> None:
    is_hold = tr.day >= hold_day
    hr = tr.r[is_hold]
    fam.hold[r] = (len(hr), float(hr.sum()))
    d, rr, cc = tr.day[~is_hold], tr.r[~is_hold], tr.cost_r[~is_hold]
    if len(rr):
        fam.s[r] = np.bincount(d, weights=rr, minlength=fam.days)[:fam.days]
        fam.c[r] = np.bincount(d, minlength=fam.days)[:fam.days]
        fam.cost[r] = np.bincount(d, weights=cc, minlength=fam.days)[:fam.days]
        fam.pow_[r] = [rr.sum(), (rr ** 2).sum(), (rr ** 3).sum(), (rr ** 4).sum()]
        fam.kinds[r] = np.bincount(tr.kind[~is_hold], minlength=4)[:4]
    fam.capped[r] = tr.capped


def simulate_all(s: Series, ss: Sessions, f: dict[str, np.ndarray], hold_day: int,
                 rules: Rules, cost_mult: float = 1.0, log: bool = True) -> Family:
    """Simula las 100 % de las recetas de la rejilla. `hold_day` = primera sesión de la reserva."""
    recipes = space.enumerate_recipes()
    fam = Family(recipes, hold_day)
    mk = market(s, ss, f)
    by_id = {r.id: i for i, r in enumerate(recipes)}
    seen: dict[bytes, tuple[str, str, str]] = {}
    t0 = time.time()
    done = 0
    for trig in space.TRIGGERS:
        raw = np.asarray(trig.fn(f), dtype=np.int8)
        for d in space.DIRECTIONS:
            for fl in space.FILTERS:
                sig = space.apply(raw, d, fl, f, ss.can_signal)
                key = hashlib.blake2b(sig.tobytes(), digest_size=16).digest()
                twin = seen.get(key)
                if twin is None:
                    seen[key] = (trig.id, d, fl)
                    for ex in space.EXITS:
                        r = by_id[f"{trig.id}|{d}|{fl}|{ex.id}"]
                        tr = simulate(mk, sig, ex, rules, cost_mult, flip=raw)
                        _put(fam, r, tr, hold_day)
                else:
                    for ex in space.EXITS:                      # gemela: mismos resultados
                        a = by_id[f"{twin[0]}|{twin[1]}|{twin[2]}|{ex.id}"]
                        r = by_id[f"{trig.id}|{d}|{fl}|{ex.id}"]
                        for arr in (fam.s, fam.c, fam.cost, fam.pow_, fam.hold, fam.kinds):
                            arr[r] = arr[a]
                        fam.capped[r] = fam.capped[a]
                done += len(space.EXITS)
                if log and done % 1000 < len(space.EXITS):
                    print(f"  {done}/{len(recipes)} recetas · {time.time() - t0:.0f} s", flush=True)
    fam.distinct_signals = len(seen)
    fam.seconds = time.time() - t0
    return fam


def random_control(s: Series, ss: Sessions, f: dict[str, np.ndarray], rules: Rules,
                   n_sig: int, series: int = 40, seed: int = 20261121) -> dict:
    """Control: entradas al azar con la misma cadencia y las mismas salidas. Debe dar ≈ −costo."""
    rng = np.random.default_rng(seed)
    mk = market(s, ss, f)
    pool = np.flatnonzero(ss.can_signal)
    out: dict[str, dict] = {}
    for ex in space.EXITS:
        rs, ns = [], 0
        for _ in range(series):
            pick = rng.choice(pool, size=min(n_sig, len(pool)), replace=False)
            sig = np.zeros(len(s), dtype=np.int8)
            sig[np.sort(pick)] = rng.choice(np.array([-1, 1], np.int8), size=len(pick))
            tr = simulate(mk, sig, ex, rules)
            rs.append(float(tr.r.sum()))
            ns += len(tr)
        out[ex.id] = {"trades": ns, "mean_r": (sum(rs) / ns) if ns else None, "series": series}
    return out


def screen(fam: Family, prereg: dict, reps: int, seed: int) -> dict:
    """Mide la familia: Romano-Wolf, Sharpe deflactado, PBO y quién sobrevive. Sin tocar reserva."""
    from eim.paper.exits.stats import pbo

    crit = prereg["criteria"]
    names = [r.id for r in fam.recipes]
    m = len(names)
    n = fam.n
    rw = fstats.stepm(fam.s, fam.c, names, reps, seed, min_trades=crit["min_trades"])
    ds, z_max = fstats.dsr(n, *(fam.pow_[:, k] for k in range(4)), m)
    sl = fstats.slice_means(fam.s, fam.c, crit["cscv_splits"])
    ok = np.flatnonzero(n >= crit["min_trades"])
    # el PBO solo admite recetas con operaciones en TODOS los tramos: un tramo vacío (NaN) haría
    # que el «mejor dentro de muestra» fuese un hueco
    full = [i for i in ok if np.all(np.isfinite(sl[i]))]
    fam_pbo = (pbo({names[i]: sl[i] for i in full}, crit["cscv_splits"]) if len(full) >= 2
               else {"pbo": None, "reason": "hacen falta >= 2 recetas con todos los tramos"})
    fam_pbo["recipes"] = len(full)
    mean_r = fam.mean_r
    rows = []
    for i in ok:
        p_rw = rw["p_rw"].get(names[i])
        rows.append({"id": names[i], "family": fam.recipes[i].family, "n": int(n[i]),
                     "mean_r": float(mean_r[i]), "t": rw["t"].get(names[i]),
                     "p_raw": rw["p_raw"].get(names[i]), "p_rw": p_rw,
                     "p_holm": rw["p_holm"].get(names[i]),
                     "dsr": None if np.isnan(ds[i]) else float(ds[i]),
                     "cost_r": float(fam.cost[i].sum() / max(n[i], 1)),
                     "gross_r": float((fam.s[i].sum() + fam.cost[i].sum()) / max(n[i], 1)),
                     "capped": int(fam.capped[i]),
                     "exits": {k: int(v) for k, v in zip(("stop", "objetivo", "senal", "cierre"),
                                                         fam.kinds[i], strict=True)}})
    rows.sort(key=lambda r: -r["mean_r"])
    pbo_ok = fam_pbo.get("pbo") is not None and fam_pbo["pbo"] <= crit["pbo_max"]
    surv = [r for r in rows
            if r["n"] >= crit["min_trades"]
            and r["p_rw"] is not None and r["p_rw"] < crit["alpha_rw"]
            and r["dsr"] is not None and r["dsr"] > crit["dsr_min"] and pbo_ok]
    costs = float(fam.cost[ok].sum() / max(n[ok].sum(), 1)) if len(ok) else None
    barrier = {"mean_cost_r": costs,
               "mean_r": float(fam.s[ok].sum() / max(n[ok].sum(), 1)) if len(ok) else None,
               "mean_gross_r": (float((fam.s[ok].sum() + fam.cost[ok].sum())
                                      / max(n[ok].sum(), 1)) if len(ok) else None),
               "positive_gross": int(sum(1 for r in rows if r["gross_r"] > 0)),
               "positive_net": int(sum(1 for r in rows if r["mean_r"] > 0))}
    return {"m": m, "distinct_signals": fam.distinct_signals, "with_min_trades": int(len(ok)),
            "cost_barrier": barrier,
            "days": int(fam.days), "seconds": fam.seconds, "pbo": fam_pbo,
            "expected_max_z": z_max, "t_null_max_mean": rw.get("t_null_max_mean"),
            "rows": rows, "survivors": [r["id"] for r in surv],
            "best": rows[0] if rows else None,
            "trades_total": int(n.sum()), "reps": reps, "seed": seed}


def holdout(fam: Family, ids: list[str]) -> dict:
    """La reserva, mirada UNA sola vez, solo para las recetas que ya pasaron todo lo demás."""
    by = {r.id: i for i, r in enumerate(fam.recipes)}
    return {i: {"n": int(fam.hold[by[i]][0]),
                "mean_r": (float(fam.hold[by[i]][1] / fam.hold[by[i]][0])
                           if fam.hold[by[i]][0] else None)} for i in ids}


def build_features(s: Series) -> tuple[Sessions, dict[str, np.ndarray]]:
    from eim.forge import session

    ss = session.build(s.t)
    return ss, features.build(s, ss)
