"""T212: la puerta del marco mayor publica su dirección, su giro y su retraso.

Solo BTCUSDT (foco del proyecto, T122) y sin red: las velas son sintéticas y el instante es fijo,
así que lo que se comprueba es la aritmética del retraso, no el mercado.
"""

from __future__ import annotations

from eim.core import Candle
from eim.paper import gates

H = 3_600_000
T0 = 1_790_000_000_000 // H * H     # instante redondo en ms


def candles(closes: list[float], bar: int = H, start: int = T0) -> list[Candle]:
    """Velas con `l`/`h` pegados al cierre: el extremo de la ventana es el cierre extremo."""
    return [Candle(t=start + i * bar, o=c, h=c, l=c, c=c, v=1.0) for i, c in enumerate(closes)]


def test_sin_velas_suficientes_no_hay_direccion() -> None:
    # tambien es el caso de la puerta de 4 h (EMA50/200): sin 200 velas no publica direccion
    g = gates.status("4h", "4h", 50, 200, candles([100.0] * 10), H, T0 + 10 * H)
    assert g.dir == 0 and g.since_t is None and g.hours is None
    assert "faltan velas de 4h para la EMA de 200" in g.text
    assert g.to_json()["label"] == "sin dato" and g.to_json()["disagrees"] is False


BAJA = [200.0 - i for i in range(100)]                     # 200 → 101, un punto por vela
REBOTE = [101.0 + 0.1 * i for i in range(1, 31)]           # 30 h de rebote suave: 101,1 → 104


def test_puerta_bajista_cuenta_horas_y_distancia_al_minimo() -> None:
    # tras 100 h de caída, un rebote del 3 % no mueve la EMA21 por encima de la EMA55
    cs = candles(BAJA + REBOTE)
    now = cs[-1].t + H
    g = gates.status("15m", "1h", 21, 55, cs, H, now, ("moderado", "agresivo"))
    assert g.dir == -1
    assert g.extreme_kind == "min" and g.extreme_px == 101.0
    assert g.move_pct > 0 and g.against_pct == g.move_pct   # el precio subió contra la puerta
    assert g.hours is not None and g.hours > 0
    assert g.since_t is not None and g.since_t <= now
    assert g.enforced_by == ("moderado", "agresivo")
    assert g.disagrees is True                              # > 24 h y > 2 % en contra
    assert "bajista desde hace" in g.text and "mínimo de 7 d" in g.text


def test_el_giro_se_fecha_en_la_vela_en_que_cambio() -> None:
    cs = candles(BAJA + [101.0 + 2 * i for i in range(1, 121)])
    now = cs[-1].t + H
    g = gates.status("15m", "1h", 21, 55, cs, H, now)
    assert g.dir == 1 and g.since_t is not None
    # en `since_t` la puerta ya era alcista y una vela antes todavía no
    assert gates.HtfTrend(cs, H, 21, 55).at(g.since_t) == 1
    assert gates.HtfTrend(cs, H, 21, 55).at(g.since_t - H) == -1
    assert g.hours == (now - g.since_t) / H
    assert g.extreme_kind == "max"                          # a la alcista la contradice el máximo


def test_no_se_adelanta_a_las_velas_cerradas() -> None:
    cs = candles(BAJA + REBOTE)
    media = cs[110].t + H                                   # a mitad del rebote
    g = gates.status("15m", "1h", 21, 55, cs, H, media)
    assert g.dir == -1 and g.since_t is not None and g.since_t <= media
    assert g.price == cs[110].c                             # el último cierre de ENTONCES
    assert g.hours == (media - g.since_t) / H


def test_sin_desacuerdo_cuando_el_recorrido_en_contra_es_pequeno() -> None:
    cs = candles(BAJA + [101.0, 101.1])
    g = gates.status("1h", "4h", 21, 55, cs, H, cs[-1].t + H)
    assert g.dir == -1 and g.against_pct is not None
    assert g.against_pct < gates.DISAGREE_PCT and g.disagrees is False


def test_el_json_lleva_los_umbrales_y_el_texto() -> None:
    cs = candles(BAJA + REBOTE)
    j = gates.status("4h", "4h", 21, 55, cs, H, cs[-1].t + H).to_json()
    assert j["thresholds"] == {"disagree_h": gates.DISAGREE_H,
                               "disagree_pct": gates.DISAGREE_PCT,
                               "window_h": gates.WINDOW_MS / H}
    assert j["timeframe"] == "4h" and j["htf"] == "4h" and j["fast"] == 21 and j["slow"] == 55
    assert j["dir"] == -1 and j["label"] == "bajista" and isinstance(j["text"], str)
