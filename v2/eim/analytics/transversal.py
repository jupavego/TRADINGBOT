"""T164: carry y momentum transversales sobre los perpetuos USDT, con el pre-registro congelado.

Todo sale de `PLAN/notas/T164_preregistro.md` (`transversal_v1`); aquí no se decide nada nuevo:
universo semanal (§1), señales y carteras (§2), unidad y prueba (§3) y la **puerta de potencia, que
se aplica antes de calcular ningún retorno** (§4). Si no pasa, la función devuelve sin haber tocado
un solo precio de salida.

Funciones puras sobre tablas de pandas (fila = día UTC, columna = símbolo); la lectura del almacén de
T181 está en `load`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

DAY = pd.Timedelta(days=1)
STABLE = {"USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USDP", "EUR", "GBP", "AEUR"}
MIN_AGE_D, MIN_BARS, WIN = 60, 28, 30
MIN_QVOL, MIN_N = 5_000_000.0, 30
COST_SIDE = 0.0010                    # 5 pb de comisión + 5 pb de deslizamiento por lado
CARRY_D, MOM_D, VOL_WARM = 7, 14, 26  # días de funding, días de momentum, semanas de escala
T_NEEDED_Y, Z = 5.1, 1.645            # §4: combinada, m = 1, ρ = 0,3
NW_LAGS = 4


@dataclass(frozen=True)
class Panel:
    close: pd.DataFrame       # cierre diario (índice = día de apertura de la vela, UTC)
    qvol: pd.DataFrame        # volumen en USDT ≈ volumen × cierre
    funding: pd.DataFrame     # suma diaria del funding liquidado ese día
    onboard: pd.Series        # alta de cada símbolo (Timestamp)
    base: pd.Series           # moneda base


def mondays(p: Panel) -> list[pd.Timestamp]:
    first, last = p.close.index.min() + MIN_AGE_D * DAY, p.close.index.max() - 7 * DAY
    d = first + pd.Timedelta(days=(7 - first.weekday()) % 7)
    return list(pd.date_range(d, last, freq="7D"))


def eligible(p: Panel, t: pd.Timestamp) -> list[str]:
    """§1: con alta ≥ 60 días, ≥ 28 de las 30 velas previas, mediana de volumen ≥ 5 M y no estable."""
    win = slice(t - WIN * DAY, t - DAY)
    bars = p.close.loc[win].notna().sum()
    vol = p.qvol.loc[win].median()
    ok = (p.onboard <= t - MIN_AGE_D * DAY) & (bars >= MIN_BARS) & (vol >= MIN_QVOL) \
        & ~p.base.isin(STABLE)
    return sorted(ok[ok].index)


def available_years(p: Panel) -> dict:
    """§4, sin retornos: semanas con ≥ 30 elegibles, menos el calentamiento de la escala."""
    weeks = [t for t in mondays(p) if len(eligible(p, t)) >= MIN_N]
    years = max(0, len(weeks) - VOL_WARM) / 52.18
    return {"weeks": len(weeks), "first": str(weeks[0].date()) if weeks else None,
            "years": round(years, 2), "needed_years": T_NEEDED_Y, "passes": years >= T_NEEDED_Y}


def _vol30(p: Panel, t: pd.Timestamp, syms: list[str]) -> pd.Series:
    r = np.log(p.close.loc[t - (WIN + 1) * DAY:t - DAY, syms]).diff()
    return r.std()


def legs(p: Panel, t: pd.Timestamp, syms: list[str]) -> dict[str, dict[str, pd.Series]]:
    """§2: pesos de las dos carteras en `t` (largo y corto, cada pata suma 1), con datos ≤ t."""
    vol = _vol30(p, t, syms).replace(0, np.nan).dropna()
    syms = list(vol.index)
    fund = p.funding.loc[t - CARRY_D * DAY:t - DAY, syms].sum() / (CARRY_D * 3)
    carry = (fund / vol).dropna()
    c0, c1 = p.close.loc[t - (MOM_D + 1) * DAY, syms], p.close.loc[t - DAY, syms]
    mom = (c1 / c0 - 1).dropna()
    out = {}
    for name, score, long_low in (("carry", carry, True), ("momentum", mom, False)):
        k = len(score) // 5
        if k < 1:
            continue
        s = score.sort_values()
        lo, hi = list(s.index[:k]), list(s.index[-k:])
        long_, short = (lo, hi) if long_low else (hi, lo)
        out[name] = {"long": _inv(vol[long_]), "short": _inv(vol[short])}
    return out


def _inv(v: pd.Series) -> pd.Series:
    w = 1.0 / v
    return w / w.sum()


def week_return(p: Panel, t: pd.Timestamp, w: dict[str, pd.Series],
                prev: dict[str, pd.Series] | None) -> float:
    """§2: retorno neto de la semana [t, t + 7 d) sobre el capital de las dos patas (2)."""
    out, cost = 0.0, 0.0
    for side, sign in (("long", 1.0), ("short", -1.0)):
        ws = w[side]
        c0 = p.close.loc[t - DAY, ws.index]
        c1 = p.close.loc[t:t + 6 * DAY, ws.index].ffill().iloc[-1]     # retirado: último cierre
        ret = (c1 / c0 - 1).fillna(0.0)
        f = p.funding.loc[t:t + 6 * DAY, ws.index].sum()
        out += sign * float((ws * ret).sum()) - sign * float((ws * f).sum())
        old = (prev or {}).get(side, pd.Series(dtype=float))
        turn = ws.subtract(old, fill_value=0.0).abs().sum()
        cost += COST_SIDE * float(turn)
    return (out - cost) / 2.0


def newey_west_t(x: np.ndarray, lags: int = NW_LAGS) -> tuple[float, float]:
    """(t de la media, error típico) con la ventana de Bartlett."""
    x = np.asarray(x, dtype=float)
    n, m = len(x), x.mean()
    e = x - m
    s = e @ e / n
    for k in range(1, lags + 1):
        s += 2 * (1 - k / (lags + 1)) * (e[k:] @ e[:-k]) / n
    se = math.sqrt(s / n) if s > 0 else float("nan")
    return (m / se if se else float("nan")), se


def run(p: Panel, btc: pd.Series | None = None) -> dict:
    """La medición entera. Con la puerta cerrada, no calcula ningún retorno."""
    gate = available_years(p)
    if not gate["passes"]:
        return {"gate": gate, "verdict": "SIN POTENCIA", "measured": False}
    rows, prev = [], {"carry": None, "momentum": None}
    for t in mondays(p):
        syms = eligible(p, t)
        if len(syms) < MIN_N:
            continue
        lg = legs(p, t, syms)
        if set(lg) != {"carry", "momentum"}:
            continue
        r = {k: week_return(p, t, lg[k], prev[k]) for k in lg}
        prev = lg
        rows.append({"t": t, "n": len(syms), **r})
    df = pd.DataFrame(rows).set_index("t")
    scale = df[["carry", "momentum"]].rolling(VOL_WARM, min_periods=VOL_WARM // 2).std().shift(1)
    comb = (0.5 * df["carry"] / scale["carry"] + 0.5 * df["momentum"] / scale["momentum"]).dropna()
    t_nw, _ = newey_west_t(comb.values)
    p_one = 0.5 * math.erfc(t_nw / math.sqrt(2))
    series = (("carry", df["carry"]), ("momentum", df["momentum"]), ("combinada", comb))
    stats = {name: {"mean_weekly": float(s.mean()), "weeks": int(len(s)),
                    "sharpe": float(s.mean() / s.std() * math.sqrt(52))} for name, s in series}
    # §3: la beta se mide en retorno (carry y momentum). La combinada está en unidades de
    # volatilidad, así que de ella solo se informa la correlación con BTC (una beta mezclaría
    # unidades: la primera corrida del 2026-11-18 dio +0,754 por eso).
    beta, corr, bw = {}, None, btc if btc is not None else btc_weekly(p)
    if bw is not None:
        for name, ser in (("carry", df["carry"]), ("momentum", df["momentum"])):
            j = ser.to_frame("c").join(bw.rename("b"), how="inner").dropna()
            if len(j) > 10:
                beta[name] = float(np.cov(j["c"], j["b"])[0, 1] / np.var(j["b"], ddof=1))
        j = comb.to_frame("c").join(bw.rename("b"), how="inner").dropna()
        corr = float(j["c"].corr(j["b"])) if len(j) > 10 else None
    rho = float(df["carry"].corr(df["momentum"]))
    return {"gate": gate, "measured": True, "t_nw": float(t_nw), "p_one_sided": p_one,
            "verdict": "PASA" if t_nw > Z else "NO PASA", "beta_btc": beta, "corr_btc": corr,
            "rho_cm": rho,
            "stats": stats, "weeks": int(len(comb)),
            "first": str(comb.index[0].date()), "last": str(comb.index[-1].date())}


def btc_weekly(p: Panel, sym: str = "BTCUSDT") -> pd.Series | None:
    """Retorno de BTC en las mismas semanas [t, t + 7 d), para la beta (§3)."""
    if sym not in p.close:
        return None
    c = p.close[sym]
    out = {t: c.loc[t:t + 6 * DAY].ffill().iloc[-1] / c.loc[t - DAY] - 1
           for t in mondays(p) if t - DAY in c.index and pd.notna(c.loc[t - DAY])}
    return pd.Series(out, dtype=float)


def load(root) -> tuple[Panel, dict]:
    """El almacén de T181 como tablas diarias, y su `universe.json` (cobertura de retirados)."""
    import json
    from pathlib import Path

    from eim.data.store import Store

    root = Path(root)
    uni = json.loads((root / "universe.json").read_text(encoding="utf-8"))
    st = Store(root)
    close, qvol, fund, onboard, base = {}, {}, {}, {}, {}
    for u in uni["symbols"]:
        s = u["symbol"]
        cs = st.read_candles(s, "1d")
        if not cs:
            continue
        idx = pd.to_datetime([c.t for c in cs], unit="ms")
        close[s] = pd.Series([c.c for c in cs], index=idx)
        qvol[s] = pd.Series([c.v * c.c for c in cs], index=idx)
        f = st.read_series("funding", s)
        if f:
            fs = pd.Series([x for _, x in f], index=pd.to_datetime([t for t, _ in f], unit="ms"))
            fund[s] = fs.groupby(fs.index.floor("D")).sum()
        onboard[s] = pd.to_datetime(u.get("onboard_t") or cs[0].t, unit="ms")
        base[s] = u.get("base") or s[:-4]
    days = pd.date_range(min(v.index.min() for v in close.values()),
                         max(v.index.max() for v in close.values()), freq="D")
    frame = lambda d: pd.DataFrame(d).reindex(days)  # noqa: E731
    return Panel(frame(close), frame(qvol), frame(fund).fillna(0.0), pd.Series(onboard),
                 pd.Series(base)), uni
