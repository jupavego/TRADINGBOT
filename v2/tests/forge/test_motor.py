"""El motor vectorizado de la forja es idéntico a un bucle lento de referencia (T208).

El bucle de abajo está escrito aparte, vela a vela, con las reglas de `PLAN/notas/T208_forja_5m.md`
§5: entrada en la apertura de la vela siguiente, stop antes que objetivo dentro de la vela, hueco a
la apertura, cierre forzoso de sesión y los costos del proyecto. Si el vectorizado se desvía en una
sola operación, esta prueba lo caza.
"""

from __future__ import annotations

import numpy as np
import pytest

from eim.forge import examine, space
from eim.forge.engine import HMAX, Market, Rules, simulate


def _ref(mk: Market, sig: np.ndarray, ex: space.Exit, rules: Rules,
         vwap: np.ndarray) -> list[dict]:
    """Operaciones de la receta, calculadas a mano."""
    cp = rules.costs
    out: list[dict] = []
    fin = -1
    for idx in np.flatnonzero(sig):
        e = int(idx) + 1
        if e <= fin or e >= len(mk.o):
            continue
        side = float(sig[idx])
        atr = mk.atr[idx]
        if not np.isfinite(atr) or atr <= 0 or not np.isfinite(mk.o[e]):
            continue
        last = int(mk.ss.last[e])
        if last <= e:
            continue
        d = ex.atr_k * atr
        p_e = mk.o[e] * (1 + side * cp.slip_entry_base_bps / 1e4)
        q = min(rules.r_dollar / d, rules.max_notional / p_e)
        sl0 = p_e - side * d
        tp = None
        if ex.kind == "objetivo":
            tp = p_e + side * ex.tp_r * d
        elif ex.kind == "nivel" and np.isfinite(vwap[idx]) and side * (vwap[idx] - p_e) > 0:
            tp = float(vwap[idx])
        hz = min(last - e, HMAX - 1)
        if ex.bars is not None:
            hz = min(hz, ex.bars)
        lvl, run = sl0, -np.inf
        kind, j, px = 3, hz, None
        for jj in range(hz + 1):
            b = e + jj
            adv = mk.l[b] if side > 0 else mk.h[b]
            fav = mk.h[b] if side > 0 else mk.l[b]
            if side * (adv - lvl) <= 0:
                kind, j = 0, jj
                px = mk.o[b] if side * (mk.o[b] - lvl) <= 0 else lvl
                break
            if tp is not None and side * (fav - tp) >= 0:
                kind, j, px = 1, jj, tp
                break
            if ex.kind == "giro" and sig[b] == -side:
                kind, j, px = 2, jj, mk.c[b]
                break
            if ex.kind == "trailing":
                run = max(run, side * fav)
                lvl = side * (run - d)
        if px is None:
            px = mk.c[e + hz]
        b = e + j
        if kind == 1:
            slip, fee_out = 0.0, cp.maker_fee
        else:
            rng = (mk.h[b] - mk.l[b]) / mk.o[b] if mk.o[b] > 0 else 0.0
            traded = mk.v[b] * mk.o[b]
            impact = (q * p_e / traded) if traded > 0 else 1.0
            slip = min(cp.slip_base_bps / 1e4 + cp.slip_vol_k * rng
                       + cp.slip_impact_k * impact / 1e4, cp.slip_cap_bps / 1e4)
            fee_out = cp.taker_fee
        fill = px * (1 - side * slip)
        pnl = side * (fill - p_e) * q - cp.taker_fee * q * p_e - fee_out * q * abs(fill)
        out.append({"entry": e, "exit": b, "kind": kind, "r": pnl / rules.r_dollar})
        fin = b
    return out


@pytest.mark.parametrize("exit_id", [e.id for e in space.EXITS])
def test_identico_al_bucle_lento(serie, sesiones, rasgos, exit_id):
    mk = examine.market(serie, sesiones, rasgos)
    rules = Rules()
    ex = next(e for e in space.EXITS if e.id == exit_id)
    trig = next(t for t in space.TRIGGERS if t.id == "ema_5_20")
    sig = space.signal(trig, "ambos", "ninguno", rasgos, sesiones.can_signal)
    assert np.count_nonzero(sig) > 20
    got = simulate(mk, sig, ex, rules)
    ref = _ref(mk, sig, ex, rules, rasgos["vwap_s"])
    assert len(got) == len(ref)
    np.testing.assert_array_equal(got.entry, [r["entry"] for r in ref])
    np.testing.assert_array_equal(got.exit, [r["exit"] for r in ref])
    np.testing.assert_array_equal(got.kind, [r["kind"] for r in ref])
    np.testing.assert_allclose(got.r, [r["r"] for r in ref], rtol=1e-9, atol=1e-12)
