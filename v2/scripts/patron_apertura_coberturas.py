"""Patron de apertura + 2 coberturas a 60x: recorridos, liquidacion y resultado medido.

Montaje evaluado (el que pide el usuario):
  - principal: 1 unidad EN CONTRA del tramo A (los 3 primeros minutos de la apertura);
  - cobertura A: 1 unidad larga;  cobertura B: 1 unidad corta  (las dos al mismo precio);
  - toma de ganancias de cada pata a +TP dolares de recorrido a favor (200 a 300);
  - tope de 4 h; apalancamiento 60x; margen aislado por pata.

Variantes de que hacer con la pata perdedora de la cobertura:
  H1 cierre simultaneo  : cuando la ganadora toca su TP, se cierra la perdedora a mercado.
  H2 cortar antes       : la perdedora se cierra sola al llegar a -STOP dolares.
  H3 dejarla correr     : la perdedora se mantiene hasta el tope de 4 h o hasta liquidarse.

A 60x, con margen M por pata: 1 dolar de BTC = 60/p0 de M. El coste taker de ida y vuelta
(9 bps de nocional) se come 5,4 % del margen POR PATA. La liquidacion llega con un recorrido en
contra de (1/60 - mmr) del precio; con mmr = 0,5 % son ~1,167 %.
Todo sale de velas de 1m reales; los recorridos se miden con maximos y minimos, y cuando en un
mismo minuto se puede tocar TP y liquidacion se cuenta la liquidacion (criterio conservador).
"""
from __future__ import annotations

import argparse
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
K = 3
APAL = 60.0
MMR = 0.005
TAKER = 0.00045


def cargar(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=["t", "o", "h", "l", "c"]).drop_duplicates("t")
    df = df.sort_values("t").reset_index(drop=True)
    df.index = pd.to_datetime(df["t"], unit="ms", utc=True)
    return df.reindex(pd.date_range(df.index[0], df.index[-1], freq="1min", tz="UTC"))


def aperturas(idx: pd.DatetimeIndex, tz: str, hh: int, mm: int) -> np.ndarray:
    loc = idx.tz_convert(ZoneInfo(tz))
    return np.flatnonzero((loc.hour == hh) & (loc.minute == mm) & (loc.dayofweek < 5))


def _primer(cond: np.ndarray) -> int:
    return int(np.argmax(cond)) if cond.any() else 10**9


def una(ah, ab, cc, ent, lado, tp, stop, liq) -> tuple[float, int, str]:
    """Resultado de una pata en DOLARES de recorrido, su duracion y por que salio."""
    if lado > 0:
        i_tp, i_st = _primer(ah >= ent + tp), _primer(ab <= ent - stop)
        i_lq = _primer(ab <= ent - liq)
    else:
        i_tp, i_st = _primer(ab <= ent - tp), _primer(ah >= ent + stop)
        i_lq = _primer(ah >= ent + liq)
    primero = min(i_tp, i_st, i_lq)
    if primero == 10**9:
        return lado * (cc[-1] - ent), len(cc), "tope"
    if i_lq <= min(i_tp, i_st):
        return -liq, i_lq + 1, "liquidada"
    if i_st <= i_tp:
        return -stop, i_st + 1, "stop"
    return tp, i_tp + 1, "tp"


def evaluar(g: pd.DataFrame, pos: np.ndarray, tp: float, stop: float) -> pd.DataFrame:
    o, c, ah, ab = (g[x].to_numpy() for x in ("o", "c", "h", "l"))
    filas = []
    for p in pos:
        if p + K + TOPE >= len(g):
            continue
        a = c[p + K - 1] / o[p] - 1.0
        ent = o[p + K]
        if not np.isfinite(a) or a == 0 or not np.isfinite(ent):
            continue
        s, e = p + K, p + K + TOPE
        AH, AB, CC = ah[s:e], ab[s:e], c[s:e]
        liq = ent * (1.0 / APAL - MMR)
        sube, baja = np.nanmax(AH) - ent, ent - np.nanmin(AB)
        i_up, i_dn = _primer(AH >= ent + tp), _primer(AB <= ent - tp)
        # patas
        pr = una(AH, AB, CC, ent, -np.sign(a), tp, liq, liq)          # principal (stop=liq)
        lg = una(AH, AB, CC, ent, +1, tp, liq, liq)                   # cobertura larga
        ct = una(AH, AB, CC, ent, -1, tp, liq, liq)                   # cobertura corta
        # H1: la ganadora marca el momento; la perdedora se cierra a mercado entonces
        gan = min(i_up, i_dn)
        if gan == 10**9:
            h1 = (CC[-1] - ent) + (ent - CC[-1])   # ninguna toco: suma 0 por construccion
            h1_dur, h1_motivo = TOPE, "tope"
        else:
            h1, h1_dur, h1_motivo = 0.0, gan + 1, "tp+cierre"
        # H2: la perdedora se corta sola a -stop
        lg2 = una(AH, AB, CC, ent, +1, tp, stop, liq)
        ct2 = una(AH, AB, CC, ent, -1, tp, stop, liq)
        filas.append({
            "ts": g.index[p], "ent": ent, "liq_usd": liq,
            "sube_usd": sube, "baja_usd": baja, "recorrido_max": max(sube, baja),
            "toco_arriba": i_up < 10**9, "toco_abajo": i_dn < 10**9,
            "ambos": (i_up < 10**9) and (i_dn < 10**9),
            "min_hasta_tp": (min(i_up, i_dn) + 1) if gan < 10**9 else np.nan,
            "principal_usd": pr[0], "principal_motivo": pr[2],
            "h1_usd": h1, "h1_dur": h1_dur, "h1_motivo": h1_motivo,
            "h2_usd": lg2[0] + ct2[0], "h2_liq": (lg2[2] == "liquidada") or (ct2[2] == "liquidada"),
            "h3_usd": lg[0] + ct[0], "h3_liq": (lg[2] == "liquidada") or (ct[2] == "liquidada"),
        })
    return pd.DataFrame(filas)


def pct_margen(usd: np.ndarray, ent: np.ndarray, patas: int) -> np.ndarray:
    """Dolares de recorrido -> % del margen total, con el coste taker de cada pata."""
    return 100.0 * (APAL * usd / ent - patas * 2 * TAKER * APAL) / patas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--tp", type=float, nargs="+", default=[200.0, 250.0, 300.0])
    ap.add_argument("--stop", type=float, default=100.0)
    a = ap.parse_args()
    g = cargar(a.path)
    print(f"COBERTURA {g.index[0]:%Y-%m-%d} -> {g.index[-1]:%Y-%m-%d %H:%M} UTC, "
          f"{len(g)} min, {100 * g['c'].notna().mean():.3f}% con vela")
    print(f"apalancamiento {APAL:.0f}x | mmr {100 * MMR:.1f}% | "
          f"taker {1e4 * TAKER:.1f} bps por lado "
          f"(= {100 * 2 * TAKER * APAL:.1f}% del margen por pata, ida y vuelta) | tope {TOPE} min")

    for tp in a.tp:
        print("\n" + "=" * 104)
        print(f"TP = {tp:.0f} USD de recorrido a favor | stop de H2 = {a.stop:.0f} USD")
        for z, ses in ZONAS.items():
            d = evaluar(g, aperturas(g.index, *ses), tp, a.stop)
            ent = d["ent"].to_numpy()
            liq = d["liq_usd"].mean()
            print(f"\n{z:11s} n={len(d)}  precio medio {ent.mean():.0f} -> "
                  f"TP={100 * APAL * tp / ent.mean():.1f}% del margen, "
                  f"liquidacion a {liq:.0f} USD en contra "
                  f"({100 * APAL * liq / ent.mean():.0f}% del margen)")
            print(f"            en 4 h: toca +{tp:.0f} arriba "
                  f"{100 * d['toco_arriba'].mean():5.1f}% | "
                  f"abajo {100 * d['toco_abajo'].mean():5.1f}% | "
                  f"LAS DOS {100 * d['ambos'].mean():5.1f}% | "
                  f"ninguna {100 * (~d['toco_arriba'] & ~d['toco_abajo']).mean():5.1f}%")
            print(f"            recorrido maximo en 4 h: "
                  f"mediana {d['recorrido_max'].median():.0f} USD, "
                  f"media {d['recorrido_max'].mean():.0f}; minutos hasta el primer TP: "
                  f"mediana {d['min_hasta_tp'].median():.0f}")
            for nombre, col, patas in (("principal (1 pata)", "principal_usd", 1),
                                       ("H1 cierre simultaneo", "h1_usd", 2),
                                       ("H2 cortar a -100", "h2_usd", 2),
                                       ("H3 dejarla correr", "h3_usd", 2)):
                r = pct_margen(d[col].to_numpy(), ent, patas)
                extra = ""
                if col == "h2_usd":
                    extra = f" | con liquidacion {100 * d['h2_liq'].mean():.1f}%"
                if col == "h3_usd":
                    extra = f" | con liquidacion {100 * d['h3_liq'].mean():.1f}%"
                if col == "principal_usd":
                    mot = d["principal_motivo"].value_counts(normalize=True) * 100
                    extra = (f" | tp {mot.get('tp', 0):.0f}% "
                             f"liquidada {mot.get('liquidada', 0):.0f}% "
                             f"tope {mot.get('tope', 0):.0f}%")
                print(f"            {nombre:22s} media={r.mean():+7.2f}% del margen  "
                      f"mediana={np.median(r):+7.2f}%  gana={100 * (r > 0).mean():5.1f}%  "
                      f"total={r.sum() / 100:+8.1f}x margen{extra}")


if __name__ == "__main__":
    main()
