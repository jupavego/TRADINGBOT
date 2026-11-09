"""T144 — La reexpresión añade la lectura corregida y NO borra lo publicado.

Entregable 5: W43–W46 se vuelven a expresar con el universo oficial, diciendo que la lectura
anterior contaba otra cosa. Lo que ya estaba publicado se conserva íntegro, y volver a correrlo
reemplaza solo el bloque nuevo (si lo reescribiera todo, el historial dejaría de ser auditable).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from eim.operation import restate

FIXTURE = (Path(__file__).resolve().parents[1] / "fixtures" / "paper" / "ledger_w43_w46.csv")
ORIGINAL = """# Informe de operación — 2026-W43

## Resultados

| Símbolo | Operaciones | Con resultado |
|---|---|---|
| BTCUSDT | 4 | 1 |

## Incidentes

ninguna.
"""


def rows() -> list[dict]:
    with FIXTURE.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_las_semanas_se_reexpresan_sin_perder_lo_publicado(tmp_path: Path) -> None:
    md = tmp_path / "semana_2026-W43.md"
    md.write_text(ORIGINAL, encoding="utf-8")
    (out,) = restate.restate(rows(), tmp_path, ["2026-W43"])
    assert out["existed"] and out["n_total"] == 161 and out["n_counted"] == 43
    assert out["retro_excluded"] == 118
    text = md.read_text(encoding="utf-8")
    # lo publicado sigue ahí, palabra por palabra
    assert ORIGINAL.strip() in text
    # y debajo está la lectura corregida, diciendo que la anterior contaba otra cosa
    assert "La lectura de arriba contaba otra cosa" in text
    assert "## Reexpresión con el universo oficial (T144)" in text
    assert "**TOTAL (universo oficial)** | 161 | **43**" in text
    assert "retro 118" in text
    j = json.loads((tmp_path / "semana_2026-W43_t144.json").read_text(encoding="utf-8"))
    assert j["week"] == "2026-W43" and j["n"] == 43 and j["counted_digest"] == out["digest"]


def test_repetirlo_reemplaza_solo_el_bloque(tmp_path: Path) -> None:
    md = tmp_path / "semana_2026-W43.md"
    md.write_text(ORIGINAL, encoding="utf-8")
    restate.restate(rows(), tmp_path, ["2026-W43"])
    once = md.read_text(encoding="utf-8")
    restate.restate(rows(), tmp_path, ["2026-W43"])
    assert md.read_text(encoding="utf-8") == once
    assert once.count(restate.BEGIN) == 1 and once.count("## Resultados") == 1


def test_una_semana_sin_informe_se_publica_aparte(tmp_path: Path) -> None:
    (out,) = restate.restate(rows(), tmp_path, ["2026-W46"])
    assert not out["existed"] and out["n_counted"] == 33 and out["retro_excluded"] == 0
    apart = tmp_path / "semana_2026-W46_t144.md"
    assert apart.exists() and not (tmp_path / "semana_2026-W46.md").exists()
    text = apart.read_text(encoding="utf-8")
    assert "no tiene informe semanal publicado" in text and "**parcial**" in text


def test_la_ventana_de_cada_semana_es_la_suya(tmp_path: Path) -> None:
    got = {r["week"]: (r["n_total"], r["n_counted"]) for r in
           restate.restate(rows(), tmp_path, ["2026-W43", "2026-W44", "2026-W45", "2026-W46"],
                           write=False)}
    assert got == {"2026-W43": (161, 43), "2026-W44": (87, 30), "2026-W45": (140, 118),
                   "2026-W46": (33, 33)}
    t0, t1 = restate.week_bounds("2026-W45")
    assert t1 - t0 == 7 * 86_400_000
