"""T169: la generación guarda vela a vela, se reanuda sin repetir y aguanta un corte a medias."""

from __future__ import annotations

import json
from pathlib import Path

from eim.nursery.exam import gen


class FakeGen:
    """Un contexto por `asof`; los múltiplos de 7 no tienen vela que los cierre."""

    def __init__(self) -> None:
        self.calls: list[int] = []

    def ctx_at(self, asof: int) -> dict | None:
        self.calls.append(asof)
        return None if asof % 7 == 0 else {"t": asof, "close": 1.0, "atr": 0.1, "nat": {}}


def test_run_resumes_and_only_computes_what_is_missing(tmp_path: Path) -> None:
    f = tmp_path / "ctx_1h.jsonl"
    g = FakeGen()
    assert gen.run(g, range(1, 11), f, limit=4) == 4
    assert g.calls == [1, 2, 3, 4]
    assert gen.run(g, range(1, 21), f) == 16              # solo lo que falta
    assert g.calls[4:] == list(range(5, 21))
    assert gen.run(g, range(1, 21), f) == 0               # nada que hacer
    rows = gen.load_ctxs(f)
    assert [r["t"] for r in rows] == [t for t in range(1, 21) if t % 7]   # sin los `skip`
    assert [r["t"] for r in gen.load_ctxs(f, start=5, end=10)] == [6, 8, 9, 10]


def test_a_half_written_last_line_is_dropped_and_recomputed(tmp_path: Path) -> None:
    f = tmp_path / "ctx_4h.jsonl"
    gen.run(FakeGen(), [1, 2, 3], f)
    with f.open("a", encoding="utf-8") as fh:
        fh.write('{"t": 4, "close": 1.0, "at')               # el proceso murió aquí
    assert [r["t"] for r in gen.load_ctxs(f)] == [1, 2, 3]   # la línea rota no se lee
    g = FakeGen()
    assert gen.run(g, [1, 2, 3, 4, 5], f) == 2 and g.calls == [4, 5]
    lines = f.read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["t"] for x in lines] == [1, 2, 3, 4, 5]


def test_repair_leaves_a_clean_file_alone(tmp_path: Path) -> None:
    f = tmp_path / "x.jsonl"
    assert gen.repair(f) == 0
    f.write_text('{"t": 1}\n', encoding="utf-8")
    assert gen.repair(f) == 0 and f.read_text(encoding="utf-8") == '{"t": 1}\n'
