"""El lado del libro y el signo de cada puerta (T213). Puro: filas y velas → cifras.

Nace de una observación del usuario el 2026-11-26 («muchos cortos y pocos largos») que hubo que
contestar a mano: el libro era **652 de 726 cortas (89,8 %)** con 15 días seguidos sin una sola
larga, porque dos de las tres puertas de T212 no habían girado en 34 días. Aquí se mide solo, en
cada auditoría, y con dos cautelas que el diagnóstico aprendió:

1. **El desequilibrio no es, por sí mismo, un hallazgo.** Es del veto `contra_tendencia`, no de las
   estrategias (la sombra generaba 39 % de largos), y en aquella ventana el lado largo rendía peor:
   operar más largos habría perdido más. Por eso se publica junto al contraste de los dos lados.
2. **El contraste se agrupa por vela de apertura.** Decenas de estrategias miran la misma vela, así
   que contar ideas como independientes infla la muestra (la misma trampa que la calibración).

No decide nada: cambiar la puerta es una entrada nueva y T139 la cerró con P1 (`PLAN/T213.md`).
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence

from eim.analytics.audit import opp
from eim.core import Candle
from eim.paper.trend import HtfTrend

DAY_MS = 86_400_000
H_MS = 3_600_000
CONTRAST_DAYS = 7           # ventana del contraste de los dos lados (la que mira la skill)
MIN_SIDE_N = 20             # ideas por lado para leer el contraste
MIN_CLUSTERS = 10           # velas de apertura distintas por lado
MIN_STRETCHES = 3           # tramos por estado para leer el signo de una puerta
HORIZON_H = 24              # retorno siguiente con que se juzga la puerta (T212 §5)
SIDE_SKEW = 0.70            # desde qué reparto el libro es «una sola apuesta»
SHADOW = "sombra"
#: La única lectura que respalda usar una puerta como puerta: alcista precede retornos mejores.
SIGN_OK = "distingue (alcista rinde mejor)"


def _f(x) -> float:
    try:
        return float(x) if x not in (None, "") else 0.0
    except ValueError:
        return 0.0


def is_long(row: Mapping) -> bool:
    return _f(row.get("side")) > 0


def split(rows: Sequence[Mapping]) -> dict:
    """Reparto por lado de un conjunto de operaciones, con su PnL."""
    out = {"n": len(rows), "long": 0, "short": 0, "pnl_long": 0.0, "pnl_short": 0.0}
    for r in rows:
        k = "long" if is_long(r) else "short"
        out[k] += 1
        out[f"pnl_{k}"] += _f(r.get("pnl_usdt"))
    n = out["n"]
    out["short_share"] = out["short"] / n if n else None
    out["dominant"] = None if not n else ("short" if out["short"] >= out["long"] else "long")
    return out


def book_sides(official: Sequence[Mapping], now_ms: int, days: int = CONTRAST_DAYS) -> dict:
    """El sesgo del libro oficial: en toda la muestra, en la ventana corta y cuánto lleva sin girar.

    `no_long_h` son las horas desde la última apertura larga: el 2026-11-26 eran más de 48 h, y
    antes del 11-23 habían sido 15 días enteros.
    """
    recent = [r for r in official if _f(r.get("exit_t")) >= now_ms - days * DAY_MS]
    allp, last = split(official), split(recent)
    opens = {"long": [_f(r.get("opened_t")) for r in official if is_long(r)],
             "short": [_f(r.get("opened_t")) for r in official if not is_long(r)]}
    out = {**allp, f"last{days}": last, "days": days}
    for k in ("long", "short"):
        t = max(opens[k], default=0.0)
        out[f"last_{k}_t"] = int(t)
        out[f"no_{k}_h"] = (now_ms - t) / H_MS if t else None
    return out


def _mean_ci(v: Sequence[float]) -> dict:
    if not v:
        return {"n": 0, "e_r": None, "sd": None, "half": None}
    sd = statistics.stdev(v) if len(v) > 1 else 0.0
    half = 1.96 * sd / math.sqrt(len(v)) if len(v) > 1 else None
    return {"n": len(v), "e_r": statistics.fmean(v), "sd": sd, "half": half}


def _diff(a: dict, b: dict) -> dict:
    """Diferencia a − b con su mínimo detectable (la mitad del IC 95 % de la diferencia)."""
    if not a["n"] or not b["n"] or a["half"] is None or b["half"] is None:
        return {"diff": None, "mdd": None, "t": None}
    d = a["e_r"] - b["e_r"]
    half = math.sqrt(a["half"] ** 2 + b["half"] ** 2)
    return {"diff": d, "mdd": half, "t": 1.96 * d / half if half else None}


def contrast(rows: Sequence[Mapping], now_ms: int, symbol: str = "BTCUSDT",
             days: int = CONTRAST_DAYS) -> dict:
    """Los dos lados sobre la sombra: lo que el veto deja pasar y lo que deja fuera, juntos.

    La sombra evalúa **todas** las ideas con las mismas reglas de salida, así que es el único sitio
    donde el lado vetado tiene cifra. Se informa por idea y agrupando por vela de apertura; el
    veredicto sale del agrupado, que es el conservador.
    """
    t0 = now_ms - days * DAY_MS
    sel = [r for r in rows if str(r.get("scope")) == SHADOW and r.get("symbol") == symbol
           and _f(r.get("opened_t")) >= t0 and r.get("r") not in (None, "")]
    per: dict[str, list[float]] = {"long": [], "short": []}
    cl: dict[tuple, dict[str, list[float]]] = defaultdict(lambda: {"long": [], "short": []})
    for r in sel:
        k = "long" if is_long(r) else "short"
        per[k].append(_f(r.get("r")))
        cl[(str(r.get("timeframe")), int(_f(r.get("opened_t"))))][k].append(_f(r.get("r")))
    raw = {k: _mean_ci(v) for k, v in per.items()}
    grp = {k: _mean_ci([statistics.fmean(g[k]) for g in cl.values() if g[k]]) for k in per}
    d_raw, d_grp = _diff(raw["long"], raw["short"]), _diff(grp["long"], grp["short"])
    reads = (min(raw["long"]["n"], raw["short"]["n"]) >= MIN_SIDE_N
             and min(grp["long"]["n"], grp["short"]["n"]) >= MIN_CLUSTERS)
    verdict = "sin muestra"
    if reads and d_grp["diff"] is not None:
        if abs(d_grp["diff"]) <= (d_grp["mdd"] or 0):
            verdict = "dentro del ruido"
        else:
            verdict = ("el lado largo rinde peor" if d_grp["diff"] < 0
                       else "el lado corto rinde peor")
    return {"universe": f"sombra de {symbol} (sin veto), últimos {days} d", "days": days,
            "symbol": symbol, "n": len(sel), "by_side": raw, "diff": d_raw,
            "grouped": grp, "diff_grouped": d_grp, "reads": reads, "verdict": verdict,
            "min_side_n": MIN_SIDE_N, "min_clusters": MIN_CLUSTERS}


def gate_sign(clock: Sequence[Candle], htf: Sequence[Candle], htf_bar_ms: int, fast: int,
              slow: int, *, horizon_h: int = HORIZON_H, days: int | None = None) -> dict:
    """¿La dirección de una puerta precede retornos distintos? Una observación por giro.

    Se mide **desde el instante en que la puerta gira**: su dirección ya se conoce y lo que venga
    después no, así que cada tramo aporta un dato limpio y sin solapamiento (la muestra es el
    número de giros, que es la potencia real: la puerta rápida de T212 cambia 39 veces en 95 días).

    Promediar todas las velas de un tramo **no** vale, y es un error que parece inocente: la
    ventana de 24 h de las últimas velas del tramo cae ya al otro lado del giro, y un giro es por
    construcción una vuelta del precio. Medido así, 10 de 12 caminatas aleatorias puras dan
    «la puerta distingue al revés» con significación; medido desde el giro, no. Parte del
    −0,180 % descriptivo de T212 §5 en la puerta rápida es ese artefacto: su tramo mediano (34 h)
    apenas supera el horizonte, mientras los de las lentas (212 y 292 h) casi no lo notan.
    """
    empty = {"reads": False, "stretches": 0, "measured": 0, "horizon_h": horizon_h,
             "days": days, "from_flip": True, "up": {"stretches": 0, "ret_pct": None},
             "down": {"stretches": 0, "ret_pct": None}, "diff_pct": None, "mdd_pct": None,
             "verdict": "sin velas", "min_stretches": MIN_STRETCHES}
    if len(clock) <= horizon_h or not htf:
        return empty
    trend = HtfTrend(htf, htf_bar_ms, fast, slow)
    bar = clock[1].t - clock[0].t if len(clock) > 1 else H_MS
    t_end = clock[-1].t
    runs: list[tuple[int, float | None]] = []
    prev = 0
    for i, c in enumerate(clock):
        if days is not None and c.t < t_end - days * DAY_MS:
            continue
        d = trend.at(c.t + bar)
        if d == 0 or not c.c:
            continue
        if d != prev:                   # giro: la única vela que se mide de este tramo
            ret = ((clock[i + horizon_h].c / c.c - 1.0) * 100.0
                   if i + horizon_h < len(clock) else None)
            runs.append((d, ret))
            prev = d
    up = [r for d, r in runs if d > 0 and r is not None]
    down = [r for d, r in runs if d < 0 and r is not None]
    a, b = _mean_ci(up), _mean_ci(down)
    dd = _diff(a, b)
    reads = min(len(up), len(down)) >= MIN_STRETCHES
    verdict = "muestra corta"
    if reads and dd["diff"] is not None:
        if abs(dd["diff"]) <= (dd["mdd"] or 0):
            verdict = "no distingue dirección"
        else:
            verdict = (SIGN_OK if dd["diff"] > 0 else "distingue al revés (alcista rinde peor)")
    span = (clock[-1].t - max(clock[0].t, t_end - days * DAY_MS if days else 0)) / DAY_MS
    return {"reads": reads, "stretches": len(runs), "horizon_h": horizon_h,
            "measured": len(up) + len(down), "days": days, "span_days": span, "from_flip": True,
            "up": {"stretches": a["n"], "ret_pct": a["e_r"]},
            "down": {"stretches": b["n"], "ret_pct": b["e_r"]},
            "diff_pct": dd["diff"], "mdd_pct": dd["mdd"], "verdict": verdict,
            "min_stretches": MIN_STRETCHES}


def gate_signs(candles: Mapping[str, Sequence[Candle]], htf_map: Mapping[str, Sequence],
               bars_ms: Mapping[str, int], clock_tf: str = "1h", *,
               horizon_h: int = HORIZON_H, days: int | None = None) -> list[dict]:
    """El signo de cada puerta de `ProfileParams.htf`, con el reloj común de `clock_tf`."""
    clock = candles.get(clock_tf) or []
    out = []
    for tf, spec in sorted(htf_map.items()):
        htf, fast, slow = spec[0], int(spec[1]), int(spec[2])
        s = gate_sign(clock, candles.get(htf) or [], bars_ms.get(htf, H_MS), fast, slow,
                      horizon_h=horizon_h, days=days)
        out.append({"timeframe": tf, "htf": htf, "fast": fast, "slow": slow, **s})
    return out


def side_opps(sides: dict | None, contrast: dict | None,
              signs: list[dict] | None = None) -> list[dict]:
    """T213: el sesgo del libro, el contraste de los dos lados y el signo de cada puerta.

    Las tres son informativas por definición —el lado lo fija la puerta y T139 la cerró con P1—,
    y van juntas a propósito: el desequilibrio solo engaña. El 2026-11-26 el libro era 89,8 %
    cortas y, en la misma ventana, el lado largo de la sombra rendía −0,53 R peor que el corto:
    «pocos largos» no explicaba la pérdida, la explicaba el costo.
    """
    out = []
    s = sides or {}
    share = s.get("short_share")
    if s.get("n") and share is not None and max(share, 1 - share) >= SIDE_SKEW:
        dom = "cortas" if s["dominant"] == "short" else "largas"
        d = s.get(f"last{s.get('days', 7)}") or {}
        ev = (f"{s[s['dominant']]} de {s['n']} {dom} ({max(share, 1 - share):.1%}); "
              f"{s.get('days')} d: {d.get('short', 0)} cortas / {d.get('long', 0)} largas")
        if s.get("no_long_h"):
            ev += f"; última larga hace {s['no_long_h']:.0f} h"
        out.append(opp("sesgo_lado", "dirección",
                        "El libro es direccionalmente una sola apuesta", ev,
                        "cerrada (T139 P1: el lado lo fija la puerta)", "T213 · T212"))
    c = contrast or {}
    if c.get("n"):
        g, dg = c["grouped"], c["diff_grouped"]
        ev = (f"sombra sin veto: largo {g['long']['e_r'] or 0:+.3f} R ({g['long']['n']} velas) "
              f"frente a corto {g['short']['e_r'] or 0:+.3f} ({g['short']['n']}), diferencia "
              f"{dg['diff'] or 0:+.3f} ± {dg['mdd'] or 0:.3f} agrupando por vela de apertura")
        if not c.get("reads"):
            ev += (f"; muestra corta (mínimos {c['min_side_n']} ideas y {c['min_clusters']} "
                   "velas por lado)")
        out.append(opp("contraste_lados", "dirección",
                        f"Los dos lados, contrastados: {c['verdict']}", ev,
                        "cerrada (T139 P1: informativo, no cambia el lado)", "T213 · T144"))
    odd = [x for x in (signs or []) if x.get("reads") and x["verdict"] != SIGN_OK]
    if odd:
        ev = "; ".join(f"{x['timeframe']} ({x['htf']} EMA{x['fast']}/{x['slow']}): "
                       f"{x['up']['ret_pct'] or 0:+.3f} % alcista frente a "
                       f"{x['down']['ret_pct'] or 0:+.3f} % bajista a {x['horizon_h']} h, "
                       f"{x['stretches']} tramos, mínimo detectable {x['mdd_pct'] or 0:.3f} % "
                       f"→ {x['verdict']}" for x in odd)
        out.append(opp("puerta_sin_signo", "dirección",
                       f"{len(odd)} puerta(s) cuyo signo no respalda su uso en la ventana", ev,
                       "cerrada (T139 P1: tocar la puerta, invertirla o acortar sus EMAs es una "
                       "entrada nueva · ◆)", "T213 · T212"))
    return out

def text(sides: dict, con: dict | None = None) -> str:
    """Una línea para la consola y el informe; descriptiva, sin recomendación."""
    d = sides.get(f"last{sides.get('days', CONTRAST_DAYS)}") or {}
    out = (f"{sides.get('short', 0)}/{sides.get('n', 0)} cortas "
           f"({(sides.get('short_share') or 0):.1%}) · {sides.get('days')} d "
           f"{d.get('short', 0)}/{d.get('long', 0)}")
    if sides.get("no_long_h"):
        out += f" · última larga hace {sides['no_long_h']:.0f} h"
    if con and con.get("reads"):
        g, dg = con["grouped"], con["diff_grouped"]
        out += (f" · sombra agrupada L {g['long']['e_r']:+.3f} vs S {g['short']['e_r']:+.3f} "
                f"(dif {dg['diff']:+.3f} ± {dg['mdd']:.3f}: {con['verdict']})")
    return out
