"""T213 — las tomas de las cadenas de opciones entran en la copia diaria y vuelven al restaurar
(no se pueden volver a descargar: Deribit no publica la cadena pasada)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("duckdb")

from eim.data import backup as B  # noqa: E402
from eim.data.options_chain import snapshot_paths, take_snapshot  # noqa: E402
from tests.data.options_helpers import T0, provider_for, raw_chain  # noqa: E402

CLOCK = 1_795_800_000.0


def test_backup_and_restore_keep_the_option_snapshots(tmp_path):
    d = tmp_path / "data"
    take_snapshot(d, "BTC", provider_for(raw_chain()), clock=lambda: T0)
    out = B.create(d, tmp_path / "bk", clock=lambda: CLOCK)
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert "options/BTC/2026-11-27/14.jsonl.gz" in m["files"]
    assert "options/BTC/2026-11-27/14.quality.json" in m["files"]
    assert B.verify(out) == []
    d2 = tmp_path / "otra"
    d2.mkdir()
    assert "options/" in B.restore(out, d2)
    data, quality = snapshot_paths(d2, "BTC", T0)
    assert data.exists() and quality.exists()
