"""T223 — La vela del llenado de una entrada límite en la escalera (BACKLOG T143 (5)).

`tests/fixtures/paper/t223_fill_bar.json` trae los seis pares de T143 que cambiaron de salida, con
sus velas reales de 15 m y 1 min de BTCUSDT y los parámetros de ejecución de cada mesa: misma idea,
mismo precio y mismo minuto de entrada; T31 entró a mercado y cerró por stop dinámico, t143 la
convirtió a límite y cerró por el SL inicial (−7,2 R). La causa: la escalera no miraba la vela del
llenado de una límite. Una entrada a mercado vive toda su primera vela (con 1 min si es ambigua) y
puede subir el SL en sus primeros minutos; la límite llenada a la apertura no podía proteger nada
hasta la vela siguiente.

Cada caso prueba que los datos son los del fallo (el mercado da lo que registró T31; la límite sin
las velas de 1 min de la vela del llenado da lo que registró t143) y que con ellas la límite ya
protege como la entrada a mercado, salvo el minuto del llenado, cuyo orden no se conoce.
"""

from __future__ import annotations

import json
import random
from pathlib import Path as FsPath

import numpy as np
import pytest

from eim.backtest.params import ZERO_COSTS
from eim.core import Candle
from eim.paper.engine import Outcome, Path
from eim.paper.ideas import Idea, to_limit
from eim.paper.ladder import simulate_ladder
from eim.paper.ladder_audit import audit_outcome
from eim.paper.params import LADDER_BY_PROFILE, ExecParams, LadderParams, spec_for
from tests.paper.helpers import M15, T0, bar, idea, walk

FIX = json.loads((FsPath(__file__).parents[1] / "fixtures" / "paper" / "t223_fill_bar.json")
                 .read_text(encoding="utf-8"))
EP = {"t31": ExecParams.model_validate(FIX["exec_t31"]),
      "t143": ExecParams.model_validate(FIX["exec_t143"])}
GROUP = {g["t"]: g for g in FIX["groups"]}
SPEC = spec_for("BTCUSDT")
M1 = 60_000


def _path(g: dict) -> Path:
    return Path([Candle(t=r[0], o=r[1], h=r[2], l=r[3], c=r[4], v=1.0) for r in g["candles"]],
                [tuple(f) for f in g["funding"]], M15)


def _fine(g: dict, skip_fill_bar: bool = False) -> Path:
    rows = [r for r in g["fine"] if not (skip_fill_bar and r[0] < g["t"] + M15)]
    return Path.from_arrays({k: np.array([r[n] for r in rows], dtype=float)
                             for n, k in enumerate(("t", "o", "h", "l", "c"))}, M1)


def _market(c: dict) -> Idea:
    return Idea(id=c["idea_id"], strategy=c["idea_id"].rsplit(":", 1)[1], family="indicadores",
                symbol="BTCUSDT", t=c["t"], side=c["side"], kind="market", entry=c["entry"],
                sl=c["sl"], tp=c["entry"] * (1 + c["side"] * 0.5), fill_ms=0,
                hold_ms=86_400_000, conf=0.5, why=("t223",))


def _run(c: dict, book: str, fine: Path) -> Outcome:
    i = _market(c) if book == "t31" else to_limit(_market(c), 1)
    return simulate_ladder(i, _path(GROUP[c["t"]]), EP[book], LADDER_BY_PROFILE.get(
        c["profile"], LadderParams()), c[book]["qty"], fine, spec=SPEC)


@pytest.mark.parametrize("c", FIX["cases"], ids=lambda c: f"{c['profile']}-{c['idea_id']}")
def test_real_pairs_reproduce_the_divergence_and_the_fix_closes_it(c):
    g = GROUP[c["t"]]
    mkt = _run(c, "t31", _fine(g))
    assert (mkt.reason, mkt.fill_t) == (c["t31"]["reason"], c["t"])      # los datos del fallo
    assert mkt.r == pytest.approx(c["t31"]["r"], abs=0.005)
    before = _run(c, "t143", _fine(g, skip_fill_bar=True))                # la regla anterior
    assert (before.reason, before.fill, before.fill_t) == ("SL", c["entry"], c["t"])
    assert before.r == pytest.approx(c["t143"]["r"], abs=0.005)
    after = _run(c, "t143", _fine(g))
    assert after.reason == "SLD" and after.fill_t == mkt.fill_t
    assert after.r > -0.1 and abs(after.r - mkt.r) < 0.2                  # ya no −1,1 R
    assert after.ladder["fine_resolved_bars"] >= 1 and audit_outcome(after) == []
    first = after.ladder["stop_history"][0]["t"]
    assert first >= c["t"] + 2 * M1          # el minuto del llenado no sube el SL (orden incierto)


# --- casos sintéticos ------------------------------------------------------------------------
E, QTY = 70_000.0, 0.1
ZERO = ExecParams(costs=ZERO_COSTS, funding_8h_assumed=0.0)
LP = LadderParams()                   # escalones fijos de +10 y +5 USDT: con 0,1 BTC, +100 y +50


def _case(walks: list[list[float]], kind: str, fine: bool = True) -> Outcome:
    """Largo en E con SL E − 500: a mercado, o la misma idea como límite al mismo precio."""
    ws = [walk(pts, T0 + k * M15) for k, pts in enumerate(walks)]
    path = Path([bar(T0 + k * M15, w[0].o, max(x.h for x in w), min(x.l for x in w), w[-1].c)
                 for k, w in enumerate(ws)])
    i = idea(entry=E, sl=E - 500, tp=E + 1500)
    i = to_limit(i, 1) if kind == "limit" else i
    return simulate_ladder(i, path, ZERO, LP, QTY, Path([c for w in ws for c in w], (), M1)
                           if fine else None, spec=spec_for("BTCUSDT"))


UP_THEN_DOWN = [[E, E + 140, E - 10], [E - 10, E - 600]]     # sube +14 USDT, cae y llega al SL


def test_limit_filled_at_the_open_protects_like_market():
    mkt, lim = _case(UP_THEN_DOWN, "market"), _case(UP_THEN_DOWN, "limit")
    assert (mkt.fill, mkt.fill_t) == (lim.fill, lim.fill_t) == (E, T0)
    assert mkt.reason == lim.reason == "SLD"
    assert mkt.exit == lim.exit == pytest.approx(E + 100)                 # primer escalón: +10
    assert audit_outcome(lim) == []


def test_without_fine_bars_the_fill_bar_only_checks_the_stop():
    lim = _case(UP_THEN_DOWN, "limit", fine=False)                        # regla conservadora
    assert lim.reason == "SL" and lim.exit == E - 500 and lim.ladder["stop_history"] == []


def test_the_fill_minute_itself_does_not_move_the_stop():
    """El orden dentro del minuto del llenado no se conoce: su avance no cuenta en la límite."""
    ws = [walk([E, E - 10], T0), walk([E - 10, E - 600], T0 + M15)]
    ws[0][0] = bar(T0, E, E + 150, E - 1, E - 1)                          # +15 USDT en el minuto 0
    path = Path([bar(T0, E, E + 150, E - 10, E - 10), bar(T0 + M15, E - 10, E - 10, E - 600,
                                                          E - 600)])
    fine = Path([c for w in ws for c in w], (), M1)
    i = idea(entry=E, sl=E - 500, tp=E + 1500)
    mkt = simulate_ladder(i, path, ZERO, LP, QTY, fine, spec=SPEC)
    lim = simulate_ladder(to_limit(i, 1), path, ZERO, LP, QTY, fine, spec=SPEC)
    assert mkt.reason == "SLD"            # a mercado el minuto 0 es posterior a la apertura
    assert lim.reason == "SL" and lim.ladder["stop_history"] == []


def test_stop_in_the_fill_minute_closes_at_the_initial_sl():
    ws = [walk([E + 50, E - 10], T0), walk([E - 10, E - 20], T0 + M15)]
    ws[0][3] = bar(T0 + 3 * M1, ws[0][3].o, ws[0][3].o, E - 600, ws[0][3].c)   # llena y cae
    path = Path([bar(T0, E + 50, E + 50, E - 600, E - 10), bar(T0 + M15, E - 10, E - 10, E - 20,
                                                               E - 20)])
    i = to_limit(idea(entry=E, sl=E - 500, tp=E + 1500), 1)
    o = simulate_ladder(i, path, ZERO, LP, QTY, Path([c for w in ws for c in w], (), M1),
                        spec=SPEC)
    assert o.reason == "SL" and o.exit == E - 500 and o.fill == E
    assert o.exit_t == T0 + 4 * M1                                        # al cerrar ese minuto


def test_fine_bars_that_miss_the_limit_fall_back_to_the_conservative_rule():
    """Si las velas de 1 min no tocan el precio límite (no cuadran con la de 15 m), manda la
    regla de la vela entera: no se inventa el minuto del llenado."""
    ws = [walk([E + 5, E + 140, E + 5], T0), walk([E + 5, E - 600], T0 + M15)]
    path = Path([bar(T0, E + 5, E + 140, E - 1, E + 5), bar(T0 + M15, E + 5, E + 5, E - 600,
                                                            E - 600)])
    i = to_limit(idea(entry=E, sl=E - 500, tp=E + 1500), 1)
    o = simulate_ladder(i, path, ZERO, LP, QTY, Path([c for w in ws for c in w], (), M1),
                        spec=SPEC)
    assert o.fill == E and o.reason == "SL" and o.ladder["fine_resolved_bars"] == 0


def test_limit_fill_bar_never_breaks_the_rules_fuzz():
    rng = random.Random(223)
    for case in range(60):
        side = 1 if case % 2 == 0 else -1
        px, walks = E + side * rng.uniform(0, 60), []
        for _ in range(rng.randint(2, 30)):
            pts = [px] + [px + rng.gauss(0, 120) for _ in range(rng.randint(2, 5))]
            walks.append(pts)
            px = pts[-1]
        ws = [walk(p, T0 + k * M15) for k, p in enumerate(walks)]
        path = Path([bar(T0 + k * M15, w[0].o, max(c.h for c in w), min(c.l for c in w), w[-1].c)
                     for k, w in enumerate(ws)])
        fine = Path([c for w in ws for c in w], (), M1)
        i = to_limit(idea(side=side, entry=E, sl=E - side * 500, tp=E + side * 1500), 4)
        o = simulate_ladder(i, path, ExecParams(), LP, QTY, fine, spec=SPEC)
        if o.ladder is None:                      # la límite no se llenó: no hay escalera
            assert o.status in ("CANCELADA", "PENDIENTE", "RECHAZADA"), case
            continue
        assert audit_outcome(o) == [], (case, o.ladder)
        if o.fill_t is not None and o.ladder["stop_history"]:
            assert o.ladder["stop_history"][0]["t"] >= o.fill_t + 2 * M1, case
