"""Implementación de referencia, ingenua y deliberadamente independiente de `eim.indicators`.

Bucles en Python puro sobre listas, escritos desde las definiciones textuales (Wilder,
Appel, Lane, Lambert, Arms, Hutson, convenciones de los gráficos chinos para KDJ/MTM/EMV/TRIX).
No importa nada de `eim`. Se usa SOLO para generar una vez las fixtures (`_make_fixtures.py`).
Interino: falta contrastar con TA-Lib/pandas-ta-classic (elegidas en T33; ver PLAN/BACKLOG.md).
"""

from __future__ import annotations

import math

NAN = float("nan")


def isn(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def r_sma(x, n):
    out = []
    for i in range(len(x)):
        w = x[i - n + 1:i + 1] if i >= n - 1 else None
        out.append(NAN if w is None or any(isn(v) for v in w) else sum(w) / n)
    return out


def r_ema_first(x, n):
    a, out, y = 2 / (n + 1), [], None
    for v in x:
        if isn(v):
            out.append(NAN)
            continue
        y = v if y is None else a * v + (1 - a) * y
        out.append(y)
    return out


def r_wilder(x, n):
    """Wilder: primer valor = media de los n primeros válidos (contiguos), luego (p·(n−1)+x)/n."""
    out, y, buf = [], None, []
    for v in x:
        if y is None:
            if isn(v):
                if buf:
                    return [NAN] * len(x)
                out.append(NAN)
                continue
            buf.append(v)
            if len(buf) == n:
                y = sum(buf) / n
                out.append(y)
            else:
                out.append(NAN)
        elif isn(v):
            out.append(NAN)
        else:
            y = (y * (n - 1) + v) / n
            out.append(y)
    return out


def r_tr(h, lo, c):
    return [h[0] - lo[0]] + [max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1]))
                             for i in range(1, len(c))]


def r_wma(x, n):
    out = []
    for i in range(len(x)):
        if i < n - 1:
            out.append(NAN)
            continue
        w = x[i - n + 1:i + 1]
        out.append(sum((k + 1) * w[k] for k in range(n)) / (n * (n + 1) / 2))
    return out


def r_std(x, n):
    out = []
    for i in range(len(x)):
        if i < n - 1:
            out.append(NAN)
            continue
        w = x[i - n + 1:i + 1]
        m = sum(w) / n
        out.append(math.sqrt(sum((v - m) ** 2 for v in w) / n))
    return out


def r_hhv(x, n):
    return [NAN if i < n - 1 else max(x[i - n + 1:i + 1]) for i in range(len(x))]


def r_llv(x, n):
    return [NAN if i < n - 1 else min(x[i - n + 1:i + 1]) for i in range(len(x))]


def r_rsi(c, n):
    gains = [max(c[i] - c[i - 1], 0.0) for i in range(1, len(c))]
    losses = [max(c[i - 1] - c[i], 0.0) for i in range(1, len(c))]
    g, lo = r_wilder(gains, n), r_wilder(losses, n)
    out = [NAN]
    for a, b in zip(g, lo, strict=True):
        if isn(a):
            out.append(NAN)
        elif a + b == 0:
            out.append(50.0)
        else:
            out.append(100 * a / (a + b))
    return out


def r_sar(h, lo, start, step, mx):
    out = [NAN] * len(h)
    long = (h[1] - h[0]) > (lo[0] - lo[1])
    sar = lo[0] if long else h[0]
    ep = h[1] if long else lo[1]
    af = start
    out[1] = sar
    for i in range(2, len(h)):
        sar = sar + af * (ep - sar)
        if long:
            sar = min(sar, lo[i - 1], lo[i - 2])
            if lo[i] < sar:
                long, sar, ep, af = False, ep, lo[i], start
            elif h[i] > ep:
                ep = h[i]
                af = min(af + step, mx)
        else:
            sar = max(sar, h[i - 1], h[i - 2])
            if h[i] > sar:
                long, sar, ep, af = True, ep, h[i], start
            elif lo[i] < ep:
                ep = lo[i]
                af = min(af + step, mx)
        out[i] = sar
    return out


def r_atr(h, lo, c, n):
    tr = r_tr(h, lo, c)
    return [NAN] + r_wilder(tr[1:], n)


def r_supertrend(h, lo, c, n, k):
    a = r_atr(h, lo, c, n)
    st, dr = [], []
    fu = fl = None
    d = 1.0
    for i in range(len(c)):
        if isn(a[i]):
            st.append(NAN)
            dr.append(NAN)
            continue
        mid = (h[i] + lo[i]) / 2
        bu, bl = mid + k * a[i], mid - k * a[i]
        if fu is None:
            fu, fl = bu, bl
            d = 1.0 if c[i] >= mid else -1.0
        else:
            if bu < fu or c[i - 1] > fu:
                fu = bu
            if bl > fl or c[i - 1] < fl:
                fl = bl
            if d < 0 and c[i] > fu:
                d = 1.0
            elif d > 0 and c[i] < fl:
                d = -1.0
        st.append(fl if d > 0 else fu)
        dr.append(d)
    return {"st": st, "dir": dr}


def r_dmi(h, lo, c, n, m):
    pdm, mdm = [], []
    for i in range(1, len(c)):
        up, dn = h[i] - h[i - 1], lo[i - 1] - lo[i]
        pdm.append(up if (up > dn and up > 0) else 0.0)
        mdm.append(dn if (dn > up and dn > 0) else 0.0)
    tr = r_tr(h, lo, c)[1:]
    st, sp, sm = r_wilder(tr, n), r_wilder(pdm, n), r_wilder(mdm, n)
    pdi, mdi, dx = [NAN], [NAN], [NAN]
    for a, b, t in zip(sp, sm, st, strict=True):
        if isn(t) or t == 0:
            pdi.append(NAN)
            mdi.append(NAN)
            dx.append(NAN)
            continue
        p, q = 100 * a / t, 100 * b / t
        pdi.append(p)
        mdi.append(q)
        dx.append(NAN if p + q == 0 else 100 * abs(p - q) / (p + q))
    first = next(i for i, v in enumerate(dx) if not isn(v))
    adx = [NAN] * first + r_wilder(dx[first:], m)
    adxr = [NAN if i < m or isn(adx[i - m]) else (adx[i] + adx[i - m]) / 2
            for i in range(len(adx))]
    return {"pdi": pdi, "mdi": mdi, "adx": adx, "adxr": adxr}


def r_kdj(h, lo, c, n, m1, m2):
    hh, ll = r_hhv(h, n), r_llv(lo, n)
    k = d = 50.0
    ks, ds, js = [], [], []
    for i in range(len(c)):
        if isn(hh[i]) or hh[i] == ll[i]:  # sin RSV: hueco, K y D conservan su estado
            ks.append(NAN)
            ds.append(NAN)
            js.append(NAN)
            continue
        rsv = (c[i] - ll[i]) / (hh[i] - ll[i]) * 100
        k = (rsv + (m1 - 1) * k) / m1
        d = (k + (m2 - 1) * d) / m2
        ks.append(k)
        ds.append(d)
        js.append(3 * k - 2 * d)
    return {"k": ks, "d": ds, "j": js}


def r_cci(h, lo, c, n):
    tp = [(h[i] + lo[i] + c[i]) / 3 for i in range(len(c))]
    out = []
    for i in range(len(tp)):
        if i < n - 1:
            out.append(NAN)
            continue
        w = tp[i - n + 1:i + 1]
        m = sum(w) / n
        md = sum(abs(v - m) for v in w) / n
        out.append(NAN if md == 0 else (tp[i] - m) / (0.015 * md))
    return out


def r_mfi(h, lo, c, v, n):
    tp = [(h[i] + lo[i] + c[i]) / 3 for i in range(len(c))]
    out = []
    for i in range(len(tp)):
        if i < n:
            out.append(NAN)
            continue
        pos = sum(tp[j] * v[j] for j in range(i - n + 1, i + 1) if tp[j] > tp[j - 1])
        neg = sum(tp[j] * v[j] for j in range(i - n + 1, i + 1) if tp[j] < tp[j - 1])
        out.append(NAN if pos + neg == 0 else 100 * pos / (pos + neg))
    return out


def r_emv(h, lo, v, n, m):
    ma_v = r_sma(v, n)
    rng = [h[i] - lo[i] for i in range(len(h))]
    ma_rng = r_sma(rng, n)
    raw = [NAN]
    for i in range(1, len(h)):
        hl, phl = h[i] + lo[i], h[i - 1] + lo[i - 1]
        if isn(ma_v[i]) or v[i] == 0 or isn(ma_rng[i]) or ma_rng[i] == 0:
            raw.append(NAN)
            continue
        raw.append(100 * (hl - phl) / hl * (ma_v[i] / v[i]) * rng[i] / ma_rng[i])
    e = r_sma(raw, n)
    return {"emv": e, "maemv": r_sma(e, m)}


def r_vwap(h, lo, c, v, t, period):
    out, day, spv, sv = [], None, 0.0, 0.0
    for i in range(len(c)):
        if t[i] // period != day:
            day, spv, sv = t[i] // period, 0.0, 0.0
        spv += (h[i] + lo[i] + c[i]) / 3 * v[i]
        sv += v[i]
        out.append(NAN if sv == 0 else spv / sv)
    return out
