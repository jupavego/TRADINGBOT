"""T144 — La regla del universo oficial: qué cuenta como resultado y qué no.

Una sola función responde (`eim.paper.universe.counts_as_result`) y aquí se fija su regla caso a
caso, incluida la parte que motivó la tarea: una operación `retro` nunca entra en una cifra de
resultado, y las que quedan fuera salen declaradas con su motivo en vez de desaparecer.
"""

from __future__ import annotations

from eim.paper import accounting, universe
from eim.paper.params import PROFILES as PROFILE_PARAMS


def row(**kw) -> dict:
    """Una fila del libro que cuenta; cada prueba rompe una sola dimensión."""
    base = {"ledger_id": "perfil|agresivo|BTCUSDT|i1", "scope": "perfil", "profile": "agresivo",
            "symbol": "BTCUSDT", "idea_id": "i1", "origin": "vivo", "weight": 1.0,
            "retro": False, "exit_t": 1_792_400_000_000, "r": 0.5, "pnl_usdt": 10.0,
            "floor_trade": False, "reason": "SLD"}
    return {**base, **kw}


def test_una_fila_vivida_con_peso_cuenta() -> None:
    v = universe.counts_as_result(row())
    assert v.counts and v.code == universe.COUNTS_CODE
    assert "cuenta como resultado" in v.why


def test_retro_nunca_cuenta() -> None:
    v = universe.counts_as_result(row(retro=True))
    assert not v.counts and v.code == "retro"
    assert "nadie la vivió" in v.why
    # y da igual cómo venga escrito el booleano (la base, el CSV y la API no coinciden)
    for x in (True, "True", "true", 1):
        assert not universe.counts_as_result(row(retro=x)).counts
    for x in (False, "False", "", None, 0):
        assert universe.counts_as_result(row(retro=x)).counts


def test_sombra_no_es_resultado() -> None:
    v = universe.counts_as_result(row(scope="sombra", profile=""))
    assert not v.counts and v.code == universe.SHADOW


def test_lo_reconstruido_y_lo_sin_peso_no_cuentan() -> None:
    assert universe.counts_as_result(row(origin="backtest")).code == "no_vivo"
    assert universe.counts_as_result(row(weight=0.0)).code == "sin_peso"
    assert universe.counts_as_result(row(weight=None)).code == "sin_peso"


def test_perfil_desconocido_se_cuenta_aparte() -> None:
    assert universe.counts_as_result(row(profile="experimento")).code == "perfil_desconocido"


def test_una_fila_que_no_declara_retro_no_cuenta() -> None:
    """Sin esa columna no se puede saber si se vivió: lo que no se declara, no suma."""
    sin = {k: v for k, v in row().items() if k != "retro"}
    assert universe.counts_as_result(sin).code == "sin_declarar"
    assert accounting.figures([sin])["n"] == 0


def test_sin_cierre_ni_resultado_no_cuenta() -> None:
    assert universe.counts_as_result(row(exit_t=None)).code == "abierta"
    assert universe.counts_as_result(row(r=None)).code == "sin_resultado"
    assert universe.counts_as_result(row(pnl_usdt="")).code == "sin_resultado"


def test_entrada_de_suelo_si_cuenta_pero_se_informa_aparte() -> None:
    assert universe.counts_as_result(row(floor_trade=True)).counts
    f = accounting.figures([row(floor_trade=True), row(ledger_id="x", idea_id="x")])
    assert f["n"] == 2 and f["floor_trades"] == 1


def test_el_carril_de_operacion_es_vista_no_cifra_oficial() -> None:
    v = universe.counts_as_result(row(lane=universe.OPERATION_VIEW))
    assert not v.counts and v.code == universe.OPERATION_VIEW


def test_los_perfiles_del_universo_son_los_del_broker() -> None:
    assert universe.PROFILES == tuple(p.id for p in PROFILE_PARAMS)
    # que sigan siendo estos cuatro es parte de la decisión: añadir uno cambia el universo
    assert set(universe.PROFILES) == {"conservador", "moderado", "agresivo", "ppp_btcusdt"}


def test_el_recuento_declara_cuantas_cuentan_y_por_que_no_las_demas() -> None:
    rows = [row(), row(ledger_id="a", retro=True), row(ledger_id="b", scope="sombra"),
            row(ledger_id="c", weight=0)]
    t = universe.tally(rows)
    assert t == {"universe": universe.OFFICIAL, "n_total": 4, "n_counted": 1,
                 "excluded": {"retro": 1, "sin_peso": 1, universe.SHADOW: 1},
                 "excluded_why": {k: universe.EXCLUSIONS[k]
                                  for k in sorted(("retro", "sin_peso", universe.SHADOW))},
                 "retro": 1}


def test_la_declaracion_publica_la_regla_entera() -> None:
    d = universe.declaration()
    assert d["universe"] == universe.OFFICIAL
    dims = {x["dimension"] for x in d["rule"]}
    # las cinco dimensiones que la ficha exige declarar, más el cierre
    assert {"alcance", "perfil", "peso", "retro", "entradas de suelo"} <= dims
    assert all(x["regla"] for x in d["rule"])
    assert set(d["exclusions"]) >= {"retro", universe.SHADOW, "sin_peso", "no_vivo"}


def test_ninguna_cifra_de_resultado_incluye_retro() -> None:
    vivida, no_vivida = row(r=1.0, pnl_usdt=100.0), row(ledger_id="z", retro=True, r=-5.0,
                                                        pnl_usdt=-900.0)
    f = accounting.figures([vivida, no_vivida])
    assert f["n"] == 1
    assert f["pnl_usdt"] == 100.0 and f["total_r"] == 1.0 and f["win_rate"] == 1.0
    assert f["dd"]["usdt"] == 0.0            # la pérdida no vivida no hunde la curva
    # pero se puede consultar, con su etiqueta y el dinero que NO suma
    assert f["retro_excluded"]["n"] == 1 and f["retro_excluded"]["pnl_excluded"] == -900.0
    assert universe.retro_rows([vivida, no_vivida]) == [no_vivida]
