"""Backtest del "patron de apertura" en BTCUSDT 1m, por zona horaria, 2024-2026.

Regla evaluada (la del usuario): los k=3 primeros minutos desde la apertura marcan el
tramo A; se entra EN CONTRA de A en la apertura del minuto k+1 y se cierra por:
  - tiempo fijo (h minutos), o
  - objetivo/stop simetricos de tamano |A| con tope de 4 h (si en un mismo minuto se tocan
    los dos, se asume que salto el stop: criterio conservador).
Costes: taker ida y vuelta en bps (por defecto 9 = 0,045% x 2 de Binance futuros).
Todas las cifras salen de velas reales descargadas; la cobertura se informa.
"""
from __future__ import annotations

import argparse
import math
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ZONAS = {
    "tokio": ("Asia/Tokyo", 9, 0),
    "hong_kong": ("Asia/Hong_Kong", 9, 30),
    "londres": ("Europe/London", 8, 0),
    "francfort": ("Europe/Berlin", 9, 0),
    "nueva_york": ("America/New_York", 9, 30),
    "cme": ("America/Chicago", 17, 0),
}
TOPE = 240  # minutos (4 h)
SALIDAS = (3, 6, 15, 30, 60, 120, 240)


def cargar(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=["t", "o", "h", "l", "c", "v"]).drop_duplicates("t")
    df = df.sort_values("t").reset_index(drop=True)
    df.index = pd.to_datetime(df["t"], unit="ms", utc=True)
    full = pd.date_range(df.index[0], df.index[-1], freq="1min", tz="UTC")
    return df.reindex(full)


def aperturas(idx: pd.DatetimeIndex, tz: str, hh: int, mm: int) -> np.ndarray:
    loc = idx.tz_convert(ZoneInfo(tz))
    sel = (loc.hour == hh) & (loc.minute == mm) & (loc.dayofweek < 5)
    return np.flatnonzero(sel)


def perfil(g: pd.DataFrame, pos: np.ndarray, k: int, desde: int = -5, hasta: int = 30):
    o = g["o"].to_numpy()
    c = g["c"].to_numpy()
    pos = pos[(pos + desde >= 0) & (pos + hasta < len(g))]
    a = c[pos + k - 1] / o[pos] - 1.0
    sa = np.sign(a)
    ok = np.isfinite(a) & (sa != 0)
    pos, sa = pos[ok], sa[ok]
    filas = []
    for d in range(desde, hasta + 1):
        r = c[pos + d] / o[pos + d] - 1.0
        m = np.isfinite(r)
        filas.append({
            "min": d,
            "n": int(m.sum()),
            "ret_bps": 1e4 * r[m].mean(),
            "abs_bps": 1e4 * np.abs(r[m]).mean(),
            "a_favor_bps": 1e4 * (sa[m] * r[m]).mean(),  # >0 continua, <0 revierte
        })
    return pd.DataFrame(filas)


def operaciones(g: pd.DataFrame, pos: np.ndarray, k: int, costo: float) -> pd.DataFrame:
    """Una fila por apertura: tramo A, lado contrario y salidas (tiempo fijo y objetivo/stop)."""
    o = g["o"].to_numpy()
    c = g["c"].to_numpy()
    altos = g["h"].to_numpy()
    bajos = g["l"].to_numpy()
    pos = pos[pos + k + TOPE < len(g)]
    a = c[pos + k - 1] / o[pos] - 1.0
    ent = o[pos + k]
    ok = np.isfinite(a) & (a != 0) & np.isfinite(ent)
    pos, a, ent = pos[ok], a[ok], ent[ok]
    lado = -np.sign(a)
    filas = {"ts": g.index[pos], "a_bps": 1e4 * a, "lado": lado, "entrada": ent}
    for h in SALIDAS:
        filas[f"t{h}"] = 1e4 * (lado * (c[pos + k - 1 + h] / ent - 1.0)) - costo

    dist = np.abs(a) * ent
    obj = ent + lado * dist
    stop = ent - lado * dist
    res = np.full(len(pos), np.nan)
    mins = np.full(len(pos), TOPE, dtype=int)
    for j in range(len(pos)):
        s, e = pos[j] + k, pos[j] + k + TOPE
        ah, ab = altos[s:e], bajos[s:e]
        if lado[j] > 0:
            toco_obj, toco_stop = ah >= obj[j], ab <= stop[j]
        else:
            toco_obj, toco_stop = ab <= obj[j], ah >= stop[j]
        io = int(np.argmax(toco_obj)) if toco_obj.any() else 10**9
        istop = int(np.argmax(toco_stop)) if toco_stop.any() else 10**9
        if min(io, istop) == 10**9:
            res[j] = 1e4 * (lado[j] * (c[e - 1] / ent[j] - 1.0))
        elif istop <= io:  # empate en el mismo minuto -> stop (conservador)
            res[j] = -1e4 * abs(a[j])
            mins[j] = istop + 1
        else:
            res[j] = 1e4 * abs(a[j])
            mins[j] = io + 1
    filas["objstop"] = res - costo
    filas["minutos"] = mins
    return pd.DataFrame(filas)


def resumen(r: np.ndarray) -> dict:
    r = r[np.isfinite(r)]
    n = r.size
    if n < 5:
        return {"n": n}
    sd = r.std(ddof=1)
    eq = np.cumsum(r)
    dd = float((np.maximum.accumulate(eq) - eq).max())
    gan, per = r[r > 0].sum(), -r[r < 0].sum()
    return {"n": n, "aciertos_pct": 100.0 * (r > 0).mean(), "media_bps": float(r.mean()),
            "mediana_bps": float(np.median(r)), "total_pct": float(eq[-1]) / 100.0,
            "t": float(r.mean() / (sd / math.sqrt(n))) if sd else 0.0,
            "pf": float(gan / per) if per else float("inf"), "dd_pct": dd / 100.0}


def tabla(d: dict[str, np.ndarray], titulo: str) -> None:
    print(f"\n{titulo}")
    print(f"{'salida':>10} {'n':>5} {'acierto':>8} {'media':>8} {'mediana':>8} "
          f"{'total':>9} {'t':>6} {'PF':>5} {'peor caida':>11}")
    for nombre, r in d.items():
        s = resumen(r)
        if s["n"] < 5:
            print(f"{nombre:>10} {s['n']:>5} insuficiente")
            continue
        print(f"{nombre:>10} {s['n']:>5} {s['aciertos_pct']:7.1f}% {s['media_bps']:+7.2f} "
              f"{s['mediana_bps']:+7.2f} {s['total_pct']:+8.2f}% {s['t']:+6.2f} {s['pf']:5.2f} "
              f"{s['dd_pct']:10.2f}%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--costo-bps", type=float, default=9.0)
    ap.add_argument("--csv", default="operaciones_apertura.csv")
    a = ap.parse_args()
    g = cargar(a.path)
    print(f"COBERTURA {g.index[0]:%Y-%m-%d %H:%M} -> {g.index[-1]:%Y-%m-%d %H:%M} UTC | "
          f"{len(g)} minutos de rejilla, {100 * g['c'].notna().mean():.3f}% con vela | "
          f"coste ida y vuelta {a.costo_bps} bps | tope {TOPE} min | k={a.k}")

    print("\n" + "=" * 104)
    print("1) APERTURAS: a que hora UTC caen (el horario de verano las mueve)")
    for z, (tz, hh, mm) in ZONAS.items():
        pos = aperturas(g.index, tz, hh, mm)
        u = pd.Series(g.index[pos].strftime("%H:%M")).value_counts()
        print(f"{z:11s} {hh:02d}:{mm:02d} {tz:17s} -> "
              + ", ".join(f"{h} UTC x{n}" for h, n in u.items()) + f"  (n={len(pos)})")

    print("\n" + "=" * 104)
    print("2) COMO SE COMPORTA EL PRECIO alrededor de cada apertura")
    print("   a_favor = retorno del minuto en el sentido del tramo A (+ continua, - revierte)")
    for z, (tz, hh, mm) in ZONAS.items():
        p = perfil(g, aperturas(g.index, tz, hh, mm), a.k)
        base = p.loc[p["min"].between(15, 30), "abs_bps"].mean()
        pre = p.loc[p["min"].between(-5, -1), "abs_bps"].mean()
        tres = p.loc[p["min"].between(a.k, a.k + 2), "a_favor_bps"].sum()
        print(f"\n{z:11s} |ret| 5 min antes={pre:5.2f} | apertura(min 0)="
              f"{p.loc[p['min'] == 0, 'abs_bps'].iloc[0]:5.2f} | min 15-30={base:5.2f} bps")
        print(f"            a_favor acumulado en los 3 min siguientes = {tres:+.2f} bps")
        print("            " + "  ".join(
            f"{int(r['min']):+d}:{r['a_favor_bps']:+.2f}"
            for _, r in p[p["min"].between(-1, 8)].iterrows()))

    print("\n" + "=" * 104)
    print("3) OPERACIONES SIGUIENDO EL PATRON (en contra del tramo A), netas de coste")
    todo = {}
    for z, (tz, hh, mm) in ZONAS.items():
        ops = operaciones(g, aperturas(g.index, tz, hh, mm), a.k, a.costo_bps)
        todo[z] = ops
        cols = {f"{h} min": ops[f"t{h}"].to_numpy() for h in SALIDAS}
        cols["objstop"] = ops["objstop"].to_numpy()
        tabla(cols, f"--- {z} (apertura {hh:02d}:{mm:02d} local, n={len(ops)}) ---")
        print(f"            objstop: duracion media {ops['minutos'].mean():.0f} min, "
              f"{100 * (ops['minutos'] >= TOPE).mean():.0f}% llega al tope de 4 h; "
              f"|A| medio {ops['a_bps'].abs().mean():.1f} bps")

    print("\n" + "=" * 104)
    print("4) TODAS LAS ZONAS JUNTAS y por ano")
    allops = pd.concat([v.assign(zona=z) for z, v in todo.items()])
    tabla({"3 min": allops["t3"].to_numpy(), "6 min": allops["t6"].to_numpy(),
           "30 min": allops["t30"].to_numpy(), "240 min": allops["t240"].to_numpy(),
           "objstop": allops["objstop"].to_numpy()}, "--- conjunto ---")
    for ano, sub in allops.groupby(allops["ts"].dt.year):
        s3, so = resumen(sub["t3"].to_numpy()), resumen(sub["objstop"].to_numpy())
        print(f"  {ano}: n={so['n']:4d}  3 min: media={s3['media_bps']:+6.2f} bps "
              f"total={s3['total_pct']:+7.2f}% | objstop: acierto={so['aciertos_pct']:4.1f}% "
              f"media={so['media_bps']:+6.2f} bps total={so['total_pct']:+7.2f}%")

    print("\n5) CONTROL: la misma regla en 2000 minutos al azar (no aperturas)")
    rng = np.random.default_rng(7)
    pos = rng.choice(np.arange(10, len(g) - TOPE - 10), 2000, replace=False)
    ops = operaciones(g, pos, a.k, a.costo_bps)
    tabla({"3 min": ops["t3"].to_numpy(), "6 min": ops["t6"].to_numpy(),
           "30 min": ops["t30"].to_numpy(), "objstop": ops["objstop"].to_numpy()},
          "--- al azar ---")

    allops.to_csv(a.csv, index=False)
    print(f"\noperaciones guardadas en {a.csv}")


if __name__ == "__main__":
    main()
