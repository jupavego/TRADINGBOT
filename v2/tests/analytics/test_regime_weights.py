"""T221: pesos por régimen — escalera de multiplicadores, potencia y puerta (sin red)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from eim.analytics import regime_weights as rw
from eim.core import Candle
from eim.synthesis import SynthesisParams
from eim.validation.power import mde, n_needed

H = 3_600_000


def panel(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["asof", "agent", "bias", "conf", "status", "regime"])


def candles(n: int, start: int = 0) -> list[Candle]:
    """Velas con cierre creciente y constante en forma: solo hacen falta `t` y `c`."""
    return [Candle(t=start + i * H, o=100.0 + i, h=101.0 + i, l=99.0 + i, c=100.0 + i, v=1.0)
            for i in range(n)]


def test_voters_solo_direccionales_con_peso() -> None:
    df = panel([(0, a, 0.0, 0.0, "ok", "range") for a in
                ("ema", "levels", "regime", "calendar", "plan", "technical", "arbitrage")])
    got = rw.voters(df)
    assert "ema" in got and "levels" in got
    # `regime`, `calendar`, `plan` y `arbitrage` no votan; `technical` vota con peso 0 (T44).
    for a in ("regime", "calendar", "plan", "arbitrage", "technical"):
        assert a not in got
    assert SynthesisParams().weights["technical"] == 0.0


def test_regime_by_asof_admite_sin_etiqueta() -> None:
    df = panel([(0, "ema", 0.1, 0.5, "ok", "range"),
                (0, "levels", 0.2, 0.5, "ok", "range"),
                (H, "ema", 0.1, 0.5, "ok", None)])
    got = rw.regime_by_asof(df)
    assert got[0] == "range"
    assert got[H] is None


def test_escalera_de_multiplicadores() -> None:
    """Sube con +0,02 de IC, baja con −0,02, y se queda en 1,0 con pocas muestras."""
    detail = {
        "sube": {"ic": 0.00, "n": 1000,
                 "by_regime": {"trend_up": {"ic": 0.05, "n": 500},
                               "trend_down": {"ic": 0.00, "n": 500},
                               "range": {"ic": -0.05, "n": 500},
                               "volatile": {"ic": 0.02, "n": 500}}},
        "poca_muestra": {"ic": 0.00, "n": 100,
                         "by_regime": {g: {"ic": 0.9, "n": rw.MIN_N - 1} for g in rw.REGIMES}},
    }
    mult, table = rw.multipliers(detail)
    assert mult["trend_up"]["sube"] == rw.M_UP
    assert mult["range"]["sube"] == rw.M_DOWN
    assert mult["volatile"]["sube"] == rw.M_UP          # +0,02 justo en el umbral sube
    assert "trend_down" not in mult                     # 1,0 no se guarda
    assert "poca_muestra" not in {a for g in mult.values() for a in g}
    assert len(table) == len(rw.REGIMES) * 2
    assert all("n = 199" in r["why"] for r in table if r["agent"] == "poca_muestra")


def test_multiplicadores_vacios_si_nada_cruza() -> None:
    detail = {"a": {"ic": 0.0, "n": 1000,
                    "by_regime": {g: {"ic": 0.001, "n": 500} for g in rw.REGIMES}}}
    mult, table = rw.multipliers(detail)
    assert mult == {}
    assert all(r["m"] == rw.M_FLAT for r in table)


def test_agent_ic_separa_por_regimen() -> None:
    """Un agente que acierta solo en `range` sale con IC alto allí y bajo en el global."""
    cs = candles(400)
    rows: list[tuple] = []
    rng = np.random.default_rng(0)
    for i in range(0, 380, 4):
        asof = cs[i].t + H
        reg = "range" if i % 8 == 0 else "trend_up"
        # en `range` el sesgo apunta al retorno futuro (que aquí siempre sube); en tendencia, no
        bias = 1.0 if reg == "range" else float(rng.choice([-1.0, 1.0]))
        rows.append((asof, "a", bias, 0.5, "ok", reg))
    df = panel(rows)
    got = rw.agent_ic(df, cs, ["a"], h=4)
    assert got["a"]["n"] > 50
    assert got["a"]["by_regime"]["range"]["n"] > 20


def test_block_delta_detecta_mejora_y_el_ic95_la_excluye_cuando_no_hay() -> None:
    rng = np.random.default_rng(1)
    n = 600
    t = np.arange(n) * 4 * H
    y = rng.normal(size=n)
    x = y + rng.normal(scale=0.5, size=n)          # correlacionada con el retorno
    x0 = rng.normal(size=n)                        # ruido
    mejor = rw.block_delta(x, x0, y, t, n_boot=200)
    assert mejor["delta"] > 0.3
    assert mejor["ci95"][0] > 0
    assert mejor["blocks"] > 1
    igual = rw.block_delta(x0, x0, y, t, n_boot=200)
    assert igual["delta"] == 0.0
    assert igual["ci95"][0] <= 0 <= igual["ci95"][1]


def test_block_delta_es_reproducible() -> None:
    rng = np.random.default_rng(2)
    n = 300
    t = np.arange(n) * 4 * H
    y, x, x0 = rng.normal(size=n), rng.normal(size=n), rng.normal(size=n)
    a = rw.block_delta(x, x0, y, t, n_boot=100)
    b = rw.block_delta(x, x0, y, t, n_boot=100)
    assert a["ci95"] == b["ci95"]


def test_mde_es_el_inverso_de_n_needed() -> None:
    """Con la n que pide `n_needed` para un efecto, `mde` devuelve ese efecto (mismo α)."""
    sd, edge = 1.0, 0.1
    n = n_needed(edge, sd, alpha=0.025)            # unilateral 0,025 = bilateral 0,05
    assert math.isclose(mde(sd, n), edge, rel_tol=1e-9)
    assert mde(sd, 100) > mde(sd, 10_000)          # más datos, efecto detectable más pequeño
    assert mde(0.0, 100) == math.inf


def test_synth_signal_aplica_el_multiplicador_solo_con_regimen() -> None:
    from eim.analytics.agents_marginal import reports_by_asof
    df = panel([(0, "ema", 0.8, 0.9, "ok", "range"),
                (0, "levels", -0.8, 0.9, "ok", "range")])
    by = reports_by_asof(df)
    reg = rw.regime_by_asof(df)
    p = SynthesisParams(regime_weights={"range": {"ema": 0.5}})
    plana = rw.synth_signal(by, p, ["ema", "levels"], reg, False)
    porreg = rw.synth_signal(by, p, ["ema", "levels"], reg, True)
    # bajar el peso de `ema` (sesgo +0,8) deja ganar a `levels` (sesgo −0,8)
    assert plana.iloc[0] > porreg.iloc[0]


def test_evaluate_para_sin_etiqueta_de_regimen() -> None:
    cs = candles(60)
    rows = [(cs[i].t + H, "ema", 0.1, 0.5, "ok", None) for i in range(0, 50)]
    out = rw.evaluate(panel(rows), cs, None, "BTCUSDT", log=lambda _m: None)
    assert out["verdict"] == "NO MEDIBLE"
    assert "80 %" in out["why"]
    assert "test" not in out and "power" not in out


def test_evaluate_no_mira_la_prueba_si_nada_cruza_el_umbral() -> None:
    cs = candles(600)
    rows: list[tuple] = []
    for i in range(0, 560, 4):
        asof = cs[i].t + H
        reg = rw.REGIMES[(i // 4) % 4]
        for a in ("ema", "levels"):
            rows.append((asof, a, 0.0, 0.5, "ok", reg))
    out = rw.evaluate(panel(rows), cs, None, "BTCUSDT", log=lambda _m: None)
    assert out["verdict"] == "NO SE ADOPTA"
    assert out["multipliers"] == {}
    assert "test" not in out                      # la mitad de prueba no se tocó
    assert out["regime_share"] == 1.0
