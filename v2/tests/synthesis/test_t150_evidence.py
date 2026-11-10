"""T150: un agente sin datos no vota, la correlación baja la confianza y se ven los votos
efectivos. Las pruebas de los entregables 1 y 3 fallan con la síntesis v1 (se comprueba abajo)."""
from __future__ import annotations

import random

import pytest

from eim.api.reports_db import ReportStore
from eim.core import AgentReport
from eim.synthesis import synthesize
from eim.synthesis.evidence import Evidence, coverage_of, effective_votes, mean_rho
from eim.synthesis.params import EvidenceParams

P = EvidenceParams()
T = 1_700_000_000_000
H = 3_600_000
FIVE = ("ema", "structure", "price_action", "levels", "elliott")


def rep(i: str, bias: float, conf: float = 0.6, status: str = "ok", asof: int = T) -> AgentReport:
    return AgentReport(agent_id=i, version="1", asof=asof, bias=bias, confidence=conf,
                       horizon_bars=10, status=status)


def _hist(series: dict[str, list[tuple[float, str]]]) -> list[tuple]:
    """Filas (asof, agente, sesgo, confianza, estado), con la última vela en `T`."""
    n = max(len(v) for v in series.values())
    return [(T - (n - 1 - k) * H, a, b, 0.0 if st == "no_data" else 0.5, st)
            for a, v in series.items() for k, (b, st) in enumerate(v)]


def _noise(seed: int, n: int) -> list[float]:
    r = random.Random(seed)
    return [max(-1.0, min(1.0, r.gauss(0, 0.4))) for _ in range(n)]


def _correlated(n: int = 200, mix: float = 0.85) -> dict[str, list[tuple[float, str]]]:
    common = _noise(1, n)
    return {a: [(mix * c + (1 - mix) * e, "ok")
                for c, e in zip(common, _noise(10 + i, n), strict=True)]
            for i, a in enumerate(FIVE)}


def _independent(n: int = 200) -> dict[str, list[tuple[float, str]]]:
    return {a: [(x, "ok") for x in _noise(100 + i, n)] for i, a in enumerate(FIVE)}


# --- Entregable 1: sin datos no vota -----------------------------------------------------------

def _no_data_case(vwap_bias: float):
    hist = {a: [(0.3, "ok")] * 48 for a in ("ema", "structure")}
    hist["vwap"] = [(0.0, "no_data")] * 40 + [(0.5, "ok")] * 8      # 83 % sin datos
    ev = coverage_of(_hist(hist), ["ema", "structure", "vwap"], P)
    reps = [rep("ema", 0.6), rep("structure", 0.4), rep("vwap", vwap_bias, 0.9)]
    return reps, ev


@pytest.mark.parametrize("vwap_bias", [-0.9, 0.0, 0.9])
def test_agente_sin_datos_en_la_ventana_no_influye_en_el_sesgo(vwap_bias):
    reps, ev = _no_data_case(vwap_bias)
    s = synthesize(reps, evidence=ev)
    alone = synthesize(reps[:2], evidence=ev)
    assert s.bias == pytest.approx(alone.bias) and s.confidence == pytest.approx(alone.confidence)
    assert "vwap" not in s.contributions and s.blocked == ["vwap"]
    assert s.weights["vwap"] == 0                     # la interfaz no lo pinta como votante
    assert s.coverage["vwap"]["state"] == "no_data" and not s.coverage["vwap"]["votes"]
    assert "Sin voto por falta de datos en las últimas 48 velas: vwap" in s.thesis


def test_la_sintesis_v1_si_dejaba_votar_al_agente_sin_datos():
    """La prueba de arriba falla con v1: el mismo agente mueve el sesgo."""
    lo = synthesize(_no_data_case(-0.9)[0])
    hi = synthesize(_no_data_case(0.9)[0])
    assert hi.bias - lo.bias > 0.3


def test_degradado_por_encima_del_umbral_tampoco_vota():
    hist = {"ema": [(0.3, "ok")] * 48,
            "tech": [(0.1, "degraded")] * 30 + [(0.1, "ok")] * 18}      # 62 % degradado
    ev = coverage_of(_hist(hist), list(hist), P)
    assert ev.coverage["tech"].state == "degraded" and not ev.coverage["tech"].votes
    hist["tech"] = [(0.1, "degraded")] * 20 + [(0.1, "ok")] * 28       # 42 % ≤ 50 %
    assert coverage_of(_hist(hist), list(hist), P).coverage["tech"].votes


def test_ausente_cuenta_como_sin_datos_y_ventana_corta_decide_la_vela():
    ev = coverage_of(_hist({"ema": [(0.3, "ok")] * 48, "vwap": [(0.3, "ok")] * 10}),
                     ["ema", "vwap", "nuevo"], P)
    assert ev.coverage["vwap"].ok == 10 and not ev.coverage["vwap"].votes
    assert ev.coverage["nuevo"].no_data == 48
    short = coverage_of(_hist({"ema": [(0.3, "ok")] * 5}), ["ema", "vwap"], P)
    assert short.coverage["vwap"].votes and short.coverage["vwap"].short
    assert "ventana corta" in short.coverage["vwap"].reason(P)


# --- Entregables 3 y 4: correlación y votos efectivos -------------------------------------------

def test_votos_efectivos_con_rho_igual():
    for rho, want in ((0.6, 25 / 17), (0.44, 5 / (1 + 4 * 0.44)), (0.0, 5.0), (1.0, 1.0)):
        assert effective_votes(dict.fromkeys(FIVE, 1.0), Evidence({}, {}), rho) == \
            pytest.approx(want)
    assert 5 / (1 + 4 * 0.44) == pytest.approx(1.81, abs=0.01)


def test_cinco_correlacionados_no_dan_la_confianza_de_cinco_independientes():
    reps = [rep(a, 0.5, 0.6) for a in FIVE]
    ev_c = coverage_of(_hist(_correlated()), FIVE, P)
    ev_i = coverage_of(_hist(_independent()), FIVE, P)
    assert mean_rho(FIVE, ev_c, P.rho_prior) > 0.6
    assert mean_rho(FIVE, ev_i, P.rho_prior) < 0.2
    corr, ind = synthesize(reps, evidence=ev_c), synthesize(reps, evidence=ev_i)
    assert corr.effective_votes < 2.0 and ind.effective_votes > 4.0
    assert corr.confidence < 0.75 * ind.confidence
    assert corr.factors["correlacion"] == pytest.approx((corr.effective_votes / 5) ** 0.5,
                                                        abs=1e-3)
    assert corr.bias == pytest.approx(ind.bias)          # cambia lo que sabe, no adónde apunta
    assert "5 votantes ≈ 1." in corr.thesis and corr.voters == 5


def test_la_sintesis_v1_daba_la_misma_confianza_correlacionados_o_no():
    """La prueba de arriba falla con v1: no mira la correlación entre los cinco."""
    s = synthesize([rep(a, 0.5, 0.6) for a in FIVE])
    assert s.confidence == pytest.approx(0.6)
    assert s.effective_votes is None and s.method == "v1"


def test_sin_solape_suficiente_se_usa_el_rho_previo_no_la_independencia():
    ev = coverage_of(_hist({"ema": [(0.3, "ok")] * 20, "structure": [(0.1, "ok")] * 20}),
                     ["ema", "structure"], P)
    assert ev.rho_of("ema", "structure", P.rho_prior) == P.rho_prior and not ev.measured


def test_informativos_del_rombo_no_votan_aunque_tengan_datos():
    """◆ de T150: estacionalidad, liquidaciones y smart money se muestran, nunca votan (v2)."""
    hist = {a: [(0.3, "ok")] * 48 for a in ("ema", "seasonality", "liquidations")}
    ev = coverage_of(_hist(hist), list(hist), P)
    reps = [rep("ema", 0.5), rep("seasonality", -0.9, 0.9), rep("liquidations", -0.9, 0.9)]
    s = synthesize(reps, evidence=ev)
    assert set(s.contributions) == {"ema"} and s.bias == pytest.approx(0.5)
    assert s.informative == ["liquidations", "seasonality"] and s.weights["seasonality"] == 0
    assert "Informativos, no votan" in s.thesis
    assert set(synthesize(reps).contributions) == {"ema", "seasonality", "liquidations"}  # v1


def test_solo_se_correlaciona_a_quien_puede_votar():
    hist = {"ema": [(0.3, "ok")] * 48, "calendar": [(0.0, "ok")] * 48,
            "vwap": [(0.0, "no_data")] * 48}
    ev = coverage_of(_hist(hist), list(hist), P, corr_agents=["ema", "vwap"])
    assert ev.rho == {} and set(ev.coverage) == set(hist)


def test_rho_negativa_se_recorta_a_cero():
    xs = _noise(3, 100)
    ev = coverage_of(_hist({"ema": [(x, "ok") for x in xs],
                            "structure": [(-x, "ok") for x in xs]}), ["ema", "structure"], P)
    assert ev.rho_of("ema", "structure", P.rho_prior) == 0.0


# --- v1 intacta y almacén ------------------------------------------------------------------------

def test_sin_evidencia_el_resultado_es_v1():
    reps = [rep("ema", 0.6), rep("structure", -0.2, 0.3), rep("vwap", 0.1, 0.0, "no_data")]
    s = synthesize(reps)
    assert s.method == "v1" and s.coverage == {} and "correlacion" not in s.factors
    assert "votos efectivos" not in s.thesis


def test_history_devuelve_los_ultimos_instantes_y_la_version_mas_nueva():
    st = ReportStore(":memory:")
    for k in range(5):
        st.save("BTCUSDT", "1h", [rep("ema", 0.1 * k, asof=T + k * H)])
    st.save("BTCUSDT", "1h", [AgentReport(agent_id="ema", version="2", asof=T + 4 * H,
                                          bias=-0.9, confidence=0.5, horizon_bars=1)])
    rows = st.history("BTCUSDT", "1h", 3)
    assert sorted(r[0] for r in rows) == [T + 2 * H, T + 3 * H, T + 4 * H]
    assert next(r for r in rows if r[0] == T + 4 * H)[2] == -0.9
    assert {r[0] for r in st.history("BTCUSDT", "1h", 2, end=T + 2 * H)} == {T + H, T + 2 * H}
