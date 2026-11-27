"""El lado del libro y el signo de las puertas (T215): sesgo, contraste y lectura de cada puerta."""

from __future__ import annotations

import math
import random

import pytest

from eim.analytics.audit import sides
from eim.core import Candle

NOW = 1_800_000_000_000
H = 3_600_000


def _trade(side: int, *, r=0.1, pnl=10.0, days_ago=1.0, scope="", tf="15m", opened=None) -> dict:
    return {"side": side, "r": r, "pnl_usdt": pnl, "scope": scope, "symbol": "BTCUSDT",
            "timeframe": tf, "opened_t": NOW - int(days_ago * sides.DAY_MS)
            if opened is None else opened,
            "exit_t": NOW - int(days_ago * sides.DAY_MS)}


def test_el_reparto_por_lado_y_las_horas_sin_largos():
    rows = [_trade(-1, pnl=-5.0) for _ in range(9)] + [_trade(1, pnl=20.0, days_ago=10.0)]
    s = sides.book_sides(rows, NOW)
    assert s["n"] == 10 and s["short"] == 9 and s["long"] == 1
    assert s["short_share"] == pytest.approx(0.9) and s["dominant"] == "short"
    assert s["pnl_short"] == pytest.approx(-45.0) and s["pnl_long"] == pytest.approx(20.0)
    # la ventana corta se recorta por cierre, como el resto de la auditoría
    assert s["last7"]["n"] == 9 and s["last7"]["long"] == 0
    assert s["no_long_h"] == pytest.approx(240.0) and s["no_short_h"] == pytest.approx(24.0)
    assert sides.split([])["short_share"] is None


def test_el_contraste_se_agrupa_por_vela_para_no_inflar_la_muestra():
    """20 velas, y en cada una 10 ideas largas iguales: agrupado son 20 datos, no 200."""
    rows = []
    for i in range(20):
        t = NOW - (i + 1) * H
        rows += [_trade(1, r=-0.5, scope="sombra", opened=t) for _ in range(10)]
        rows += [_trade(-1, r=+0.5, scope="sombra", opened=t)]
    rows.append(_trade(1, r=9.9, opened=NOW - H))      # no es sombra: no entra
    c = sides.contrast(rows, NOW)
    assert c["n"] == 220
    assert c["by_side"]["long"]["n"] == 200 and c["grouped"]["long"]["n"] == 20
    assert c["by_side"]["short"]["n"] == 20 and c["grouped"]["short"]["n"] == 20
    assert c["diff_grouped"]["diff"] == pytest.approx(-1.0)
    assert c["reads"] and c["verdict"] == "el lado largo rinde peor"


def test_el_contraste_sin_muestra_no_se_lee():
    rows = [_trade(1, scope="sombra") for _ in range(3)] + [_trade(-1, scope="sombra")]
    c = sides.contrast(rows, NOW)
    assert not c["reads"] and c["verdict"] == "sin muestra"
    assert sides.contrast([], NOW)["n"] == 0


def _candles(closes: list[float], bar=H) -> list[Candle]:
    t0 = NOW - len(closes) * bar
    return [Candle(t=t0 + i * bar, o=c, h=c, l=c, c=c, v=1.0) for i, c in enumerate(closes)]


def _noise(seed: int, n: int = 1500) -> list[float]:
    rnd, px, out = random.Random(seed), 100.0, []
    for _ in range(n):
        px *= math.exp(rnd.gauss(0, 0.004))
        out.append(px)
    return out


def test_una_puerta_con_signo_se_distingue_de_una_de_ruido():
    # ciclos de verdad: cuando la puerta gira a alcista, las 24 h siguientes suben
    cycle = ([100.0 * math.exp(0.004 * i) for i in range(120)]
             + [100.0 * math.exp(0.004 * 120) * math.exp(-0.004 * i) for i in range(120)])
    cs = _candles(cycle * 6)
    s = sides.gate_sign(cs, cs, H, 21, 55, horizon_h=24)
    assert s["reads"] and s["stretches"] >= 6 and s["from_flip"]
    assert s["verdict"] == sides.SIGN_OK and s["diff_pct"] > s["mdd_pct"]
    # dos tramos largos (sube y baja): no hay giros que medir
    up = [100.0 * math.exp(0.002 * i) for i in range(400)]
    lento = _candles(up + [up[-1] * math.exp(-0.002 * i) for i in range(400)])
    assert sides.gate_sign(lento, lento, H, 21, 55)["verdict"] == "muestra corta"
    assert sides.gate_sign([], [], H, 21, 55)["reads"] is False


def test_el_signo_se_mide_desde_el_giro_para_que_el_ruido_no_lo_aparente():
    """Promediar las velas de cada tramo inventa signo: su ventana cae al otro lado del giro.

    Con 12 caminatas aleatorias puras, aquella versión daba «distingue al revés» en 10; midiendo
    desde el giro, ninguna aparenta señal (parte del −0,180 % de T212 §5 era ese artefacto).
    """
    verdicts = set()
    for seed in range(12):
        cs = _candles(_noise(seed))
        s = sides.gate_sign(cs, cs, H, 21, 55, horizon_h=24)
        assert s["reads"] and s["measured"] <= s["stretches"]
        verdicts.add(s["verdict"])
    assert verdicts == {"no distingue dirección"}


def test_las_puertas_salen_con_el_reloj_comun():
    cs = _candles([100.0 + i for i in range(300)])
    cs4 = _candles([100.0 + 4 * i for i in range(300)], bar=4 * H)
    out = sides.gate_signs({"1h": cs, "4h": cs4}, {"15m": ("1h", 21, 55), "1h": ("4h", 21, 55)},
                           {"1h": H, "4h": 4 * H})
    assert [x["timeframe"] for x in out] == ["15m", "1h"]
    assert out[0]["htf"] == "1h" and out[1]["htf"] == "4h"
    assert all(x["horizon_h"] == sides.HORIZON_H for x in out)


def test_las_tres_lineas_son_informativas_y_nunca_proponen_cambiar_la_puerta():
    s = sides.book_sides([_trade(-1) for _ in range(30)], NOW)
    c = sides.contrast([_trade(1, r=-0.5, scope="sombra", opened=NOW - (i + 1) * H)
                        for i in range(30)]
                       + [_trade(-1, r=0.5, scope="sombra", opened=NOW - (i + 1) * H)
                          for i in range(30)], NOW)
    signs = [{"timeframe": "15m", "htf": "1h", "fast": 21, "slow": 55, "reads": True,
              "stretches": 40, "horizon_h": 24, "up": {"stretches": 20, "ret_pct": -0.98},
              "down": {"stretches": 20, "ret_pct": 0.46}, "diff_pct": -1.44, "mdd_pct": 0.89,
              "verdict": "distingue al revés (alcista rinde peor)"}]
    out = {o["id"]: o for o in sides.side_opps(s, c, signs)}
    assert set(out) == {"sesgo_lado", "contraste_lados", "puerta_sin_signo"}
    assert all(o["route"].startswith("cerrada") for o in out.values())
    assert all(o["category"] == "dirección" and "T215" in o["ref"] for o in out.values())
    assert "30 de 30 cortas (100.0%)" in out["sesgo_lado"]["evidence"]
    assert "40 tramos" in out["puerta_sin_signo"]["evidence"]
    assert "al revés" in out["puerta_sin_signo"]["evidence"]
    # un libro equilibrado no genera la línea del sesgo, y una puerta con signo tampoco la suya
    eq = sides.book_sides([_trade(1) for _ in range(5)] + [_trade(-1) for _ in range(5)], NOW)
    ok = [signs[0] | {"verdict": sides.SIGN_OK}]
    assert {o["id"] for o in sides.side_opps(eq, None, ok)} == set()
    assert sides.side_opps(None, None, None) == []


def test_la_linea_del_lado_dice_el_veredicto_del_agrupado():
    s = sides.book_sides([_trade(-1) for _ in range(9)] + [_trade(1, days_ago=3.0)], NOW)
    c = sides.contrast([_trade(1, r=-0.5, scope="sombra", opened=NOW - (i + 1) * H)
                        for i in range(25)]
                       + [_trade(-1, r=0.5, scope="sombra", opened=NOW - (i + 1) * H)
                          for i in range(25)], NOW)
    line = sides.text(s, c)
    assert "9/10 cortas (90.0%)" in line and "7 d 9/1" in line
    assert "última larga hace 72 h" in line and "el lado largo rinde peor" in line
    assert "sombra" in sides.text(s, c) and "sombra" not in sides.text(s, None)
