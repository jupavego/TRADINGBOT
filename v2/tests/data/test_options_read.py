"""T214: lectura de la última toma de opciones para el snapshot (sin red)."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

from eim.data import options_read as orr
from tests.options.surface_helpers import T0, chain

H = 3_600_000


def _write(root: Path, taken: int, rows: list[dict], cur: str = "BTC") -> Path:
    d = datetime.fromtimestamp(taken / 1000, UTC)
    folder = root / "options" / cur / d.strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    data = folder / f"{d:%H}.jsonl.gz"
    text = "".join(json.dumps(r) + "\n" for r in rows)
    data.write_bytes(gzip.compress(text.encode("utf-8")))
    (folder / f"{d:%H}.quality.json").write_text(json.dumps({"taken_ms": taken}), "utf-8")
    return data


def test_latest_chain_known_at_asof(tmp_path):
    rows = chain()
    _write(tmp_path, T0 - 2 * H, rows[:10])
    _write(tmp_path, T0, rows)
    oc = orr.read_option_chain(tmp_path, "BTCUSDT", T0 + 5 * 60_000)
    assert oc is not None and oc.taken_ms == T0 and len(oc.rows) == len(rows)
    assert oc.currency == "BTC" and oc.source.startswith("deribit-options")
    earlier = orr.read_option_chain(tmp_path, "BTCUSDT", T0 - 1)       # nunca la posterior
    assert earlier is not None and earlier.taken_ms == T0 - 2 * H and len(earlier.rows) == 10


def test_crosses_midnight_but_not_the_age_limit(tmp_path):
    _write(tmp_path, T0, chain())                                       # 23:01 UTC
    assert orr.read_option_chain(tmp_path, "BTCUSDT", T0 + 3 * H) is not None    # día siguiente
    assert orr.read_option_chain(tmp_path, "BTCUSDT", T0 + 27 * H) is None


def test_no_chain_for_other_symbols_or_without_folder(tmp_path):
    assert orr.read_option_chain(tmp_path, "BTCUSDT", T0) is None
    _write(tmp_path, T0, chain())
    assert orr.read_option_chain(tmp_path, "SOLUSDT", T0 + H) is None
    assert orr.read_option_chain(tmp_path, "ETHUSDT", T0 + H) is None


def test_unreadable_snapshot_falls_back_to_the_previous_one(tmp_path):
    rows = chain()
    _write(tmp_path, T0 - H, rows)
    bad = _write(tmp_path, T0, rows)
    bad.write_bytes(b"no es gzip")
    oc = orr.read_option_chain(tmp_path, "BTCUSDT", T0 + 60_000)
    assert oc is not None and oc.taken_ms == T0 - H
