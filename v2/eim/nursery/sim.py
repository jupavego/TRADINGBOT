"""Una operación de la cantera sobre el camino real de 15 m (T168). Puro y sin anticipación.

Reglas (conservadoras, explícitas; las de `paper/engine.py` salvo donde se dice):
- **Mercado:** se llena a la apertura de la primera vela de 15 m tras el cierre de decisión, con el
  deslizamiento de entrada y la comisión de tomador.
- **Límite (maker, rec. 16):** al cierre de decisión, vigente `fill_ms`. **Solo se llena si una
  vela atraviesa el límite** (mínimo < límite en largo, máximo > límite en corto): tocarlo no
  basta. Si antes llega al objetivo, se cancela; si vence, no hay operación. En la vela del
  llenado solo se comprueba el SL (el orden dentro de la vela no se conoce) y no se cuenta su
  extremo para la escalera.
- **Markout:** se guarda el movimiento a favor, en pb, desde el llenado hasta el cierre de la vela
  de 15 m que termina `MARKOUT_BARS` velas después (1 h): mide si la límite llena justo antes de
  que el precio se vaya en contra.
- **Salidas:** en cada vela, primero la salida forzada a la apertura (regla o tiempo), luego el
  stop vigente (un hueco más allá se ejecuta a la apertura), luego el objetivo (límite, creador).
  El stop solo sube desde la vela siguiente a la que confirmó el avance (escalones en R netos de
  la escalera vigente y BE+, como `ladder.py`, sin velas de 1 min).
- **Funding** real del almacén entre llenado y salida; donde falta, la tasa supuesta escalada a la
  **frecuencia real del símbolo** (8 h, 4 h o 1 h, deducida de los cobros guardados).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from eim.paper.engine import Path, _slip
from eim.paper.ladder_math import level_of, nominal
from eim.paper.params import LADDER_BY_PROFILE, ExecParams

H = 3_600_000
FUNDING_STEPS = (H, 4 * H, 8 * H)
MARKOUT_BARS = 4


@dataclass(frozen=True)
class Order:
    side: int
    t: int                      # cierre de la vela de decisión
    ref: float                  # precio de referencia (cierre) = límite en las maker
    sl: float
    tp: float | None = None
    maker: bool = False
    fill_ms: int = 0            # vigencia de la límite
    forced_t: int | None = None  # salida a la apertura de la primera vela con t ≥ forced_t
    forced_reason: str = "TIEMPO"  # TIEMPO | REGLA | GEMELO
    protect: bool = False       # escalones + BE+ (plantilla `atr_ladder`)
    be: bool = False            # BE+ en este marco (`ExecParams.be_timeframes`)

    def twin(self, side: int, until: int | None) -> Order:
        """La misma orden del otro lado (distancias espejo), con salida a más tardar en `until`."""
        if side == self.side:
            return replace(self, forced_t=_earliest(self.forced_t, until), forced_reason="GEMELO")
        tp = None if self.tp is None else 2 * self.ref - self.tp
        return replace(self, side=side, sl=2 * self.ref - self.sl, tp=tp,
                       forced_t=_earliest(self.forced_t, until), forced_reason="GEMELO")


def _earliest(a: int | None, b: int | None) -> int | None:
    return b if a is None else a if b is None else min(a, b)


@dataclass(frozen=True)
class Trade:
    status: str                 # CERRADA | ABIERTA | NO_LLENADA | CANCELADA | PENDIENTE | RECHAZADA
    reason: str = ""            # SL | SLD | TP | REGLA | TIEMPO | ...
    fill_t: int | None = None
    fill: float | None = None
    exit_t: int | None = None
    exit: float | None = None
    fee_in: float = 0.0         # fracciones del nocional de entrada
    fee_out: float = 0.0
    slip: float = 0.0
    funding: float = 0.0        # + = pagado
    funding_assumed: bool = False
    gross: float = 0.0
    markout_bps: float | None = None
    sl: float | None = None

    @property
    def cost(self) -> float:
        return self.fee_in + self.fee_out + self.slip + self.funding

    @property
    def net(self) -> float:
        return self.gross - self.cost

    @property
    def risk(self) -> float:
        return abs(self.fill - self.sl) / self.fill if self.fill and self.sl else 0.0

    @property
    def r(self) -> float | None:
        """Neto en R (cerradas); las no llenadas valen 0 R (no son gratis, pero no pierden)."""
        if self.status in ("NO_LLENADA", "CANCELADA"):
            return 0.0
        return self.net / self.risk if self.status == "CERRADA" and self.risk > 0 else None

    @property
    def cost_r(self) -> float | None:
        return self.cost / self.risk if self.status == "CERRADA" and self.risk > 0 else None

    @property
    def busy_until(self) -> int | None:
        return self.exit_t if self.status != "ABIERTA" else None


def funding_step(path: Path) -> int:
    """Frecuencia de cobro del funding deducida de los cobros guardados (8 h si no se sabe)."""
    if len(path.ft) < 3:
        return 8 * H
    d = float(np.median(np.diff(path.ft[-30:])))
    return min(FUNDING_STEPS, key=lambda s: abs(s - d))


def funding_paid(path: Path, side: int, t0: int, t1: int, ep: ExecParams,
                 step: int) -> tuple[float, bool]:
    lo, hi = int(np.searchsorted(path.ft, t0, "right")), int(np.searchsorted(path.ft, t1, "right"))
    paid = side * float(path.fr[lo:hi].sum())
    missing = max(0, (t1 // step - t0 // step) - (hi - lo))
    return paid + side * missing * ep.funding_8h_assumed * step / (8 * H), missing > 0


def _entry(o: Order, path: Path, ep: ExecParams) -> tuple[str, int, float, float, float]:
    """(estado, vela del llenado, precio, comisión, deslizamiento)."""
    s, cp = o.side, ep.costs
    j0 = int(np.searchsorted(path.t, o.t))
    if j0 >= len(path.t):
        return "PENDIENTE", -1, 0.0, 0.0, 0.0
    if not o.maker:
        slip = _slip(path, j0, ep, entry=True)
        return "OK", j0, float(path.o[j0]) * (1 + s * slip), cp.taker_fee, slip
    kend = min(len(path.t), int(np.searchsorted(path.t, o.t + o.fill_ms)))
    for j in range(j0, kend):
        if (path.l[j] < o.ref) if s > 0 else (path.h[j] > o.ref):
            return "OK", j, o.ref, cp.maker_fee, 0.0
        if o.tp is not None and ((path.h[j] >= o.tp) if s > 0 else (path.l[j] <= o.tp)):
            return "OBJETIVO_SIN_LLENAR", j, 0.0, 0.0, 0.0
    return ("NO_LLENADA" if path.end >= o.t + o.fill_ms else "PENDIENTE"), -1, 0.0, 0.0, 0.0


def simulate(o: Order, path: Path, ep: ExecParams, fstep: int | None = None) -> Trade:
    s, cp = o.side, ep.costs
    what, k, fill, fee_in, slip_in = _entry(o, path, ep)
    if what == "PENDIENTE":
        return Trade("PENDIENTE", sl=o.sl)
    if what == "NO_LLENADA":
        return Trade("NO_LLENADA", "NO_LLENADA", exit_t=o.t + o.fill_ms, sl=o.sl)
    if what != "OK":
        return Trade("CANCELADA", what, exit_t=int(path.t[k]) + path.step, sl=o.sl)
    fill_t = int(path.t[k])
    if (fill - o.sl) * s <= ep.min_risk_frac * fill or (
            o.tp is not None and (o.tp - fill) * s <= 0):
        return Trade("RECHAZADA", "GEOMETRIA", fill_t, fill, exit_t=fill_t, sl=o.sl)
    risk = abs(fill - o.sl)
    cost_r = ep.est_cost_frac * fill / risk
    stop, best = o.sl, fill
    jm = k + MARKOUT_BARS
    mk = s * (float(path.c[jm]) - fill) / fill * 1e4 if jm < len(path.t) else None
    reason, ex, jx = "", 0.0, -1
    for j in range(k, len(path.t)):
        intra = o.maker and j == k            # vela del llenado de una límite
        if o.forced_t is not None and path.t[j] >= o.forced_t and not intra:
            reason, ex, jx = o.forced_reason, float(path.o[j]), j
            break
        lo, hi, op = path.l[j], path.h[j], path.o[j]
        if (lo <= stop) if s > 0 else (hi >= stop):
            gap = j > k and ((op <= stop) if s > 0 else (op >= stop))
            reason, ex, jx = ("SL" if stop == o.sl else "SLD"), float(op if gap else stop), j
            break
        if not intra and o.tp is not None and ((hi >= o.tp) if s > 0 else (lo <= o.tp)):
            reason, ex, jx = "TP", float(o.tp), j
            break
        if intra or not o.protect:
            continue
        best = max(best, hi) if s > 0 else min(best, lo)
        fav = s * (best - fill) / risk
        cands = [stop]
        lvl = level_of(fav - cost_r, PROTECT_FIRST, PROTECT_STEP)
        if lvl > 0:
            cands.append(fill + s * risk * (nominal(lvl, PROTECT_FIRST, PROTECT_STEP) + cost_r))
        if o.be and fav >= ep.be_trigger_r:
            cands.append(fill + s * risk * (ep.be_lock_r + (cost_r if ep.be_cover_costs else 0)))
        stop = max(cands) if s > 0 else min(cands)
    fstep = fstep or funding_step(path)
    if not reason:
        fund, assumed = funding_paid(path, s, fill_t, path.end, ep, fstep)
        return Trade("ABIERTA", "", fill_t, fill, None, float(path.c[-1]), fee_in, 0.0, slip_in,
                     fund, assumed, s * (float(path.c[-1]) - fill) / fill, mk, o.sl)
    forced = reason not in ("SL", "SLD", "TP")
    exit_t = int(path.t[jx]) + (0 if forced else path.step)
    slip_out = 0.0 if reason == "TP" else _slip(path, jx, ep)
    fee_out = (cp.maker_fee if reason == "TP" else cp.taker_fee) * ex / fill
    fund, assumed = funding_paid(path, s, fill_t, exit_t, ep, fstep)
    return Trade("CERRADA", reason, fill_t, fill, exit_t, ex, fee_in, fee_out, slip_in + slip_out,
                 fund, assumed, s * (ex - fill) / fill, mk, o.sl)


#: Escalera vigente del perfil Moderado (1 % de riesgo, el de la cantera), en R netos. Solo sus
#: escalones: ni peso aprendido ni freno propio (nota §9.1, `params.NurseryParams`).
PROFILE = "moderado"
PROTECT_FIRST = LADDER_BY_PROFILE[PROFILE].first_r
PROTECT_STEP = LADDER_BY_PROFILE[PROFILE].step_r
