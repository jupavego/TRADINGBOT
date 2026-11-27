"""Canal de apertura (soporte/resistencia de los 3 primeros minutos) con ordenes limite.

Canal: alto y bajo de las k=3 velas desde la apertura. W = alto - bajo, medio = (alto+bajo)/2.
Niveles de entrada: soporte = bajo + f*W, resistencia = alto - f*W  (f=0 en el extremo,
f>0 metido hacia dentro: se llena mas facil pero a peor precio).

Estrategia A - REVERSION EN EL CANAL (lo que pide el patron: hacer lo contrario):
  limite de compra en el soporte, limite de venta en la resistencia; se toma la PRIMERA
  que el precio toque dentro de `ventana` minutos; si las dos en el mismo minuto, se
  descarta (ambigua). Objetivo = medio o extremo opuesto; stop = s*W mas alla; tope 4 h.

Estrategia B - RUPTURA: entrada al romper el extremo, objetivo W, stop en el medio, tope 4 h.

Costes: entrada limite = maker; salida = taker. Binance futuros: maker 1,8 bps, taker 4,5 bps.
Supuestos conservadores: el limite exige que el precio ATRAVIESE el nivel; si en un mismo
minuto se tocan objetivo y stop, se cuenta el stop. Las cifras salen de velas reales.
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
    "nueva_york": ("America/New_York", 9, 30),
    "cme": ("America/Chicago", 17, 0),
}
TOPE = 240
MAKER, TAKER = 1.8, 4.5


def cargar(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=["t", "o", "h", "l", "c"]).drop_duplicates("t")
    df = df.sort_values("t").reset_index(drop=True)
    df.index = pd.to_datetime(df["t"], unit="ms", utc=True)
    return df.reindex(pd.date_range(df.index[0], df.index[-1], freq="1min", tz="UTC"))


def aperturas(idx: pd.DatetimeIndex, tz: str, hh: int, mm: int) -> np.ndarray:
    loc = idx.tz_convert(ZoneInfo(tz))
    return np.flatnonzero((loc.hour == hh) & (loc.minute == mm) & (loc.dayofweek < 5))


def _salida(ah, ab, cc, lado, ent, obj, stop):
    """Primer toque entre objetivo y stop; empate en el mismo minuto -> stop."""
    if lado > 0:
        t_obj, t_stop = ah >= obj, ab <= stop
    else:
        t_obj, t_stop = ab <= obj, ah >= stop
    io = int(np.argmax(t_obj)) if t_obj.any() else 10**9
    ist = int(np.argmax(t_stop)) if t_stop.any() else 10**9
    if min(io, ist) == 10**9:
        return cc[-1], len(cc), "tope"
    if ist <= io:
        return stop, ist + 1, "stop"
    return obj, io + 1, "objetivo"


def reversion(g, pos, k, f, s, ventana, objetivo, costo):
    o, c, ah, ab = (g[x].to_numpy() for x in ("o", "c", "h", "l"))
    filas = []
    ambiguas = 0
    for p in pos:
        if p + k + ventana + TOPE >= len(g):
            continue
        alto, bajo = np.nanmax(ah[p:p + k]), np.nanmin(ab[p:p + k])
        if not np.isfinite(alto) or not np.isfinite(bajo) or alto <= bajo:
            continue
        W = alto - bajo
        medio = 0.5 * (alto + bajo)
        sop, res = bajo + f * W, alto - f * W
        fill = None
        for i in range(p + k, p + k + ventana):
            baja, sube = ab[i] < sop, ah[i] > res
            if baja and sube:
                ambiguas += 1
                break
            if baja:
                fill = (i, +1, sop)
                break
            if sube:
                fill = (i, -1, res)
                break
        if fill is None:
            filas.append({"ts": g.index[p], "W_bps": 1e4 * W / medio, "lleno": False})
            continue
        i, lado, ent = fill
        obj = medio if objetivo == "medio" else (res if lado > 0 else sop)
        stop = ent - lado * s * W
        j, f_ = i + 1, i + 1 + TOPE
        sal, dur, motivo = _salida(ah[j:f_], ab[j:f_], c[j:f_], lado, ent, obj, stop)
        filas.append({"ts": g.index[p], "W_bps": 1e4 * W / medio, "lleno": True, "lado": lado,
                      "espera_min": i - (p + k) + 1, "dur_min": dur, "motivo": motivo,
                      "bruto_bps": 1e4 * lado * (sal / ent - 1.0),
                      "neto_bps": 1e4 * lado * (sal / ent - 1.0) - costo})
    return pd.DataFrame(filas), ambiguas


def ruptura(g, pos, k, ventana, costo):
    o, c, ah, ab = (g[x].to_numpy() for x in ("o", "c", "h", "l"))
    filas = []
    for p in pos:
        if p + k + ventana + TOPE >= len(g):
            continue
        alto, bajo = np.nanmax(ah[p:p + k]), np.nanmin(ab[p:p + k])
        if not np.isfinite(alto) or not np.isfinite(bajo) or alto <= bajo:
            continue
        W = alto - bajo
        medio = 0.5 * (alto + bajo)
        fill = None
        for i in range(p + k, p + k + ventana):
            if ah[i] > alto and ab[i] < bajo:
                break
            if ah[i] > alto:
                fill = (i, +1, alto)
                break
            if ab[i] < bajo:
                fill = (i, -1, bajo)
                break
        if fill is None:
            filas.append({"ts": g.index[p], "W_bps": 1e4 * W / medio, "lleno": False})
            continue
        i, lado, ent = fill
        obj, stop = ent + lado * W, medio
        j, f_ = i + 1, i + 1 + TOPE
        sal, dur, motivo = _salida(ah[j:f_], ab[j:f_], c[j:f_], lado, ent, obj, stop)
        filas.append({"ts": g.index[p], "W_bps": 1e4 * W / medio, "lleno": True, "lado": lado,
                      "espera_min": i - (p + k) + 1, "dur_min": dur, "motivo": motivo,
                      "bruto_bps": 1e4 * lado * (sal / ent - 1.0),
                      "neto_bps": 1e4 * lado * (sal / ent - 1.0) - costo})
    return pd.DataFrame(filas), 0


def linea(nombre: str, d: pd.DataFrame, amb: int) -> None:
    n = len(d)
    llenas = d[d.get("lleno", False) == True] if n else d  # noqa: E712
    if n == 0 or len(llenas) < 5:
        print(f"{nombre:34s} n={n:4d} llenado={100 * len(llenas) / max(n, 1):5.1f}%  sin muestra")
        return
    r = llenas["neto_bps"].to_numpy()
    br = llenas["bruto_bps"].to_numpy()
    sd = r.std(ddof=1)
    eq = np.cumsum(r)
    dd = float((np.maximum.accumulate(eq) - eq).max())
    mot = llenas["motivo"].value_counts(normalize=True) * 100
    print(f"{nombre:34s} n={n:4d} llenado={100 * len(llenas) / n:5.1f}% "
          f"W={llenas['W_bps'].mean():5.1f}bps  acierto={100 * (r > 0).mean():5.1f}% "
          f"bruto={br.mean():+6.2f} neto={r.mean():+6.2f} "
          f"t={r.mean() / (sd / math.sqrt(len(r))):+6.2f} "
          f"total={eq[-1] / 100:+7.2f}% caida={dd / 100:6.2f}% "
          f"dur={llenas['dur_min'].mean():5.1f}min obj/stop/tope="
          f"{mot.get('objetivo', 0):.0f}/{mot.get('stop', 0):.0f}/{mot.get('tope', 0):.0f}"
          + (f" amb={amb}" if amb else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--ventana", type=int, default=30, help="minutos para que se llene el limite")
    a = ap.parse_args()
    g = cargar(a.path)
    costo = MAKER + TAKER
    print(f"COBERTURA {g.index[0]:%Y-%m-%d} -> {g.index[-1]:%Y-%m-%d %H:%M} UTC, "
          f"{len(g)} min, {100 * g['c'].notna().mean():.3f}% con vela")
    print(f"canal = alto/bajo de los {a.k} primeros minutos | ventana de llenado {a.ventana} min | "
          f"tope {TOPE} min | coste maker+taker = {costo:.1f} bps\n")

    for z, ses in ZONAS.items():
        pos = aperturas(g.index, *ses)
        print(f"=== {z} ({ses[1]:02d}:{ses[2]:02d} {ses[0]}) ===")
        for f in (0.0, 0.15, 0.30):
            for s in (0.5, 1.0):
                for obj in ("medio", "opuesto"):
                    d, amb = reversion(g, pos, a.k, f, s, a.ventana, obj, costo)
                    linea(f"rev f={f:.2f} stop={s}W obj={obj:7s}", d, amb)
        d, amb = ruptura(g, pos, a.k, a.ventana, costo)
        linea("ruptura obj=W stop=medio", d, amb)
        print()


if __name__ == "__main__":
    main()
