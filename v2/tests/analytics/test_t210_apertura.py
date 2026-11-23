"""T210 — patrón de apertura: rejilla, horarios con verano, reglas y congelado del pre-registro.

Sin red: todas las velas se construyen a mano.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pytest

from eim.analytics import apertura as A
from eim.analytics import apertura_report as R
from eim.core import Candle

MIN = 60_000


def ms(txt: str) -> int:
    return int(datetime.fromisoformat(txt).replace(tzinfo=UTC).timestamp() * 1000)


def velas(t0: int, cierres: list[float], alto: float = 0.0, bajo: float = 0.0) -> list[Candle]:
    """Velas de 1 m encadenadas: la apertura de cada una es el cierre de la anterior."""
    out, prev = [], cierres[0]
    for i, c in enumerate(cierres):
        o = prev if i else cierres[0]
        out.append(Candle(t=t0 + i * MIN, o=o, h=max(o, c) + alto, l=min(o, c) - bajo, c=c,
                          v=1.0))
        prev = c
    return out


def test_rejilla_deja_huecos_en_nan():
    cs = [Candle(t=0, o=1, h=1, l=1, c=1, v=1), Candle(t=2 * MIN, o=2, h=2, l=2, c=2, v=1)]
    b = A.bars_from_candles(cs)
    assert len(b) == 3
    assert np.isnan(b.c[1])          # el minuto que falta no se inventa
    assert b.c[0] == 1 and b.c[2] == 2


def test_apertura_de_londres_sigue_al_horario_de_verano():
    # 08:00 de Londres es 07:00 UTC en verano y 08:00 UTC en invierno.
    verano = A.bars_from_candles(velas(ms("2026-07-15T06:55:00"), [100.0] * 20))
    invierno = A.bars_from_candles(velas(ms("2026-12-15T07:55:00"), [100.0] * 20))
    iv = A.opens(verano, "Europe/London", 8, 0)
    ii = A.opens(invierno, "Europe/London", 8, 0)
    assert datetime.fromtimestamp(verano.t[iv[0]] / 1000, UTC).hour == 7
    assert datetime.fromtimestamp(invierno.t[ii[0]] / 1000, UTC).hour == 8


def test_fin_de_semana_fuera():
    sabado = A.bars_from_candles(velas(ms("2026-11-21T07:55:00"), [100.0] * 20))
    assert A.opens(sabado, "Europe/London", 8, 0).size == 0


def test_contra_a_mide_la_reversion_y_descuenta_el_coste():
    # A sube (100 -> 103) y los 3 minutos siguientes bajan: el contrario gana.
    cs = velas(ms("2026-11-23T08:00:00"), [100.0, 101.0, 103.0, 102.0, 101.0, 100.0, 100.0])
    b = A.bars_from_candles(cs)
    op = A.contra_a(b, 0, 3, 3, costo_bps=9.0)
    assert op is not None
    assert op["lado"] == -1.0                      # A fue al alza -> se entra corto
    assert op["sentido"] == "revirtio"
    assert op["bruto_bps"] == pytest.approx(1e4 * (1 - 100.0 / 103.0), rel=1e-6)
    assert op["neto_bps"] == pytest.approx(op["bruto_bps"] - 9.0)


def test_contra_a_descarta_el_tramo_a_plano():
    cs = velas(ms("2026-11-23T08:00:00"), [100.0, 101.0, 100.0, 99.0, 98.0, 97.0, 97.0])
    b = A.bars_from_candles(cs)
    assert A.contra_a(b, 0, 3, 3, 9.0) is None     # A == 0 no define el patrón


def test_canal_ruptura_cobra_el_objetivo_de_una_anchura():
    cierres = [100.0, 101.0, 100.5] + [103.0] + [112.0] * 3 + [112.0] * 300
    b = A.bars_from_candles(velas(ms("2026-11-23T08:00:00"), cierres))
    alto, bajo = A.canal(b, 0, 3)
    r = A.canal_op(b, 0, 3, "ruptura", ventana=5, tope=240, costo_bps=6.3)
    assert r["lleno"] is True and r["lado"] == 1.0
    assert r["entrada"] == pytest.approx(alto)
    assert r["motivo"] == "objetivo"
    assert r["bruto_bps"] == pytest.approx(1e4 * (alto - bajo) / alto, rel=1e-6)


def test_empate_en_el_mismo_minuto_cuenta_como_stop():
    # Vela ancha que toca objetivo y stop a la vez: el criterio conservador elige el stop.
    cs = velas(ms("2026-11-23T08:00:00"), [100.0, 101.0, 100.5], alto=0.0, bajo=0.0)
    cs += [Candle(t=cs[-1].t + MIN, o=100.5, h=101.2, l=100.4, c=101.1, v=1.0)]
    cs += [Candle(t=cs[-1].t + MIN, o=101.1, h=130.0, l=70.0, c=101.0, v=1.0)]
    cs += velas(cs[-1].t + MIN, [101.0] * 300)
    b = A.bars_from_candles(cs)
    r = A.canal_op(b, 0, 3, "ruptura", ventana=5, tope=240, costo_bps=0.0)
    assert r["lleno"] is True and r["motivo"] == "stop" and r["bruto_bps"] < 0


def test_romper_los_dos_bordes_en_un_minuto_queda_ambigua():
    cs = velas(ms("2026-11-23T08:00:00"), [100.0, 101.0, 100.5])
    cs += [Candle(t=cs[-1].t + MIN, o=100.5, h=140.0, l=60.0, c=100.5, v=1.0)]
    cs += velas(cs[-1].t + MIN, [100.5] * 300)
    b = A.bars_from_candles(cs)
    r = A.canal_op(b, 0, 3, "ruptura", ventana=5, tope=240, costo_bps=0.0)
    assert r["lleno"] is False and r["ambigua"] is True


def test_falta_de_velas_no_inventa_operacion():
    b = A.bars_from_candles(velas(ms("2026-11-23T08:00:00"), [100.0] * 10))
    assert A.canal_op(b, 0, 3, "ruptura", ventana=5, tope=240, costo_bps=0.0) is None


def test_resumen_y_potencia():
    s = A.resumen([1.0, 2.0, 3.0, float("nan")])
    assert s["n"] == 3 and s["media_bps"] == pytest.approx(2.0)
    assert s["aciertos_pct"] == 100.0
    assert A.n_necesaria(10.0, 2.0) == pytest.approx((2.80 * 5) ** 2)
    assert A.n_necesaria(10.0, 0.0) == float("inf")


def test_veredicto_exige_muestra_y_signo():
    base = {"n_minima": 100}
    assert "sin veredicto" in A.veredicto({"n": 10, "media_bps": 5, "t": 9}, base, 2.0)
    assert A.veredicto({"n": 200, "media_bps": 5, "t": 3}, base, 2.0).startswith("PASA")
    assert A.veredicto({"n": 200, "media_bps": -1, "t": -3}, base, 2.0).startswith("NO PASA")
    assert A.veredicto({"n": 200, "media_bps": 1, "t": 0.5}, base, 2.0).startswith("NO CONCLUYE")


def test_prereg_publicado_no_se_puede_editar():
    pr = A.load_prereg()
    assert pr["sha256"] == A.PUBLISHED[A.DEFAULT_VERSION], (
        "el pre-registro cambió: eso es una versión nueva con reloj nuevo, no una edición")
    assert pr["k"] == 3 and len(pr["zonas"]) == 5
    assert pr["reloj"]["muestra_hacia_delante_desde"] == "2026-11-24T00:00:00Z"
    cand = [v["id"] for v in pr["variantes"] if v["papel"] == "candidatura"]
    assert cand == ["canal_ruptura"]


def test_prereg_manipulado_falla(tmp_path):
    pr = json.loads((A.PREREG_DIR / f"{A.DEFAULT_VERSION}.json").read_text(encoding="utf-8"))
    pr["k"] = 5
    p = tmp_path / f"{A.DEFAULT_VERSION}.json"
    p.write_text(json.dumps(pr), encoding="utf-8")
    with pytest.raises(ValueError, match="reloj nuevo"):
        A.load_prereg(path=p)


def test_registro_no_duplica_aperturas(tmp_path):
    filas = [{"zona": "londres", "t": 1, "contra_a_3m": -9.0},
             {"zona": "tokio", "t": 2, "contra_a_3m": +3.0}]
    reg = tmp_path / "aperturas.jsonl"
    assert R.acumular(reg, filas, "abc123") == (2, 2)
    assert R.acumular(reg, filas, "abc123") == (0, 2)       # idempotente
    assert len(R.leer_registro(reg, 0)) == 2
    assert len(R.leer_registro(reg, 2)) == 1                 # respeta la ventana
