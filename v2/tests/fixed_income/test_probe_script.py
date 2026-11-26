"""T100: la sonda `scripts/fixed_income_probe.py` sin red (cliente falso con el fixture real
del Tesoro y un CSV del BCE construido con parámetros conocidos)."""

import importlib.util
from pathlib import Path

import httpx
import pytest

from eim.fixed_income.curve import svensson

V2 = Path(__file__).resolve().parents[2]
FIX = V2 / "tests" / "fixtures" / "treasury" / "par_curve_2026_sample.csv"
PARAMS = {"BETA0": 2.9, "BETA1": -0.8, "BETA2": -1.4, "BETA3": 3.1, "TAU1": 1.7, "TAU2": 11.0}


def _load():
    spec = importlib.util.spec_from_file_location("fi_probe", V2 / "scripts" /
                                                  "fixed_income_probe.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ecb_csv(shift_pb: float = 0.0) -> str:
    rows = ["KEY,FREQ,TIME_PERIOD,OBS_VALUE"]
    base = "YC.B.U2.EUR.4F.G_N_A.SV_C_YM."
    rows += [f"{base}{k},B,2026-11-25,{v}" for k, v in PARAMS.items()]
    for name, m in {"SR_1Y": 1, "SR_10Y": 10, "SR_30Y": 30}.items():
        rows.append(f"{base}{name},B,2026-11-25,{svensson(m, *PARAMS.values()) + shift_pb / 100}")
    return "\n".join(rows) + "\n"


class _Resp:
    def __init__(self, text, ok=True):
        self.text, self.ok = text, ok

    def raise_for_status(self):
        if not self.ok:
            raise httpx.HTTPError("caída")


class _Client:
    def __init__(self, ecb_text=None, treasury_ok=True):
        self.ecb_text, self.treasury_ok = ecb_text, treasury_ok

    def get(self, url, params=None):
        if "treasury" in url:
            return _Resp(FIX.read_text(encoding="utf-8"), self.treasury_ok)
        return _Resp(self.ecb_text or "", self.ecb_text is not None)


def test_run_with_real_treasury_sample_and_matching_ecb():
    mod = _load()
    res = mod.run(_Client(_ecb_csv()), 2026)
    assert res["n_days"] == 3 and res["curve"]["as_of"] == "2026-11-25"
    assert res["carry"]["10a"]["status"] == "no_data"          # 3 días no bastan para la vol.
    assert res["ecb"]["status"] == "coincide" and res["ecb"]["max_dif_pb"] < 1e-6
    md = mod.render(res)
    assert "Curva del 2026-11-25" in md and "coincide" in md and "no disponible" in md
    assert mod.summary(res).startswith("sonda T100: curva del 2026-11-25: 10a 4.85 %")


def test_ecb_mismatch_is_reported_not_hidden():
    res = _load().ecb_check(_load().parse_ecb(_ecb_csv(shift_pb=3.0)))
    assert res["status"] == "NO coincide" and res["max_dif_pb"] == pytest.approx(3.0, abs=1e-6)


def test_without_network_everything_is_marked_unavailable():
    mod = _load()
    res = mod.run(_Client(None, treasury_ok=False), 2026)
    assert "curve" not in res and res["ecb"]["status"] == "no disponible"
    assert "no disponible" in mod.render(res) and "no disponible" in mod.summary(res)
