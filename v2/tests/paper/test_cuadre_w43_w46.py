"""T144 — Prueba de cuadre con los datos REALES de W43–W46: el informe y el libro cuentan lo mismo.

`tests/fixtures/paper/ledger_w43_w46.csv` son las 421 filas de alcance `perfil` del libro fijo de
`juanpablo-cpu` que cerraron entre el lunes de la W43 y el lunes de la W47 de 2026, leídas de
`GET /v2/paper/ledger.csv` el 2026-11-09 (sin la columna `payload`). Son los mismos datos con los
que `PLAN/notas/diagnostico_rentabilidad_2026-11-09.md` §6 encontró la doble contabilidad.

La prueba falla si el total que publica el informe semanal y el del libro no coinciden bajo el
mismo universo, y la diferencia se explica operación a operación (`accounting.cuadre`).
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import pytest

from eim.operation import weekly
from eim.paper import accounting, universe

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "paper" / "ledger_w43_w46.csv"
#: Lo medido en el libro real, semana a semana: (filas en el tramo, cuántas cuentan, `retro`).
REAL = {"2026-W43": (161, 43, 118), "2026-W44": (87, 30, 57),
        "2026-W45": (140, 118, 22), "2026-W46": (33, 33, 0)}


def monday(year: int, week: int) -> int:
    return int(dt.datetime.fromisocalendar(year, week, 1).replace(tzinfo=dt.UTC).timestamp()
               * 1000)


@pytest.fixture(scope="module")
def book() -> list[dict]:
    with FIXTURE.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def compose(book: list[dict], t0: int) -> dict:
    """El informe semanal tal como lo compone el servicio, con el libro entero como entrada."""
    return weekly.compose(t0=t0, t1=t0 + weekly.WEEK_MS, mode="SIMULADO", symbols=("BTCUSDT",),
                          trades=[], fee_rate=0.0004, equity=[], alerts=[], active_alerts=[],
                          decisions=[], edge=None,
                          calib={"BTCUSDT": weekly.calibration([], {}, 25)}, started_at=t0,
                          book_rows=book)


def test_el_libro_real_trae_las_421_filas_de_w43_a_w46(book: list[dict]) -> None:
    assert len(book) == 421
    assert {r["scope"] for r in book} == {"perfil"}
    assert sum(universe.is_retro(r) for r in book) == 197
    assert len(universe.result_rows(book)) == 224


@pytest.mark.parametrize("week", sorted(REAL))
def test_el_informe_cuadra_con_el_libro_operacion_a_operacion(book: list[dict], week: str) -> None:
    t0 = monday(2026, int(week.split("W")[1]))
    off = compose(book, t0)["official"]
    # el libro leído por fuera del informe, con la misma regla
    mine = accounting.window(book, t0, t0 + weekly.WEEK_MS)
    c = accounting.cuadre(universe.result_rows(mine), mine)
    assert c["match"], (f"{week}: el informe y el libro no cuentan lo mismo · "
                        f"faltan {c['missing']} · sobran {c['extra']} · difieren {c['differ']}")
    n_total, n_counted, n_retro = REAL[week]
    assert off["tally"]["n_total"] == n_total
    assert off["n"] == n_counted == c["n_libro"]
    assert off["retro_excluded"]["n"] == n_retro
    assert off["counted_digest"] == accounting.digest(universe.result_rows(mine))
    assert off["pnl_usdt"] == pytest.approx(c["pnl_libro"])


def test_la_diferencia_se_explica_operacion_a_operacion(book: list[dict]) -> None:
    """Si alguien publica una cifra con una operación de menos, el cuadre dice CUÁL."""
    t0 = monday(2026, 45)
    mine = accounting.window(book, t0, t0 + weekly.WEEK_MS)
    kept = universe.result_rows(mine)
    c = accounting.cuadre(kept[1:], mine)      # al informe le falta la primera
    assert not c["match"] and len(c["missing"]) == 1
    (m,) = c["missing"]
    assert m["ledger_id"] == kept[0]["ledger_id"] and m["profile"] == kept[0]["profile"]
    assert m["reason"] and m["pnl_usdt"] == pytest.approx(float(kept[0]["pnl_usdt"]))
    # y al revés: una que el libro no tiene aparece como sobrante, no se pierde en el agregado
    inventada = {**kept[0], "ledger_id": "perfil|agresivo|BTCUSDT|inventada"}
    assert accounting.cuadre([*kept, inventada], mine)["extra"][0]["ledger_id"] == (
        "perfil|agresivo|BTCUSDT|inventada")


def test_las_retro_no_mueven_ninguna_cifra_de_w43(book: list[dict]) -> None:
    """W43 es el caso extremo: 118 de 161 son `retro`. Excluirlas cambia el veredicto."""
    t0 = monday(2026, 43)
    rows = accounting.window(book, t0, t0 + weekly.WEEK_MS)
    off = accounting.figures(rows)
    assert off["n"] == 43 and off["retro_excluded"]["n"] == 118
    # la cifra oficial NO es la de contarlas todas: por eso había dos contabilidades
    todas = [dict(r, retro="False") for r in rows]
    assert accounting.figures(todas)["n"] == 161
    assert off["pnl_usdt"] != pytest.approx(accounting.figures(todas)["pnl_usdt"])
    assert off["pnl_usdt"] == pytest.approx(
        sum(float(r["pnl_usdt"]) for r in rows if not universe.is_retro(r)))
