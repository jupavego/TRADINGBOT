"""T144 — Una sola función decide qué cuenta; esta prueba falla si alguien publica sin ella.

Dos guardias:

1. **De código:** quien publica una cifra de resultado importa `eim.paper.universe` (o la pieza que
   lo hace por él, `eim.paper.accounting`), y **nadie fuera de esas dos** lee la columna `retro`
   por su cuenta: excluir las no vividas «a mano» en cada sitio fue exactamente lo que produjo la
   doble contabilidad que T144 cierra.
2. **De comportamiento:** lo que sale publicado lleva la declaración del universo y su recuento
   (informe semanal en JSON y en Markdown, panel y escuadrón), así que una cifra sin universo no
   llega a la vista.
"""

from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path

from eim.operation import report, weekly
from eim.paper import accounting, universe

EIM = Path(universe.__file__).resolve().parents[1]
#: Los sitios que publican una cifra de resultado (la ficha: informe, panel, libro, escuadrón).
PUBLISHERS = ("operation/weekly.py", "paper/desk.py", "api/paper.py", "bots/scorecard.py")
#: Quien puede leer `retro` directamente: la regla, la pieza que la aplica y quien la escribe.
MAY_READ_RETRO = ("paper/universe.py", "paper/accounting.py", "paper/ledger.py")
MON_W45 = int(dt.datetime.fromisocalendar(2026, 45, 1).replace(tzinfo=dt.UTC).timestamp() * 1000)


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
    return out


def test_quien_publica_cifras_pasa_por_la_funcion_unica() -> None:
    for rel in PUBLISHERS:
        imports = _imports(EIM / rel)
        assert {"eim.paper.universe", "eim.paper.accounting",
                "eim.paper.universe.declaration", "eim.paper.accounting.figures"} & imports, (
            f"{rel} publica cifras de resultado pero no pasa por eim.paper.universe (T144)")


def _reads_retro(path: Path) -> list[int]:
    """Líneas donde el código lee la columna `retro` (subíndice o `.get`)."""
    hits: list[int] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant)
                and node.slice.value == "retro"):
            hits.append(node.lineno)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == "get" and node.args
              and isinstance(node.args[0], ast.Constant) and node.args[0].value == "retro"):
            hits.append(node.lineno)
    return hits


def test_nadie_mas_decide_por_su_cuenta_que_es_retro() -> None:
    for path in sorted(EIM.rglob("*.py")):
        rel = path.relative_to(EIM).as_posix()
        if rel in MAY_READ_RETRO:
            continue
        assert not _reads_retro(path), (
            f"{rel} lee la columna `retro` por su cuenta (líneas {_reads_retro(path)}): la regla "
            "vive en eim.paper.universe (T144)")


def test_la_regla_esta_en_un_solo_sitio() -> None:
    """`counts_as_result` es la única puerta: `accounting` y el resto la llaman, no la repiten."""
    src = (EIM / "paper" / "accounting.py").read_text(encoding="utf-8")
    assert "counts_as_result" in src and "result_rows" in src
    # ninguna pieza de publicación reimplementa el filtro con sus propias condiciones
    for rel in PUBLISHERS:
        text = (EIM / rel).read_text(encoding="utf-8")
        assert 'scope"] == "perfil"' not in text and "scope'] == 'perfil'" not in text, (
            f"{rel} filtra el alcance a mano en vez de preguntar al universo (T144)")


def _report(book: list[dict] | None) -> dict:
    return weekly.compose(t0=MON_W45, t1=MON_W45 + weekly.WEEK_MS, mode="SIMULADO",
                          symbols=("BTCUSDT",), trades=[], fee_rate=0.0004, equity=[], alerts=[],
                          active_alerts=[], decisions=[], edge=None,
                          calib={"BTCUSDT": weekly.calibration([], {}, 25)}, started_at=MON_W45,
                          book_rows=book)


def test_el_informe_semanal_declara_su_universo_y_su_recuento() -> None:
    row = {"ledger_id": "perfil|agresivo|BTCUSDT|i1", "scope": "perfil", "profile": "agresivo",
           "symbol": "BTCUSDT", "origin": "vivo", "weight": 1.0, "retro": False,
           "exit_t": MON_W45 + 1000, "r": 0.4, "pnl_usdt": 12.0, "reason": "SLD"}
    rep = _report([row, {**row, "ledger_id": "x", "retro": True, "r": -2.0, "pnl_usdt": -50.0}])
    assert rep["universe"] == universe.declaration()
    assert rep["official"]["tally"]["n_total"] == 2 and rep["official"]["n"] == 1
    assert rep["official"]["retro_excluded"]["n"] == 1
    assert rep["acceptance"]["universe"] == universe.OFFICIAL
    # el carril de operación queda declarado como vista, no como la cifra que decide
    assert rep["operation_view"]["universe"] == universe.OPERATION_VIEW
    assert "NO la cifra que decide" in rep["operation_view"]["label"]
    assert rep["all_trades"]["universe"] == universe.OPERATION_VIEW

    md = report.render_md(rep)
    assert "## Resultados (universo oficial)" in md
    assert "Quedan fuera 1 de 2" in md and "retro 1" in md
    assert "`retro` excluidas: 1" in md
    assert "## Vista: corrida de operación (NO es la cifra oficial)" in md
    assert universe.UNIVERSE_LABEL.split("(")[0].strip() in md


def test_sin_libro_el_informe_lo_dice_y_no_publica_cifra_oficial() -> None:
    rep = _report(None)
    assert rep["official"]["available"] is False and rep["official"]["n"] == 0
    md = report.render_md(rep)
    assert "sin cifra oficial" in md
    assert "no se sustituye por la del carril de operación" in md


def test_las_cifras_oficiales_solo_salen_de_lo_que_cuenta() -> None:
    """Cualquier figura de `accounting` se calcula sobre `result_rows`, nunca sobre el total."""
    rows = [{"ledger_id": str(i), "scope": "perfil", "profile": "moderado", "origin": "vivo",
             "weight": 1.0, "retro": i % 2 == 0, "exit_t": 1 + i, "r": 1.0, "pnl_usdt": 10.0}
            for i in range(10)]
    f = accounting.figures(rows)
    assert f["n"] == 5 and f["pnl_usdt"] == 50.0
    assert f["counted_digest"] == accounting.digest(universe.result_rows(rows))
