"""Ejecución en papel sobre el camino de 15 m (función pura, sin anticipación).

Reglas (conservadoras, explícitas):
- Mercado: se llena en la APERTURA de la primera vela de 15 m con `t ≥ idea.t`, con deslizamiento
  (base + volatilidad de la vela) y comisión taker. Si a ese precio el SL o el TP ya quedaron
  del otro lado: RECHAZADA (geometría).
- Límite: se llena al precio límite (maker) si una vela lo toca dentro de su vigencia; si antes
  el precio alcanza el TP sin tocar la entrada: CANCELADA (objetivo sin llenar); si vence: NO
  LLENADA. En la vela del llenado solo se comprueba el SL (el orden intra-vela es desconocido).
- Salidas: SL antes que TP si caben en la misma vela; un hueco más allá del SL se ejecuta a la
  apertura; TP como límite (maker); por tiempo a la apertura (taker + deslizamiento).
- Break-even+ (T48b): si el precio avanza `be_trigger_r` R, desde la vela SIGUIENTE el SL pasa a
  entrada + `be_lock_r` R (salida «BE», taker + deslizamiento). En la vela del disparo manda el SL
  original si también lo toca (conservador).
- Funding real del almacén entre llenado y salida; donde falta, la tasa supuesta (marcado).
Resultado en fracciones del nocional de entrada y en R (riesgo = |llenado − SL| / llenado).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np

from eim.core import Candle
from eim.data.timeframes import tf_ms
from eim.paper.ideas import Idea
from eim.paper.params import ExecParams

FUNDING_MS = 8 * 3_600_000
NEVER = 2**62
# Diagnóstico de pérdidas (T48): de cada operación perdida se registra su causa.
NEAR_TP = 0.7       # llegó a ≥ 70 % del recorrido al TP y se dio la vuelta → «casi TP»
QUICK_BARS = 2      # SL en ≤ 2 velas del marco sin haber avanzado … → «SL rápido»
QUICK_MFE = 0.3     # … (avance máximo < 0,3 R)
CAUSES: dict[str, str] = {
    "direccion": "Dirección equivocada: el precio fue contra la operación hasta el SL",
    "sl_rapido": "SL rápido: tocó el stop en ≤ 2 velas sin avanzar (ruido o entrada prematura)",
    "casi_tp": "Casi TP: llegó a ≥ 70 % del objetivo y se dio la vuelta (TP lejos)",
    "tiempo": "Por tiempo: no alcanzó el objetivo dentro del horizonte",
    "costos": "Costos: habría ganado antes de comisiones, deslizamiento y funding",
}


@dataclass(frozen=True)
class Outcome:
    idea: Idea
    status: str                  # PENDIENTE | ABIERTA | CERRADA | CANCELADA | RECHAZADA
    reason: str = ""     # TP | SL | BE | TIEMPO | NO_LLENADA | OBJETIVO_SIN_LLENAR | GEOMETRIA
    fill_t: int | None = None
    fill: float | None = None
    exit_t: int | None = None    # salida o cancelación
    exit: float | None = None
    fee_in: float = 0.0          # fracciones del nocional de entrada
    fee_out: float = 0.0
    slip: float = 0.0
    funding: float = 0.0         # + = pagado
    funding_assumed: bool = False
    gross: float = 0.0           # lado·(salida o marca − llenado)/llenado
    r: float | None = None       # neto en R (cerradas) o latente (abiertas)
    mfe_r: float = 0.0
    mae_r: float = 0.0
    mark: float | None = None    # último precio conocido (abiertas)

    @property
    def net(self) -> float:
        return self.gross - self.fee_in - self.fee_out - self.slip - self.funding

    @property
    def risk(self) -> float:
        return abs(self.fill - self.idea.sl) / self.fill if self.fill else 0.0

    @property
    def cause(self) -> str | None:
        """Causa de una pérdida cerrada (clave de `CAUSES`); None si ganó o no cerró."""
        if self.status != "CERRADA" or self.r is None or self.net > 0 or not self.fill:
            return None
        if self.gross > 0:
            return "costos"
        if self.reason == "TIEMPO":
            return "tiempo"
        risk = abs(self.fill - self.idea.sl)
        tp_r = abs(self.idea.tp - self.fill) / risk if risk else 0.0
        if tp_r and self.mfe_r >= NEAR_TP * tp_r:
            return "casi_tp"
        quick = (self.exit_t or 0) - (self.fill_t or 0) <= QUICK_BARS * tf_ms(self.idea.timeframe)
        return "sl_rapido" if quick and self.mfe_r < QUICK_MFE else "direccion"

    @property
    def busy_until(self) -> int:
        return self.exit_t if self.exit_t is not None else NEVER

    def to_json(self) -> dict:
        return {**self.idea.to_json(), "status": self.status, "reason": self.reason,
                "fill_t": self.fill_t, "fill": self.fill, "exit_t": self.exit_t,
                "exit": self.exit, "fees": self.fee_in + self.fee_out, "slip": self.slip,
                "funding": self.funding, "funding_assumed": self.funding_assumed,
                "gross": self.gross, "net": self.net, "r": self.r, "mfe_r": self.mfe_r,
                "mae_r": self.mae_r, "mark": self.mark, "cause": self.cause}


class Path:
    """Velas del camino (15 m) como arreglos + funding (t, tasa)."""

    def __init__(self, candles: Sequence[Candle], funding: Sequence[tuple[int, float]] = (),
                 step_ms: int = 15 * 60_000) -> None:
        self.t = np.array([c.t for c in candles], dtype=np.int64)
        self.o = np.array([c.o for c in candles], dtype=float)
        self.h = np.array([c.h for c in candles], dtype=float)
        self.l = np.array([c.l for c in candles], dtype=float)
        self.c = np.array([c.c for c in candles], dtype=float)
        self.step = step_ms
        self.ft = np.array([t for t, _ in funding], dtype=np.int64)
        self.fr = np.array([x for _, x in funding], dtype=float)

    @property
    def end(self) -> int:
        return int(self.t[-1]) + self.step if len(self.t) else 0


def _hits(path: Path, s: int, a: int, b: int, sl: float, tp: float
          ) -> tuple[int | None, int | None]:
    """Primeras velas (desde `a`, antes de `b`) que tocan el SL y el TP."""
    seg = slice(a, max(a, b))
    adv = (path.l[seg] <= sl) if s > 0 else (path.h[seg] >= sl)
    fav = (path.h[seg] >= tp) if s > 0 else (path.l[seg] <= tp)
    ia, it = _first(adv), _first(fav)
    return (None if ia is None else a + ia), (None if it is None else a + it)


def _touch(path: Path, s: int, a: int, b: int, level: float) -> int | None:
    """Primera vela (desde `a`, antes de `b`) que alcanza `level` a favor del lado `s`."""
    seg = slice(a, max(a, b))
    j = _first((path.h[seg] >= level) if s > 0 else (path.l[seg] <= level))
    return None if j is None else a + j


def _stop_exit(path: Path, s: int, j: int, level: float, k: int) -> float:
    """Precio de un stop en la vela `j`: el nivel, o la apertura si abre más allá (hueco)."""
    gap = (path.o[j] <= level) if s > 0 else (path.o[j] >= level)
    return float(path.o[j]) if gap and j > k else level


def _first(mask: np.ndarray) -> int | None:
    i = int(np.argmax(mask)) if len(mask) else 0
    return i if len(mask) and mask[i] else None


def _slip(path: Path, j: int, p: ExecParams, entry: bool = False) -> float:
    """Deslizamiento relativo de un llenado a mercado. La entrada usa parámetros propios
    (libro real: ≈ 0,01 pb); las salidas por SL/BE/tiempo conservan el término de volatilidad."""
    cp = p.costs
    rng = float((path.h[j] - path.l[j]) / path.o[j]) if path.o[j] > 0 else 0.0
    base, k = ((cp.slip_entry_base_bps, cp.slip_entry_vol_k) if entry
               else (cp.slip_base_bps, cp.slip_vol_k))
    return min(max(base / 1e4 + k * rng, 0.0), cp.slip_cap_bps / 1e4)


def _funding(path: Path, side: int, t0: int, t1: int, p: ExecParams) -> tuple[float, bool]:
    lo, hi = int(np.searchsorted(path.ft, t0, "right")), int(np.searchsorted(path.ft, t1, "right"))
    paid = side * float(path.fr[lo:hi].sum())
    expected = t1 // FUNDING_MS - t0 // FUNDING_MS
    missing = max(0, expected - (hi - lo))
    return paid + side * missing * p.funding_8h_assumed, missing > 0


def _limit_fill(idea: Idea, path: Path, j0: int) -> tuple[str, int | None]:
    """('fill', k) | ('cancel_tp', k) | ('expired', None) | ('pending', None)."""
    s = idea.side
    kend = int(np.searchsorted(path.t, idea.t + idea.fill_ms))
    seg = slice(j0, kend)
    touch = (path.l[seg] <= idea.entry) if s > 0 else (path.h[seg] >= idea.entry)
    tp_hit = (path.h[seg] >= idea.tp) if s > 0 else (path.l[seg] <= idea.tp)
    k, ktp = _first(touch), _first(tp_hit)
    if k is not None and (ktp is None or k <= ktp):
        return "fill", j0 + k
    if ktp is not None:
        return "cancel_tp", j0 + ktp
    return ("expired", None) if path.end >= idea.t + idea.fill_ms else ("pending", None)


def simulate(idea: Idea, path: Path, p: ExecParams) -> Outcome:
    s, cp = idea.side, p.costs
    j0 = int(np.searchsorted(path.t, idea.t))
    if j0 >= len(path.t):
        return Outcome(idea, "PENDIENTE")
    if idea.kind == "market":
        slip_in = _slip(path, j0, p, entry=True)
        fill = float(path.o[j0]) * (1 + s * slip_in)
        fee_in, k, start = cp.taker_fee, j0, j0
    else:
        what, k = _limit_fill(idea, path, j0)
        if what == "pending":
            return Outcome(idea, "PENDIENTE")
        if what == "expired":
            return Outcome(idea, "CANCELADA", "NO_LLENADA", exit_t=idea.t + idea.fill_ms)
        if what == "cancel_tp":
            return Outcome(idea, "CANCELADA", "OBJETIVO_SIN_LLENAR",
                           exit_t=int(path.t[k]) + path.step)
        slip_in, fill, fee_in, start = 0.0, idea.entry, cp.maker_fee, k + 1
    fill_t = int(path.t[k])
    if (fill - idea.sl) * s <= p.min_risk_frac * fill or (idea.tp - fill) * s <= 0:
        return Outcome(idea, "RECHAZADA", "GEOMETRIA", exit_t=fill_t, fill=fill)
    risk = abs(fill - idea.sl)

    reason, ex, jx = "", None, None
    if start > k and ((path.l[k] <= idea.sl) if s > 0 else (path.h[k] >= idea.sl)):
        reason, ex, jx = "SL", idea.sl, k                # límite llenada y SL en la misma vela
    else:
        kh = int(np.searchsorted(path.t, fill_t + idea.hold_ms))
        ia, it = _hits(path, s, start, kh, idea.sl, idea.tp)
        ib = None
        if p.be_trigger_r > 0 and idea.timeframe in p.be_timeframes:
            trig = fill + s * p.be_trigger_r * risk
            ib = _touch(path, s, start, kh, trig)
        if ia is not None and (it is None or ia <= it) and (ib is None or ia <= ib):
            reason, ex, jx = "SL", _stop_exit(path, s, ia, idea.sl, k), ia
        elif it is not None and (ib is None or it <= ib):
            reason, ex, jx = "TP", idea.tp, it
        elif ib is not None:                                         # SL movido a BE+
            lock_r = p.be_lock_r + (p.est_cost_frac * fill / risk if p.be_cover_costs else 0.0)
            lock = fill + s * lock_r * risk
            ia2, it2 = _hits(path, s, ib + 1, kh, lock, idea.tp)
            if ia2 is not None and (it2 is None or ia2 <= it2):
                reason, ex, jx = "BE", _stop_exit(path, s, ia2, lock, k), ia2
            elif it2 is not None:
                reason, ex, jx = "TP", idea.tp, it2
        if not reason and kh < len(path.t):
            reason, ex, jx = "TIEMPO", float(path.o[kh]), kh

    last = jx if jx is not None else len(path.t) - 1
    hi, lo = float(path.h[k:last + 1].max()), float(path.l[k:last + 1].min())
    fav_px, adv_px = (min(hi, idea.tp), max(lo, idea.sl)) if s > 0 else (max(lo, idea.tp),
                                                                          min(hi, idea.sl))
    mfe, mae = max(0.0, (fav_px - fill) * s) / risk, max(0.0, (fill - adv_px) * s) / risk
    if reason:
        # SL/TP se resuelven dentro de la vela (se sabe a su cierre); tiempo, a la apertura
        exit_t = int(path.t[jx]) + (0 if reason == "TIEMPO" else path.step)
        slip_out = _slip(path, jx, p) if reason in ("SL", "BE", "TIEMPO") else 0.0
        fee_out = (cp.maker_fee if reason == "TP" else cp.taker_fee) * ex / fill
        fund, assumed = _funding(path, s, fill_t, exit_t, p)
        gross = s * (ex - fill) / fill
        o = Outcome(idea, "CERRADA", reason, fill_t, fill, exit_t, ex, fee_in, fee_out,
                    slip_in + slip_out, fund, assumed, gross, None, mfe, mae)
        return _with_r(o)
    mark = float(path.c[-1])
    fund, assumed = _funding(path, s, fill_t, path.end, p)
    o = Outcome(idea, "ABIERTA", "", fill_t, fill, None, None, fee_in, 0.0, slip_in, fund,
                assumed, s * (mark - fill) / fill, None, mfe, mae, mark)
    return _with_r(o)


def _with_r(o: Outcome) -> Outcome:
    return replace(o, r=o.net / o.risk if o.risk > 0 else None)


def run_shadow(ideas: Sequence[Idea], path: Path, p: ExecParams | None = None) -> list[Outcome]:
    """Evaluación «sombra»: cada estrategia con UNA idea viva a la vez (como una cuenta propia).

    Una idea entra si su estrategia —en su marco, `idea.sid`— está libre en `idea.t` (la
    anterior ya cerró o se canceló, más `cooldown_bars` de ese marco) y su `key` no se operó
    antes. Igual para todos los perfiles.
    """
    p = p or ExecParams()
    busy: dict[str, int] = {}
    seen: dict[str, set[str]] = {}
    out: list[Outcome] = []
    for idea in sorted(ideas, key=lambda x: (x.t, x.sid)):
        if idea.t < busy.get(idea.sid, -1):
            continue
        cool = p.cooldown_bars * tf_ms(idea.timeframe)
        keys = seen.setdefault(idea.sid, set())
        if idea.key and idea.key in keys:
            continue
        o = simulate(idea, path, p)
        if idea.key:
            keys.add(idea.key)
        if o.status != "RECHAZADA":
            busy[idea.sid] = o.busy_until + cool if o.busy_until < NEVER else NEVER
        out.append(o)
    return out
