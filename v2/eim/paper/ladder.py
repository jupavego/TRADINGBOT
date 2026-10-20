"""Protección progresiva de ganancias (perfil PPP): SL dinámico por escalones de beneficio neto.

Reglas (deterministas; ningún agente las toca una vez abierta la posición):
- Fase A: manda el SL inicial (el de la idea, dimensionado por riesgo).
- Fase B: cuando el beneficio NETO estimado máximo llega a `first_usdt` (10) se activa la
  protección y el SL pasa al precio cuyo neto es ese nivel; cada `step_usdt` (5) más de beneficio
  máximo sube un escalón (10, 15, 20, …). Sin TP final y sin cierre por tiempo: solo cierra el
  SL vigente. La protección nunca baja, ni vuelve a la entrada.
- Beneficio neto estimado de salir a un precio `p` (misma contabilidad que `engine.Outcome.net`,
  en USDT con `qty` BTC y entrada `f`):
      neto(p) = qty·(lado·(p − f) − fee_sal·p) − qty·f·(fee_ent + desl_ent + desl_sal + funding)
  Precio de protección del nivel L (despeje exacto; luego se redondea al tick EN CONTRA del
  operador —largo arriba, corto abajo— y se vuelve a comprobar `neto ≥ L`):
      largo : p = (L/qty + f·(1+K)) / (1 − fee_sal)       K = fee_ent+desl_ent+desl_sal+funding
      corto : p = (f·(1−K) − L/qty) / (1 + fee_sal)
- Camino de 15 m, sin anticipación y conservador: en cada vela primero se comprueba el SL vigente
  AL ABRIR la vela (un hueco más allá se ejecuta a la apertura); el avance de esa vela solo sube
  el SL desde la vela SIGUIENTE (no se sabe si el extremo llegó antes o después del retroceso).
  Si una vela cruza varios escalones se aplica el último confirmado por su extremo.
- Estimado vs realizado: el SL se calcula con una RESERVA: el mayor deslizamiento de las últimas
  `slip_lookback` velas (datos ya conocidos) y `funding_reserve` liquidaciones futuras de funding;
  al salir se cobra el de la vela real y el funding hasta ese
  momento, así que el neto realizado puede diferir del nominal (hueco, vela más ancha).
- Datos no finitos en una vela = incidencia técnica: la posición queda ABIERTA marcada
  «incidencia», sin cierre inventado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from eim.paper.engine import Outcome, Path, _funding, _limit_fill, _slip, _stop_exit, _with_r
from eim.paper.ideas import Idea
from eim.paper.params import ExecParams, LadderParams

EPS = 1e-9


@dataclass(frozen=True)
class LadderCosts:
    """Costos de entrada (ya conocidos) y de salida a SL (estimados), como fracciones."""

    fee_in: float
    slip_in: float
    fee_out: float
    slip_out: float


def net_usd(side: int, qty: float, fill: float, price: float, funding: float,
            c: LadderCosts) -> float:
    """Beneficio neto (USDT) de cerrar `qty` a `price`, con todos los costos modelados."""
    k = c.fee_in + c.slip_in + c.slip_out + funding
    return qty * (side * (price - fill) - c.fee_out * price) - qty * fill * k


def protect_price(side: int, qty: float, fill: float, level: float, funding: float,
                  c: LadderCosts, tick: float) -> float:
    """Precio de SL cuyo neto estimado es `level` USDT, redondeado al tick y verificado."""
    k = c.fee_in + c.slip_in + c.slip_out + funding
    if side > 0:
        exact = (level / qty + fill * (1 + k)) / (1 - c.fee_out)
        n = math.ceil(exact / tick - EPS)
    else:
        exact = (fill * (1 - k) - level / qty) / (1 + c.fee_out)
        n = math.floor(exact / tick + EPS)
    for _ in range(5):                       # el redondeo nunca puede dejar el neto bajo el nivel
        price = round(n * tick, 8)
        if net_usd(side, qty, fill, price, funding, c) >= level - EPS:
            return price
        n += side
    return round(n * tick, 8)


def level_of(max_float: float, lp: LadderParams) -> int:
    """Escalón confirmado por el beneficio neto máximo (0 = aún sin protección)."""
    if max_float + EPS < lp.first_usdt:
        return 0
    return 1 + int(math.floor((max_float - lp.first_usdt) / lp.step_usdt + EPS))


def nominal(level: int, lp: LadderParams) -> float:
    """Beneficio neto nominal protegido por un escalón (10, 15, 20, …)."""
    return lp.first_usdt + (level - 1) * lp.step_usdt if level > 0 else 0.0


def floor_qty(qty: float, lp: LadderParams) -> float:
    return math.floor(qty / lp.qty_step + EPS) * lp.qty_step


def costs_for(fee_in: float, slip_in: float, ep: ExecParams) -> LadderCosts:
    cp = ep.costs
    return LadderCosts(fee_in, slip_in, cp.taker_fee, cp.slip_base_bps / 1e4)


def _entry(idea: Idea, path: Path, ep: ExecParams) -> tuple[str, int, int, float, float, float]:
    """('ok'|'pending'|'cancel'|'expired', k, start, fill, fee_in, slip_in)."""
    s, cp = idea.side, ep.costs
    j0 = int(np.searchsorted(path.t, idea.t))
    if j0 >= len(path.t):
        return "pending", 0, 0, 0.0, 0.0, 0.0
    if idea.kind == "market":
        slip = _slip(path, j0, ep)
        return "ok", j0, j0, float(path.o[j0]) * (1 + s * slip), cp.taker_fee, slip
    what, k = _limit_fill(idea, path, j0)
    if what == "fill":
        return "ok", int(k), int(k) + 1, idea.entry, cp.maker_fee, 0.0
    return ("pending" if what == "pending" else "cancel" if what == "cancel_tp" else "expired",
            int(k or 0), 0, 0.0, 0.0, 0.0)


def simulate_ladder(idea: Idea, path: Path, ep: ExecParams, lp: LadderParams,
                    qty: float) -> Outcome:
    """Simula la operación con SL inicial y escalera de protección (sin TP ni tiempo)."""
    s = idea.side
    what, k, start, fill, fee_in, slip_in = _entry(idea, path, ep)
    if what == "pending":
        return Outcome(idea, "PENDIENTE")
    if what == "expired":
        return Outcome(idea, "CANCELADA", "NO_LLENADA", exit_t=idea.t + idea.fill_ms)
    if what == "cancel":
        return Outcome(idea, "CANCELADA", "OBJETIVO_SIN_LLENAR",
                       exit_t=int(path.t[k]) + path.step)
    fill_t = int(path.t[k])
    if (fill - idea.sl) * s <= ep.min_risk_frac * fill:
        return Outcome(idea, "RECHAZADA", "GEOMETRIA", exit_t=fill_t, fill=fill)
    risk = abs(fill - idea.sl)
    c = costs_for(fee_in, slip_in, ep)
    stop, level, max_float, hist, incident = idea.sl, 0, -math.inf, [], ""
    c_stop = c
    reason, ex, jx, last_ok = "", None, None, k
    if start > k and ((path.l[k] <= idea.sl) if s > 0 else (path.h[k] >= idea.sl)):
        reason, ex, jx = "SL", idea.sl, k                # límite llenada y SL en la misma vela
    else:
        for j in range(start, len(path.t)):
            o, h, lo, cl = float(path.o[j]), float(path.h[j]), float(path.l[j]), float(path.c[j])
            if not all(math.isfinite(x) for x in (o, h, lo, cl)):
                incident = f"vela sin datos válidos en t={int(path.t[j])}"
                break
            last_ok = j
            if (lo <= stop) if s > 0 else (h >= stop):    # SL vigente AL ABRIR la vela
                reason, ex, jx = ("SLD" if level else "SL"), _stop_exit(path, s, j, stop, k), j
                break
            fav = h if s > 0 else lo
            end = int(path.t[j]) + path.step
            fund = _funding(path, s, fill_t, end, ep)[0]
            fund += max(0.0, s * ep.funding_8h_assumed) * lp.funding_reserve   # reserva de funding
            slip = max(_slip(path, x, ep) for x in range(max(start, j - lp.slip_lookback + 1),
                                                         j + 1))
            cj = replace(c, slip_out=slip)                    # deslizamiento esperado (reserva)
            max_float = max(max_float, net_usd(s, qty, fill, fav, fund, cj))
            new = level_of(max_float, lp)
            if new > level:
                p = protect_price(s, qty, fill, nominal(new, lp), fund, cj, lp.tick)
                if (p - stop) * s > 0 and (fav - p) * s >= 0:   # solo sube y está demostrado
                    stop, level, c_stop = p, new, cj
                    hist.append({"t": end, "level": level, "nominal": nominal(level, lp),
                                 "stop": stop, "max_float": max_float})
    end_i = jx if jx is not None else last_ok
    hi, lo = float(path.h[k:end_i + 1].max()), float(path.l[k:end_i + 1].min())
    mfe = max(0.0, ((hi if s > 0 else lo) - fill) * s) / risk
    mae = max(0.0, (fill - (lo if s > 0 else hi)) * s) / risk
    info = {"qty": qty, "level": level, "nominal_usd": nominal(level, lp),
            "max_float_usd": None if max_float == -math.inf else max_float, "stop": stop,
            "initial_sl": idea.sl, "stop_history": hist, "incident": incident,
            "levels": [h_["nominal"] for h_ in hist], "last_bar_t": int(path.t[end_i]) + path.step}
    if reason:
        exit_t = int(path.t[jx]) + path.step
        fund, assumed = _funding(path, s, fill_t, exit_t, ep)
        slip_out = _slip(path, jx, ep)
        fee_out = ep.costs.taker_fee * ex / fill
        info |= {"state": "cerrada_sl_dinamico" if level else "cerrada_sl_inicial",
                 "protected_est_usd": net_usd(s, qty, fill, stop, fund, c_stop) if level else None,
                 "elapsed_ms": exit_t - fill_t}
        return _with_r(Outcome(idea, "CERRADA", reason, fill_t, fill, exit_t, ex, fee_in, fee_out,
                               slip_in + slip_out, fund, assumed, s * (ex - fill) / fill, None,
                               mfe, mae, ladder=info))
    mark = float(path.c[end_i])
    fund, assumed = _funding(path, s, fill_t, int(path.t[end_i]) + path.step, ep)
    info |= {"state": "incidencia" if incident else "protegida" if level else "inicial",
             "float_usd": net_usd(s, qty, fill, mark, fund, c),
             "elapsed_ms": int(path.t[end_i]) + path.step - fill_t}
    return _with_r(Outcome(idea, "ABIERTA", "", fill_t, fill, None, None, fee_in, 0.0, slip_in,
                           fund, assumed, s * (mark - fill) / fill, None, mfe, mae, mark,
                           ladder=info))
