"""T100: curva par del Tesoro de EE. UU. El fixture son las tres primeras filas reales del CSV
de 2026 (descargado el 2026-11-26; reutilización declarada sin restricción, ◆ T88 §2.1)."""

from pathlib import Path

import pytest

from eim.data.providers.meta import US_TREASURY
from eim.data.providers.treasury import BASE, TENORS, TreasuryPar, parse_par_csv

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "treasury" / "par_curve_2026_sample.csv"


def test_parse_real_sample_oldest_first_with_14_tenors():
    curves = parse_par_csv(FIX.read_text(encoding="utf-8"))
    assert [c.date for c in curves] == ["2026-11-23", "2026-11-24", "2026-11-25"]
    last = curves[-1]
    assert len(last.tenors) == 14 == len(TENORS)
    assert last.get(10.0) == 4.85 and last.get(30.0) == 5.24 and last.get(1 / 12) == 4.27
    assert last.tenors == tuple(sorted(last.tenors)) and last.source == "us-treasury"


def test_blank_cells_and_unknown_columns_are_skipped():
    text = ('Date,"1 Mo","4 Mo","10 Yr","Extra"\n'
            '01/03/2019,2.40,,2.66,x\n'
            'no-es-fecha,1,1,1,1\n')
    (c,) = parse_par_csv(text)
    assert c.date == "2019-01-03" and c.tenors == (1 / 12, 10.0) and c.get(4 / 12) is None


def test_rejects_a_csv_without_the_expected_columns():
    with pytest.raises(ValueError):
        parse_par_csv("Fecha,uno\n1,2\n")
    with pytest.raises(ValueError):
        parse_par_csv("Date,uno\n01/01/2020,2\n")


class _Resp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class _Client:
    def __init__(self, text):
        self.text, self.calls = text, []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return _Resp(self.text)


def test_year_builds_the_official_url_without_a_key():
    cli = _Client(FIX.read_text(encoding="utf-8"))
    got = TreasuryPar(client=cli).year(2026)
    url, params = cli.calls[0]
    assert url == BASE.format(year=2026)
    assert params["type"] == "daily_treasury_yield_curve" and params["_format"] == "csv"
    assert "api_key" not in params and len(got) == 3
    assert TreasuryPar.meta is US_TREASURY and US_TREASURY.coverage == 2
