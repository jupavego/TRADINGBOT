"""T163: puerta de potencia de la cartera TSMOM con volatilidad objetivo, y medición si pasa.

    python scripts/t163_tsmom.py --data backups/t139_banco

Especificación única, tramos, ventaja mínima a detectar y puerta en
`PLAN/notas/T163_potencia.md`, commit anterior a cualquier cifra. El paso 1 es la **puerta**: del
tramo de potencia se leen solo dispersión, asimetría, curtosis y dependencia serie —nunca la media
ni el Sharpe— y con ellas se contesta si el tramo de evaluación puede detectar `S_min`. Si no
puede, el script **no toca el tramo de evaluación** y no se gasta el intento de la familia de Holm.

Escribe `reports/t163_tsmom.json`; el informe en Markdown se redacta a partir de él. Va por la cola
(`eim.operation.jobs`). No abre red y no toca el almacén vivo: lee la copia estática del banco.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # el `eim` de este checkout

from statistics import NormalDist  # noqa: E402

import duckdb  # noqa: E402
import numpy as np  # noqa: E402

from eim.backtest import tsmom  # noqa: E402
from eim.backtest.params import CostParams  # noqa: E402
from eim.copytrading.stats import moments  # noqa: E402
from eim.core import Candle  # noqa: E402
from eim.data.store import Store  # noqa: E402
from eim.validation.lineage import ms_iso  # noqa: E402
from eim.validation.power import min_track_record, n_needed  # noqa: E402
from eim.validation.spa import block_length  # noqa: E402

SYMBOL = "BTCUSDT"
DAY_MS = tsmom.DAY_MS
HOUR_MS = 3_600_000
MIN_COV = 0.90                      # un día cuenta si tiene ≥ 90 % de sus 1 440 velas de 1 min
POWER_FROM = "2020-01-06"           # tramo de potencia (solo dispersión y dependencia)
POWER_TO = "2020-12-31"
EVAL_FROM = "2021-01-01"            # el único tramo que decide
SUB_FROM = "2024-01-01"             # subtramo que se informa por separado
S_MIN = 0.70                        # ventaja mínima a detectar: Sharpe neto anualizado
ALPHA, POWER = 0.05, 0.80
Z_SUM = 2.4865                      # z_0,05 + z_0,20, la constante de `power.n_needed`
_N = NormalDist()


def log(t0: float, msg: str) -> None:
    """Traza por consola; la salida de la cola no siempre es UTF-8, así que no revienta por eso."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    print(f"[{time.perf_counter() - t0:7.1f} s] {msg}", flush=True)


def day_of(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=UTC).timestamp() * 1000) // DAY_MS


def load(data: Path, t0: float) -> dict:
    """Días UTC válidos (OHLCV de 1 min agregado), velas de 1 h de ejecución y funding."""
    store = Store(data)
    con = duckdb.connect()
    src = store.sql_source("candles", SYMBOL, "1m", None, None)
    d = con.execute(
        f"SELECT t // {DAY_MS} AS day, count(*) AS n, first(o ORDER BY t) AS o, "
        f"last(c ORDER BY t) AS c FROM {src} GROUP BY 1 ORDER BY 1").fetchnumpy()
    log(t0, f"días de 1 min: {len(d['day'])}")
    src1h = store.sql_source("candles", SYMBOL, "1h", None, None)
    h = con.execute(f"SELECT t, o, h, l, c, v FROM {src1h} ORDER BY t").fetchnumpy()
    fund = np.asarray(store.read_series("funding", SYMBOL), float).reshape(-1, 2)
    log(t0, f"velas de 1 h: {len(h['t'])} · funding: {len(fund)}")
    return {"day": np.asarray(d["day"], np.int64), "n": np.asarray(d["n"], np.int64),
            "o": np.asarray(d["o"], float), "c": np.asarray(d["c"], float),
            "h1": {k: np.asarray(v, float) for k, v in h.items()}, "fund": fund}


def exec_bars(day: np.ndarray, h1: dict) -> list[Candle | None]:
    """Vela de 1 h de las 00:00 UTC de cada día (la de ejecución del rebalanceo)."""
    ht = h1["t"].astype(np.int64)
    want = day * DAY_MS
    j = np.searchsorted(ht, want)
    out: list[Candle | None] = []
    for k, w in zip(j, want, strict=True):
        if k < len(ht) and ht[k] == w:
            out.append(Candle(t=int(w), o=float(h1["o"][k]), h=float(h1["h"][k]),
                              l=float(h1["l"][k]), c=float(h1["c"][k]), v=float(h1["v"][k])))
        else:
            out.append(None)
    return out


def funding_prices(fund: np.ndarray, h1: dict) -> np.ndarray:
    """Precio en cada punto de funding: apertura de la vela de 1 h que lo contiene."""
    ht = h1["t"].astype(np.int64)
    if not len(fund):
        return np.zeros(0)
    j = np.clip(np.searchsorted(ht, fund[:, 0].astype(np.int64), side="right") - 1, 0, len(ht) - 1)
    return h1["o"][j]


def nw_kappa(r: np.ndarray, block: float) -> tuple[float, float, list[float], float]:
    """(κ con suelo 1, ventana B, autocorrelaciones, κ sin suelo) de Newey-West.

    κ es la inflación de la varianza de la media por dependencia serie. Se declara con suelo 1
    (nunca premia a la hipótesis), pero se informa también el valor sin suelo.
    """
    x = np.asarray(r, float)
    x = x[np.isfinite(x)] - np.mean(x[np.isfinite(x)])
    b = max(1, int(round(block)))
    n, g0 = len(x), float(np.dot(x, x) / len(x))
    rho = [float(np.dot(x[k:], x[:-k]) / len(x) / g0) for k in range(1, min(b, n - 1) + 1)]
    k = 1.0 + 2.0 * sum((1 - (i + 1) / (b + 1)) * p for i, p in enumerate(rho))
    return max(1.0, k), float(b), rho, k


def power_gate(ret: np.ndarray, n_eval: int, n_sub: int, n_max: int) -> dict:
    """La puerta: ¿alcanza la historia para detectar `S_MIN` con potencia 0,80?

    Del tramo de potencia se usan **solo** desviación, asimetría, curtosis y dependencia serie; la
    media y el Sharpe de ese tramo no se calculan ni se informan (pre-registro).
    """
    r = ret[np.isfinite(ret)]
    _, sd, skew, kurt = moments(list(r))
    block = block_length(r)
    kappa, b, rho, kappa_raw = nw_kappa(r, block)
    sr_day = S_MIN / math.sqrt(365.0)
    n_ap = kappa * n_needed(sr_day, 1.0, ALPHA, POWER)
    mintrl = kappa * min_track_record(sr_day, 0.0, skew, kurt, ALPHA)

    def mde(n: int) -> float:
        """Sharpe anualizado mínimo detectable con `n` días, α = 0,05 y potencia 0,80."""
        return Z_SUM * math.sqrt(kappa / n) * math.sqrt(365.0) if n > 0 else math.inf

    def threshold(n: int) -> float:
        """Sharpe anualizado que haría falta **observar** para que fuera significativo."""
        return _N.inv_cdf(1 - ALPHA) * math.sqrt(kappa / n) * math.sqrt(365.0)

    def achieved(n: int) -> float:
        """Potencia real para `S_MIN` con `n` días: P(observar por encima del umbral)."""
        return float(_N.cdf(sr_day * math.sqrt(n / kappa) - _N.inv_cdf(1 - ALPHA)))

    curve = {f"{s:.2f}": round(kappa * n_needed(s / math.sqrt(365.0), 1.0, ALPHA, POWER) / 365.0, 2)
             for s in (0.50, 0.70, 1.00, 1.41, 2.00, 2.41)}
    return {"power_tramo": {"from": POWER_FROM, "to": POWER_TO, "n": len(r),
                            "sd_daily": round(sd, 6), "vol_annual": round(sd * math.sqrt(365), 4),
                            "skew": round(skew, 4), "kurt": round(kurt, 4),
                            "politis_white_block": round(block, 3), "nw_window": b,
                            "kappa_raw": round(kappa_raw, 4),
                            "acf": [round(x, 4) for x in rho], "kappa": round(kappa, 4),
                            "mean_and_sharpe": "no calculados (pre-registro)"},
            "s_min": S_MIN, "alpha": ALPHA, "power": POWER,
            "n_apriori_days": round(n_ap, 1), "n_apriori_years": round(n_ap / 365.0, 2),
            "mintrl_days": round(mintrl, 1), "mintrl_years": round(mintrl / 365.0, 2),
            "n_eval_days": n_eval, "n_eval_years": round(n_eval / 365.0, 2),
            "mde_eval": round(mde(n_eval), 4), "n_sub_days": n_sub,
            "mde_sub": round(mde(n_sub), 4),
            "n_max_days": n_max, "n_max_years": round(n_max / 365.0, 2),
            "mde_max": round(mde(n_max), 4),
            "observable_threshold_eval": round(threshold(n_eval), 4),
            "observable_threshold_sub": round(threshold(n_sub), 4),
            "achieved_power_eval": round(achieved(n_eval), 4),
            "achieved_power_sub": round(achieved(n_sub), 4),
            "achieved_power_max": round(achieved(n_max), 4),
            "years_needed_by_sharpe": curve,
            "passes": bool(n_eval >= n_ap)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=Path("backups/t139_banco"))
    ap.add_argument("--out", type=Path, default=Path("reports/t163_tsmom.json"))
    a = ap.parse_args()
    t0 = time.perf_counter()

    raw = load(a.data, t0)
    ok = raw["n"] / 1440.0 >= MIN_COV
    day, o, c = raw["day"][ok], raw["o"][ok], raw["c"][ok]
    full = np.diff(day) == 1
    if not np.all(full):
        log(t0, f"aviso: {int((~full).sum())} saltos entre días válidos (huecos declarados)")
    p = tsmom.TsmomParams()
    ret_d = np.r_[np.nan, np.diff(np.log(c))]
    sig = tsmom.trend_signal(c, p.lookbacks)
    vol = tsmom.realized_vol(ret_d, p.vol_window, p.year_days)
    w = tsmom.target_weight(sig, vol, p)
    bars = exec_bars(day, raw["h1"])
    fp = funding_prices(raw["fund"], raw["h1"])

    d_pow, d_pow_end = day_of(POWER_FROM), day_of(POWER_TO)
    d_eval, d_sub = day_of(EVAL_FROM), day_of(SUB_FROM)
    i_pow = int(np.searchsorted(day, d_pow))
    j_pow = int(np.searchsorted(day, d_pow_end, side="right"))
    n_eval = int(np.sum(day >= d_eval))
    n_sub = int(np.sum(day >= d_sub))
    first_signal = int(np.flatnonzero(np.isfinite(w))[0])
    log(t0, f"días válidos {len(day)} · primer peso en {ms_iso(int(day[first_signal]) * DAY_MS)}"
            f" · potencia [{i_pow}, {j_pow}) · evaluación {n_eval} días")
    # El primer día del banco (2019-09-08) es parcial y no cuenta, así que el calentamiento acaba
    # un día después de lo escrito en la nota: el tramo de potencia arranca en el primer día con
    # peso del día anterior disponible. Un día de 361 y ninguna cifra depende de ello.
    i_pow = max(i_pow, first_signal + 1)
    if i_pow >= j_pow:
        raise RuntimeError("el calentamiento no cabe antes del tramo de potencia")

    out = tsmom.run_portfolio(day[:j_pow], o[:j_pow], c[:j_pow], w[:j_pow], bars[:j_pow],
                              raw["fund"], fp, p, CostParams(), start=i_pow)
    if out["ruined"]:
        raise RuntimeError("la cartera se arruinó en el tramo de potencia")
    n_max = len(day) - (first_signal + 1)            # toda la vida del instrumento con señal
    gate = power_gate(out["ret"], n_eval, n_sub, n_max)
    gate["power_tramo"]["first_day_real"] = ms_iso(int(day[i_pow]) * DAY_MS)
    log(t0, f"κ = {gate['power_tramo']['kappa']} · n a priori = {gate['n_apriori_days']} días"
            f" · n disponible = {n_eval} → {'PASA' if gate['passes'] else 'NO PASA'}")

    res = {"task": "T163", "generated_at": ms_iso(int(time.time() * 1000)),
           "prereg": "PLAN/notas/T163_potencia.md", "symbol": SYMBOL, "mode": "SIMULADO",
           "data": {"bank": str(a.data), "days_valid": len(day),
                    "first_day": ms_iso(int(day[0]) * DAY_MS),
                    "last_day": ms_iso(int(day[-1]) * DAY_MS),
                    "min_coverage": MIN_COV, "funding_points": len(raw["fund"])},
           "spec": {"lookbacks": list(p.lookbacks), "vol_window": p.vol_window,
                    "vol_target": p.vol_target, "max_leverage": p.max_leverage,
                    "rebalance": "lunes 00:00 UTC", "costs": "T25 CostParams() + funding 8 h"},
           "gate": gate,
           "verdict": ("PASA la puerta de potencia: se escribe el pre-registro y se mide"
                       if gate["passes"] else
                       "SIN POTENCIA: se cierra sin pre-registro y sin gastar el intento de Holm"),
           "holm_family_spent": bool(gate["passes"])}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    log(t0, f"escrito {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
