"""T184: el vigía de calibración juzga con reglas fijas y mide en sombra sin tocar el pronóstico."""
from __future__ import annotations

import pytest

from eim.forecast.calib_watch import (
    ALERT,
    NO_VERDICT,
    OK,
    SUSTAINED,
    WATCH,
    WatchParams,
    assess,
    shadow,
    shadow_streak,
    to_obs,
)
from eim.forecast.calibration import Outcome
from eim.forecast.recal import MIN_FIT, Obs

P = WatchParams()


def rep(cov50=0.5, cov80=0.8, cov90=0.9, ece=0.02, skill=0.0, n=1000, h=25) -> dict:
    nom = {"50": cov50, "80": cov80, "90": cov90}
    return {"n_evaluated": n, "n_effective": round(n / h, 1), "ece": ece, "brier_skill": skill,
            "coverage": {k: {"nominal": int(k) / 100, "terminal": v, "pooled": v}
                         for k, v in nom.items()}}


def test_sin_muestra_no_hay_veredicto():
    assert assess(rep(n=50), P)["state"] == NO_VERDICT
    assert assess(rep(n=400), P)["state"] == NO_VERDICT     # efectiva 16 < 20


def test_dentro_de_lo_declarado_es_ok():
    a = assess(rep(), P)
    assert a["state"] == OK and a["level"] == 0 and "dentro" in a["reasons"][0]


@pytest.mark.parametrize("kw,state", [
    ({"cov80": 0.73}, WATCH), ({"cov80": 0.66}, ALERT), ({"ece": 0.07}, WATCH),
    ({"ece": 0.12}, ALERT), ({"skill": -0.08}, WATCH)])
def test_umbrales(kw, state):
    assert assess(rep(**kw), P)["state"] == state


def test_dos_alertas_seguidas_son_alerta_sostenida():
    assert assess(rep(cov90=0.7), P, prev=ALERT)["state"] == SUSTAINED
    assert assess(rep(cov90=0.7), P, prev=SUSTAINED)["state"] == SUSTAINED
    assert assess(rep(cov90=0.7), P, prev=OK)["state"] == ALERT
    assert assess(rep(), P, prev=SUSTAINED)["state"] == OK


def _out(t: int, probs: dict, realized: str) -> Outcome:
    return Outcome(made_at=t, realized=realized, ret=0.0, probs=probs, top="neutral", brier=0.0,
                   brier_rw=0.0, pinball=None, pinball_rw=None, dir_pred=0, dir_real=0)


def test_to_obs_no_deja_ver_un_horizonte_abierto():
    obs = to_obs([_out(2_000, {"bull": .3, "neutral": .4, "bear": .3}, "bull"),
                  _out(1_000, {"bull": .3, "neutral": .4, "bear": .3}, "bear")], 25, 10)
    assert [o.made_at for o in obs] == [1_000, 2_000] and obs[0].end_t == 1_000 + 26 * 10


def test_sombra_insuficiente_lo_dice():
    s = shadow([], 25, P)
    assert s["state"] == "insuficiente" and s["need"] == MIN_FIT + P.shadow_min_eval


def _obs(n: int, biased: bool) -> list[Obs]:
    """Pronóstico que sobrestima «bull» (20 pp) si `biased`; resultados en ciclo fijo."""
    seq = ["bear", "neutral", "bear", "bull", "neutral"]
    p = ({"bull": 0.45, "neutral": 0.30, "bear": 0.25} if biased else
         {"bull": 0.20, "neutral": 0.40, "bear": 0.40})
    return [Obs(made_at=i, end_t=i + 1, probs=p, realized=seq[i % 5]) for i in range(n)]


def test_sombra_detecta_una_mejora_clara_y_no_la_inventa():
    good = shadow(_obs(900, biased=True), 1, P)
    assert good["state"] == "mejora_en_sombra" and "pre-registro" in good["note"]
    assert good["methods"]["M1_priors"]["pasa_holm"] and good["methods"]["M1_priors"]["d_mean"] > 0
    fair = shadow(_obs(900, biased=False), 1, P)
    assert fair["state"] == "no_mejora" and not fair["better"]


def test_racha_en_sombra():
    hist = [{"shadow": {"state": "no_mejora"}}, {"shadow": {"state": "mejora_en_sombra"}}]
    assert shadow_streak(hist, {"state": "mejora_en_sombra"}) == 2
    assert shadow_streak(hist, {"state": "no_mejora"}) == 0
